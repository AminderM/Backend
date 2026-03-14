from fastapi import APIRouter, HTTPException, Depends
from models import *
from auth import get_current_user
from database import db
from datetime import datetime, timezone
from typing import List

router = APIRouter(prefix="/locations", tags=["Locations"])

@router.post("/locations", response_model=dict)
async def update_location(location_data: LocationUpdate, current_user: User = Depends(get_current_user)):
    # Verify user has access to this equipment
    equipment = await db.equipment.find_one({"id": location_data.equipment_id})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    
    # Check if user is the owner or assigned driver
    if equipment["owner_id"] != current_user.id and equipment.get("current_driver_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update equipment location
    await db.equipment.update_one(
        {"id": location_data.equipment_id},
        {
            "$set": {
                "location_lat": location_data.latitude,
                "location_lng": location_data.longitude,
                "current_latitude": location_data.latitude,
                "current_longitude": location_data.longitude,
                "last_location_update": datetime.now(timezone.utc)
            }
        }
    )
    
    # Store location history
    await db.location_history.insert_one(location_data.dict())
    
    # Broadcast location update to WebSocket clients
    broadcast_data = {
        "vehicle_id": location_data.equipment_id,
        "latitude": location_data.latitude,
        "longitude": location_data.longitude,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await manager.broadcast_location_update(broadcast_data)
    
    return {"message": "Location updated successfully"}

@router.get("/locations/{equipment_id}", response_model=List[LocationUpdate])
async def get_equipment_locations(equipment_id: str, current_user: User = Depends(get_current_user)):
    # Verify access
    equipment = await db.equipment.find_one({"id": equipment_id})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    
    if equipment["owner_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    locations = await db.location_history.find({"equipment_id": equipment_id}).sort("timestamp", -1).limit(100).to_list(length=None)
    return [LocationUpdate(**location) for location in locations]

# Booking Routes
