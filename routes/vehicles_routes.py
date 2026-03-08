"""
Vehicles Routes - Phase 4
Fleet management with Canadian compliance (CVIP inspections)
VIN tracking, maintenance, driver assignments
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime, timezone, date, timedelta
from models import User
from models_vehicles import (
    Vehicle, VehicleCreate, VehicleUpdate, VehicleResponse,
    VehicleType, VehicleCategory, VehicleStatus, OwnershipType, FuelType,
    InspectionRecord, InspectionType, InspectionResult,
    MaintenanceRecord, MaintenanceType, MaintenanceStatus,
    VehicleLocationUpdate, VehicleLocationHistory,
    DriverVehicleAssignment,
    calculate_cvip_status, format_year_make_model
)
from auth import (
    get_current_user,
    require_admin,
    require_dispatcher,
    is_platform_admin,
    is_dispatcher_or_above,
    check_tenant_access
)
from database import db

router = APIRouter(tags=["Vehicles"])


# =============================================================================
# VEHICLE CRUD ENDPOINTS
# =============================================================================

@router.post("/vehicles", response_model=dict)
async def create_vehicle(
    data: VehicleCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new vehicle (power unit or trailer)"""
    # Check tenant access
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant != data.tenant_id:
            raise HTTPException(status_code=403, detail="Cannot create vehicle for another tenant")
    
    # Check for duplicate unit number within tenant
    existing = await db.vehicles.find_one({
        "tenant_id": data.tenant_id,
        "unit_number": data.unit_number
    })
    if existing:
        raise HTTPException(status_code=400, detail=f"Unit number {data.unit_number} already exists")
    
    # Check for duplicate VIN if provided
    if data.vin:
        vin_exists = await db.vehicles.find_one({"vin": data.vin})
        if vin_exists:
            raise HTTPException(status_code=400, detail=f"VIN {data.vin} already registered")
    
    # Create vehicle
    vehicle = Vehicle(
        **data.dict(),
        created_by=current_user.id
    )
    
    # Set category based on vehicle type
    trailer_types = [
        VehicleType.DRY_VAN_TRAILER, VehicleType.REEFER_TRAILER,
        VehicleType.FLATBED_TRAILER, VehicleType.STEP_DECK_TRAILER,
        VehicleType.LOWBOY_TRAILER, VehicleType.CONESTOGA_TRAILER,
        VehicleType.TANKER_TRAILER, VehicleType.HOPPER_TRAILER,
        VehicleType.DUMP_TRAILER, VehicleType.INTERMODAL_CHASSIS
    ]
    if data.vehicle_type in trailer_types:
        vehicle.category = VehicleCategory.TRAILER
    else:
        vehicle.category = VehicleCategory.POWER_UNIT
    
    # Calculate CVIP status if expiry date provided
    if data.dict().get('cvip_expiry_date'):
        # This would be set during update, not create
        pass
    
    # Convert to dict for MongoDB
    doc = vehicle.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    
    # Handle date fields
    date_fields = ['license_plate_expiry', 'lease_end_date', 'purchase_date', 
                   'insurance_expiry', 'last_cvip_date', 'cvip_expiry_date',
                   'last_pm_date', 'next_pm_due_date']
    for field in date_fields:
        if doc.get(field):
            doc[field] = doc[field].isoformat() if hasattr(doc[field], 'isoformat') else doc[field]
    
    await db.vehicles.insert_one(doc)
    
    return {
        "message": "Vehicle created successfully",
        "id": vehicle.id,
        "unit_number": vehicle.unit_number,
        "vehicle_type": vehicle.vehicle_type.value,
        "category": vehicle.category.value
    }


