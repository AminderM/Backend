from fastapi import APIRouter, HTTPException, Depends
from models import *
from auth import get_current_user, hash_password
from database import db
from typing import List

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/users/company", response_model=List[User])
async def get_company_users(current_user: User = Depends(get_current_user)):
    # Get company
    company = await db.companies.find_one({"owner_id": current_user.id})
    if not company:
        raise HTTPException(status_code=404, detail="No company found")
    
    # Get all users for this company (users who registered with this company)
    users = await db.users.find({"company_id": company["id"]}).to_list(length=None)
    return [User(**user) for user in users]

@router.post("/users", response_model=dict)
async def create_user(user_data: UserCreate, current_user: User = Depends(get_current_user)):
    # Only fleet owners can create users
    if current_user.role != UserRole.FLEET_OWNER:
        raise HTTPException(status_code=403, detail="Only company admins can create users")
    
    # Check if email already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Get company
    company = await db.companies.find_one({"owner_id": current_user.id})
    if not company:
        raise HTTPException(status_code=404, detail="No company found")
    
    # Create user account
    hashed_password = hash_password(user_data.password)
    
    user_dict = user_data.dict()
    user_dict.pop("password")
    user_dict["password_hash"] = hashed_password
    user_dict["company_id"] = company["id"]
    user_dict["email_verified"] = True  # Auto-verify company-created users
    user_dict["registration_status"] = RegistrationStatus.VERIFIED
    user_obj = User(**user_dict)
    
    await db.users.insert_one(user_obj.dict())
    
    return {"message": "User created successfully", "user_id": user_obj.id}

@router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: User = Depends(get_current_user)):
    # Only fleet owners can delete users
    if current_user.role != UserRole.FLEET_OWNER:
        raise HTTPException(status_code=403, detail="Only company admins can delete users")
    
    # Cannot delete yourself
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "User deleted successfully"}

# Equipment Routes
