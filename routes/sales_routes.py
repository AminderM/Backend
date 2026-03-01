"""
Sales Routes - Rate Quotes Management
Handles CRUD operations for rate quotes in the Sales & Business Development department
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from database import db
from models import User
from auth import get_current_user
import uuid

router = APIRouter(prefix="/sales", tags=["Sales"])

# Pydantic Models
class StopLocation(BaseModel):
    address: str
    lat: Optional[float] = None
    lng: Optional[float] = None

class RateQuoteCreate(BaseModel):
    quote_number: str
    pickup: str
    destination: str
    stops: Optional[List[StopLocation]] = []
    distance: Optional[float] = None
    duration: Optional[str] = None
    base_rate: Optional[float] = 0
    fuel_surcharge: Optional[float] = 0
    accessorials: Optional[float] = 0
    total_quote: Optional[float] = 0
    consignor: Optional[str] = None
    consignee: Optional[str] = None
    customer: Optional[str] = None
    ftl_ltl_percentage: Optional[float] = None
    unit_type: Optional[str] = None
    weight: Optional[float] = None
    dimensions: Optional[dict] = None
    notes: Optional[str] = None
    status: str = "draft"  # draft, sent, accepted, declined, expired

class RateQuoteUpdate(BaseModel):
    pickup: Optional[str] = None
    destination: Optional[str] = None
    stops: Optional[List[StopLocation]] = None
    distance: Optional[float] = None
    duration: Optional[str] = None
    base_rate: Optional[float] = None
    fuel_surcharge: Optional[float] = None
    accessorials: Optional[float] = None
    total_quote: Optional[float] = None
    consignor: Optional[str] = None
    consignee: Optional[str] = None
    customer: Optional[str] = None
    ftl_ltl_percentage: Optional[float] = None
    unit_type: Optional[str] = None
    weight: Optional[float] = None
    dimensions: Optional[dict] = None
    notes: Optional[str] = None
    status: Optional[str] = None

# Helper function to get next quote number
async def get_next_quote_number() -> str:
    """Generate the next sequential quote number (RQ-0001, RQ-0002, etc.)"""
    # Find the highest quote number
    last_quote = await db.rate_quotes.find_one(
        {},
        sort=[("quote_number", -1)],
        projection={"quote_number": 1}
    )
    
    if last_quote and last_quote.get("quote_number"):
        try:
            # Extract number from RQ-XXXX format
            last_num = int(last_quote["quote_number"].replace("RQ-", ""))
            next_num = last_num + 1
        except (ValueError, AttributeError):
            next_num = 1
    else:
        next_num = 1
    
    return f"RQ-{next_num:04d}"

# Routes
@router.get('/rate-quotes')
async def get_rate_quotes(
    status: Optional[str] = None,
    customer: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get all rate quotes with optional filtering"""
    query = {}
    
    if status:
        query["status"] = status
    
    if customer:
        query["customer"] = {"$regex": customer, "$options": "i"}
    
    if search:
        query["$or"] = [
            {"quote_number": {"$regex": search, "$options": "i"}},
            {"pickup": {"$regex": search, "$options": "i"}},
            {"destination": {"$regex": search, "$options": "i"}},
            {"consignor": {"$regex": search, "$options": "i"}},
            {"consignee": {"$regex": search, "$options": "i"}},
            {"customer": {"$regex": search, "$options": "i"}}
        ]
    
    # Get quotes
    quotes = await db.rate_quotes.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Get total count
    total = await db.rate_quotes.count_documents(query)
    
    return {
        "quotes": quotes,
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.get('/rate-quotes/next-number')
async def get_next_quote_number_endpoint(current_user: User = Depends(get_current_user)):
    """Get the next available quote number"""
    next_number = await get_next_quote_number()
    return {"next_quote_number": next_number}

@router.get('/rate-quotes/{quote_id}')
async def get_rate_quote(quote_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific rate quote by ID"""
    quote = await db.rate_quotes.find_one({"id": quote_id}, {"_id": 0})
    
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    return quote

@router.post('/rate-quotes')
async def create_rate_quote(quote_data: RateQuoteCreate, current_user: User = Depends(get_current_user)):
    """Create a new rate quote"""
    
    # Check if quote number already exists
    existing = await db.rate_quotes.find_one({"quote_number": quote_data.quote_number})
    if existing:
        # Generate a new unique number if duplicate
        quote_data.quote_number = await get_next_quote_number()
    
    # Create quote document
    quote_dict = {
        "id": str(uuid.uuid4()),
        "quote_number": quote_data.quote_number,
        "pickup": quote_data.pickup,
        "destination": quote_data.destination,
        "stops": [stop.dict() for stop in (quote_data.stops or [])],
        "distance": quote_data.distance,
        "duration": quote_data.duration,
        "base_rate": quote_data.base_rate,
        "fuel_surcharge": quote_data.fuel_surcharge,
        "accessorials": quote_data.accessorials,
        "total_quote": quote_data.total_quote,
        "consignor": quote_data.consignor,
        "consignee": quote_data.consignee,
        "customer": quote_data.customer,
        "ftl_ltl_percentage": quote_data.ftl_ltl_percentage,
        "unit_type": quote_data.unit_type,
        "weight": quote_data.weight,
        "dimensions": quote_data.dimensions,
        "notes": quote_data.notes,
        "status": quote_data.status,
        "created_by": current_user.id,
        "created_by_name": current_user.full_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Insert into database
    await db.rate_quotes.insert_one(quote_dict)
    
    return {
        "message": "Quote created successfully",
        "quote_id": quote_dict["id"],
        "quote_number": quote_dict["quote_number"]
    }

@router.put('/rate-quotes/{quote_id}')
async def update_rate_quote(quote_id: str, quote_data: RateQuoteUpdate, current_user: User = Depends(get_current_user)):
    """Update an existing rate quote"""
    
    # Check if quote exists
    existing = await db.rate_quotes.find_one({"id": quote_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    # Build update data
    update_data = {}
    
    for field, value in quote_data.dict(exclude_unset=True).items():
        if value is not None:
            if field == "stops" and value:
                update_data[field] = [stop if isinstance(stop, dict) else stop.dict() for stop in value]
            else:
                update_data[field] = value
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Add metadata
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = current_user.id
    
    # Update in database
    await db.rate_quotes.update_one({"id": quote_id}, {"$set": update_data})
    
    return {
        "message": "Quote updated successfully",
        "quote_id": quote_id
    }

@router.delete('/rate-quotes/{quote_id}')
async def delete_rate_quote(quote_id: str, current_user: User = Depends(get_current_user)):
    """Delete a rate quote"""
    
    result = await db.rate_quotes.delete_one({"id": quote_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    return {"message": "Quote deleted successfully"}

@router.put('/rate-quotes/{quote_id}/status')
async def update_quote_status(quote_id: str, status_data: dict, current_user: User = Depends(get_current_user)):
    """Update quote status"""
    
    status = status_data.get("status")
    valid_statuses = ["draft", "sent", "accepted", "declined", "expired"]
    
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {', '.join(valid_statuses)}")
    
    # Check if quote exists
    existing = await db.rate_quotes.find_one({"id": quote_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    # Update status
    await db.rate_quotes.update_one(
        {"id": quote_id},
        {
            "$set": {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": current_user.id
            }
        }
    )
    
    return {
        "message": f"Quote status updated to {status}",
        "quote_id": quote_id,
        "status": status
    }

# Stats endpoint
@router.get('/stats')
async def get_sales_stats(current_user: User = Depends(get_current_user)):
    """Get sales statistics"""
    
    total_quotes = await db.rate_quotes.count_documents({})
    draft_quotes = await db.rate_quotes.count_documents({"status": "draft"})
    sent_quotes = await db.rate_quotes.count_documents({"status": "sent"})
    accepted_quotes = await db.rate_quotes.count_documents({"status": "accepted"})
    declined_quotes = await db.rate_quotes.count_documents({"status": "declined"})
    
    # Calculate total value of accepted quotes
    pipeline = [
        {"$match": {"status": "accepted"}},
        {"$group": {"_id": None, "total_value": {"$sum": "$total_quote"}}}
    ]
    result = await db.rate_quotes.aggregate(pipeline).to_list(1)
    total_value = result[0]["total_value"] if result else 0
    
    return {
        "total_quotes": total_quotes,
        "draft_quotes": draft_quotes,
        "sent_quotes": sent_quotes,
        "accepted_quotes": accepted_quotes,
        "declined_quotes": declined_quotes,
        "total_accepted_value": total_value
    }
