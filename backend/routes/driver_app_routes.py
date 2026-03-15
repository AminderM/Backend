from fastapi import APIRouter, HTTPException, Depends
from models import *
from auth import get_current_user, hash_password
from database import db
from datetime import datetime, timezone
from typing import List, Optional
import uuid

router = APIRouter(prefix="/driver", tags=["Driver App"])

@router.post("/login")
async def driver_login(credentials: UserLogin):
    """Driver login endpoint for mobile app"""
    from auth import verify_password, create_access_token
    
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_password(credentials.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if user.get("role") not in [UserRole.DRIVER, UserRole.FLEET_OWNER]:
        raise HTTPException(status_code=403, detail="Access denied. Driver or Fleet Owner role required.")
    
    access_token = create_access_token(data={"sub": user["id"]})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "phone": user.get("phone", ""),
            "fleet_owner_id": user.get("fleet_owner_id")
        }
    }

@router.post("/signup")
async def driver_signup(driver_data: DriverCreate):
    """Allow owner-operators to create their own driver account"""
    
    existing_user = await db.users.find_one({"email": driver_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = hash_password(driver_data.password)
    
    driver_dict = driver_data.dict()
    driver_dict.pop("password")
    driver_dict["password_hash"] = hashed_password
    driver_dict["role"] = UserRole.DRIVER
    driver_dict["fleet_owner_id"] = None
    driver_dict["registration_status"] = RegistrationStatus.PENDING
    driver_dict["id"] = str(uuid.uuid4())
    driver_dict["created_at"] = datetime.now(timezone.utc)
    driver_dict["is_active"] = True
    driver_dict["email_verified"] = False
    
    await db.users.insert_one(driver_dict)
    
    return {
        "message": "Driver account created successfully. Awaiting verification.",
        "driver_id": driver_dict["id"]
    }

@router.get("/profile")
async def get_driver_profile(current_user: User = Depends(get_current_user)):
    """Get driver profile information"""
    if current_user.role not in [UserRole.DRIVER, UserRole.FLEET_OWNER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    user_data = await db.users.find_one({"id": current_user.id}, {"_id": 0})
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    company_info = None
    if user_data.get("fleet_owner_id"):
        owner = await db.users.find_one({"id": user_data["fleet_owner_id"]}, {"_id": 0})
        if owner:
            company = await db.companies.find_one({"owner_id": user_data["fleet_owner_id"]}, {"_id": 0})
            if company:
                company_info = {
                    "id": company["id"],
                    "name": company["name"],
                    "phone": company.get("phone_number"),
                    "email": company.get("company_email")
                }
    
    return {
        "id": user_data["id"],
        "email": user_data["email"],
        "full_name": user_data["full_name"],
        "phone": user_data.get("phone", ""),
        "role": user_data["role"],
        "registration_status": user_data.get("registration_status", "pending"),
        "company": company_info
    }

@router.get("/loads")
async def get_assigned_loads(current_user: User = Depends(get_current_user)):
    """Get loads/orders assigned to the driver"""
    if current_user.role not in [UserRole.DRIVER, UserRole.FLEET_OWNER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    loads = await db.bookings.find(
        {"driver_id": current_user.id, "status": {"$nin": ["paid", "cancelled"]}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return loads

@router.get("/loads/{load_id}")
async def get_load_details(load_id: str, current_user: User = Depends(get_current_user)):
    """Get detailed information about a specific load"""
    if current_user.role not in [UserRole.DRIVER, UserRole.FLEET_OWNER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    load = await db.bookings.find_one(
        {"id": load_id, "driver_id": current_user.id},
        {"_id": 0}
    )
    
    if not load:
        raise HTTPException(status_code=404, detail="Load not found or not assigned to you")
    
    return load

@router.post("/loads/{load_id}/accept")
async def accept_load(load_id: str, current_user: User = Depends(get_current_user)):
    """Driver accepts/confirms the load assignment"""
    if current_user.role not in [UserRole.DRIVER, UserRole.FLEET_OWNER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id})
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    result = await db.bookings.update_one(
        {"id": load_id},
        {"$set": {"status": "planned"}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to accept load")
    
    return {"message": "Load accepted successfully", "status": "planned"}

@router.put("/loads/{load_id}/status")
async def update_load_status(
    load_id: str,
    status_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update the status of a load in real-time"""
    if current_user.role not in [UserRole.DRIVER, UserRole.FLEET_OWNER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    new_status = status_data.get("status")
    valid_statuses = [
        "planned",
        "in_transit_pickup",
        "at_pickup",
        "in_transit_delivery",
        "at_delivery",
        "delivered"
    ]
    
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
    
    load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id})
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    update_data = {"status": new_status}
    
    if new_status == "at_pickup":
        update_data["pickup_time_actual"] = datetime.now(timezone.utc)
    elif new_status == "delivered":
        update_data["delivery_time_actual"] = datetime.now(timezone.utc)
    
    result = await db.bookings.update_one(
        {"id": load_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update load status")
    
    updated_load = await db.bookings.find_one({"id": load_id}, {"_id": 0})
    
    return {
        "message": "Load status updated successfully",
        "load": updated_load
    }

@router.post("/loads/{load_id}/location")
async def update_driver_location(
    load_id: str,
    location_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update driver's current location for real-time tracking"""
    if current_user.role not in [UserRole.DRIVER, UserRole.FLEET_OWNER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id})
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    location_update = {
        "load_id": load_id,
        "driver_id": current_user.id,
        "latitude": location_data.get("latitude"),
        "longitude": location_data.get("longitude"),
        "timestamp": datetime.now(timezone.utc),
        "speed": location_data.get("speed"),
        "heading": location_data.get("heading")
    }
    
    await db.driver_locations.insert_one(location_update)
    
    return {"message": "Location updated successfully"}

@router.get("/loads/{load_id}/route")
async def get_load_route(load_id: str, current_user: User = Depends(get_current_user)):
    """Get the route information for navigation"""
    if current_user.role not in [UserRole.DRIVER, UserRole.FLEET_OWNER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id}, {"_id": 0})
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    route_info = {
        "load_id": load_id,
        "order_number": load.get("order_number"),
        "origin": {
            "address": load.get("pickup_location"),
            "city": load.get("pickup_city"),
            "state": load.get("pickup_state"),
            "country": load.get("pickup_country", "USA")
        },
        "destination": {
            "address": load.get("delivery_location"),
            "city": load.get("delivery_city"),
            "state": load.get("delivery_state"),
            "country": load.get("delivery_country", "USA")
        },
        "stops": [],
        "pickup_time": load.get("pickup_time_planned"),
        "delivery_time": load.get("delivery_time_planned")
    }
    
    return route_info