@router.get("/vehicles", response_model=List[dict])
async def list_vehicles(
    status: Optional[VehicleStatus] = None,
    vehicle_type: Optional[VehicleType] = None,
    category: Optional[VehicleCategory] = None,
    carrier_id: Optional[str] = None,
    assigned_driver_id: Optional[str] = None,
    ownership_type: Optional[OwnershipType] = None,
    cvip_expiring_soon: bool = False,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List vehicles with filtering"""
    query = {}
    
    # Tenant isolation
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    if status:
        query["status"] = status.value
    
    if vehicle_type:
        query["vehicle_type"] = vehicle_type.value
    
    if category:
        query["category"] = category.value
    
    if carrier_id:
        query["carrier_id"] = carrier_id
    
    if assigned_driver_id:
        query["assigned_driver_id"] = assigned_driver_id
    
    if ownership_type:
        query["ownership_type"] = ownership_type.value
    
    if cvip_expiring_soon:
        # CVIP expiring within 30 days
        thirty_days = (date.today() + timedelta(days=30)).isoformat()
        query["cvip_expiry_date"] = {"$lte": thirty_days}
        query["is_cvip_expired"] = False
    
    results = await db.vehicles.find(query, {"_id": 0}).sort("unit_number", 1).skip(skip).limit(limit).to_list(length=limit)
    
    # Enhance with computed fields
    for vehicle in results:
        # Calculate CVIP status
        cvip_expiry = vehicle.get('cvip_expiry_date')
        if cvip_expiry:
            if isinstance(cvip_expiry, str):
                cvip_expiry = date.fromisoformat(cvip_expiry)
            status_str, days = calculate_cvip_status(cvip_expiry)
            vehicle['cvip_status'] = status_str
            vehicle['days_until_cvip_expiry'] = days
        
        # Format year/make/model
        vehicle['year_make_model'] = format_year_make_model(
            vehicle.get('year'),
            vehicle.get('make'),
            vehicle.get('model')
        )
    
    return results


@router.get("/vehicles/summary", response_model=dict)
async def get_vehicles_summary(
    current_user: User = Depends(get_current_user)
):
    """Get fleet summary statistics"""
    query = {}
    
    # Tenant isolation
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    # Get counts by status
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]
    status_counts = await db.vehicles.aggregate(pipeline).to_list(length=100)
    
    # Get counts by category
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$category",
            "count": {"$sum": 1}
        }}
    ]
    category_counts = await db.vehicles.aggregate(pipeline).to_list(length=100)
    
    # Get CVIP expiring soon count
    thirty_days = (date.today() + timedelta(days=30)).isoformat()
    cvip_expiring = await db.vehicles.count_documents({
        **query,
        "cvip_expiry_date": {"$lte": thirty_days},
        "status": {"$ne": "inactive"}
    })
    
    # Get CVIP expired count
    today = date.today().isoformat()
    cvip_expired = await db.vehicles.count_documents({
        **query,
        "cvip_expiry_date": {"$lt": today},
        "status": {"$ne": "inactive"}
    })
    
    total = await db.vehicles.count_documents(query)
    
    return {
        "total_vehicles": total,
        "by_status": {item["_id"]: item["count"] for item in status_counts},
        "by_category": {item["_id"]: item["count"] for item in category_counts},
        "cvip_expiring_30_days": cvip_expiring,
        "cvip_expired": cvip_expired,
        "compliance_alerts": cvip_expiring + cvip_expired
    }


@router.get("/vehicles/{vehicle_id}", response_model=dict)
async def get_vehicle(
    vehicle_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific vehicle with full details"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get assigned driver details
    driver = None
    if vehicle.get("assigned_driver_id"):
        driver = await db.users.find_one(
            {"id": vehicle["assigned_driver_id"]},
            {"_id": 0, "id": 1, "full_name": 1, "phone": 1, "email": 1}
        )
    
    # Get carrier details
    carrier = None
    if vehicle.get("carrier_id"):
        carrier = await db.carriers_brokers.find_one(
            {"id": vehicle["carrier_id"]},
            {"_id": 0, "id": 1, "company_name": 1}
        )
    
    # Get owner-operator details
    owner_operator = None
    if vehicle.get("owner_operator_id"):
        owner_operator = await db.users.find_one(
            {"id": vehicle["owner_operator_id"]},
            {"_id": 0, "id": 1, "full_name": 1}
        )
    
    # Get recent inspections
    inspections = await db.vehicle_inspections.find(
        {"vehicle_id": vehicle_id},
        {"_id": 0}
    ).sort("inspection_date", -1).limit(5).to_list(length=5)
    
    # Get recent maintenance
    maintenance = await db.vehicle_maintenance.find(
        {"vehicle_id": vehicle_id},
        {"_id": 0}
    ).sort("completed_at", -1).limit(5).to_list(length=5)
    
    # Calculate CVIP status
    cvip_expiry = vehicle.get('cvip_expiry_date')
    if cvip_expiry:
        if isinstance(cvip_expiry, str):
            cvip_expiry = date.fromisoformat(cvip_expiry)
        status_str, days = calculate_cvip_status(cvip_expiry)
        vehicle['cvip_status'] = status_str
        vehicle['days_until_cvip_expiry'] = days
    
    # Format year/make/model
    vehicle['year_make_model'] = format_year_make_model(
        vehicle.get('year'),
        vehicle.get('make'),
        vehicle.get('model')
    )
    
    return {
        **vehicle,
        "assigned_driver": driver,
        "carrier": carrier,
        "owner_operator": owner_operator,
        "recent_inspections": inspections,
        "recent_maintenance": maintenance
    }


@router.put("/vehicles/{vehicle_id}", response_model=dict)
async def update_vehicle(
    vehicle_id: str,
    data: VehicleUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a vehicle"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build update dict
    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = current_user.id
    
    # Handle date fields
    date_fields = ['license_plate_expiry']
    for field in date_fields:
        if field in update_data and update_data[field]:
            update_data[field] = update_data[field].isoformat()
    
    # If status changes to available, set is_available for legacy compatibility
    if 'status' in update_data:
        update_data['is_available'] = update_data['status'] in ['active', 'available']
    
    await db.vehicles.update_one({"id": vehicle_id}, {"$set": update_data})
    
    return {"message": "Vehicle updated successfully", "id": vehicle_id}


@router.delete("/vehicles/{vehicle_id}", response_model=dict)
async def delete_vehicle(
    vehicle_id: str,
    current_user: User = Depends(require_admin)
):
    """Deactivate a vehicle (soft delete)"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    await db.vehicles.update_one(
        {"id": vehicle_id},
        {"$set": {
            "status": VehicleStatus.INACTIVE.value,
            "is_available": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": current_user.id
        }}
    )
    
    return {"message": "Vehicle deactivated successfully"}


