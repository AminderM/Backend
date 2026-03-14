from fastapi import APIRouter, HTTPException, Depends
from models import *
from auth import get_current_user
from database import db
from datetime import datetime, timezone
from typing import List

router = APIRouter(prefix="/equipment", tags=["Equipment"])

@router.post("", response_model=dict)
async def create_equipment(equipment_data: EquipmentCreate, current_user: User = Depends(get_current_user)):
    # Get user's company
    company = await db.companies.find_one({"owner_id": current_user.id})
    if not company:
        raise HTTPException(status_code=400, detail="User must have a company to add equipment")
    
    # Create equipment
    equipment_dict = equipment_data.dict()
    equipment_dict["owner_id"] = current_user.id
    equipment_dict["company_id"] = company["id"]
    equipment_obj = Equipment(**equipment_dict)
    
    # Insert equipment
    await db.equipment.insert_one(equipment_obj.dict())
    
    return {"message": "Equipment added successfully", "equipment_id": equipment_obj.id}

@router.get("", response_model=List[Equipment])
async def get_equipment(skip: int = 0, limit: int = 50, equipment_type: Optional[EquipmentType] = None):
    query = {"is_available": True}
    if equipment_type:
        query["equipment_type"] = equipment_type
    
    equipment_list = await db.equipment.find(query).skip(skip).limit(limit).to_list(length=None)
    return [Equipment(**equipment) for equipment in equipment_list]

@router.get("/my", response_model=List[Equipment])
async def get_my_equipment(current_user: User = Depends(get_current_user)):
    equipment_list = await db.equipment.find({"owner_id": current_user.id}).to_list(length=None)
    return [Equipment(**equipment) for equipment in equipment_list]

@router.get("/my/locations", response_model=List[dict])
async def get_my_equipment_locations(current_user: User = Depends(get_current_user)):
    """Get all equipment with their current locations and associated driver/load info for fleet tracking"""
    equipment_list = await db.equipment.find({"owner_id": current_user.id}).to_list(length=None)
    
    result = []
    for equipment in equipment_list:
        vehicle_data = {
            "vehicle_id": equipment["id"],
            "name": equipment["name"],

# admin block moved below

            "asset_number": equipment.get("id", "N/A"),
            "latitude": equipment.get("current_latitude") or equipment.get("location_lat"),
            "longitude": equipment.get("current_longitude") or equipment.get("location_lng"),
            "last_update": equipment.get("last_location_update").isoformat() if equipment.get("last_location_update") else None,
            "status": "active" if equipment.get("is_available") else "idle",
            "driver_id": None,
            "driver_name": None,
            "driver_phone": None,
            "load_number": None
        }
        
        # Get current driver information if assigned
        current_driver_id = equipment.get("current_driver_id")
        if current_driver_id:
            driver = await db.users.find_one({"id": current_driver_id})
            if driver:
                vehicle_data["driver_id"] = driver.get("id", "N/A")
                vehicle_data["driver_name"] = driver.get("full_name", "N/A")
                vehicle_data["driver_phone"] = driver.get("phone", "N/A")
        
        # Get current active load/booking for this equipment
        active_booking = await db.bookings.find_one({
            "equipment_id": equipment["id"],
            "status": {"$in": ["planned", "in_transit_pickup", "at_pickup", "in_transit_delivery", "at_delivery"]}
        })
        
        if active_booking:
            vehicle_data["load_number"] = active_booking.get("order_number", "N/A")
            # If driver info is in booking, use it (override if available)
            if active_booking.get("driver_name"):
                vehicle_data["driver_name"] = active_booking.get("driver_name")
            if active_booking.get("driver_id"):
                vehicle_data["driver_id"] = active_booking.get("driver_id")
        
        result.append(vehicle_data)
    
    return result

@router.get("/{equipment_id}", response_model=Equipment)

# admin block moved below (duplicate removed)

async def get_equipment_details(equipment_id: str):
    equipment = await db.equipment.find_one({"id": equipment_id})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return Equipment(**equipment)

# Driver Management Routes
