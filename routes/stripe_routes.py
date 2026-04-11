from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from auth import require_web_user, get_current_user
from database import db
from datetime import datetime, timezone
import stripe
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe", tags=["Stripe"])

# ---------------------------------------------------------------------------
# Config — loaded from environment
# ---------------------------------------------------------------------------

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://integratedtech.ca")

PRICE_IDS = {
    "pro": {
        "monthly": os.environ.get("STRIPE_PRO_MONTHLY_PRICE_ID", ""),
        "annual":  os.environ.get("STRIPE_PRO_ANNUAL_PRICE_ID", ""),
    },
    "enterprise": {
        "monthly": os.environ.get("STRIPE_ENTERPRISE_MONTHLY_PRICE_ID", ""),
        "annual":  os.environ.get("STRIPE_ENTERPRISE_ANNUAL_PRICE_ID", ""),
    },
}

# Map Stripe price IDs back to plan info for webhook processing
def _price_to_plan(price_id: str) -> dict:
    for tier, cycles in PRICE_IDS.items():
        for cycle, pid in cycles.items():
            if pid and pid == price_id:
                return {"tier": tier, "billing_cycle": cycle}
    return {"tier": "free", "billing_cycle": None}


# ---------------------------------------------------------------------------
# GET /api/user/subscription  (also lives in user_profile_routes — this is
# the canonical Stripe-aware version that replaces it)
# ---------------------------------------------------------------------------

# NOTE: This endpoint is intentionally NOT here — it's already in
# user_profile_routes.py and reads from the user document directly.
# The webhook keeps the user document in sync, so no duplication needed.


# ---------------------------------------------------------------------------
# POST /api/stripe/create-checkout-session
# ---------------------------------------------------------------------------

@router.post("/create-checkout-session")
async def create_checkout_session(request: Request, current_user=Depends(require_web_user)):
    """
    Create a Stripe Checkout session for a website user.
    Body: { "plan": "pro" | "enterprise", "billing_cycle": "monthly" | "annual" }
    Returns: { "url": "https://checkout.stripe.com/..." }
    """
    body = await request.json()
    plan = body.get("plan", "pro")
    billing_cycle = body.get("billing_cycle", "monthly")

    price_id = PRICE_IDS.get(plan, {}).get(billing_cycle)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Invalid plan '{plan}' or billing_cycle '{billing_cycle}'")

    user_id = str(current_user.id)
    email = current_user.email

    # Get or create Stripe customer
    stripe_customer_id = getattr(current_user, "stripe_customer_id", None)
    if not stripe_customer_id:
        customer = stripe.Customer.create(
            email=email,
            metadata={"user_id": user_id, "portal": "website"},
        )
        stripe_customer_id = customer.id
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"stripe_customer_id": stripe_customer_id}},
        )

    try:
        session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{FRONTEND_URL}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/pricing",
            metadata={"user_id": user_id},
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe checkout session error for user {user_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")

    return {"url": session.url}


# ---------------------------------------------------------------------------
# POST /api/stripe/portal
# ---------------------------------------------------------------------------

@router.post("/portal")
async def billing_portal(current_user=Depends(require_web_user)):
    """
    Create a Stripe Customer Portal session so the user can manage their subscription.
    Returns: { "url": "https://billing.stripe.com/..." }
    """
    stripe_customer_id = getattr(current_user, "stripe_customer_id", None)
    if not stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No active subscription found. Please subscribe first.",
        )

    try:
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=f"{FRONTEND_URL}/account/subscription",
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe portal error for user {current_user.id}: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")

    return {"url": session.url}


# ---------------------------------------------------------------------------
# POST /api/stripe/webhook
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events. Stripe signature is verified before processing.
    No auth dependency — Stripe calls this directly.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except stripe.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    logger.info(f"Stripe webhook received: {event_type}")

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(event["data"]["object"])

    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        await _handle_subscription_updated(event["data"]["object"])

    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(event["data"]["object"])

    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(event["data"]["object"])

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Webhook event handlers
# ---------------------------------------------------------------------------

async def _get_user_by_stripe_customer(stripe_customer_id: str):
    """Look up user in MongoDB by stripe_customer_id."""
    return await db.users.find_one({"stripe_customer_id": stripe_customer_id})


async def _handle_checkout_completed(session):
    """Upgrade user tier after successful checkout."""
    stripe_customer_id = getattr(session, "customer", None)
    subscription_id = getattr(session, "subscription", None)

    logger.info(f"Checkout completed: customer={stripe_customer_id} subscription={subscription_id}")
    if not stripe_customer_id or not subscription_id:
        logger.warning("Missing customer or subscription ID in checkout event")
        return

    # Retrieve the subscription to get the price ID
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
    except stripe.StripeError as e:
        logger.error(f"Could not retrieve subscription {subscription_id}: {e}")
        return

    price_id = subscription.items.data[0].price.id
    plan_info = _price_to_plan(price_id)
    renewal_date = datetime.fromtimestamp(
        subscription.current_period_end, tz=timezone.utc
    ).isoformat()

    user = await _get_user_by_stripe_customer(stripe_customer_id)
    logger.info(f"User lookup by stripe_customer_id={stripe_customer_id}: {'found' if user else 'not found'}")
    if not user:
        # Try fallback via session metadata
        metadata = getattr(session, "metadata", None) or {}
        user_id = metadata.get("user_id") if hasattr(metadata, "get") else getattr(metadata, "user_id", None)
        logger.info(f"Fallback lookup by user_id={user_id}")
        if user_id:
            user = await db.users.find_one({"id": user_id})

    if not user:
        logger.warning(f"No user found for stripe_customer_id={stripe_customer_id}")
        return

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "stripe_subscription_id": subscription_id,
            "tier": plan_info["tier"],
            "billing_cycle": plan_info["billing_cycle"],
            "renewal_date": renewal_date,
        }},
    )
    logger.info(f"User {user.get('email')} upgraded to {plan_info['tier']} ({plan_info['billing_cycle']})")


async def _handle_subscription_updated(subscription):
    """Sync tier when plan changes (e.g. upgrade, downgrade, renewal)."""
    stripe_customer_id = getattr(subscription, "customer", None)
    price_id = subscription.items.data[0].price.id
    plan_info = _price_to_plan(price_id)
    renewal_date = datetime.fromtimestamp(
        subscription.current_period_end, tz=timezone.utc
    ).isoformat()

    user = await _get_user_by_stripe_customer(stripe_customer_id)
    if not user:
        return

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "stripe_subscription_id": subscription.id,
            "tier": plan_info["tier"],
            "billing_cycle": plan_info["billing_cycle"],
            "renewal_date": renewal_date,
        }},
    )
    logger.info(f"User {user.get('email')} subscription updated to {plan_info['tier']}")


async def _handle_subscription_deleted(subscription):
    """Downgrade user to free when subscription is cancelled."""
    stripe_customer_id = getattr(subscription, "customer", None)
    user = await _get_user_by_stripe_customer(stripe_customer_id)
    if not user:
        return

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "stripe_subscription_id": None,
            "tier": "free",
            "billing_cycle": None,
            "renewal_date": None,
        }},
    )
    logger.info(f"User {user.get('email')} downgraded to free (subscription cancelled)")


async def _handle_payment_failed(invoice):
    """Log payment failures — optionally notify user."""
    stripe_customer_id = getattr(invoice, "customer", None)
    user = await _get_user_by_stripe_customer(stripe_customer_id)
    if user:
        invoice_id = getattr(invoice, "id", None)
        logger.warning(f"Payment failed for user {user.get('email')} — invoice {invoice_id}")