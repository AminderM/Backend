"""
Rate Cards & Accessorial Charges Routes - Phase 6
Lane-based pricing, standard accessorial codes, rate quotes
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime, timezone, date
from models import User
import sys
sys.path.insert(0, '/app/backend')
from models_rates import (
    RateCard, RateCardCreate, RateCardUpdate, RateCardStatus,
    LaneRate, RateType,
    AccessorialDefinition, AccessorialDefinitionCreate, AccessorialCode, AccessorialChargeType,
    RateQuote, calculate_rate_quote, find_matching_lane,
    DEFAULT_ACCESSORIALS
)
from auth import (
    get_current_user,
    require_admin,
    require_billing,
    is_platform_admin,
    check_tenant_access
)
from database import db

router = APIRouter(tags=["Rate Cards & Accessorials"])


# =============================================================================
# ACCESSORIAL DEFINITIONS ENDPOINTS
# =============================================================================

@router.get("/accessorials/codes", response_model=List[dict])
async def get_accessorial_codes(
    current_user: User = Depends(get_current_user)
):
    """Get list of standard accessorial codes"""
    codes = [
        {"code": code.value, "name": code.name.replace("_", " ").title()}
        for code in AccessorialCode
    ]
    return codes


@router.get("/accessorials/defaults", response_model=List[dict])
async def get_default_accessorials(
    current_user: User = Depends(get_current_user)
):
    """Get default accessorial charges (Canadian standard rates)"""
    return DEFAULT_ACCESSORIALS


@router.post("/accessorials", response_model=dict)
async def create_accessorial_definition(
    data: AccessorialDefinitionCreate,
    current_user: User = Depends(get_current_user)
):
    """Create or override an accessorial definition for a tenant"""
    # Check for existing
    existing = await db.accessorial_definitions.find_one({
        "tenant_id": data.tenant_id,
        "code": data.code.value
    })
    
    if existing:
        # Update existing
        await db.accessorial_definitions.update_one(
            {"id": existing["id"]},
            {"$set": {
                **data.dict(),
                "code": data.code.value,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        return {"message": "Accessorial definition updated", "id": existing["id"]}
    
    # Create new
    definition = AccessorialDefinition(
        **data.dict(),
        created_by=current_user.id
    )
    
    doc = definition.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['code'] = doc['code'].value if hasattr(doc['code'], 'value') else doc['code']
    doc['charge_type'] = doc['charge_type'].value if hasattr(doc['charge_type'], 'value') else doc['charge_type']
    
    await db.accessorial_definitions.insert_one(doc)
    
    return {
        "message": "Accessorial definition created",
        "id": definition.id,
        "code": data.code.value
    }


@router.get("/accessorials", response_model=List[dict])
async def list_accessorial_definitions(
    active_only: bool = True,
    current_user: User = Depends(get_current_user)
):
    """List accessorial definitions for the tenant"""
    query = {}
    
    # Tenant isolation
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    if active_only:
        query["is_active"] = True
    
    # Get tenant-specific definitions
    tenant_defs = await db.accessorial_definitions.find(query, {"_id": 0}).to_list(length=100)
    
    # Merge with defaults (tenant overrides take precedence)
    tenant_codes = {d["code"] for d in tenant_defs}
    
    result = list(tenant_defs)
    
    # Add defaults that aren't overridden
    for default in DEFAULT_ACCESSORIALS:
        if default["code"] not in tenant_codes:
            result.append({**default, "is_default": True})
    
    return result


@router.put("/accessorials/{code}", response_model=dict)
async def update_accessorial_definition(
    code: str,
    default_rate: Optional[float] = None,
    minimum_charge: Optional[float] = None,
    maximum_charge: Optional[float] = None,
    free_time_minutes: Optional[int] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_user)
):
    """Update an accessorial definition"""
    user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
    
    definition = await db.accessorial_definitions.find_one({
        "tenant_id": user_tenant,
        "code": code
    })
    
    if not definition:
        raise HTTPException(status_code=404, detail="Accessorial definition not found. Create it first.")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if default_rate is not None:
        update_data["default_rate"] = default_rate
    if minimum_charge is not None:
        update_data["minimum_charge"] = minimum_charge
    if maximum_charge is not None:
        update_data["maximum_charge"] = maximum_charge
    if free_time_minutes is not None:
        update_data["free_time_minutes"] = free_time_minutes
    if is_active is not None:
        update_data["is_active"] = is_active
    
    await db.accessorial_definitions.update_one(
        {"id": definition["id"]},
        {"$set": update_data}
    )
    
    return {"message": "Accessorial updated", "code": code}


# =============================================================================
# RATE CARD ENDPOINTS
# =============================================================================

@router.post("/rate-cards", response_model=dict)
async def create_rate_card(
    data: RateCardCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new rate card"""
    # Check tenant access
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant != data.tenant_id:
            raise HTTPException(status_code=403, detail="Cannot create rate card for another tenant")
    
    # Create rate card
    rate_card = RateCard(
        **data.dict(),
        created_by=current_user.id
    )
    
    # Convert to dict for MongoDB
    doc = rate_card.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['effective_date'] = doc['effective_date'].isoformat()
    if doc.get('expiry_date'):
        doc['expiry_date'] = doc['expiry_date'].isoformat()
    
    # Convert lane rates
    for lane in doc.get('lane_rates', []):
        lane['rate_type'] = lane['rate_type'].value if hasattr(lane['rate_type'], 'value') else lane['rate_type']
    
    await db.rate_cards.insert_one(doc)
    
    return {
        "message": "Rate card created successfully",
        "id": rate_card.id,
        "name": rate_card.name,
        "lanes_count": len(rate_card.lane_rates)
    }


