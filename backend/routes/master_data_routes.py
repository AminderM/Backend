"""
Master Data Routes - Phase 2
Carriers/Brokers, Locations, Shippers, Consignees, Customers
Plus Canadian Tax Calculator
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime, timezone
from models import User
from models_master_data import (
    # Carriers/Brokers
    CarrierBroker, CarrierBrokerCreate, CarrierBrokerUpdate, EntityType, EntityStatus,
    # Locations
    Location, LocationCreate, LocationUpdate, LocationType,
    # Shippers
    Shipper, ShipperCreate, ShipperUpdate,
    # Consignees
    Consignee, ConsigneeCreate, ConsigneeUpdate,
    # Customers
    Customer, CustomerCreate, CustomerUpdate,
    # Tax
    TaxCalculation, calculate_canadian_tax, get_all_tax_rates, get_tax_rates_by_province,
    CANADIAN_TAX_RATES,
)
from auth import (
    get_current_user, 
    require_admin, 
    require_dispatcher,
    is_platform_admin,
    check_tenant_access
)
from database import db

router = APIRouter(tags=["Master Data"])


# =============================================================================
# CANADIAN TAX CALCULATOR ENDPOINTS
# =============================================================================

@router.get("/tax/rates", response_model=dict)
async def get_tax_rates(current_user: User = Depends(get_current_user)):
    """Get all Canadian tax rates by province"""
    return {
        "rates": CANADIAN_TAX_RATES,
        "federal_gst_rate": 5.0,
        "notes": {
            "gst": "Federal Goods & Services Tax - applies to all provinces",
            "pst": "Provincial Sales Tax - BC, MB, SK",
            "hst": "Harmonized Sales Tax (GST+Provincial) - ON, NB, NL, NS, PE",
            "qst": "Quebec Sales Tax - calculated on GST-inclusive amount"
        }
    }


@router.get("/tax/rates/{province}", response_model=dict)
async def get_province_tax_rate(
    province: str,
    current_user: User = Depends(get_current_user)
):
    """Get tax rate for a specific province"""
    try:
        rates = get_tax_rates_by_province(province)
        return rates
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tax/calculate", response_model=TaxCalculation)
async def calculate_tax(
    subtotal: float = Query(..., description="Pre-tax amount in CAD"),
    province: str = Query(..., description="Province code (e.g., ON, BC, QC)"),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate Canadian taxes for a given amount and province
    
    Returns full breakdown of GST, PST/HST/QST as applicable
    """
    if subtotal < 0:
        raise HTTPException(status_code=400, detail="Subtotal cannot be negative")
    
    try:
        result = calculate_canadian_tax(subtotal, province)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tax/calculate-multi", response_model=List[TaxCalculation])