# =============================================================================
# DRIVER ASSIGNMENT ENDPOINTS
# =============================================================================

@router.post("/vehicles/{vehicle_id}/assign-driver", response_model=dict)
async def assign_driver_to_vehicle(
    vehicle_id: str,
    driver_id: str = Query(..., description="Driver user ID"),
    is_primary: bool = Query(True, description="Is this the primary driver?"),
    current_user: User = Depends(require_dispatcher)
):
    """Assign a driver to a vehicle"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Verify driver exists
    driver = await db.users.find_one({"id": driver_id}, {"_id": 0})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Check if driver is already assigned to another vehicle
    existing_assignment = await db.vehicles.find_one({
        "assigned_driver_id": driver_id,
        "id": {"$ne": vehicle_id},
        "status": {"$in": ["active", "available", "in_use"]}
    })
    if existing_assignment and is_primary:
        raise HTTPException(
            status_code=400, 
            detail=f"Driver is already assigned to vehicle {existing_assignment.get('unit_number')}"
        )
    
    # Update vehicle
    update_field = "assigned_driver_id" if is_primary else "co_driver_id"
    await db.vehicles.update_one(
        {"id": vehicle_id},
        {"$set": {
            update_field: driver_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": current_user.id
        }}
    )
    
    # Log assignment history
    assignment = DriverVehicleAssignment(
        driver_id=driver_id,
        vehicle_id=vehicle_id,
        is_primary=is_primary,
        odometer_at_assignment=vehicle.get('current_odometer_km'),
        assigned_by=current_user.id
    )
    doc = assignment.dict()
    doc['assigned_at'] = doc['assigned_at'].isoformat()
    await db.driver_vehicle_assignments.insert_one(doc)
    
    return {
        "message": f"Driver assigned as {'primary' if is_primary else 'co-driver'} successfully",
        "vehicle_id": vehicle_id,
        "driver_id": driver_id,
        "driver_name": driver.get("full_name")
    }


@router.post("/vehicles/{vehicle_id}/unassign-driver", response_model=dict)
async def unassign_driver_from_vehicle(
    vehicle_id: str,
    is_primary: bool = Query(True, description="Unassign primary driver?"),
    reason: str = Query(None, description="Reason for unassignment"),
    current_user: User = Depends(require_dispatcher)
):
    """Unassign a driver from a vehicle"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get current driver
    field = "assigned_driver_id" if is_primary else "co_driver_id"
    driver_id = vehicle.get(field)
    
    if not driver_id:
        raise HTTPException(status_code=400, detail="No driver assigned")
    
    # Update vehicle
    await db.vehicles.update_one(
        {"id": vehicle_id},
        {"$set": {
            field: None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": current_user.id
        }}
    )
    
    # Update assignment history
    await db.driver_vehicle_assignments.update_one(
        {
            "driver_id": driver_id,
            "vehicle_id": vehicle_id,
            "unassigned_at": None
        },
        {"$set": {
            "unassigned_at": datetime.now(timezone.utc).isoformat(),
            "unassignment_reason": reason,
            "odometer_at_unassignment": vehicle.get('current_odometer_km'),
            "unassigned_by": current_user.id
        }}
    )
    
    return {"message": "Driver unassigned successfully", "vehicle_id": vehicle_id}