@router.get("/rate-cards", response_model=List[dict])
async def list_rate_cards(
    status: Optional[RateCardStatus] = None,
    customer_id: Optional[str] = None,
    carrier_id: Optional[str] = None,
    is_customer_rate: Optional[bool] = None,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List rate cards with filtering"""
    query = {}
    
    # Tenant isolation
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    if status:
        query["status"] = status.value
    elif active_only:
        query["status"] = "active"
    
    if customer_id:
        query["customer_id"] = customer_id
    
    if carrier_id:
        query["carrier_id"] = carrier_id
    
    if is_customer_rate is not None:
        query["is_customer_rate"] = is_customer_rate
    
    rate_cards = await db.rate_cards.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    
    # Add summary info
    for rc in rate_cards:
        rc['lanes_count'] = len(rc.get('lane_rates', []))
        rc['accessorials_count'] = len(rc.get('accessorial_overrides', {}))
    
    return rate_cards


@router.get("/rate-cards/{rate_card_id}", response_model=dict)
async def get_rate_card(
    rate_card_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific rate card with full details"""
    rate_card = await db.rate_cards.find_one({"id": rate_card_id}, {"_id": 0})
    if not rate_card:
        raise HTTPException(status_code=404, detail="Rate card not found")
    
    if not check_tenant_access(current_user, rate_card.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get customer name if applicable
    if rate_card.get('customer_id'):
        customer = await db.customers.find_one(
            {"id": rate_card['customer_id']},
            {"_id": 0, "company_name": 1}
        )
        rate_card['customer_name'] = customer.get('company_name') if customer else None
    
    # Get carrier name if applicable
    if rate_card.get('carrier_id'):
        carrier = await db.carriers_brokers.find_one(
            {"id": rate_card['carrier_id']},
            {"_id": 0, "company_name": 1}
        )
        rate_card['carrier_name'] = carrier.get('company_name') if carrier else None
    
    return rate_card


@router.put("/rate-cards/{rate_card_id}", response_model=dict)
async def update_rate_card(
    rate_card_id: str,
    data: RateCardUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a rate card"""
    rate_card = await db.rate_cards.find_one({"id": rate_card_id})
    if not rate_card:
        raise HTTPException(status_code=404, detail="Rate card not found")
    
    if not check_tenant_access(current_user, rate_card.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = current_user.id
    
    # Handle dates
    if 'effective_date' in update_data and update_data['effective_date']:
        update_data['effective_date'] = update_data['effective_date'].isoformat()
    if 'expiry_date' in update_data and update_data['expiry_date']:
        update_data['expiry_date'] = update_data['expiry_date'].isoformat()
    
    await db.rate_cards.update_one({"id": rate_card_id}, {"$set": update_data})
    
    return {"message": "Rate card updated", "id": rate_card_id}


@router.post("/rate-cards/{rate_card_id}/lanes", response_model=dict)
async def add_lane_rate(
    rate_card_id: str,
    origin_city: Optional[str] = None,
    origin_province: str = Query(..., description="Origin province code (e.g., ON, BC)"),
    destination_city: Optional[str] = None,
    destination_province: str = Query(..., description="Destination province code"),
    lane_name: Optional[str] = None,
    distance_km: Optional[int] = None,
    dry_van_rate: Optional[float] = None,
    reefer_rate: Optional[float] = None,
    flatbed_rate: Optional[float] = None,
    rate_type: RateType = RateType.FLAT_RATE,
    minimum_charge: Optional[float] = None,
    transit_days: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """Add a lane rate to a rate card"""
    rate_card = await db.rate_cards.find_one({"id": rate_card_id})
    if not rate_card:
        raise HTTPException(status_code=404, detail="Rate card not found")
    
    if not check_tenant_access(current_user, rate_card.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build rates dict
    rates = {}
    if dry_van_rate is not None:
        rates["dry_van"] = dry_van_rate
    if reefer_rate is not None:
        rates["reefer"] = reefer_rate
    if flatbed_rate is not None:
        rates["flatbed"] = flatbed_rate
    
    if not rates:
        raise HTTPException(status_code=400, detail="At least one equipment rate is required")
    
    # Create lane rate
    lane = LaneRate(
        origin_city=origin_city,
        origin_province=origin_province.upper(),
        destination_city=destination_city,
        destination_province=destination_province.upper(),
        lane_name=lane_name or f"{origin_province.upper()}-{destination_province.upper()}",
        distance_km=distance_km,
        distance_miles=int(distance_km * 0.621371) if distance_km else None,
        rates=rates,
        rate_type=rate_type,
        minimum_charge=minimum_charge,
        transit_days=transit_days
    )
    
    lane_dict = lane.dict()
    lane_dict['rate_type'] = lane_dict['rate_type'].value
    
    await db.rate_cards.update_one(
        {"id": rate_card_id},
        {
            "$push": {"lane_rates": lane_dict},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    return {
        "message": "Lane rate added",
        "lane_id": lane.id,
        "lane_name": lane.lane_name
    }


@router.delete("/rate-cards/{rate_card_id}/lanes/{lane_id}", response_model=dict)
async def remove_lane_rate(
    rate_card_id: str,
    lane_id: str,
    current_user: User = Depends(get_current_user)
):
    """Remove a lane rate from a rate card"""
    rate_card = await db.rate_cards.find_one({"id": rate_card_id})
    if not rate_card:
        raise HTTPException(status_code=404, detail="Rate card not found")
    
    if not check_tenant_access(current_user, rate_card.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    await db.rate_cards.update_one(
        {"id": rate_card_id},
        {
            "$pull": {"lane_rates": {"id": lane_id}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    return {"message": "Lane rate removed", "lane_id": lane_id}


@router.post("/rate-cards/{rate_card_id}/activate", response_model=dict)
async def activate_rate_card(
    rate_card_id: str,
    current_user: User = Depends(get_current_user)
):
    """Activate a rate card"""
    rate_card = await db.rate_cards.find_one({"id": rate_card_id})
    if not rate_card:
        raise HTTPException(status_code=404, detail="Rate card not found")
    
    if not check_tenant_access(current_user, rate_card.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # If there's an existing active rate card for the same customer/carrier, mark it superseded
    query = {
        "tenant_id": rate_card.get("tenant_id"),
        "status": "active",
        "is_customer_rate": rate_card.get("is_customer_rate"),
        "id": {"$ne": rate_card_id}
    }
    if rate_card.get("customer_id"):
        query["customer_id"] = rate_card["customer_id"]
    if rate_card.get("carrier_id"):
        query["carrier_id"] = rate_card["carrier_id"]
    
    await db.rate_cards.update_many(
        query,
        {"$set": {"status": "superseded", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    # Activate this rate card
    await db.rate_cards.update_one(
        {"id": rate_card_id},
        {"$set": {
            "status": "active",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Rate card activated", "id": rate_card_id}


# =============================================================================
# RATE QUOTE ENDPOINTS
# =============================================================================

@router.post("/rate-cards/quote", response_model=RateQuote)
async def get_rate_quote(
    origin_city: str = Query(...),
    origin_province: str = Query(...),
    destination_city: str = Query(...),
    destination_province: str = Query(...),
    equipment_type: str = Query("dry_van"),
    distance_km: Optional[int] = None,
    customer_id: Optional[str] = None,
    tenant_id: Optional[str] = Query(None, description="Tenant ID for rate card lookup"),
    accessorial_codes: str = Query("", description="Comma-separated accessorial codes"),
    current_user: User = Depends(get_current_user)
):
    """
    Get a rate quote for a lane
    Finds the best matching rate card and calculates the rate
    """
    user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
    
    # Platform admin can specify tenant_id, otherwise use user's tenant
    lookup_tenant = tenant_id if (is_platform_admin(current_user) and tenant_id) else user_tenant
    
    # Build query for rate card
    query = {
        "status": "active",
        "is_customer_rate": True
    }
    
    # Only filter by tenant if specified
    if lookup_tenant:
        query["tenant_id"] = lookup_tenant
    
    # First try customer-specific rate card
    rate_card = None
    if customer_id:
        query["customer_id"] = customer_id
        rate_card_doc = await db.rate_cards.find_one(query, {"_id": 0})
        if rate_card_doc:
            rate_card = RateCard(**rate_card_doc)
    
    # Fall back to default rate card (no customer_id)
    if not rate_card:
        query.pop("customer_id", None)
        query["customer_id"] = None
        rate_card_doc = await db.rate_cards.find_one(query, {"_id": 0})
        if rate_card_doc:
            rate_card = RateCard(**rate_card_doc)
    
    if not rate_card:
        raise HTTPException(
            status_code=404,
            detail="No active rate card found. Create and activate a rate card first."
        )
    
    # Get accessorial definitions
    acc_codes = [c.strip() for c in accessorial_codes.split(",") if c.strip()]
    accessorial_defs = {}
    
    # Use the rate card's tenant for accessorial lookup
    rate_card_tenant = rate_card.tenant_id
    
    if acc_codes:
        defs = await db.accessorial_definitions.find(
            {"tenant_id": rate_card_tenant, "code": {"$in": acc_codes}},
            {"_id": 0}
        ).to_list(length=50)
        
        accessorial_defs = {d["code"]: AccessorialDefinition(**d) for d in defs}
        
        # Add defaults for missing codes
        for code in acc_codes:
            if code not in accessorial_defs:
                for default in DEFAULT_ACCESSORIALS:
                    if default["code"] == code:
                        accessorial_defs[code] = AccessorialDefinition(
                            tenant_id=rate_card_tenant,
                            code=AccessorialCode(code),
                            name=default["name"],
                            charge_type=AccessorialChargeType(default["charge_type"]),
                            default_rate=default["default_rate"],
                            is_taxable=default["is_taxable"]
                        )
                        break
    
    # Calculate quote
    quote = calculate_rate_quote(
        rate_card=rate_card,
        origin_city=origin_city,
        origin_province=origin_province,
        destination_city=destination_city,
        destination_province=destination_province,
        equipment_type=equipment_type,
        distance_km=distance_km,
        accessorial_codes=acc_codes,
        accessorial_definitions=accessorial_defs
    )
    
    # Update usage stats
    await db.rate_cards.update_one(
        {"id": rate_card.id},
        {
            "$inc": {"times_used": 1},
            "$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    return quote


@router.get("/rate-cards/lanes/search", response_model=List[dict])
async def search_lanes(
    origin_province: Optional[str] = None,
    destination_province: Optional[str] = None,
    tenant_id: Optional[str] = Query(None, description="Tenant ID for filtering"),
    current_user: User = Depends(get_current_user)
):
    """Search for lane rates across all active rate cards"""
    user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
    
    # Platform admin can specify tenant_id, otherwise use user's tenant
    lookup_tenant = tenant_id if (is_platform_admin(current_user) and tenant_id) else user_tenant
    
    # Build query
    query = {"status": "active", "is_customer_rate": True}
    if lookup_tenant:
        query["tenant_id"] = lookup_tenant
    
    # Get all active rate cards
    rate_cards = await db.rate_cards.find(query, {"_id": 0}).to_list(length=100)
    
    results = []
    for rc in rate_cards:
        for lane in rc.get('lane_rates', []):
            # Filter by origin/destination if provided
            if origin_province and lane.get('origin_province', '').upper() != origin_province.upper():
                continue
            if destination_province and lane.get('destination_province', '').upper() != destination_province.upper():
                continue
            
            results.append({
                "rate_card_id": rc["id"],
                "rate_card_name": rc["name"],
                "customer_id": rc.get("customer_id"),
                **lane
            })
    
    return results
