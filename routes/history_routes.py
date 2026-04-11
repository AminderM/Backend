from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, List, Any
from database import db
from auth import require_web_user
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


TYPE_LABELS = {
    "bol": "Bill of Lading",
    "fuel-surcharge": "Fuel Surcharge",
    "ifta": "IFTA Calculation",
    "invoice": "Invoice",
    "pdf-to-word": "PDF to Word",
    "word-to-pdf": "Word to PDF",
    "e-signature": "E-Signature",
}


def _build_title(doc: dict) -> str:
    """Build a human-readable title from a history record."""
    t = doc.get("type", "")
    data = doc.get("data") or {}

    if t == "bol":
        shipper = data.get("shipper_name", "")
        consignee = data.get("consignee_name", "")
        pro = data.get("pro_number", "")
        parts = [f"BOL #{pro}" if pro else "BOL", f"{shipper} to {consignee}" if shipper and consignee else ""]
        return " — ".join(p for p in parts if p)

    if t == "invoice":
        num = data.get("invoice_number", "")
        vendor = data.get("vendor_name", "") or data.get("bill_to_name", "")
        parts = [f"Invoice #{num}" if num else "Invoice", vendor]
        return " — ".join(p for p in parts if p)

    if t == "fuel-surcharge":
        desc = data.get("description", "")
        return f"Fuel Surcharge — {desc}" if desc else "Fuel Surcharge Calculation"

    if t == "ifta":
        quarter = data.get("quarter", "") or data.get("period", "")
        return f"IFTA — {quarter}" if quarter else "IFTA Calculation"

    return TYPE_LABELS.get(t, t.replace("-", " ").title())


def _str_id(doc: dict) -> dict:
    """Convert MongoDB _id to string id and add title/download_url."""
    doc["id"] = str(doc.pop("_id"))
    doc["title"] = _build_title(doc)
    doc.setdefault("download_url", None)
    return doc


# ── GET /api/history ──────────────────────────────────────────────────────────

@router.get("", response_model=dict)
async def get_history(
    type: Optional[str] = Query(None, description="Filter by type: bol, fuel-surcharge, ifta"),
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    current_user=Depends(require_web_user),
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
    current_user=Depends(require_web_user),
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


# ── POST /api/history/fuel-surcharge ─────────────────────────────────────────

class FuelSurchargeHistoryRequest(BaseModel):
    # Frontend snake_case fields
    current_fuel_price: Optional[float] = None
    base_fuel_price: Optional[float] = None
    base_rate: Optional[float] = None
    miles: Optional[float] = None
    surcharge_method: Optional[str] = None
    surcharge_percent: Optional[float] = None
    surcharge_amount: Optional[float] = None
    total_with_surcharge: Optional[float] = None
    cpm_surcharge: Optional[float] = None
    # Legacy camelCase fields (kept for backward compatibility)
    method: Optional[str] = None
    fuelPrice: Optional[float] = None
    linehaul: Optional[float] = None
    surcharge: Optional[float] = None
    totalWithLH: Optional[float] = None
    fscPercent: Optional[float] = None
    currency: Optional[str] = "USD"
    description: Optional[str] = None


async def _is_paid(current_user) -> bool:
    role = str(getattr(current_user, "role", "")).replace("UserRole.", "")
    if role == "platform_admin":
        return True
    if not current_user.tenant_id:
        return False
    company = await db.companies.find_one({"id": current_user.tenant_id})
    if not company:
        return False
    if company.get("subscription_status") == "active":
        return True
    return any(s.get("status") == "active" for s in company.get("subscriptions", []))


@router.post("/fuel-surcharge", response_model=dict, status_code=201)
async def save_fuel_surcharge(
    payload: FuelSurchargeHistoryRequest,
    current_user=Depends(require_web_user),
):
    """
    Manually save a fuel surcharge calculation to history.
    Requires an active paid subscription. Returns HTTP 402 for free users.
    """
    if not await _is_paid(current_user):
        return JSONResponse(
            status_code=402,
            content={"detail": "History saving requires an active subscription."},
        )

    doc = {
        "type": "fuel-surcharge",
        "user_id": str(current_user.id),
        "company_id": str(getattr(current_user, "tenant_id", "") or ""),
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
    current_user=Depends(require_web_user),
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


# ── POST /api/history/invoice ────────────────────────────────────────────────

class InvoiceHistoryRequest(BaseModel):
    invoice_number: Optional[str] = None
    document_type: Optional[str] = None
    vendor_name: Optional[str] = None
    bill_to_name: Optional[str] = None
    total: Optional[float] = None
    status: Optional[str] = "finalized"
    invoice_id: Optional[str] = None  # MongoDB _id from POST /api/invoice/generate


@router.post("/invoice", response_model=dict, status_code=201)
async def save_invoice_history(
    payload: InvoiceHistoryRequest,
    current_user=Depends(require_web_user),
):
    """Save a lightweight invoice summary to the shared history collection."""
    doc = {
        "type": "invoice",
        "user_id": str(current_user.id),
        "tenant_id": str(getattr(current_user, "tenant_id", "") or ""),
        "data": {
            "invoice_id": payload.invoice_id,
            "invoice_number": payload.invoice_number,
            "document_type": payload.document_type,
            "vendor_name": payload.vendor_name,
            "bill_to_name": payload.bill_to_name,
            "total": payload.total,
            "status": payload.status,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await db.history.insert_one(doc)
    return {"id": str(result.inserted_id), "saved_to_history": True}


# ── GET /api/history/ifta ─────────────────────────────────────────────────────

@router.get("/ifta", response_model=dict)
async def get_ifta_history(
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    current_user=Depends(require_web_user),
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