# =============================================================================
# INSPECTION ENDPOINTS
# =============================================================================

@router.post("/vehicles/{vehicle_id}/inspections", response_model=dict)
async def add_inspection(
    vehicle_id: str,
    inspection_type: InspectionType,
    inspection_date: date,
    result: InspectionResult,
    expiry_date: Optional[date] = None,
    location: Optional[str] = None,
    inspector_name: Optional[str] = None,
    sticker_number: Optional[str] = None,
    defects_found: List[str] = Query(default=[]),
    notes: Optional[str] = None,
    cost: Optional[float] = None,
    current_user: User = Depends(get_current_user)
):
    """Add an inspection record for a vehicle"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Create inspection record
    inspection = InspectionRecord(
        vehicle_id=vehicle_id,
        inspection_type=inspection_type,
        inspection_date=inspection_date,
        expiry_date=expiry_date,
        location=location,
        inspector_name=inspector_name,
        sticker_number=sticker_number,
        result=result,
        defects_found=defects_found,
        notes=notes,
        cost=cost,
        created_by=current_user.id
    )
    
    doc = inspection.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['inspection_date'] = doc['inspection_date'].isoformat()
    if doc.get('expiry_date'):
        doc['expiry_date'] = doc['expiry_date'].isoformat()
    
    await db.vehicle_inspections.insert_one(doc)
    
    # Update vehicle if this is a CVIP/annual inspection
    if inspection_type in [InspectionType.CVIP, InspectionType.DOT_ANNUAL]:
        update_data = {
            "last_cvip_date": inspection_date.isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        if expiry_date:
            update_data["cvip_expiry_date"] = expiry_date.isoformat()
            status_str, days = calculate_cvip_status(expiry_date)
            update_data["is_cvip_expired"] = status_str == "expired"
            update_data["days_until_cvip_expiry"] = days
        if sticker_number:
            update_data["cvip_sticker_number"] = sticker_number
        
        # Update status if out of service
        if result == InspectionResult.OUT_OF_SERVICE:
            update_data["status"] = VehicleStatus.OUT_OF_SERVICE.value
            update_data["is_available"] = False
        
        await db.vehicles.update_one({"id": vehicle_id}, {"$set": update_data})
    
    return {
        "message": "Inspection recorded successfully",
        "id": inspection.id,
        "result": result.value
    }


@router.get("/vehicles/{vehicle_id}/inspections", response_model=List[dict])
async def get_vehicle_inspections(
    vehicle_id: str,
    inspection_type: Optional[InspectionType] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    """Get inspection history for a vehicle"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0, "tenant_id": 1})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    query = {"vehicle_id": vehicle_id}
    if inspection_type:
        query["inspection_type"] = inspection_type.value
    
    inspections = await db.vehicle_inspections.find(
        query, {"_id": 0}
    ).sort("inspection_date", -1).limit(limit).to_list(length=limit)
    
    return inspections


