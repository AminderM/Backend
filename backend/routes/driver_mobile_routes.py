from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from models import User, UserRole, UserLogin
from auth import get_current_user, verify_password, create_access_token
from database import db
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import uuid
import os
import base64

router = APIRouter(prefix="/driver-mobile", tags=["Driver Mobile App"])

# ============== AUTHENTICATION ==============

@router.post("/login")
async def driver_mobile_login(credentials: UserLogin):
    """Driver login for mobile app - validates driver role"""
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_password(credentials.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if user.get("role") != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Access denied. Driver role required.")
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")
    
    access_token = create_access_token(data={"sub": user["id"], "role": user["role"]})
    
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

@router.get("/me")
async def get_driver_info(current_user: User = Depends(get_current_user)):
    """Get current driver information"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    user_data = await db.users.find_one({"id": current_user.id}, {"_id": 0, "password_hash": 0})
    return user_data

# ============== LOADS ==============

@router.get("/loads")
async def get_driver_loads(current_user: User = Depends(get_current_user)):
    """Get all loads assigned to the driver"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    # First, find the driver record to get driver_id
    driver = await db.drivers.find_one({
        "$or": [
            {"user_id": current_user.id},
            {"email": current_user.email}
        ]
    })
    
    driver_id = driver.get("id") if driver else current_user.id
    
    all_loads = []
    seen_booking_ids = set()
    
    # Check driver_loads collection (created when push-to-driver is used)
    driver_loads = await db.driver_loads.find(
        {"$or": [
            {"driver_id": driver_id},
            {"driver_user_id": current_user.id}
        ]},
        {"_id": 0}
    ).sort("assigned_at", -1).to_list(100)
    
    for load in driver_loads:
        booking_id = load.get("booking_id")
        if booking_id and booking_id not in seen_booking_ids:
            seen_booking_ids.add(booking_id)
            all_loads.append({
                **load,
                "id": load.get("id"),
                "pickup_city": load.get("pickup_location", "").split(",")[0] if load.get("pickup_location") else "",
                "delivery_city": load.get("delivery_location", "").split(",")[0] if load.get("delivery_location") else ""
            })
    
    # Check loads collection (skip if booking_id already seen)
    loads = await db.loads.find(
        {"$or": [
            {"assigned_driver_id": current_user.id},
            {"assigned_driver_id": driver_id}
        ]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    for load in loads:
        load_id = load.get("id")
        if load_id and load_id not in seen_booking_ids:
            seen_booking_ids.add(load_id)
            all_loads.append(load)
    
    # Check bookings collection (skip if already seen)
    bookings = await db.bookings.find(
        {"$or": [
            {"driver_id": current_user.id},
            {"assigned_driver_id": current_user.id},
            {"assigned_driver_id": driver_id}
        ]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    for booking in bookings:
        booking_id = booking.get("id")
        if booking_id and booking_id not in seen_booking_ids:
            seen_booking_ids.add(booking_id)
            all_loads.append({
                **booking,
                "pickup_city": booking.get("pickup_location", "").split(",")[0] if booking.get("pickup_location") else "",
                "delivery_city": booking.get("delivery_location", "").split(",")[0] if booking.get("delivery_location") else ""
            })
    
    return all_loads

@router.get("/loads/{load_id}")
async def get_load_detail(load_id: str, current_user: User = Depends(get_current_user)):
    """Get detailed load information - only if assigned to driver"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    # Check loads collection
    load = await db.loads.find_one(
        {"id": load_id, "assigned_driver_id": current_user.id},
        {"_id": 0}
    )
    
    # Fallback to bookings
    if not load:
        load = await db.bookings.find_one(
            {"id": load_id, "driver_id": current_user.id},
            {"_id": 0}
        )
    
    if not load:
        raise HTTPException(status_code=404, detail="Load not found or not assigned to you")
    
    return load

# ============== STATUS WORKFLOW ==============

VALID_STATUSES = [
    "assigned",
    "en_route_pickup",
    "arrived_pickup",
    "loaded",
    "en_route_delivery",
    "arrived_delivery",
    "delivered",
    "problem"
]

STATUS_TRANSITIONS = {
    "assigned": ["en_route_pickup"],
    "en_route_pickup": ["arrived_pickup"],
    "arrived_pickup": ["loaded"],
    "loaded": ["en_route_delivery"],
    "en_route_delivery": ["arrived_delivery"],
    "arrived_delivery": ["delivered"],
    "delivered": [],
    "problem": VALID_STATUSES  # Can transition to any status from problem
}

@router.post("/loads/{load_id}/status")
async def update_load_status(
    load_id: str,
    status_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update load status with validation and event logging"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    new_status = status_data.get("status")
    note = status_data.get("note", "")
    latitude = status_data.get("latitude")
    longitude = status_data.get("longitude")
    
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")
    
    if new_status == "problem" and not note:
        raise HTTPException(status_code=400, detail="Note is required for problem status")
    
    # Get current load
    load = await db.loads.find_one({"id": load_id, "assigned_driver_id": current_user.id})
    collection = "loads"
    
    if not load:
        load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id})
        collection = "bookings"
    
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    current_status = load.get("status", "assigned")
    
    # Validate transition (drivers can only move forward, except for problem)
    if new_status != "problem" and current_status != "problem":
        allowed_transitions = STATUS_TRANSITIONS.get(current_status, [])
        if new_status not in allowed_transitions and new_status != current_status:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot transition from {current_status} to {new_status}"
            )
    
    # Create status event
    event = {
        "id": str(uuid.uuid4()),
        "load_id": load_id,
        "driver_id": current_user.id,
        "previous_status": current_status,
        "new_status": new_status,
        "note": note,
        "latitude": latitude,
        "longitude": longitude,
        "created_at": datetime.now(timezone.utc)
    }
    await db.load_status_events.insert_one(event)
    
    # Update load status
    update_data = {
        "status": new_status,
        "last_status_update": datetime.now(timezone.utc),
        "last_status_note": note
    }
    
    if new_status == "arrived_pickup":
        update_data["actual_pickup_arrival"] = datetime.now(timezone.utc)
    elif new_status == "loaded":
        update_data["actual_pickup_departure"] = datetime.now(timezone.utc)
    elif new_status == "arrived_delivery":
        update_data["actual_delivery_arrival"] = datetime.now(timezone.utc)
    elif new_status == "delivered":
        update_data["actual_delivery_time"] = datetime.now(timezone.utc)
    
    if collection == "loads":
        await db.loads.update_one({"id": load_id}, {"$set": update_data})
    else:
        await db.bookings.update_one({"id": load_id}, {"$set": update_data})
    
    return {
        "message": "Status updated successfully",
        "status": new_status,
        "event_id": event["id"]
    }

@router.get("/loads/{load_id}/status-history")
async def get_status_history(load_id: str, current_user: User = Depends(get_current_user)):
    """Get status change history for a load"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    events = await db.load_status_events.find(
        {"load_id": load_id, "driver_id": current_user.id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return events

# ============== MESSAGING ==============

@router.get("/loads/{load_id}/messages")
async def get_load_messages(load_id: str, current_user: User = Depends(get_current_user)):
    """Get all messages for a load"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    # Verify driver is assigned to this load
    load = await db.loads.find_one({"id": load_id, "assigned_driver_id": current_user.id})
    if not load:
        load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id})
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    messages = await db.load_messages.find(
        {"load_id": load_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    
    # Mark messages as read by driver
    await db.load_messages.update_many(
        {"load_id": load_id, "sender_type": "dispatch", "read_by_driver": False},
        {"$set": {"read_by_driver": True, "read_at": datetime.now(timezone.utc)}}
    )
    
    return messages

@router.post("/loads/{load_id}/messages")
async def send_message(
    load_id: str,
    message_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Send a message to dispatch for a load"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    # Verify driver is assigned
    load = await db.loads.find_one({"id": load_id, "assigned_driver_id": current_user.id})
    if not load:
        load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id})
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    message = {
        "id": str(uuid.uuid4()),
        "load_id": load_id,
        "sender_id": current_user.id,
        "sender_name": current_user.full_name,
        "sender_type": "driver",
        "content": message_data.get("content", ""),
        "image_url": message_data.get("image_url"),
        "read_by_dispatch": False,
        "read_by_driver": True,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.load_messages.insert_one(message)
    
    return {"message": "Message sent", "data": {**message, "_id": None}}

@router.get("/messages/unread-count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    """Get count of unread messages across all loads"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    # Get driver's load IDs
    loads = await db.loads.find(
        {"assigned_driver_id": current_user.id},
        {"id": 1}
    ).to_list(100)
    load_ids = [l["id"] for l in loads]
    
    bookings = await db.bookings.find(
        {"driver_id": current_user.id},
        {"id": 1}
    ).to_list(100)
    load_ids.extend([b["id"] for b in bookings])
    
    count = await db.load_messages.count_documents({
        "load_id": {"$in": load_ids},
        "sender_type": "dispatch",
        "read_by_driver": False
    })
    
    return {"unread_count": count}

# ============== DOCUMENTS ==============

@router.get("/loads/{load_id}/documents")
async def get_load_documents(load_id: str, current_user: User = Depends(get_current_user)):
    """Get all documents for a load"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    # Verify assignment
    load = await db.loads.find_one({"id": load_id, "assigned_driver_id": current_user.id})
    if not load:
        load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id})
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    documents = await db.load_documents.find(
        {"load_id": load_id},
        {"_id": 0}
    ).sort("uploaded_at", -1).to_list(100)
    
    return documents

@router.post("/loads/{load_id}/documents")
async def upload_document(
    load_id: str,
    doc_type: str = Form(...),
    stop_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload a document for a load"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    # Verify assignment
    load = await db.loads.find_one({"id": load_id, "assigned_driver_id": current_user.id})
    if not load:
        load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id})
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    valid_doc_types = ["bol", "pod", "lumper", "scale_ticket", "other"]
    if doc_type.lower() not in valid_doc_types:
        raise HTTPException(status_code=400, detail=f"Invalid doc_type. Must be one of: {valid_doc_types}")
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Store as base64 for simplicity (can upgrade to cloud storage later)
    file_base64 = base64.b64encode(content).decode('utf-8')
    
    document = {
        "id": str(uuid.uuid4()),
        "load_id": load_id,
        "stop_id": stop_id,
        "doc_type": doc_type.lower(),
        "filename": file.filename,
        "content_type": file.content_type,
        "file_size": file_size,
        "file_data": file_base64,
        "uploaded_by": current_user.id,
        "uploader_name": current_user.full_name,
        "uploaded_at": datetime.now(timezone.utc)
    }
    
    await db.load_documents.insert_one(document)
    
    # Return without file_data
    return {
        "message": "Document uploaded successfully",
        "document": {
            "id": document["id"],
            "load_id": load_id,
            "doc_type": doc_type,
            "filename": file.filename,
            "uploaded_at": document["uploaded_at"]
        }
    }

@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific document with file data"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    doc = await db.load_documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Verify driver has access to this load
    load = await db.loads.find_one({"id": doc["load_id"], "assigned_driver_id": current_user.id})
    if not load:
        load = await db.bookings.find_one({"id": doc["load_id"], "driver_id": current_user.id})
    if not load:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return doc

# ============== LOCATION TRACKING ==============

@router.post("/location/ping")
async def ping_location(
    location_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Record driver location ping"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    location = {
        "id": str(uuid.uuid4()),
        "driver_id": current_user.id,
        "load_id": location_data.get("load_id"),
        "lat": location_data.get("lat"),
        "lng": location_data.get("lng"),
        "accuracy_m": location_data.get("accuracy_m"),
        "speed_mps": location_data.get("speed_mps"),
        "heading_deg": location_data.get("heading_deg"),
        "recorded_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.driver_locations.insert_one(location)
    
    # Update driver's last known location
    await db.users.update_one(
        {"id": current_user.id},
        {"$set": {
            "last_location_lat": location["lat"],
            "last_location_lng": location["lng"],
            "last_location_at": location["recorded_at"],
            "last_accuracy_m": location["accuracy_m"]
        }}
    )
    
    return {"message": "Location recorded", "id": location["id"]}

@router.get("/location/latest")
async def get_my_latest_location(current_user: User = Depends(get_current_user)):
    """Get driver's latest recorded location"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    location = await db.driver_locations.find_one(
        {"driver_id": current_user.id},
        {"_id": 0},
        sort=[("recorded_at", -1)]
    )
    
    return location or {}

# ============== PROFILE ==============

@router.put("/profile")
async def update_profile(
    profile_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update driver profile"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    allowed_fields = ["phone", "full_name"]
    update_data = {k: v for k, v in profile_data.items() if k in allowed_fields}
    
    if update_data:
        await db.users.update_one(
            {"id": current_user.id},
            {"$set": update_data}
        )
    
    updated_user = await db.users.find_one({"id": current_user.id}, {"_id": 0, "password_hash": 0})
    return updated_user

# ============== LOAD ACCEPT/REJECT ==============

@router.post("/loads/{load_id}/accept")
async def accept_load(
    load_id: str,
    accept_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Accept a load offer"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    # Find load
    load = await db.loads.find_one({"id": load_id, "assigned_driver_id": current_user.id})
    collection = "loads"
    
    if not load:
        load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id})
        collection = "bookings"
    
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    # Update status to accepted/en_route_pickup
    update_data = {
        "status": "en_route_pickup",
        "accepted_at": datetime.now(timezone.utc),
        "accepted_by_driver": True
    }
    
    if collection == "loads":
        await db.loads.update_one({"id": load_id}, {"$set": update_data})
    else:
        await db.bookings.update_one({"id": load_id}, {"$set": update_data})
    
    # Log event
    event = {
        "id": str(uuid.uuid4()),
        "load_id": load_id,
        "driver_id": current_user.id,
        "event_type": "load_accepted",
        "previous_status": load.get("status"),
        "new_status": "en_route_pickup",
        "created_at": datetime.now(timezone.utc)
    }
    await db.load_status_events.insert_one(event)
    
    return {"message": "Load accepted", "status": "en_route_pickup"}

@router.post("/loads/{load_id}/reject")
async def reject_load(
    load_id: str,
    reject_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Reject a load offer"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    reason = reject_data.get("reason", "Driver declined")
    
    # Find load
    load = await db.loads.find_one({"id": load_id, "assigned_driver_id": current_user.id})
    collection = "loads"
    
    if not load:
        load = await db.bookings.find_one({"id": load_id, "driver_id": current_user.id})
        collection = "bookings"
    
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    # Update - remove assignment or mark as rejected
    update_data = {
        "status": "rejected",
        "rejected_at": datetime.now(timezone.utc),
        "rejection_reason": reason,
        "assigned_driver_id": None
    }
    
    if collection == "loads":
        await db.loads.update_one({"id": load_id}, {"$set": update_data})
    else:
        await db.bookings.update_one({"id": load_id}, {"$set": update_data})
    
    # Log event
    event = {
        "id": str(uuid.uuid4()),
        "load_id": load_id,
        "driver_id": current_user.id,
        "event_type": "load_rejected",
        "reason": reason,
        "created_at": datetime.now(timezone.utc)
    }
    await db.load_status_events.insert_one(event)
    
    return {"message": "Load rejected"}

# ============== DRIVER ANALYTICS ==============

@router.get("/analytics")
async def get_driver_analytics(current_user: User = Depends(get_current_user)):
    """Get driver work analytics - earnings, miles, hours"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    week_start = now - timedelta(days=now.weekday())  # Monday
    
    # Get completed loads
    all_loads = await db.loads.find(
        {"assigned_driver_id": current_user.id},
        {"_id": 0}
    ).to_list(500)
    
    # Also check bookings
    bookings = await db.bookings.find(
        {"driver_id": current_user.id},
        {"_id": 0}
    ).to_list(500)
    
    all_loads.extend(bookings)
    
    # Calculate metrics
    def calculate_metrics(loads, start_time=None):
        filtered = loads
        if start_time:
            filtered = [l for l in loads if l.get("actual_delivery_time") and 
                       datetime.fromisoformat(str(l["actual_delivery_time"]).replace('Z', '+00:00')) >= start_time]
        
        total_earnings = sum(float(l.get("rate", 0) or l.get("price", 0) or 0) for l in filtered)
        total_miles = sum(int(l.get("estimated_miles", 0) or l.get("distance", 0) or 0) for l in filtered)
        total_hours = sum(float(l.get("estimated_hours", 0) or 0) for l in filtered)
        completed = len([l for l in filtered if l.get("status") == "delivered"])
        
        return {
            "earnings": round(total_earnings, 2),
            "miles": total_miles,
            "hours": round(total_hours, 1),
            "loads_completed": completed
        }
    
    # Get delivered loads for time-based calculations
    delivered_loads = [l for l in all_loads if l.get("status") == "delivered"]
    
    # Calculate for different periods
    last_24h_metrics = calculate_metrics(delivered_loads, last_24h)
    last_7d_metrics = calculate_metrics(delivered_loads, last_7d)
    weekly_metrics = calculate_metrics(delivered_loads, week_start)
    all_time_metrics = calculate_metrics(delivered_loads)
    
    # Get active loads count
    active_statuses = ['en_route_pickup', 'arrived_pickup', 'loaded', 'en_route_delivery', 'arrived_delivery']
    active_loads = len([l for l in all_loads if l.get("status") in active_statuses])
    
    # Calculate averages
    avg_miles_per_load = round(all_time_metrics["miles"] / max(all_time_metrics["loads_completed"], 1), 1)
    avg_earnings_per_load = round(all_time_metrics["earnings"] / max(all_time_metrics["loads_completed"], 1), 2)
    avg_earnings_per_mile = round(all_time_metrics["earnings"] / max(all_time_metrics["miles"], 1), 2)
    
    return {
        "last_24h": last_24h_metrics,
        "last_7d": last_7d_metrics,
        "weekly": weekly_metrics,
        "all_time": all_time_metrics,
        "active_loads": active_loads,
        "averages": {
            "miles_per_load": avg_miles_per_load,
            "earnings_per_load": avg_earnings_per_load,
            "earnings_per_mile": avg_earnings_per_mile
        },
        "generated_at": now.isoformat()
    }
