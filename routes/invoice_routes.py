from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from auth import get_current_user
from database import db
from bson import ObjectId
import anthropic
import logging
import json
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoice", tags=["Invoice Generator"])

SUPPORTED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}

SYSTEM_PROMPT = """You are an expert freight invoice parser for Canadian/US trucking companies.
Extract all invoice data from the provided document and return ONLY valid JSON with this exact structure:
{
  "confidence": <0.0-1.0 float>,
  "documentType": "<freight_invoice|bol|rate_confirmation|fuel_surcharge|lumper|detention|delivery_receipt|purchase_order|general_invoice>",
  "vendor": {"name":"","address":"","city":"","state":"","zip":"","phone":"","email":"","mc":"","dot":""},
  "billTo": {"name":"","address":"","city":"","state":"","zip":"","phone":"","email":""},
  "invoice": {"number":"","date":"YYYY-MM-DD","dueDate":"YYYY-MM-DD","poNumber":"","bolNumber":"","loadNumber":""},
  "lineItems": [
    {"id":"item_1","description":"","category":"<linehaul|fuel_surcharge|detention|lumper|accessorial|layover|tonu|stop_off|other>","quantity":1,"unit":"<load|mile|hour|flat|cwt|day|trip>","rate":0.00,"taxable":false}
  ],
  "totals": {"taxRate":0,"discountAmount":0},
  "notes": "",
  "paymentTerms": "<Net 15|Net 30|Net 45|Net 60|Due on Receipt|COD>",
  "aiSuggestions": ["up to 3 short improvement suggestions as strings"]
}
Return ONLY the JSON object. No markdown, no explanation."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ParseRequest(BaseModel):
    file: Optional[str] = None       # base64-encoded file content
    mimeType: Optional[str] = None   # MIME type of the file
    text: Optional[str] = None       # raw text fallback


class InvoiceLineItem(BaseModel):
    id: Optional[str] = None
    description: Optional[str] = ""
    category: Optional[str] = "other"
    quantity: Optional[float] = 1
    unit: Optional[str] = "load"
    rate: Optional[float] = 0.0
    taxable: Optional[bool] = False


class VendorInfo(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    mc: Optional[str] = None
    dot: Optional[str] = None


class BillToInfo(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class InvoiceMeta(BaseModel):
    number: Optional[str] = None
    date: Optional[str] = None
    dueDate: Optional[str] = None
    poNumber: Optional[str] = None
    bolNumber: Optional[str] = None
    loadNumber: Optional[str] = None


class TotalsInfo(BaseModel):
    taxRate: Optional[float] = 0
    discountAmount: Optional[float] = 0
    subtotal: Optional[float] = 0
    taxAmount: Optional[float] = 0
    total: Optional[float] = 0


class GenerateRequest(BaseModel):
    documentType: Optional[str] = None
    vendor: Optional[VendorInfo] = None
    billTo: Optional[BillToInfo] = None
    invoice: Optional[InvoiceMeta] = None
    lineItems: Optional[list[InvoiceLineItem]] = []
    totals: Optional[TotalsInfo] = None
    notes: Optional[str] = None
    paymentTerms: Optional[str] = None


# ---------------------------------------------------------------------------
# POST /api/invoice/parse
# ---------------------------------------------------------------------------

@router.post("/parse")
async def parse_invoice(req: ParseRequest, current_user=Depends(get_current_user)):
    """Accept a base64-encoded PDF/image or raw text, extract invoice fields via Claude."""
    if not req.file and not req.text:
        raise HTTPException(status_code=400, detail="Provide either 'file' (base64) or 'text'")

    client = anthropic.Anthropic()

    if req.file:
        mime_type = req.mimeType or "application/pdf"
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{mime_type}'. Supported: PDF, JPEG, PNG, GIF, WEBP."
            )

        # Strip data URL prefix if present
        b64_data = req.file
        if "," in b64_data:
            b64_data = b64_data.split(",", 1)[1]

        content_type = "document" if mime_type == "application/pdf" else "image"
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": content_type,
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64_data,
                    },
                },
                {"type": "text", "text": "Extract all invoice data from this document and return as JSON."},
            ],
        }]
    else:
        messages = [{
            "role": "user",
            "content": f"Extract all invoice data from this text and return as JSON:\n\n{req.text}",
        }]

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except anthropic.APIError as e:
        logger.error(f"Claude API error during invoice parse: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse Claude response as JSON: {raw[:200]}")
        raise HTTPException(status_code=422, detail="Failed to parse AI response as JSON")

    return {"data": parsed}


# ---------------------------------------------------------------------------
# POST /api/invoice/generate
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_invoice(req: GenerateRequest, current_user=Depends(get_current_user)):
    """Save a finalized invoice to MongoDB."""
    doc = req.dict()
    doc["invoice_number"] = (req.invoice.number if req.invoice else None)
    doc["status"] = "finalized"
    doc["created_by"] = str(current_user.id)
    doc["tenant_id"] = str(getattr(current_user, "tenant_id", "") or "")
    doc["created_at"] = datetime.now(timezone.utc)
    doc["updated_at"] = None

    result = await db["invoices"].insert_one(doc)
    doc["_id"] = str(result.inserted_id)

    return {"invoice": doc}


# ---------------------------------------------------------------------------
# GET /api/invoice/{id}
# ---------------------------------------------------------------------------

@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str, current_user=Depends(get_current_user)):
    """Return a single invoice document. Users can only fetch their own invoices.

    Accepts either:
    - The invoice document's _id (returned by POST /api/invoice/generate as invoice._id)
    - A history record's _id (returned by GET /api/history as id) — looks up the
      linked invoice_id stored in data.invoice_id on that history record
    """
    try:
        oid = ObjectId(invoice_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Try direct invoice lookup first
    doc = await db["invoices"].find_one({"_id": oid, "created_by": str(current_user.id)})

    if not doc:
        # Fall back: treat invoice_id as a history record _id and resolve the linked invoice
        history_rec = await db.history.find_one({
            "_id": oid,
            "user_id": str(current_user.id),
            "type": "invoice",
        })
        if not history_rec:
            raise HTTPException(status_code=404, detail="Invoice not found")

        linked_id = (history_rec.get("data") or {}).get("invoice_id")
        if not linked_id:
            raise HTTPException(status_code=404, detail="Invoice not found")

        try:
            linked_oid = ObjectId(linked_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Invoice not found")

        doc = await db["invoices"].find_one({"_id": linked_oid, "created_by": str(current_user.id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Invoice not found")

    doc["_id"] = str(doc["_id"])
    return {"invoice": doc}
