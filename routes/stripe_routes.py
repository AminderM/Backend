import os
import stripe
import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from auth import require_web_user
from database import db
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe", tags=["Stripe"])

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://integratedtech.ca")

PRICE_IDS = {
    "pro": {
        "monthly": os.environ.get("STRIPE_PRO_MONTHLY_PRICE_ID"),
        "annual": os.environ.get("STRIPE_PRO_ANNUAL_PRICE_ID"),
    },
    "enterprise": {
        "monthly": os.environ.get("STRIPE_ENTERPRISE_MONTHLY_PRICE_ID"),
        "annual": os.environ.get("STRIPE_ENTERPRISE_ANNUAL_PRICE_ID"),
    },
}


class CheckoutRequest(BaseModel):
    plan: str           # "pro" or "enterprise"
    billing_cycle: str  # "monthly" or "annual"


# ---------------------------------------------------------------------------
# POST /api/stripe/create-checkout-session
# ---------------------------------------------------------------------------

@router.post("/create-checkout-session")
async def create_checkout_session(body: CheckoutRequest, current_user=Depends(require_web_user)):
    plan = body.plan.lower()
    billing_cycle = body.billing_cycle.lower()

    price_id = PRICE_IDS.get(plan, {}).get(billing_cycle)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Invalid plan '{plan}' or billing cycle '{billing_cycle}'")

    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    # Get or create Stripe customer
    user_doc = await db.users.find_one({"id": current_user.id})
    stripe_customer_id = user_doc.get("stripe_customer_id") if user_doc else None

    if not stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            name=current_user.full_name,
            metadata={"user_id": current_user.id},
        )
        stripe_customer_id = customer.id
        await db.users.update_one(
            {"id": current_user.id},
            {"$set": {"stripe_customer_id": stripe_customer_id}}
        )

    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{FRONTEND_URL}/checkout-success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{FRONTEND_URL}/pricing",
        metadata={"user_id": current_user.id, "plan": plan, "billing_cycle": billing_cycle},
    )

    return {"url": session.url}


# ---------------------------------------------------------------------------
# POST /api/stripe/portal
# ---------------------------------------------------------------------------

@router.post("/portal")
async def customer_portal(current_user=Depends(require_web_user)):
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    user_doc = await db.users.find_one({"id": current_user.id})
    stripe_customer_id = user_doc.get("stripe_customer_id") if user_doc else None

    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found. Please subscribe first.")

    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=f"{FRONTEND_URL}/account",
    )

    return {"url": session.url}


# ---------------------------------------------------------------------------
# POST /api/stripe/webhook
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data)

    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data)

    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data)

    elif event_type in ("invoice.payment_succeeded", "invoice.payment_failed"):
        await _handle_invoice_event(event_type, data)

    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Webhook handlers
# ---------------------------------------------------------------------------

async def _handle_checkout_completed(session: dict):
    user_id = session.get("metadata", {}).get("user_id")
    plan = session.get("metadata", {}).get("plan")
    billing_cycle = session.get("metadata", {}).get("billing_cycle")
    stripe_customer_id = session.get("customer")
    subscription_id = session.get("subscription")

    if not user_id:
        logger.warning("checkout.session.completed missing user_id in metadata")
        return

    now = datetime.now(timezone.utc)

    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": subscription_id,
            "subscription_plan": plan,
            "subscription_status": "active",
            "billing_cycle": billing_cycle,
            "subscription_started_at": now,
        }}
    )
    logger.info(f"Subscription activated for user {user_id}: {plan} {billing_cycle}")


async def _handle_subscription_updated(subscription: dict):
    stripe_customer_id = subscription.get("customer")
    status = subscription.get("status")

    user_doc = await db.users.find_one({"stripe_customer_id": stripe_customer_id})
    if not user_doc:
        return

    await db.users.update_one(
        {"stripe_customer_id": stripe_customer_id},
        {"$set": {"subscription_status": status}}
    )
    logger.info(f"Subscription updated for customer {stripe_customer_id}: status={status}")


async def _handle_subscription_deleted(subscription: dict):
    stripe_customer_id = subscription.get("customer")

    await db.users.update_one(
        {"stripe_customer_id": stripe_customer_id},
        {"$set": {
            "subscription_status": "cancelled",
            "subscription_plan": None,
            "stripe_subscription_id": None,
        }}
    )
    logger.info(f"Subscription cancelled for customer {stripe_customer_id}")


async def _handle_invoice_event(event_type: str, invoice: dict):
    stripe_customer_id = invoice.get("customer")
    status = "active" if event_type == "invoice.payment_succeeded" else "past_due"

    await db.users.update_one(
        {"stripe_customer_id": stripe_customer_id},
        {"$set": {"subscription_status": status}}
    )
    logger.info(f"Invoice event {event_type} for customer {stripe_customer_id}: status={status}")
