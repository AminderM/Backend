from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from models import User, UserCreate, UserLogin, UserRole, RegistrationStatus
from auth import get_current_user, hash_password, verify_password, create_access_token, get_workspaces_for_user
from database import db
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, EmailStr
from typing import Optional
import secrets
import hashlib
import os
import httpx
import json
import jwt as pyjwt
from jwt.algorithms import RSAAlgorithm
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from email_service import send_otp_email

router = APIRouter(prefix="/auth", tags=["Authentication"])

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
APPLE_CLIENT_ID = os.environ.get("APPLE_CLIENT_ID")
_apple_jwks_cache: Optional[dict] = None


# ---------------------------------------------------------------------------
# Request body models
# ---------------------------------------------------------------------------

class GoogleAuthRequest(BaseModel):
    id_token: str


class AppleAuthRequest(BaseModel):
    id_token: str
    full_name: Optional[str] = None


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp_code: str


class SendOTPRequest(BaseModel):
    email: EmailStr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_login_response(user: User) -> dict:
    workspaces = get_workspaces_for_user(user)
    return {
        "access_token": create_access_token(data={"sub": user.id, "role": user.role}),
        "token_type": "bearer",
        "user": user.dict(),
        "registration_status": user.registration_status,
        "allowed_workspaces": workspaces,
    }


async def _get_apple_jwks(force_refresh: bool = False) -> dict:
    global _apple_jwks_cache
    if _apple_jwks_cache is None or force_refresh:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://appleid.apple.com/auth/keys", timeout=10)
            resp.raise_for_status()
            _apple_jwks_cache = resp.json()
    return _apple_jwks_cache


def _generate_otp() -> tuple[str, str]:
    """Return (raw_otp, hashed_otp)."""
    raw = f"{secrets.randbelow(1_000_000):06d}"
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=dict)
async def register_user(user_data: UserCreate, background_tasks: BackgroundTasks):
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Generate OTP
    raw_otp, hashed_otp = _generate_otp()

    # Hash password
    hashed_password = hash_password(user_data.password)

    # Build user document
    user_dict = user_data.dict()
    user_dict.pop("password")
    user_dict["password_hash"] = hashed_password
    user_dict["auth_provider"] = "email"
    user_dict["email_verified"] = False
    user_dict["otp_code"] = hashed_otp
    user_dict["otp_expires_at"] = datetime.now(timezone.utc) + timedelta(minutes=10)
    user_dict["otp_attempts"] = 0
    user_obj = User(**user_dict)

    await db.users.insert_one(user_obj.dict())

    await send_otp_email(background_tasks, user_data.email, user_data.full_name, raw_otp)

    return {
        "message": "Registration successful! Check your email for a 6-digit verification code.",
        "user_id": user_obj.id,
        "status": "otp_sent",
    }


@router.post("/signup", response_model=dict)
async def signup_user(user_data: UserCreate, background_tasks: BackgroundTasks):
    """Alias for /register — used by the website frontend"""
    return await register_user(user_data, background_tasks)


@router.post("/login", response_model=dict)
async def login_user(login_data: UserLogin):
    user = await db.users.find_one({"email": login_data.email})
    # Guard: Google/Apple users have no password_hash
    if not user or not user.get("password_hash") or not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.get("email_verified"):
        raise HTTPException(status_code=403, detail="Please verify your email before logging in.")

    user_obj = User(**user)
    return _build_login_response(user_obj)


@router.get("/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/workspaces", response_model=dict)
async def get_user_workspaces_endpoint(current_user: User = Depends(get_current_user)):
    """
    Get list of workspaces the current user has access to.
    Frontend should call this on login to filter sidebar/menu items.
    """
    workspaces = get_workspaces_for_user(current_user)

    workspace_details = {
        "dashboard": {"name": "Dashboard", "icon": "home", "path": "/dashboard"},
        "dispatch": {"name": "Dispatch Operations", "icon": "truck", "path": "/dispatch"},
        "sales": {"name": "Sales / CRM", "icon": "dollar-sign", "path": "/sales"},
        "accounting": {"name": "Accounting", "icon": "calculator", "path": "/accounting"},
        "hr": {"name": "HR & Users", "icon": "users", "path": "/hr"},
        "fleet": {"name": "Fleet Management", "icon": "truck", "path": "/fleet"},
        "reports": {"name": "Reports & Analytics", "icon": "bar-chart", "path": "/reports"},
        "settings": {"name": "Settings", "icon": "settings", "path": "/settings"},
        "driver_app": {"name": "Driver App", "icon": "smartphone", "path": "/driver"},
        "rate_cards": {"name": "Rate Cards", "icon": "tag", "path": "/rate-cards"},
    }

    return {
        "allowed_workspaces": workspaces,
        "workspace_details": {ws: workspace_details.get(ws, {}) for ws in workspaces},
        "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
    }


# ---------------------------------------------------------------------------
# Email OTP endpoints
# ---------------------------------------------------------------------------

