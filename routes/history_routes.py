from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, List, Any
from database import db
from auth import get_current_user
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["History"])


# ── Models ────────────────────────────────────────────────────────────────────

class BOLRequest(BaseModel):
    shipper_name: str
    shipper_address: str
    consignee_name: str
    consignee_address: str
    carrier_name: Optional[str] = None
    pro_number: Optional[str] = None
    freight_description: Optional[str] = None
    weight: Optional[float] = None
    pieces: Optional[int] = None
    commodity: Optional[str] = None
    special_instructions: Optional[str] = None
    reference_number: Optional[str] = None


def _str_id(doc: dict) -> dict:
    """Convert MongoDB _id to string id."""
    doc["id"] = str(doc.pop("_id"))
    return doc


# ── GET /api/history ──────────────────────────────────────────────────────────

@router.get("", response_model=dict)
async def get_history(
    type: Optional[str] = Query(None, description="Filter by type: bol, fuel-surcharge, ifta"),
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
):
    """
    Return paginated activity history for the current user.
    Optionally filter by record type (bol, fuel-surcharge, ifta).
    """
    query: dict = {"user_id": str(current_user.id)}
    if type:
        query["type"] = type

    cursor = db.history.find(query).sort("created_at", -1).skip(skip).limit(limit)
    records = await cursor.to_list(limit)
    total = await db.history.count_documents(query)

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "records": [_str_id(r) for r in records],
    }


# ── POST /api/history/bol ─────────────────────────────────────────────────────

@router.post("/bol", response_model=dict, status_code=201)
async def save_bol(
    payload: BOLRequest,
    current_user=Depends(get_current_user),
):
    """
    Save a generated Bill of Lading to the user's history.
    Called from BOLGeneratorPage after the BOL is produced on the frontend.
    """
    doc = {
        "type": "bol",
        "user_id": str(current_user.id),
        "company_id": str(getattr(current_user, "company_id", "") or ""),
        "data": payload.dict(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await db.history.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)

    return {"status": "success", "id": doc["id"], "record": doc}


# ── GET /api/history/fuel-surcharge ───────────────────────────────────────────

@router.get("/fuel-surcharge", response_model=dict)
async def get_fuel_surcharge_history(
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
):
    """
    Return the current user's fuel-surcharge calculation history.
    Used by FuelSurchargePage and ToolsPage.
    """
    query = {"user_id": str(current_user.id), "type": "fuel-surcharge"}
    cursor = db.history.find(query).sort("created_at", -1).skip(skip).limit(limit)
    records = await cursor.to_list(limit)
    total = await db.history.count_documents(query)

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "records": [_str_id(r) for r in records],
    }


# ── GET /api/history/ifta ─────────────────────────────────────────────────────

@router.get("/ifta", response_model=dict)
async def get_ifta_history(
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
):
    """
    Return the current user's IFTA calculation history.
    Used by IFTACalculatorPage and ToolsPage.
    """
    query = {"user_id": str(current_user.id), "type": "ifta"}
    cursor = db.history.find(query).sort("created_at", -1).skip(skip).limit(limit)
    records = await cursor.to_list(limit)
    total = await db.history.count_documents(query)

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "records": [_str_id(r) for r in records],
    }