async def calculate_tax_multi_province(
    subtotal: float = Query(..., description="Pre-tax amount in CAD"),
    provinces: str = Query(..., description="Comma-separated province codes"),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate taxes for multiple provinces at once
    Useful for comparing rates across provinces
    """
    if subtotal < 0:
        raise HTTPException(status_code=400, detail="Subtotal cannot be negative")
    
    province_list = [p.strip().upper() for p in provinces.split(",")]
    results = []
    
    for province in province_list:
        try:
            result = calculate_canadian_tax(subtotal, province)
            results.append(result)
        except ValueError:
            continue  # Skip invalid provinces
    
    if not results:
        raise HTTPException(status_code=400, detail="No valid provinces provided")
    
    return results


# =============================================================================
# CARRIERS & BROKERS ENDPOINTS
# =============================================================================

@router.post("/carriers-brokers", response_model=dict)
async def create_carrier_broker(
    data: CarrierBrokerCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new carrier or broker"""
    # Check tenant access
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant != data.tenant_id:
            raise HTTPException(status_code=403, detail="Cannot create carrier/broker for another tenant")
    
    # Create carrier/broker object
    carrier_broker = CarrierBroker(
        **data.dict(),
        created_by=current_user.id
    )
    
    # Convert to dict for MongoDB
    doc = carrier_broker.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc.get('address'):
        doc['address'] = dict(doc['address'])
    
    await db.carriers_brokers.insert_one(doc)
    
    return {
        "message": f"{data.entity_type.value.title()} created successfully",
        "id": carrier_broker.id,
        "company_name": carrier_broker.company_name
    }


@router.get("/carriers-brokers", response_model=List[dict])
async def list_carriers_brokers(
    entity_type: Optional[EntityType] = None,
    status: Optional[EntityStatus] = None,
    province: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List carriers and/or brokers with filtering"""
    query = {}
    
    # Tenant isolation (unless platform admin)
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    if entity_type:
        query["entity_type"] = entity_type.value
    
    if status:
        query["status"] = status.value
    
    if province:
        query["operating_provinces"] = province.upper()
    
    results = await db.carriers_brokers.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(length=limit)
    return results


@router.get("/carriers-brokers/{entity_id}", response_model=dict)
async def get_carrier_broker(
    entity_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific carrier/broker by ID"""
    entity = await db.carriers_brokers.find_one({"id": entity_id}, {"_id": 0})
    if not entity:
        raise HTTPException(status_code=404, detail="Carrier/Broker not found")
    
    # Check tenant access
    if not check_tenant_access(current_user, entity.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return entity


@router.put("/carriers-brokers/{entity_id}", response_model=dict)
async def update_carrier_broker(
    entity_id: str,
    data: CarrierBrokerUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a carrier/broker"""
    entity = await db.carriers_brokers.find_one({"id": entity_id})
    if not entity:
        raise HTTPException(status_code=404, detail="Carrier/Broker not found")
    
    # Check tenant access
    if not check_tenant_access(current_user, entity.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build update dict
    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = current_user.id
    
    # Handle nested objects
    if "address" in update_data and update_data["address"]:
        update_data["address"] = dict(update_data["address"])
    
    await db.carriers_brokers.update_one({"id": entity_id}, {"$set": update_data})
    
    return {"message": "Carrier/Broker updated successfully", "id": entity_id}


@router.delete("/carriers-brokers/{entity_id}", response_model=dict)
async def delete_carrier_broker(
    entity_id: str,
    current_user: User = Depends(require_admin)
):
    """Delete (deactivate) a carrier/broker"""
    entity = await db.carriers_brokers.find_one({"id": entity_id})
    if not entity:
        raise HTTPException(status_code=404, detail="Carrier/Broker not found")
    
    # Soft delete
    await db.carriers_brokers.update_one(
        {"id": entity_id},
        {"$set": {
            "status": EntityStatus.INACTIVE.value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": current_user.id
        }}
    )
    
    return {"message": "Carrier/Broker deactivated successfully"}


# =============================================================================
# LOCATIONS ENDPOINTS
# =============================================================================

@router.post("/locations", response_model=dict)
async def create_location(
    data: LocationCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new location"""
    location = Location(
        **data.dict(),
        created_by=current_user.id
    )
    
    doc = location.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc.get('address'):
        doc['address'] = dict(doc['address'])
    
    await db.locations.insert_one(doc)
    
    return {
        "message": "Location created successfully",
        "id": location.id,
        "location_name": location.location_name
    }


@router.get("/locations", response_model=List[dict])
async def list_locations(
    location_type: Optional[LocationType] = None,
    province: Optional[str] = None,
    is_active: bool = True,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List locations with filtering"""
    query = {"is_active": is_active}
    
    # Tenant isolation
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    if location_type:
        query["location_type"] = location_type.value
    
    if province:
        query["address.state_province"] = province.upper()
    
    results = await db.locations.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(length=limit)
    return results


@router.get("/locations/{location_id}", response_model=dict)
async def get_location(
    location_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific location"""
    location = await db.locations.find_one({"id": location_id}, {"_id": 0})
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    if not check_tenant_access(current_user, location.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return location


@router.put("/locations/{location_id}", response_model=dict)
async def update_location(
    location_id: str,
    data: LocationUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a location"""
    location = await db.locations.find_one({"id": location_id})
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    if not check_tenant_access(current_user, location.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    if "address" in update_data and update_data["address"]:
        update_data["address"] = dict(update_data["address"])
    
    await db.locations.update_one({"id": location_id}, {"$set": update_data})
    
    return {"message": "Location updated successfully"}


# =============================================================================
# SHIPPERS ENDPOINTS
# =============================================================================

@router.post("/shippers", response_model=dict)
async def create_shipper(
    data: ShipperCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new shipper"""
    shipper = Shipper(
        **data.dict(),
        created_by=current_user.id
    )
    
    doc = shipper.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc.get('address'):
        doc['address'] = dict(doc['address'])
    
    await db.shippers.insert_one(doc)
    
    return {
        "message": "Shipper created successfully",
        "id": shipper.id,
        "company_name": shipper.company_name
    }


@router.get("/shippers", response_model=List[dict])
async def list_shippers(
    is_active: bool = True,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List shippers"""
    query = {"is_active": is_active}
    
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    results = await db.shippers.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(length=limit)
    return results


@router.get("/shippers/{shipper_id}", response_model=dict)
async def get_shipper(shipper_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific shipper"""
    shipper = await db.shippers.find_one({"id": shipper_id}, {"_id": 0})
    if not shipper:
        raise HTTPException(status_code=404, detail="Shipper not found")
    
    if not check_tenant_access(current_user, shipper.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return shipper


@router.put("/shippers/{shipper_id}", response_model=dict)
async def update_shipper(
    shipper_id: str,
    data: ShipperUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a shipper"""
    shipper = await db.shippers.find_one({"id": shipper_id})
    if not shipper:
        raise HTTPException(status_code=404, detail="Shipper not found")
    
    if not check_tenant_access(current_user, shipper.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    if "address" in update_data and update_data["address"]:
        update_data["address"] = dict(update_data["address"])
    
    await db.shippers.update_one({"id": shipper_id}, {"$set": update_data})
    
    return {"message": "Shipper updated successfully"}


# =============================================================================
# CONSIGNEES ENDPOINTS
# =============================================================================

@router.post("/consignees", response_model=dict)
async def create_consignee(
    data: ConsigneeCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new consignee"""
    consignee = Consignee(
        **data.dict(),
        created_by=current_user.id
    )
    
    doc = consignee.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc.get('address'):
        doc['address'] = dict(doc['address'])
    
    await db.consignees.insert_one(doc)
    
    return {
        "message": "Consignee created successfully",
        "id": consignee.id,
        "company_name": consignee.company_name
    }


@router.get("/consignees", response_model=List[dict])
async def list_consignees(
    is_active: bool = True,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List consignees"""
    query = {"is_active": is_active}
    
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    results = await db.consignees.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(length=limit)
    return results


@router.get("/consignees/{consignee_id}", response_model=dict)
async def get_consignee(consignee_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific consignee"""
    consignee = await db.consignees.find_one({"id": consignee_id}, {"_id": 0})
    if not consignee:
        raise HTTPException(status_code=404, detail="Consignee not found")
    
    if not check_tenant_access(current_user, consignee.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return consignee


@router.put("/consignees/{consignee_id}", response_model=dict)
async def update_consignee(
    consignee_id: str,
    data: ConsigneeUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a consignee"""
    consignee = await db.consignees.find_one({"id": consignee_id})
    if not consignee:
        raise HTTPException(status_code=404, detail="Consignee not found")
    
    if not check_tenant_access(current_user, consignee.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    if "address" in update_data and update_data["address"]:
        update_data["address"] = dict(update_data["address"])
    
    await db.consignees.update_one({"id": consignee_id}, {"$set": update_data})
    
    return {"message": "Consignee updated successfully"}


# =============================================================================
# CUSTOMERS ENDPOINTS
# =============================================================================

@router.post("/customers", response_model=dict)
async def create_customer(
    data: CustomerCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new customer"""
    customer = Customer(
        **data.dict(),
        created_by=current_user.id
    )
    
    doc = customer.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc.get('billing_address'):
        doc['billing_address'] = dict(doc['billing_address'])
    
    await db.customers.insert_one(doc)
    
    return {
        "message": "Customer created successfully",
        "id": customer.id,
        "company_name": customer.company_name
    }


@router.get("/customers", response_model=List[dict])
async def list_customers(
    is_active: bool = True,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List customers"""
    query = {"is_active": is_active}
    
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    results = await db.customers.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(length=limit)
    return results


@router.get("/customers/{customer_id}", response_model=dict)
async def get_customer(customer_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific customer"""
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if not check_tenant_access(current_user, customer.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return customer


@router.put("/customers/{customer_id}", response_model=dict)
async def update_customer(
    customer_id: str,
    data: CustomerUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a customer"""
    customer = await db.customers.find_one({"id": customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if not check_tenant_access(current_user, customer.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    if "billing_address" in update_data and update_data["billing_address"]:
        update_data["billing_address"] = dict(update_data["billing_address"])
    
    await db.customers.update_one({"id": customer_id}, {"$set": update_data})
    
    return {"message": "Customer updated successfully"}


@router.get("/customers/{customer_id}/tax-calculation", response_model=TaxCalculation)
async def calculate_customer_tax(
    customer_id: str,
    subtotal: float = Query(..., description="Pre-tax amount"),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate tax for a customer based on their tax province
    Returns breakdown with GST/PST/HST/QST as applicable
    """
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if not check_tenant_access(current_user, customer.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check for tax exemption
    if customer.get("is_tax_exempt"):
        return TaxCalculation(
            province="EXEMPT",
            province_name="Tax Exempt",
            subtotal=subtotal,
            total_tax_rate=0.0,
            total_tax_amount=0.0,
            grand_total=subtotal,
            tax_type="exempt",
            breakdown={"Tax Exempt": 0.0}
        )
    
    # Get tax province
    tax_province = customer.get("tax_province")
    if not tax_province:
        # Try to get from billing address
        billing_address = customer.get("billing_address", {})
        tax_province = billing_address.get("state_province")
    
    if not tax_province:
        raise HTTPException(
            status_code=400, 
            detail="Customer has no tax province set. Update customer billing address or tax_province field."
        )
    
    try:
        return calculate_canadian_tax(subtotal, tax_province)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
