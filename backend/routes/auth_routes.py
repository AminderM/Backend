from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from models import User, UserCreate, UserLogin, UserRole, RegistrationStatus
from auth import get_current_user, hash_password, verify_password, create_access_token
from database import db
from datetime import datetime, timezone, timedelta
import secrets
import hashlib
import os
from email_service import send_verification_email

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=dict)
async def register_user(user_data: UserCreate, background_tasks: BackgroundTasks):
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Generate email verification token
    token = secrets.token_urlsafe(32)
    hashed_token = hashlib.sha256(token.encode()).hexdigest()
    
    # Hash password
    hashed_password = hash_password(user_data.password)
    
    # Create user
    user_dict = user_data.dict()
    user_dict.pop("password")
    user_dict["password_hash"] = hashed_password
    user_dict["verification_token"] = hashed_token
    user_dict["token_expires_at"] = datetime.now(timezone.utc) + timedelta(hours=24)
    user_dict["email_verified"] = False
    user_obj = User(**user_dict)
    
    # Insert user
    await db.users.insert_one(user_obj.dict())
    
    # Send verification email
    app_url = os.environ.get('APP_URL', 'http://localhost:3000')
    verification_url = f"{app_url}/verify-email/{token}"
    await send_verification_email(
        background_tasks,
        user_data.email,
        user_data.full_name,
        verification_url
    )
    
    return {
        "message": "User registered successfully! Please check your email to verify your account.", 
        "user_id": user_obj.id, 
        "status": "email_verification_sent"
    }

@router.post("/login", response_model=dict)
async def login_user(login_data: UserLogin):
    # Find user
    user = await db.users.find_one({"email": login_data.email})
    if not user or not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Create access token with user ID (not email)
    access_token = create_access_token(data={"sub": user["id"], "role": user["role"]})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": User(**user).dict(),
        "registration_status": user["registration_status"]
    }

@router.get("/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user
