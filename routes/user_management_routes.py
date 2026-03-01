from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from models import User, UserRole
from auth import get_current_user, require_platform_admin, hash_password
from database import db
from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr
import uuid

router = APIRouter()

class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str
    phone: str
    role: str  # company_admin, dispatcher, driver
    company_id: str  # Which company/tenant this user belongs to
    password: str
    assigned_products: Optional[List[str]] = []  # List of product IDs

class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    assigned_products: Optional[List[str]] = None

@router.get("/users/company/{company_id}")
async def get_company_users(
    company_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get all users for a specific company"""
    require_platform_admin(current_user)
    
    users = await db.users.find(
        {"company_id": company_id},
        {"_id": 0, "password_hash": 0}
    ).to_list(length=1000)
    
    return users

@router.post("/users")
async def create_user(
    user_data: UserCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a new user and assign to a company"""
    require_platform_admin(current_user)
    
    # Check if email already exists
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Verify company exists
    company = await db.companies.find_one({"id": user_data.company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Validate role
    valid_roles = ["company_admin", "dispatcher", "driver"]
    if user_data.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")
    
    # Create user
    new_user = {
        "id": str(uuid.uuid4()),
        "email": user_data.email,
        "full_name": user_data.full_name,
        "phone": user_data.phone,
        "role": user_data.role,
        "company_id": user_data.company_id,
        "password_hash": hash_password(user_data.password),
        "assigned_products": user_data.assigned_products or [],
        "is_active": True,
        "registration_status": "verified",
        "email_verified": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.id,
        "fleet_owner_id": None,
        "verification_token": None,
        "token_expires_at": None
    }
    
    await db.users.insert_one(new_user)
    
    # Update company's seat usage
    await db.companies.update_one(
        {"id": user_data.company_id},
        {"$inc": {"total_seats_used": 1}}
    )
    
    # Remove password_hash from response
    new_user.pop("password_hash")
    
    return {
        "message": "User created successfully",
        "user": new_user
    }

@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    user_data: UserUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update user details"""
    require_platform_admin(current_user)
    
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Build update dict
    updates = {}
    if user_data.full_name is not None:
        updates["full_name"] = user_data.full_name
    if user_data.phone is not None:
        updates["phone"] = user_data.phone
    if user_data.role is not None:
        valid_roles = ["company_admin", "dispatcher", "driver"]
        if user_data.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")
        updates["role"] = user_data.role
    if user_data.is_active is not None:
        updates["is_active"] = user_data.is_active
    if user_data.assigned_products is not None:
        updates["assigned_products"] = user_data.assigned_products
    
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = current_user.id
    
    await db.users.update_one(
        {"id": user_id},
        {"$set": updates}
    )
    
    updated_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    
    return {
        "message": "User updated successfully",
        "user": updated_user
    }

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a user"""
    require_platform_admin(current_user)
    
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    company_id = user.get("company_id")
    
    # Delete user
    result = await db.users.delete_one({"id": user_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update company's seat usage
    if company_id:
        await db.companies.update_one(
            {"id": company_id},
            {"$inc": {"total_seats_used": -1}}
        )
    
    return {"message": "User deleted successfully"}

@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    new_password: str,
    current_user: User = Depends(get_current_user)
):
    """Reset a user's password"""
    require_platform_admin(current_user)
    
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update password
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password_hash": hash_password(new_password),
            "password_reset_at": datetime.now(timezone.utc).isoformat(),
            "password_reset_by": current_user.id
        }}
    )
    
    return {"message": "Password reset successfully"}

@router.get("/users/stats/company/{company_id}")
async def get_company_user_stats(
    company_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get user statistics for a company"""
    require_platform_admin(current_user)
    
    users = await db.users.find({"company_id": company_id}).to_list(length=1000)
    
    stats = {
        "total_users": len(users),
        "active_users": len([u for u in users if u.get("is_active", True)]),
        "by_role": {
            "company_admin": len([u for u in users if u.get("role") == "company_admin"]),
            "dispatcher": len([u for u in users if u.get("role") == "dispatcher"]),
            "driver": len([u for u in users if u.get("role") == "driver"])
        }
    }
    
    return stats