@router.post("/verify-otp", response_model=dict)
async def verify_otp(data: OTPVerifyRequest):
    """Verify the 6-digit OTP and return a JWT on success."""
    user = await db.users.find_one({"email": data.email})
    if not user:
        raise HTTPException(status_code=404, detail="No account found for this email.")

    if user.get("email_verified"):
        raise HTTPException(status_code=400, detail="Email already verified. Please log in.")

    if not user.get("otp_code"):
        raise HTTPException(status_code=400, detail="No OTP requested. Use /auth/send-otp to get a code.")

    if user.get("otp_expires_at") and user["otp_expires_at"] < datetime.now(timezone.utc):
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"otp_code": None, "otp_expires_at": None, "otp_attempts": 0}},
        )
        raise HTTPException(status_code=400, detail="OTP expired. Request a new code via /auth/send-otp.")

    attempts = user.get("otp_attempts", 0)
    if attempts >= 3:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Request a new OTP via /auth/send-otp.")

    submitted_hash = hashlib.sha256(data.otp_code.encode()).hexdigest()
    if submitted_hash != user["otp_code"]:
        new_attempts = attempts + 1
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"otp_attempts": new_attempts}})
        remaining = 3 - new_attempts
        raise HTTPException(status_code=400, detail=f"Incorrect code. {remaining} attempt(s) remaining.")

    # Success — verify user
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "email_verified": True,
                "registration_status": RegistrationStatus.VERIFIED,
                "otp_code": None,
                "otp_expires_at": None,
                "otp_attempts": 0,
            }
        },
    )

    updated = await db.users.find_one({"_id": user["_id"]})
    user_obj = User(**updated)
    return _build_login_response(user_obj)


@router.post("/send-otp", response_model=dict)
async def send_otp(data: SendOTPRequest, background_tasks: BackgroundTasks):
    """Resend a fresh OTP to an unverified email address."""
    user = await db.users.find_one({"email": data.email})
    if not user:
        raise HTTPException(status_code=404, detail="No account found for this email.")

    if user.get("email_verified"):
        raise HTTPException(status_code=400, detail="Email already verified. Please log in.")

    raw_otp, hashed_otp = _generate_otp()
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "otp_code": hashed_otp,
                "otp_expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
                "otp_attempts": 0,
            }
        },
    )

    await send_otp_email(background_tasks, data.email, user.get("full_name", ""), raw_otp)

    return {"message": "Verification code sent to your email.", "status": "otp_sent"}


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------

@router.post("/google", response_model=dict)
async def google_login(data: GoogleAuthRequest):
    """Verify a Google ID token and return a Fleet Marketplace JWT."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google authentication is not configured.")

    try:
        idinfo = google_id_token.verify_oauth2_token(
            data.id_token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {exc}")

    google_sub = idinfo["sub"]
    email = idinfo.get("email", "")
    full_name = idinfo.get("name", email.split("@")[0])

    # Look up by google_id first, then by email (user may have registered with email before)
    user = await db.users.find_one({"google_id": google_sub})
    if not user and email:
        user = await db.users.find_one({"email": email})

    if user:
        # Link google_id if this is the first Google login for an existing email account
        if not user.get("google_id"):
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"google_id": google_sub, "auth_provider": "google"}},
            )
            user["google_id"] = google_sub
            user["auth_provider"] = "google"
        user_obj = User(**user)
    else:
        # Create new account
        new_user = User(
            email=email,
            full_name=full_name,
            password_hash=None,
            auth_provider="google",
            google_id=google_sub,
            email_verified=True,
            registration_status=RegistrationStatus.VERIFIED,
            role=UserRole.VIEWER,
        )
        await db.users.insert_one(new_user.dict())
        user_obj = new_user

    return _build_login_response(user_obj)


# ---------------------------------------------------------------------------
# Apple Sign-In
# ---------------------------------------------------------------------------

@router.post("/apple", response_model=dict)
async def apple_login(data: AppleAuthRequest):
    """Verify an Apple ID token and return a Fleet Marketplace JWT."""
    if not APPLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Apple authentication is not configured.")

    # Decode header to get key ID
    try:
        header = pyjwt.get_unverified_header(data.id_token)
    except pyjwt.exceptions.DecodeError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Apple token: {exc}")

    kid = header.get("kid")

    async def _find_key(jwks: dict) -> Optional[dict]:
        return next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

    try:
        jwks = await _get_apple_jwks()
        matching_key = await _find_key(jwks)
        if not matching_key:
            # Key may have rotated — refresh cache and retry once
            jwks = await _get_apple_jwks(force_refresh=True)
            matching_key = await _find_key(jwks)
        if not matching_key:
            raise HTTPException(status_code=401, detail="Apple public key not found.")

        public_key = RSAAlgorithm.from_jwk(json.dumps(matching_key))
        payload = pyjwt.decode(
            data.id_token,
            public_key,
            algorithms=["RS256"],
            audience=APPLE_CLIENT_ID,
            issuer="https://appleid.apple.com",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Could not reach Apple auth servers: {exc}")
    except pyjwt.exceptions.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Apple token: {exc}")

    apple_sub = payload["sub"]
    email = payload.get("email")
    full_name = data.full_name or (email.split("@")[0] if email else "Apple User")

    # Look up by apple_id first, then by email
    user = await db.users.find_one({"apple_id": apple_sub})
    if not user and email:
        user = await db.users.find_one({"email": email})

    if user:
        if not user.get("apple_id"):
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"apple_id": apple_sub, "auth_provider": "apple"}},
            )
            user["apple_id"] = apple_sub
            user["auth_provider"] = "apple"
        user_obj = User(**user)
    else:
        if not email:
            raise HTTPException(
                status_code=400,
                detail="Apple did not provide an email address. Please start a fresh Apple sign-in session.",
            )
        new_user = User(
            email=email,
            full_name=full_name,
            password_hash=None,
            auth_provider="apple",
            apple_id=apple_sub,
            email_verified=True,
            registration_status=RegistrationStatus.VERIFIED,
            role=UserRole.VIEWER,
        )
        await db.users.insert_one(new_user.dict())
        user_obj = new_user

    return _build_login_response(user_obj)