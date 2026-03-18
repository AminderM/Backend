"""
Orders & Shipments Routes - Phase 3
Sales-facing Orders and Operations-facing Shipments
Canada-First Design
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime, timezone, date
from models import User
from models_orders import (
    # Orders
    Order, OrderCreate, OrderUpdate, OrderStatus,
    # Shipments
    Shipment, ShipmentCreate, ShipmentUpdate, ShipmentStatus,
    # Supporting
    Stop, StopType, StopStatus, ShipmentStatusHistory, TrackingEvent, TrackingEventType,
    FreightType, EquipmentRequirement,
    # Helpers
    calculate_order_totals, create_stop_from_shipper, create_stop_from_consignee
)
from models_master_data import calculate_canadian_tax, CANADIAN_TAX_RATES
from auth import (
    get_current_user,
    require_admin,
    require_dispatcher,
    require_billing,
    is_platform_admin,
    is_dispatcher_or_above,
    check_tenant_access
)
from database import db
import uuid

router = APIRouter(tags=["Orders & Shipments"])


# =============================================================================
# ORDER ENDPOINTS (Sales/Customer facing)
# =============================================================================

@router.post("/orders", response_model=dict)
async def create_order(
    data: OrderCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new customer order
    Orders represent what the customer sees and pays for
    """
    # Verify customer exists
    customer = await db.customers.find_one({"id": data.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Check tenant access
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant != data.tenant_id:
            raise HTTPException(status_code=403, detail="Cannot create order for another tenant")
    
    # Create order
    order = Order(
        **data.dict(),
        created_by=current_user.id,
        sales_rep_id=current_user.id
    )
    
    # Calculate initial totals
    total_amount = (order.customer_rate or 0) + (order.fuel_surcharge or 0)
    accessorials_total = sum(a.get('amount', 0) for a in order.accessorials)
    total_amount += accessorials_total
    
    order.total_amount = round(total_amount, 2)
    
    # Calculate tax based on customer's province
    tax_province = customer.get('tax_province') or data.destination_state_province
    if tax_province and tax_province.upper() in CANADIAN_TAX_RATES and not customer.get('is_tax_exempt'):
        tax_calc = calculate_canadian_tax(total_amount, tax_province)
        order.tax_amount = tax_calc.total_tax_amount
        order.tax_province = tax_province.upper()
        order.grand_total = tax_calc.grand_total
    else:
        order.tax_amount = 0
        order.grand_total = total_amount
    
    # Convert to dict for MongoDB
    doc = order.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc.get('requested_pickup_date'):
        doc['requested_pickup_date'] = doc['requested_pickup_date'].isoformat()
    if doc.get('requested_delivery_date'):
        doc['requested_delivery_date'] = doc['requested_delivery_date'].isoformat()
    
    await db.orders.insert_one(doc)
    
    return {
        "message": "Order created successfully",
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status.value,
        "total_amount": order.total_amount,
        "tax_amount": order.tax_amount,
        "grand_total": order.grand_total
    }


@router.get("/orders", response_model=List[dict])
async def list_orders(
    status: Optional[OrderStatus] = None,
    customer_id: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List orders with filtering"""
    query = {}
    
    # Tenant isolation
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    if status:
        query["status"] = status.value
    
    if customer_id:
        query["customer_id"] = customer_id
    
    if from_date:
        query["created_at"] = {"$gte": from_date.isoformat()}
    
    if to_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = to_date.isoformat()
        else:
            query["created_at"] = {"$lte": to_date.isoformat()}
    
    results = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    return results


@router.get("/orders/{order_id}", response_model=dict)
async def get_order(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific order with related shipments"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if not check_tenant_access(current_user, order.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get related shipments
    shipments = await db.shipments.find(
        {"order_id": order_id},
        {"_id": 0}
    ).to_list(length=100)
    
    # Get customer details
    customer = await db.customers.find_one(
        {"id": order.get("customer_id")},
        {"_id": 0, "id": 1, "company_name": 1, "contact_name": 1}
    )
    
    return {
        **order,
        "shipments": shipments,
        "customer": customer
    }


@router.put("/orders/{order_id}", response_model=dict)
async def update_order(
    order_id: str,
    data: OrderUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update an order"""
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if not check_tenant_access(current_user, order.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build update dict
    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = current_user.id
    
    # Recalculate totals if rates changed
    if any(k in update_data for k in ['customer_rate', 'fuel_surcharge', 'accessorials']):
        customer_rate = update_data.get('customer_rate', order.get('customer_rate', 0)) or 0
        fuel_surcharge = update_data.get('fuel_surcharge', order.get('fuel_surcharge', 0)) or 0
        accessorials = update_data.get('accessorials', order.get('accessorials', []))
        accessorials_total = sum(a.get('amount', 0) for a in accessorials)
        
        total_amount = customer_rate + fuel_surcharge + accessorials_total
        update_data["total_amount"] = round(total_amount, 2)
        
        # Recalculate tax
        tax_province = order.get('tax_province')
        if tax_province and tax_province.upper() in CANADIAN_TAX_RATES:
            tax_calc = calculate_canadian_tax(total_amount, tax_province)
            update_data["tax_amount"] = tax_calc.total_tax_amount
            update_data["grand_total"] = tax_calc.grand_total
        else:
            update_data["grand_total"] = total_amount
    
    # Handle status transitions
    if 'status' in update_data:
        if update_data['status'] == 'confirmed' and not order.get('confirmed_at'):
            update_data['confirmed_at'] = datetime.now(timezone.utc).isoformat()
        elif update_data['status'] == 'completed' and not order.get('completed_at'):
            update_data['completed_at'] = datetime.now(timezone.utc).isoformat()
    
    # Convert dates
    if 'requested_pickup_date' in update_data and update_data['requested_pickup_date']:
        update_data['requested_pickup_date'] = update_data['requested_pickup_date'].isoformat()
    if 'requested_delivery_date' in update_data and update_data['requested_delivery_date']:
        update_data['requested_delivery_date'] = update_data['requested_delivery_date'].isoformat()
    
    await db.orders.update_one({"id": order_id}, {"$set": update_data})
    
    return {"message": "Order updated successfully", "id": order_id}


@router.post("/orders/{order_id}/confirm", response_model=dict)
async def confirm_order(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """Confirm a draft/quote order"""
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if not check_tenant_access(current_user, order.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if order.get("status") not in ["draft", "quote", "pending"]:
        raise HTTPException(status_code=400, detail=f"Cannot confirm order with status: {order.get('status')}")
    
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "status": "confirmed",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": current_user.id
        }}
    )
    
    return {"message": "Order confirmed successfully", "id": order_id, "status": "confirmed"}


@router.post("/orders/{order_id}/cancel", response_model=dict)
async def cancel_order(
    order_id: str,
    reason: str = Query(None, description="Cancellation reason"),
    current_user: User = Depends(get_current_user)
):
    """Cancel an order"""
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if not check_tenant_access(current_user, order.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if order.get("status") in ["invoiced", "paid"]:
        raise HTTPException(status_code=400, detail="Cannot cancel invoiced or paid orders")
    
    # Cancel related shipments
    await db.shipments.update_many(
        {"order_id": order_id, "status": {"$nin": ["delivered", "pod_received"]}},
        {"$set": {
            "status": "cancelled",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "status": "cancelled",
            "internal_notes": f"{order.get('internal_notes', '')} | CANCELLED: {reason or 'No reason provided'}",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": current_user.id
        }}
    )
    
    return {"message": "Order cancelled successfully", "id": order_id}


# =============================================================================
# SHIPMENT ENDPOINTS (Operations/Dispatch facing)
# =============================================================================

@router.post("/shipments", response_model=dict)
async def create_shipment(
    data: ShipmentCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new shipment for an order
    Shipments represent the actual freight movement
    """
    # Verify order exists
    order = await db.orders.find_one({"id": data.order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check tenant access
    if not check_tenant_access(current_user, order.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Create shipment
    shipment = Shipment(
        **data.dict(),
        created_by=current_user.id,
        dispatcher_id=current_user.id if is_dispatcher_or_above(current_user) else None
    )
    
    # Calculate total carrier cost
    carrier_cost = (shipment.carrier_rate or 0) + (shipment.carrier_fuel_surcharge or 0)
    accessorials_total = sum(a.get('amount', 0) for a in shipment.carrier_accessorials)
    shipment.total_carrier_cost = round(carrier_cost + accessorials_total, 2)
    
    # Auto-populate stops if shipper/consignee provided in order
    if not data.stops:
        stops = []
        # Get shipper for pickup stop
        if order.get('shipper_id'):
            shipper = await db.shippers.find_one({"id": order['shipper_id']}, {"_id": 0})
            if shipper:
                stops.append(create_stop_from_shipper(shipper, sequence=1))
        
        # Get consignee for delivery stop
        if order.get('consignee_id'):
            consignee = await db.consignees.find_one({"id": order['consignee_id']}, {"_id": 0})
            if consignee:
                stops.append(create_stop_from_consignee(consignee, sequence=2))
        
        if stops:
            shipment.stops = stops
    
    # Set origin/destination from first/last stop
    if shipment.stops:
        first_stop = shipment.stops[0]
        last_stop = shipment.stops[-1]
        shipment.origin_city = first_stop.city
        shipment.origin_state_province = first_stop.state_province
        shipment.origin_country = first_stop.country
        shipment.destination_city = last_stop.city
        shipment.destination_state_province = last_stop.state_province
        shipment.destination_country = last_stop.country
    
    # Convert to dict for MongoDB
    doc = shipment.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    
    # Handle stops serialization
    if doc.get('stops'):
        for stop in doc['stops']:
            if stop.get('scheduled_date'):
                stop['scheduled_date'] = stop['scheduled_date'].isoformat() if hasattr(stop['scheduled_date'], 'isoformat') else stop['scheduled_date']
    
    await db.shipments.insert_one(doc)
    
    # Update order with shipment reference
    await db.orders.update_one(
        {"id": data.order_id},
        {
            "$push": {"shipment_ids": shipment.id},
            "$set": {
                "status": "in_progress" if order.get("status") == "confirmed" else order.get("status"),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Recalculate order totals
    await _update_order_totals(data.order_id)
    
    return {
        "message": "Shipment created successfully",
        "id": shipment.id,
        "shipment_number": shipment.shipment_number,
        "order_id": data.order_id,
        "status": shipment.status.value
    }


@router.get("/shipments", response_model=List[dict])
async def list_shipments(
    status: Optional[ShipmentStatus] = None,
    order_id: Optional[str] = None,
    carrier_id: Optional[str] = None,
    driver_id: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List shipments with filtering"""
    query = {}
    
    # Tenant isolation
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    if status:
        query["status"] = status.value
    
    if order_id:
        query["order_id"] = order_id
    
    if carrier_id:
        query["carrier_id"] = carrier_id
    
    if driver_id:
        query["driver_id"] = driver_id
    
    if from_date:
        query["created_at"] = {"$gte": from_date.isoformat()}
    
    if to_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = to_date.isoformat()
        else:
            query["created_at"] = {"$lte": to_date.isoformat()}
    
    results = await db.shipments.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    return results


@router.get("/shipments/{shipment_id}", response_model=dict)
async def get_shipment(
    shipment_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific shipment with full details"""
    shipment = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    
    if not check_tenant_access(current_user, shipment.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get related order
    order = await db.orders.find_one(
        {"id": shipment.get("order_id")},
        {"_id": 0, "id": 1, "order_number": 1, "customer_id": 1, "status": 1}
    )
    
    # Get carrier details if assigned
    carrier = None
    if shipment.get("carrier_id"):
        carrier = await db.carriers_brokers.find_one(
            {"id": shipment["carrier_id"]},
            {"_id": 0, "id": 1, "company_name": 1, "entity_type": 1}
        )
    
    # Get driver details if assigned
    driver = None
    if shipment.get("driver_id"):
        driver = await db.users.find_one(
            {"id": shipment["driver_id"]},
            {"_id": 0, "id": 1, "full_name": 1, "phone": 1}
        )
    
    # Get status history
    status_history = await db.shipment_status_history.find(
        {"shipment_id": shipment_id},
        {"_id": 0}
    ).sort("changed_at", -1).to_list(length=50)
    
    return {
        **shipment,
        "order": order,
        "carrier": carrier,
        "driver": driver,
        "status_history": status_history
    }


@router.put("/shipments/{shipment_id}", response_model=dict)
async def update_shipment(
    shipment_id: str,
    data: ShipmentUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a shipment"""
    shipment = await db.shipments.find_one({"id": shipment_id})
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    
    if not check_tenant_access(current_user, shipment.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build update dict
    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = current_user.id
    
    # Recalculate carrier cost if rates changed
    if any(k in update_data for k in ['carrier_rate', 'carrier_fuel_surcharge', 'carrier_accessorials']):
        carrier_rate = update_data.get('carrier_rate', shipment.get('carrier_rate', 0)) or 0
        fuel_surcharge = update_data.get('carrier_fuel_surcharge', shipment.get('carrier_fuel_surcharge', 0)) or 0
        accessorials = update_data.get('carrier_accessorials', shipment.get('carrier_accessorials', []))
        accessorials_total = sum(a.get('amount', 0) for a in accessorials)
        
        update_data["total_carrier_cost"] = round(carrier_rate + fuel_surcharge + accessorials_total, 2)
    
    # Track status change
    if 'status' in update_data and update_data['status'] != shipment.get('status'):
        await _log_status_change(
            shipment_id=shipment_id,
            previous_status=shipment.get('status'),
            new_status=update_data['status'],
            changed_by=current_user.id
        )
        
        # Handle key status timestamps
        if update_data['status'] == 'dispatched':
            update_data['dispatched_at'] = datetime.now(timezone.utc).isoformat()
        elif update_data['status'] in ['loaded', 'in_transit']:
            update_data['picked_up_at'] = update_data.get('picked_up_at') or datetime.now(timezone.utc).isoformat()
        elif update_data['status'] == 'delivered':
            update_data['delivered_at'] = datetime.now(timezone.utc).isoformat()
        elif update_data['status'] == 'pod_received':
            update_data['pod_received'] = True
            update_data['pod_received_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.shipments.update_one({"id": shipment_id}, {"$set": update_data})
    
    # Update order totals if carrier cost changed
    if 'total_carrier_cost' in update_data:
        await _update_order_totals(shipment.get('order_id'))
    
    return {"message": "Shipment updated successfully", "id": shipment_id}


@router.post("/shipments/{shipment_id}/dispatch", response_model=dict)
async def dispatch_shipment(
    shipment_id: str,
    carrier_id: str = Query(..., description="Carrier/Broker ID"),
    driver_id: Optional[str] = Query(None, description="Driver ID"),
    carrier_rate: Optional[float] = Query(None, description="Carrier rate (buy rate)"),
    current_user: User = Depends(require_dispatcher)
):
    """Dispatch a shipment to a carrier/driver"""
    shipment = await db.shipments.find_one({"id": shipment_id})
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    
    if not check_tenant_access(current_user, shipment.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if shipment.get("status") not in ["pending", "planned"]:
        raise HTTPException(status_code=400, detail=f"Cannot dispatch shipment with status: {shipment.get('status')}")
    
    # Verify carrier exists
    carrier = await db.carriers_brokers.find_one({"id": carrier_id}, {"_id": 0})
    if not carrier:
        raise HTTPException(status_code=404, detail="Carrier not found")
    
    update_data = {
        "status": "dispatched",
        "carrier_id": carrier_id,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "dispatcher_id": current_user.id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user.id
    }
    
    if driver_id:
        update_data["driver_id"] = driver_id
    
    if carrier_rate is not None:
        update_data["carrier_rate"] = carrier_rate
        fuel_surcharge = shipment.get('carrier_fuel_surcharge', 0) or 0
        accessorials = shipment.get('carrier_accessorials', [])
        accessorials_total = sum(a.get('amount', 0) for a in accessorials)
        update_data["total_carrier_cost"] = round(carrier_rate + fuel_surcharge + accessorials_total, 2)
    
    # Log status change
    await _log_status_change(
        shipment_id=shipment_id,
        previous_status=shipment.get('status'),
        new_status='dispatched',
        changed_by=current_user.id,
        notes=f"Dispatched to {carrier.get('company_name')}"
    )
    
    await db.shipments.update_one({"id": shipment_id}, {"$set": update_data})
    
    # Update order totals
    await _update_order_totals(shipment.get('order_id'))
    
    return {
        "message": "Shipment dispatched successfully",
        "id": shipment_id,
        "carrier": carrier.get('company_name'),
        "status": "dispatched"
    }


@router.post("/shipments/{shipment_id}/status", response_model=dict)
async def update_shipment_status(
    shipment_id: str,
    status: ShipmentStatus,
    notes: Optional[str] = Query(None),
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Update shipment status with optional location and notes"""
    shipment = await db.shipments.find_one({"id": shipment_id})
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    
    if not check_tenant_access(current_user, shipment.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    previous_status = shipment.get('status')
    
    # Log status change
    await _log_status_change(
        shipment_id=shipment_id,
        previous_status=previous_status,
        new_status=status.value,
        changed_by=current_user.id,
        notes=notes,
        latitude=latitude,
        longitude=longitude
    )
    
    update_data = {
        "status": status.value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user.id
    }
    
    # Set timestamps based on status
    if status == ShipmentStatus.DISPATCHED:
        update_data['dispatched_at'] = datetime.now(timezone.utc).isoformat()
    elif status in [ShipmentStatus.LOADED, ShipmentStatus.IN_TRANSIT]:
        if not shipment.get('picked_up_at'):
            update_data['picked_up_at'] = datetime.now(timezone.utc).isoformat()
    elif status == ShipmentStatus.DELIVERED:
        update_data['delivered_at'] = datetime.now(timezone.utc).isoformat()
    elif status == ShipmentStatus.POD_RECEIVED:
        update_data['pod_received'] = True
        update_data['pod_received_at'] = datetime.now(timezone.utc).isoformat()
    elif status in [ShipmentStatus.DELAYED, ShipmentStatus.EXCEPTION]:
        update_data['has_exception'] = True
        update_data['exception_reason'] = notes
        update_data['exception_reported_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.shipments.update_one({"id": shipment_id}, {"$set": update_data})
    
    # Check if all shipments for order are delivered
    if status == ShipmentStatus.DELIVERED:
        await _check_order_completion(shipment.get('order_id'))
    
    return {
        "message": "Status updated successfully",
        "id": shipment_id,
        "previous_status": previous_status,
        "new_status": status.value
    }


@router.get("/shipments/{shipment_id}/tracking", response_model=List[dict])
async def get_shipment_tracking(
    shipment_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get tracking events for a shipment"""
    shipment = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "tenant_id": 1})
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    
    if not check_tenant_access(current_user, shipment.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    events = await db.tracking_events.find(
        {"shipment_id": shipment_id},
        {"_id": 0}
    ).sort("recorded_at", -1).limit(limit).to_list(length=limit)
    
    return events


@router.post("/shipments/{shipment_id}/tracking", response_model=dict)
async def add_tracking_event(
    shipment_id: str,
    event_type: TrackingEventType,
    message: Optional[str] = Query(None),
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    location_name: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Add a tracking event to a shipment"""
    shipment = await db.shipments.find_one({"id": shipment_id})
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    
    if not check_tenant_access(current_user, shipment.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    event = TrackingEvent(
        shipment_id=shipment_id,
        driver_id=shipment.get('driver_id'),
        event_type=event_type,
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        message=message,
        recorded_by=current_user.id
    )
    
    doc = event.dict()
    doc['recorded_at'] = doc['recorded_at'].isoformat()
    
    await db.tracking_events.insert_one(doc)
    
    return {"message": "Tracking event recorded", "id": event.id}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def _log_status_change(
    shipment_id: str,
    previous_status: Optional[str],
    new_status: str,
    changed_by: str,
    notes: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None
):
    """Log a status change in history"""
    history = ShipmentStatusHistory(
        shipment_id=shipment_id,
        previous_status=previous_status,
        new_status=new_status,
        latitude=latitude,
        longitude=longitude,
        notes=notes,
        changed_by=changed_by
    )
    
    doc = history.dict()
    doc['changed_at'] = doc['changed_at'].isoformat()
    
    await db.shipment_status_history.insert_one(doc)


async def _update_order_totals(order_id: str):
    """Recalculate order totals based on shipments"""
    if not order_id:
        return
    
    order = await db.orders.find_one({"id": order_id})
    if not order:
        return
    
    # Get all shipments for this order
    shipments = await db.shipments.find(
        {"order_id": order_id},
        {"_id": 0, "total_carrier_cost": 1}
    ).to_list(length=100)
    
    total_cost = sum(s.get('total_carrier_cost', 0) for s in shipments)
    total_amount = order.get('total_amount', 0)
    
    margin_amount = total_amount - total_cost
    margin_percentage = (margin_amount / total_amount * 100) if total_amount > 0 else 0
    
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "total_cost": round(total_cost, 2),
            "margin_amount": round(margin_amount, 2),
            "margin_percentage": round(margin_percentage, 2),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )


async def _check_order_completion(order_id: str):
    """Check if all shipments for an order are delivered"""
    if not order_id:
        return
    
    order = await db.orders.find_one({"id": order_id})
    if not order or order.get('status') in ['completed', 'invoiced', 'paid', 'cancelled']:
        return
    
    # Check if all shipments are delivered
    pending_shipments = await db.shipments.count_documents({
        "order_id": order_id,
        "status": {"$nin": ["delivered", "pod_received", "cancelled"]}
    })
    
    if pending_shipments == 0:
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
