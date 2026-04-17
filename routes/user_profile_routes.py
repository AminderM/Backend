from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from auth import verify_password, hash_password, require_web_user
from database import db
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["User Profile"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    mc_number: Optional[str] = None
    dot_number: Optional[str] = None


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str


# ---------------------------------------------------------------------------
# GET /api/user/profile
# ---------------------------------------------------------------------------

@router.get("/profile")
async def get_profile(current_user=Depends(require_web_user)):
    """Return the authenticated user's profile."""
    return {
        "full_name": getattr(current_user, "full_name", None),
        "name": getattr(current_user, "full_name", None),
        "phone": getattr(current_user, "phone", None),
        "email": current_user.email,
        "auth_provider": getattr(current_user, "auth_provider", "email"),
        "company": getattr(current_user, "company", None),
        "address": getattr(current_user, "address", None),
        "city": getattr(current_user, "city", None),
        "state": getattr(current_user, "state", None),
        "zip": getattr(current_user, "zip", None),
        "mc_number": getattr(current_user, "mc_number", None),
        "dot_number": getattr(current_user, "dot_number", None),
        "created_at": (
            current_user.created_at.isoformat()
            if isinstance(getattr(current_user, "created_at", None), datetime)
            else getattr(current_user, "created_at", None)
        ),
    }


# ---------------------------------------------------------------------------
# PUT /api/user/profile
# ---------------------------------------------------------------------------

@router.put("/profile")
async def update_profile(body: ProfileUpdate, current_user=Depends(require_web_user)):
    """Update full_name and/or phone for the authenticated user."""
    updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}

    for field in ["full_name", "phone", "company", "address", "city", "state", "zip", "mc_number", "dot_number"]:
        val = getattr(body, field, None)
        if val is not None:
            updates[field] = val

    result = await db.users.update_one(
        {"id": str(current_user.id)},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "Profile updated successfully"}


# ---------------------------------------------------------------------------
# GET /api/user/subscription
# ---------------------------------------------------------------------------

@router.get("/subscription")
async def get_subscription(current_user=Depends(require_web_user)):
    """Return the subscription details for the authenticated user's company."""
    tenant_id = getattr(current_user, "tenant_id", None)

    if not tenant_id:
        return {"plan": None, "billing_cycle": None, "renewal_date": None, "status": "none"}

    company = await db.companies.find_one({"id": tenant_id})
    if not company:
        return {"plan": None, "billing_cycle": None, "renewal_date": None, "status": "none"}

    # Check multi-product subscriptions list first, fall back to top-level fields
    subscriptions: list = company.get("subscriptions", [])
    active_sub = next((s for s in subscriptions if s.get("status") == "active"), None)

    if active_sub:
        return {
            "plan": active_sub.get("plan"),
            "billing_cycle": active_sub.get("billing_cycle"),
            "renewal_date": active_sub.get("renewal_date") or active_sub.get("current_period_end"),
            "status": active_sub.get("status"),
        }

    # Fall back to top-level company subscription fields
    return {
        "plan": company.get("plan"),
        "billing_cycle": company.get("billing_cycle"),
        "renewal_date": company.get("renewal_date"),
        "status": company.get("subscription_status", "none"),
    }


# ---------------------------------------------------------------------------
# PUT /api/user/password
# ---------------------------------------------------------------------------

@router.put("/password")
async def update_password(body: PasswordUpdate, current_user=Depends(require_web_user)):
    """Change password. Returns 400 if current password is wrong."""
    # OAuth users don't have a password
    if getattr(current_user, "auth_provider", "email") != "email":
        return JSONResponse(
            status_code=400,
            content={"error": "Password cannot be changed for Google/Apple accounts"},
        )

    stored_hash = getattr(current_user, "password_hash", None)
    if not stored_hash:
        return JSONResponse(status_code=400, content={"error": "No password set on this account"})

    if not verify_password(body.current_password, stored_hash):
        return JSONResponse(status_code=400, content={"error": "Current password is incorrect"})

    if len(body.new_password) < 8:
        return JSONResponse(status_code=400, content={"error": "New password must be at least 8 characters"})

    new_hash = hash_password(body.new_password)
    await db.users.update_one(
        {"id": str(current_user.id)},
        {"$set": {"password_hash": new_hash, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )

    return {"message": "Password updated successfully"}


# ---------------------------------------------------------------------------
# DELETE /api/user/account
# ---------------------------------------------------------------------------

@router.delete("/account")
async def delete_account(current_user=Depends(require_web_user)):
    """Permanently delete the authenticated user and all their associated data."""
    user_id = str(current_user.id)

    # Delete user's data across collections
    await db.users.delete_one({"id": user_id})
    await db.history.delete_many({"user_id": user_id})
    await db.invoices.delete_many({"created_by": user_id})

    logger.info(f"Account deleted: {current_user.email} (id={user_id})")

    return {"message": "Account deleted successfully"}