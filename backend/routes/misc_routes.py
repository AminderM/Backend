from fastapi import APIRouter, HTTPException
from models import User, UserRole, RegistrationStatus
from auth import hash_password
from database import db
from datetime import datetime, timezone
import hashlib

router = APIRouter(tags=["Miscellaneous"])

@router.get("/verify-email/{token}")
async def verify_email(token: str):
    # Hash the provided token
    hashed_token = hashlib.sha256(token.encode()).hexdigest()
    
    # Find user with matching token
    user = await db.users.find_one({
        "verification_token": hashed_token,
        "email_verified": False,
        "token_expires_at": {"$gt": datetime.now(timezone.utc)}
    })
    
    if not user:
        raise HTTPException(
            status_code=400, 
            detail="Invalid or expired verification token"
        )
    
    # Update user as verified
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "email_verified": True,
                "verified_at": datetime.now(timezone.utc)
            },
            "$unset": {"verification_token": "", "token_expires_at": ""}
        }
    )
    
    return {"message": "Email verified successfully! You can now complete your company registration."}

@router.post("/admin/seed-platform-admin")
async def seed_platform_admin(email: str = "aminderpro@gmail.com", password: str = "Admin@123!"):
    existing = await db.users.find_one({"email": email})
    if existing:
        # ensure platform admin role and update password
        hashed_password = hash_password(password)
        await db.users.update_one({"email": email}, {"$set": {"role": UserRole.PLATFORM_ADMIN, "email_verified": True, "password_hash": hashed_password}})
        return {"status": "updated", "email": email}
    hashed_password = hash_password(password)
    user = User(
        email=email,
        full_name="Platform Admin",
        phone="0000000000",
        role=UserRole.PLATFORM_ADMIN,
        email_verified=True,
        registration_status=RegistrationStatus.VERIFIED,
    ).dict()
    user["password_hash"] = hashed_password
    await db.users.insert_one(user)
    return {"status": "created", "email": email}

@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}