# =============================================================================
# MAINTENANCE ENDPOINTS
# =============================================================================

@router.post("/vehicles/{vehicle_id}/maintenance", response_model=dict)
async def add_maintenance_record(
    vehicle_id: str,
    maintenance_type: MaintenanceType,
    description: str,
    scheduled_date: Optional[date] = None,
    completed_at: Optional[datetime] = None,
    odometer_at_service: Optional[int] = None,
    shop_name: Optional[str] = None,
    labor_cost: float = 0,
    parts_cost: float = 0,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Add a maintenance record for a vehicle"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Create maintenance record
    maintenance = MaintenanceRecord(
        vehicle_id=vehicle_id,
        maintenance_type=maintenance_type,
        description=description,
        scheduled_date=scheduled_date,
        completed_at=completed_at,
        status=MaintenanceStatus.COMPLETED if completed_at else MaintenanceStatus.SCHEDULED,
        odometer_at_service=odometer_at_service,
        shop_name=shop_name,
        labor_cost=labor_cost,
        parts_cost=parts_cost,
        total_cost=labor_cost + parts_cost,
        notes=notes,
        created_by=current_user.id
    )
    
    doc = maintenance.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc.get('scheduled_date'):
        doc['scheduled_date'] = doc['scheduled_date'].isoformat()
    if doc.get('completed_at'):
        doc['completed_at'] = doc['completed_at'].isoformat()
    
    await db.vehicle_maintenance.insert_one(doc)
    
    # Update vehicle if PM completed
    if maintenance_type == MaintenanceType.PREVENTIVE and completed_at:
        next_pm = (completed_at.date() + timedelta(days=90)).isoformat()
        await db.vehicles.update_one(
            {"id": vehicle_id},
            {"$set": {
                "last_pm_date": completed_at.date().isoformat(),
                "next_pm_due_date": next_pm,
                "current_odometer_km": odometer_at_service or vehicle.get('current_odometer_km'),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    
    return {
        "message": "Maintenance record added successfully",
        "id": maintenance.id,
        "total_cost": maintenance.total_cost
    }


@router.get("/vehicles/{vehicle_id}/maintenance", response_model=List[dict])
async def get_vehicle_maintenance(
    vehicle_id: str,
    maintenance_type: Optional[MaintenanceType] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    """Get maintenance history for a vehicle"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0, "tenant_id": 1})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    query = {"vehicle_id": vehicle_id}
    if maintenance_type:
        query["maintenance_type"] = maintenance_type.value
    
    maintenance = await db.vehicle_maintenance.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)
    
    return maintenance


# =============================================================================
# LOCATION TRACKING ENDPOINTS
# =============================================================================

@router.post("/vehicles/{vehicle_id}/location", response_model=dict)
async def update_vehicle_location(
    vehicle_id: str,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    speed_kmh: Optional[float] = None,
    heading: Optional[float] = None,
    odometer_km: Optional[int] = None,
    source: str = "gps",
    current_user: User = Depends(get_current_user)
):
    """Update vehicle's current location"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    now = datetime.now(timezone.utc)
    
    # Update vehicle's current location
    update_data = {
        "current_latitude": latitude,
        "current_longitude": longitude,
        "last_location_update": now.isoformat(),
        "updated_at": now.isoformat()
    }
    
    if odometer_km:
        update_data["current_odometer_km"] = odometer_km
        # Convert to miles
        update_data["current_odometer_miles"] = int(odometer_km * 0.621371)
    
    await db.vehicles.update_one({"id": vehicle_id}, {"$set": update_data})
    
    # Store in location history
    history = VehicleLocationHistory(
        vehicle_id=vehicle_id,
        latitude=latitude,
        longitude=longitude,
        speed_kmh=speed_kmh,
        heading=heading,
        odometer_km=odometer_km,
        recorded_at=now,
        source=source
    )
    doc = history.dict()
    doc['recorded_at'] = doc['recorded_at'].isoformat()
    await db.vehicle_location_history.insert_one(doc)
    
    return {"message": "Location updated", "vehicle_id": vehicle_id}


@router.get("/vehicles/{vehicle_id}/location-history", response_model=List[dict])
async def get_vehicle_location_history(
    vehicle_id: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get location history for a vehicle"""
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0, "tenant_id": 1})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    if not check_tenant_access(current_user, vehicle.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    query = {"vehicle_id": vehicle_id}
    
    if from_date:
        query["recorded_at"] = {"$gte": from_date.isoformat()}
    if to_date:
        if "recorded_at" in query:
            query["recorded_at"]["$lte"] = to_date.isoformat()
        else:
            query["recorded_at"] = {"$lte": to_date.isoformat()}
    
    history = await db.vehicle_location_history.find(
        query, {"_id": 0}
    ).sort("recorded_at", -1).limit(limit).to_list(length=limit)
    
    return history


# =============================================================================
# FLEET TRACKING (Real-time view)
# =============================================================================

@router.get("/vehicles/fleet-tracking", response_model=List[dict])
async def get_fleet_tracking(
    status: Optional[VehicleStatus] = None,
    category: Optional[VehicleCategory] = None,
    current_user: User = Depends(get_current_user)
):
    """Get real-time fleet tracking data"""
    query = {}
    
    # Tenant isolation
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    if status:
        query["status"] = status.value
    else:
        # Exclude inactive vehicles by default
        query["status"] = {"$ne": "inactive"}
    
    if category:
        query["category"] = category.value
    
    vehicles = await db.vehicles.find(
        query,
        {
            "_id": 0, "id": 1, "unit_number": 1, "vehicle_type": 1, "category": 1,
            "status": 1, "current_latitude": 1, "current_longitude": 1,
            "last_location_update": 1, "assigned_driver_id": 1,
            "current_shipment_id": 1, "year": 1, "make": 1, "model": 1
        }
    ).to_list(length=500)
    
    result = []
    for v in vehicles:
        # Get driver name if assigned
        driver_name = None
        if v.get("assigned_driver_id"):
            driver = await db.users.find_one(
                {"id": v["assigned_driver_id"]},
                {"_id": 0, "full_name": 1}
            )
            if driver:
                driver_name = driver.get("full_name")
        
        # Get current load info
        load_number = None
        if v.get("current_shipment_id"):
            shipment = await db.shipments.find_one(
                {"id": v["current_shipment_id"]},
                {"_id": 0, "shipment_number": 1}
            )
            if shipment:
                load_number = shipment.get("shipment_number")
        
        result.append({
            "vehicle_id": v["id"],
            "unit_number": v["unit_number"],
            "vehicle_type": v["vehicle_type"],
            "category": v.get("category", "power_unit"),
            "year_make_model": format_year_make_model(v.get("year"), v.get("make"), v.get("model")),
            "status": v["status"],
            "latitude": v.get("current_latitude"),
            "longitude": v.get("current_longitude"),
            "last_update": v.get("last_location_update"),
            "driver_name": driver_name,
            "load_number": load_number
        })
    
    return result
