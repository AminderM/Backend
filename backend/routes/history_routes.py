from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from auth import get_current_user
from models import User
from database import db
import uuid

router = APIRouter(prefix="/history", tags=["History"])


# =============================================================================
# MODELS - Flexible schema to accommodate frontend requirements
# =============================================================================

class FuelSurchargeCalculation(BaseModel):
    """Fuel Surcharge calculation data - 9 fields"""
    current_fuel_price: Optional[float] = None  # Current diesel $/gal
    base_fuel_price: Optional[float] = None     # Baseline $/gal
    base_rate: Optional[float] = None           # Base freight rate $
    miles: Optional[float] = None               # Trip distance
    surcharge_method: Optional[str] = None      # "percentage" or "cpm"
    surcharge_percent: Optional[float] = None   # % increase
    surcharge_amount: Optional[float] = None    # $ surcharge
    total_with_surcharge: Optional[float] = None  # Total $
    cpm_surcharge: Optional[float] = None       # $/mile rate
    # Flexible additional data for future fields
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class IFTAJurisdiction(BaseModel):
    """IFTA Jurisdiction entry - 7 fields per jurisdiction"""
    state: Optional[str] = None
    miles: Optional[float] = None
    fuel_purchased: Optional[float] = None
    tax_rate: Optional[float] = None
    fuel_used: Optional[float] = None
    net_taxable_fuel: Optional[float] = None
    tax_due: Optional[float] = None


class IFTACalculation(BaseModel):
    """IFTA (International Fuel Tax Agreement) calculation data - 6 main fields"""
    mpg: Optional[float] = None                 # Miles per gallon
    total_fuel_purchased: Optional[float] = None
    total_miles: Optional[float] = None
    total_fuel_used: Optional[float] = None
    jurisdictions: Optional[List[IFTAJurisdiction]] = Field(default_factory=list)
    total_tax_due: Optional[float] = None
    # Flexible additional data for future fields
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class BOLData(BaseModel):
    """Bill of Lading data - 7 fields"""
    bol_number: Optional[str] = None
    bol_date: Optional[str] = None              # Date of BOL
    shipper_name: Optional[str] = None
    consignee_name: Optional[str] = None
    carrier_name: Optional[str] = None
    total_weight: Optional[float] = None
    freight_terms: Optional[str] = None         # e.g., "prepaid", "collect"
    # Flexible additional data for future fields
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class HistoryRecord(BaseModel):
    """Generic history record returned from API"""
    id: str
    user_id: str
    type: str  # 'fuel-surcharge', 'ifta', 'bol'
    data: Dict[str, Any]
    created_at: str
    updated_at: Optional[str] = None


class HistoryListResponse(BaseModel):
    """Response for history list endpoint"""
    records: List[HistoryRecord]
    total: int
    page: int
    limit: int


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/fuel-surcharge", response_model=dict)
async def save_fuel_surcharge_calculation(
    calculation: FuelSurchargeCalculation,
    current_user: User = Depends(get_current_user)
):
    """
    Save a fuel surcharge calculation to history.
    """
    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    history_record = {
        "id": record_id,
        "user_id": current_user.id,
        "type": "fuel-surcharge",
        "data": calculation.dict(),
        "created_at": now,
        "updated_at": now
    }
    
    await db.history.insert_one(history_record)
    
    # Remove MongoDB _id from response
    history_record.pop("_id", None)
    
    return {
        "message": "Fuel surcharge calculation saved successfully",
        "record": history_record
    }


@router.post("/ifta", response_model=dict)
async def save_ifta_calculation(
    calculation: IFTACalculation,
    current_user: User = Depends(get_current_user)
):
    """
    Save an IFTA calculation to history.
    """
    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    history_record = {
        "id": record_id,
        "user_id": current_user.id,
        "type": "ifta",
        "data": calculation.dict(),
        "created_at": now,
        "updated_at": now
    }
    
    await db.history.insert_one(history_record)
    
    # Remove MongoDB _id from response
    history_record.pop("_id", None)
    
    return {
        "message": "IFTA calculation saved successfully",
        "record": history_record
    }


@router.post("/bol", response_model=dict)
async def save_bol(
    bol_data: BOLData,
    current_user: User = Depends(get_current_user)
):
    """
    Save a Bill of Lading to history.
    """
    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    history_record = {
        "id": record_id,
        "user_id": current_user.id,
        "type": "bol",
        "data": bol_data.dict(),
        "created_at": now,
        "updated_at": now
    }
    
    await db.history.insert_one(history_record)
    
    # Remove MongoDB _id from response
    history_record.pop("_id", None)
    
    return {
        "message": "Bill of Lading saved successfully",
        "record": history_record
    }


@router.get("", response_model=dict)
async def get_all_history(
    current_user: User = Depends(get_current_user),
    type: Optional[str] = Query(None, description="Filter by type: fuel-surcharge, ifta, bol"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc")
):
    """
    Get all history records for the authenticated user.
    Supports filtering by type and pagination.
    """
    # Build query
    query = {"user_id": current_user.id}
    
    if type:
        if type not in ["fuel-surcharge", "ifta", "bol"]:
            raise HTTPException(
                status_code=400, 
                detail="Invalid type. Must be one of: fuel-surcharge, ifta, bol"
            )
        query["type"] = type
    
    # Get total count
    total = await db.history.count_documents(query)
    
    # Calculate skip
    skip = (page - 1) * limit
    
    # Sort direction
    sort_direction = -1 if sort_order == "desc" else 1
    
    # Fetch records
    cursor = db.history.find(
        query,
        {"_id": 0}  # Exclude MongoDB _id
    ).sort(sort_by, sort_direction).skip(skip).limit(limit)
    
    records = await cursor.to_list(length=limit)
    
    return {
        "records": records,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit
    }


@router.get("/{record_id}", response_model=dict)
async def get_history_record(
    record_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific history record by ID.
    """
    record = await db.history.find_one(
        {"id": record_id, "user_id": current_user.id},
        {"_id": 0}
    )
    
    if not record:
        raise HTTPException(status_code=404, detail="History record not found")
    
    return {"record": record}


@router.delete("/{record_id}", response_model=dict)
async def delete_history_record(
    record_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a specific history record by ID.
    """
    result = await db.history.delete_one(
        {"id": record_id, "user_id": current_user.id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="History record not found")
    
    return {"message": "History record deleted successfully", "id": record_id}
