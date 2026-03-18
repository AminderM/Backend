"""
Accounting Routes - Accounts Receivable and Accounts Payable
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from models import User
from auth import get_current_user
from database import db
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pydantic import BaseModel
import uuid
import base64
import os

router = APIRouter(prefix="/accounting", tags=["Accounting"])

# Pydantic models
class ReceivableCreate(BaseModel):
    customer_name: str
    customer_email: Optional[str] = None
    invoice_number: str
    amount: float
    due_date: str
    description: Optional[str] = None
    load_reference: Optional[str] = None
    status: str = "pending"

class PayableCreate(BaseModel):
    vendor_name: str
    vendor_email: Optional[str] = None
    bill_number: str
    amount: float
    due_date: str
    description: Optional[str] = None
    category: str = "other"
    load_reference: Optional[str] = None
    status: str = "pending"

class StatusUpdate(BaseModel):
    status: str

# Expense Categories for Trucking/Transport industry
EXPENSE_CATEGORIES = [
    "fuel",
    "repairs_maintenance", 
    "tires",
    "parts_supplies",
    "tolls",
    "permits_licenses",
    "parking",
    "driver_meals",
    "lodging",
    "scale_fees",
    "lumper_fees",
    "detention_fees",
    "insurance",
    "registration",
    "cleaning",
    "communication",
    "office_supplies",
    "professional_services",
    "other"
]

class ExpenseCreate(BaseModel):
    vendor_name: str
    expense_date: str
    amount: float
    category: str = "other"
    receipt_number: Optional[str] = None
    description: Optional[str] = None
    payment_method: Optional[str] = None
    # Linking options
    load_reference: Optional[str] = None
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    vehicle_id: Optional[str] = None
    vehicle_name: Optional[str] = None
    # Line items for detailed receipts
    line_items: Optional[List[dict]] = None
    # Receipt image reference
    receipt_image_url: Optional[str] = None

class ExpenseUpdate(BaseModel):
    vendor_name: Optional[str] = None
    expense_date: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    receipt_number: Optional[str] = None
    description: Optional[str] = None
    payment_method: Optional[str] = None
    load_reference: Optional[str] = None
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    vehicle_id: Optional[str] = None
    vehicle_name: Optional[str] = None

# ==================== ACCOUNTS RECEIVABLE ====================

@router.get("/receivables")
async def get_receivables(current_user: User = Depends(get_current_user)):
    """Get all accounts receivable for the current user's company"""
    receivables = await db.accounts_receivable.find(
        {"company_id": current_user.id},  # Use user ID as company identifier
        {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    
    return {"receivables": receivables, "total": len(receivables)}

@router.post("/receivables")
async def create_receivable(
    data: ReceivableCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new invoice/receivable"""
    # Check for duplicate invoice number
    existing = await db.accounts_receivable.find_one({
        "invoice_number": data.invoice_number,
        "company_id": current_user.id  # Use user ID as company identifier
    })
    if existing:
        raise HTTPException(status_code=400, detail="Invoice number already exists")
    
    receivable = {
        "id": str(uuid.uuid4()),
        "company_id": current_user.id,  # Use user ID as company identifier
        "customer_name": data.customer_name,
        "customer_email": data.customer_email,
        "invoice_number": data.invoice_number,
        "amount": data.amount,
        "amount_paid": 0,
        "due_date": data.due_date,
        "description": data.description,
        "load_reference": data.load_reference,
        "status": data.status,
        "created_by": current_user.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.accounts_receivable.insert_one(receivable)
    receivable.pop("_id", None)
    
    return {"message": "Invoice created successfully", "receivable": receivable}

class PaymentRecord(BaseModel):
    amount: float
    payment_method: str = "check"  # check, wire, ach, card, cash
    reference_number: Optional[str] = None
    notes: Optional[str] = None

@router.post("/receivables/{receivable_id}/payments")
async def record_ar_payment(
    receivable_id: str,
    payment: PaymentRecord,
    current_user: User = Depends(get_current_user)
):
    """Record a payment for an accounts receivable item"""
    receivable = await db.accounts_receivable.find_one({
        "id": receivable_id,
        "company_id": current_user.id
    })
    
    if not receivable:
        raise HTTPException(status_code=404, detail="Receivable not found")
    
    # Create payment record
    payment_entry = {
        "id": str(uuid.uuid4()),
        "amount": payment.amount,
        "payment_method": payment.payment_method,
        "reference_number": payment.reference_number,
        "notes": payment.notes,
        "recorded_by": current_user.id,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Calculate new amount_paid
    current_paid = receivable.get("amount_paid", 0) or 0
    new_paid = current_paid + payment.amount
    total_amount = receivable.get("amount", 0)
    
    # Determine new status
    if new_paid >= total_amount:
        new_status = "paid"
    elif new_paid > 0:
        new_status = "partial"
    else:
        new_status = receivable.get("status", "pending")
    
    # Update receivable
    await db.accounts_receivable.update_one(
        {"id": receivable_id, "company_id": current_user.id},
        {
            "$set": {
                "amount_paid": new_paid,
                "status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$push": {"payments": payment_entry}
        }
    )
    
    return {
        "message": "Payment recorded successfully",
        "payment": payment_entry,
        "amount_paid": new_paid,
        "amount_remaining": max(0, total_amount - new_paid),
        "status": new_status
    }

@router.get("/receivables/{receivable_id}/payments")
async def get_ar_payment_history(
    receivable_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get payment history for an accounts receivable item"""
    receivable = await db.accounts_receivable.find_one(
        {"id": receivable_id, "company_id": current_user.id},
        {"_id": 0}
    )
    
    if not receivable:
        raise HTTPException(status_code=404, detail="Receivable not found")
    
    return {
        "receivable_id": receivable_id,
        "invoice_number": receivable.get("invoice_number"),
        "total_amount": receivable.get("amount", 0),
        "amount_paid": receivable.get("amount_paid", 0),
        "amount_remaining": max(0, (receivable.get("amount", 0) - receivable.get("amount_paid", 0))),
        "payments": receivable.get("payments", [])
    }

@router.put("/receivables/{receivable_id}")
async def update_receivable(
    receivable_id: str,
    data: StatusUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update receivable status"""
    result = await db.accounts_receivable.update_one(
        {"id": receivable_id, "company_id": current_user.id},  # Use user ID as company identifier
        {
            "$set": {
                "status": data.status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Receivable not found")
    
    return {"message": "Status updated successfully"}

@router.delete("/receivables/{receivable_id}")
async def delete_receivable(
    receivable_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a receivable"""
    result = await db.accounts_receivable.delete_one({
        "id": receivable_id,
        "company_id": current_user.id  # Use user ID as company identifier
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Receivable not found")
    
    return {"message": "Invoice deleted successfully"}

# ==================== ACCOUNTS PAYABLE ====================

@router.get("/payables")
async def get_payables(current_user: User = Depends(get_current_user)):
    """Get all accounts payable for the current user's company"""
    payables = await db.accounts_payable.find(
        {"company_id": current_user.id},  # Use user ID as company identifier
        {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    
    return {"payables": payables, "total": len(payables)}

@router.post("/payables")
async def create_payable(
    data: PayableCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new bill/payable"""
    # Check for duplicate bill number
    existing = await db.accounts_payable.find_one({
        "bill_number": data.bill_number,
        "company_id": current_user.id  # Use user ID as company identifier
    })
    if existing:
        raise HTTPException(status_code=400, detail="Bill number already exists")
    
    payable = {
        "id": str(uuid.uuid4()),
        "company_id": current_user.id,  # Use user ID as company identifier
        "vendor_name": data.vendor_name,
        "vendor_email": data.vendor_email,
        "bill_number": data.bill_number,
        "amount": data.amount,
        "amount_paid": 0,
        "due_date": data.due_date,
        "description": data.description,
        "load_reference": data.load_reference,
        "category": data.category,
        "status": data.status,
        "created_by": current_user.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.accounts_payable.insert_one(payable)
    payable.pop("_id", None)
    
    return {"message": "Bill created successfully", "payable": payable}

@router.post("/payables/{payable_id}/payments")
async def record_ap_payment(
    payable_id: str,
    payment: PaymentRecord,
    current_user: User = Depends(get_current_user)
):
    """Record a payment for an accounts payable item"""
    payable = await db.accounts_payable.find_one({
        "id": payable_id,
        "company_id": current_user.id
    })
    
    if not payable:
        raise HTTPException(status_code=404, detail="Payable not found")
    
    # Create payment record
    payment_entry = {
        "id": str(uuid.uuid4()),
        "amount": payment.amount,
        "payment_method": payment.payment_method,
        "reference_number": payment.reference_number,
        "notes": payment.notes,
        "recorded_by": current_user.id,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Calculate new amount_paid
    current_paid = payable.get("amount_paid", 0) or 0
    new_paid = current_paid + payment.amount
    total_amount = payable.get("amount", 0)
    
    # Determine new status
    if new_paid >= total_amount:
        new_status = "paid"
    elif new_paid > 0:
        new_status = "partial"
    else:
        new_status = payable.get("status", "pending")
    
    # Update payable
    await db.accounts_payable.update_one(
        {"id": payable_id, "company_id": current_user.id},
        {
            "$set": {
                "amount_paid": new_paid,
                "status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$push": {"payments": payment_entry}
        }
    )
    
    return {
        "message": "Payment recorded successfully",
        "payment": payment_entry,
        "amount_paid": new_paid,
        "amount_remaining": max(0, total_amount - new_paid),
        "status": new_status
    }

@router.get("/payables/{payable_id}/payments")
async def get_ap_payment_history(
    payable_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get payment history for an accounts payable item"""
    payable = await db.accounts_payable.find_one(
        {"id": payable_id, "company_id": current_user.id},
        {"_id": 0}
    )
    
    if not payable:
        raise HTTPException(status_code=404, detail="Payable not found")
    
    return {
        "payable_id": payable_id,
        "bill_number": payable.get("bill_number"),
        "total_amount": payable.get("amount", 0),
        "amount_paid": payable.get("amount_paid", 0),
        "amount_remaining": max(0, (payable.get("amount", 0) - payable.get("amount_paid", 0))),
        "payments": payable.get("payments", [])
    }

@router.put("/payables/{payable_id}")
async def update_payable(
    payable_id: str,
    data: StatusUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update payable status"""
    result = await db.accounts_payable.update_one(
        {"id": payable_id, "company_id": current_user.id},  # Use user ID as company identifier
        {
            "$set": {
                "status": data.status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Payable not found")
    
    return {"message": "Status updated successfully"}

@router.delete("/payables/{payable_id}")
async def delete_payable(
    payable_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a payable"""
    result = await db.accounts_payable.delete_one({
        "id": payable_id,
        "company_id": current_user.id  # Use user ID as company identifier
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Payable not found")
    
    return {"message": "Bill deleted successfully"}

# ==================== SUMMARY ====================

@router.get("/summary")
async def get_accounting_summary(current_user: User = Depends(get_current_user)):
    """Get accounting summary statistics"""
    company_id = current_user.id  # Use user ID as company identifier
    
    # AR totals
    ar_pipeline = [
        {"$match": {"company_id": company_id}},
        {"$group": {
            "_id": "$status",
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }}
    ]
    ar_stats = await db.accounts_receivable.aggregate(ar_pipeline).to_list(100)
    
    # AP totals
    ap_pipeline = [
        {"$match": {"company_id": company_id}},
        {"$group": {
            "_id": "$status",
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }}
    ]
    ap_stats = await db.accounts_payable.aggregate(ap_pipeline).to_list(100)
    
    return {
        "accounts_receivable": {stat["_id"]: {"total": stat["total"], "count": stat["count"]} for stat in ar_stats},
        "accounts_payable": {stat["_id"]: {"total": stat["total"], "count": stat["count"]} for stat in ap_stats}
    }


# ==================== INCOME (Received AR Payments) ====================

@router.get("/income")
async def get_income(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get income entries - AR payments that have been received (paid or partial)"""
    query = {
        "company_id": current_user.id,
        "$or": [
            {"status": "paid"},
            {"status": "partial"},
            {"amount_paid": {"$gt": 0}}
        ]
    }
    
    if status:
        if status == "fully_paid":
            query = {"company_id": current_user.id, "status": "paid"}
        elif status == "partial":
            query = {"company_id": current_user.id, "status": "partial"}
    
    income_entries = await db.accounts_receivable.find(
        query,
        {"_id": 0}
    ).sort("updated_at", -1).to_list(1000)
    
    # Calculate totals
    total_received = sum(e.get("amount_paid", 0) or 0 for e in income_entries)
    total_invoiced = sum(e.get("amount", 0) or 0 for e in income_entries)
    total_outstanding = total_invoiced - total_received
    fully_paid_count = sum(1 for e in income_entries if e.get("status") == "paid")
    partial_count = sum(1 for e in income_entries if e.get("status") == "partial")
    
    return {
        "income": income_entries,
        "summary": {
            "total_entries": len(income_entries),
            "fully_paid_count": fully_paid_count,
            "partial_count": partial_count,
            "total_received": total_received,
            "total_invoiced": total_invoiced,
            "total_outstanding": total_outstanding
        }
    }

@router.get("/income/summary")
async def get_income_summary(
    current_user: User = Depends(get_current_user)
):
    """Get income summary by category/load/customer"""
    company_id = current_user.id
    
    # Get all paid/partial AR entries
    income_entries = await db.accounts_receivable.find({
        "company_id": company_id,
        "$or": [
            {"status": "paid"},
            {"status": "partial"},
            {"amount_paid": {"$gt": 0}}
        ]
    }, {"_id": 0}).to_list(1000)
    
    # Group by customer
    by_customer = {}
    for entry in income_entries:
        customer = entry.get("customer_name", "Unknown")
        if customer not in by_customer:
            by_customer[customer] = {"received": 0, "invoiced": 0, "count": 0}
        by_customer[customer]["received"] += entry.get("amount_paid", 0) or 0
        by_customer[customer]["invoiced"] += entry.get("amount", 0) or 0
        by_customer[customer]["count"] += 1
    
    # Group by load (for load-linked invoices)
    by_load = {}
    for entry in income_entries:
        load_ref = entry.get("load_reference")
        if load_ref:
            if load_ref not in by_load:
                by_load[load_ref] = {"received": 0, "invoiced": 0, "customer": entry.get("customer_name")}
            by_load[load_ref]["received"] += entry.get("amount_paid", 0) or 0
            by_load[load_ref]["invoiced"] += entry.get("amount", 0) or 0
    
    return {
        "by_customer": by_customer,
        "by_load": by_load
    }


# ==================== EXPENSES LEDGER ====================

@router.get("/expenses")
async def get_expenses(
    status: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get all expenses for the current user's company"""
    query = {"company_id": current_user.id}
    
    if status:
        query["status"] = status
    if category:
        query["category"] = category
    
    expenses = await db.expenses.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    
    # Calculate totals
    pending_total = sum(e.get("amount", 0) for e in expenses if e.get("status") == "pending")
    approved_total = sum(e.get("amount", 0) for e in expenses if e.get("status") == "approved")
    
    return {
        "expenses": expenses,
        "summary": {
            "total_count": len(expenses),
            "pending_count": sum(1 for e in expenses if e.get("status") == "pending"),
            "approved_count": sum(1 for e in expenses if e.get("status") == "approved"),
            "pending_total": pending_total,
            "approved_total": approved_total
        }
    }

@router.post("/expenses")
async def create_expense(
    data: ExpenseCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new expense entry in the ledger"""
    expense = {
        "id": str(uuid.uuid4()),
        "company_id": current_user.id,
        "vendor_name": data.vendor_name,
        "expense_date": data.expense_date,
        "amount": data.amount,
        "category": data.category if data.category in EXPENSE_CATEGORIES else "other",
        "receipt_number": data.receipt_number,
        "description": data.description,
        "payment_method": data.payment_method,
        "load_reference": data.load_reference,
        "driver_id": data.driver_id,
        "driver_name": data.driver_name,
        "vehicle_id": data.vehicle_id,
        "vehicle_name": data.vehicle_name,
        "line_items": data.line_items or [],
        "receipt_image_url": data.receipt_image_url,
        "status": "pending",  # Always starts as pending
        "created_by": current_user.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.expenses.insert_one(expense)
    expense.pop("_id", None)
    
    return {"message": "Expense created successfully", "expense": expense}

@router.get("/expenses/{expense_id}")
async def get_expense(
    expense_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a single expense by ID"""
    expense = await db.expenses.find_one(
        {"id": expense_id, "company_id": current_user.id},
        {"_id": 0}
    )
    
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    return expense

@router.put("/expenses/{expense_id}")
async def update_expense(
    expense_id: str,
    data: ExpenseUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update an expense entry (only if still pending)"""
    expense = await db.expenses.find_one({
        "id": expense_id,
        "company_id": current_user.id
    })
    
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    if expense.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Can only edit pending expenses")
    
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.expenses.update_one(
        {"id": expense_id, "company_id": current_user.id},
        {"$set": update_data}
    )
    
    updated_expense = await db.expenses.find_one(
        {"id": expense_id},
        {"_id": 0}
    )
    
    return {"message": "Expense updated successfully", "expense": updated_expense}

@router.post("/expenses/{expense_id}/approve")
async def approve_expense(
    expense_id: str,
    current_user: User = Depends(get_current_user)
):
    """Approve an expense and create corresponding AP entry"""
    expense = await db.expenses.find_one({
        "id": expense_id,
        "company_id": current_user.id
    })
    
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    if expense.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Expense is not pending approval")
    
    # Generate bill number for AP
    bill_number = f"EXP-{expense.get('receipt_number', str(uuid.uuid4())[:8].upper())}"
    
    # Check if AP already exists
    existing_ap = await db.accounts_payable.find_one({
        "expense_id": expense_id,
        "company_id": current_user.id
    })
    
    if existing_ap:
        raise HTTPException(status_code=400, detail="AP entry already exists for this expense")
    
    # Create AP entry from approved expense
    ap_entry = {
        "id": str(uuid.uuid4()),
        "company_id": current_user.id,
        "vendor_name": expense.get("vendor_name"),
        "vendor_email": "",
        "bill_number": bill_number,
        "amount": expense.get("amount"),
        "amount_paid": 0,
        "due_date": expense.get("expense_date"),  # Due immediately for expenses
        "description": expense.get("description") or f"{expense.get('category', 'Expense').replace('_', ' ').title()} - {expense.get('vendor_name')}",
        "category": expense.get("category"),
        "load_reference": expense.get("load_reference"),
        "driver_id": expense.get("driver_id"),
        "driver_name": expense.get("driver_name"),
        "vehicle_id": expense.get("vehicle_id"),
        "vehicle_name": expense.get("vehicle_name"),
        "expense_id": expense_id,  # Link back to expense
        "status": "pending",
        "created_by": current_user.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "auto_generated": True,
        "source": "expense_approval"
    }
    
    await db.accounts_payable.insert_one(ap_entry)
    
    # Update expense status
    await db.expenses.update_one(
        {"id": expense_id, "company_id": current_user.id},
        {
            "$set": {
                "status": "approved",
                "approved_by": current_user.id,
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "ap_id": ap_entry["id"],
                "ap_bill_number": bill_number
            }
        }
    )
    
    return {
        "message": "Expense approved and AP entry created",
        "expense_id": expense_id,
        "ap_entry": {
            "id": ap_entry["id"],
            "bill_number": bill_number,
            "amount": ap_entry["amount"]
        }
    }

@router.post("/expenses/{expense_id}/reject")
async def reject_expense(
    expense_id: str,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Reject an expense"""
    expense = await db.expenses.find_one({
        "id": expense_id,
        "company_id": current_user.id
    })
    
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    if expense.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Expense is not pending")
    
    await db.expenses.update_one(
        {"id": expense_id, "company_id": current_user.id},
        {
            "$set": {
                "status": "rejected",
                "rejected_by": current_user.id,
                "rejected_at": datetime.now(timezone.utc).isoformat(),
                "rejection_reason": reason
            }
        }
    )
    
    return {"message": "Expense rejected", "expense_id": expense_id}

@router.delete("/expenses/{expense_id}")
async def delete_expense(
    expense_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete an expense (only if pending)"""
    expense = await db.expenses.find_one({
        "id": expense_id,
        "company_id": current_user.id
    })
    
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    if expense.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Can only delete pending expenses")
    
    await db.expenses.delete_one({"id": expense_id, "company_id": current_user.id})
    
    return {"message": "Expense deleted", "expense_id": expense_id}

@router.get("/expense-categories")
async def get_expense_categories():
    """Get list of available expense categories"""
    return {
        "categories": [
            {"id": "fuel", "name": "Fuel", "icon": "gas-pump"},
            {"id": "repairs_maintenance", "name": "Repairs & Maintenance", "icon": "wrench"},
            {"id": "tires", "name": "Tires", "icon": "circle"},
            {"id": "parts_supplies", "name": "Parts & Supplies", "icon": "cog"},
            {"id": "tolls", "name": "Tolls", "icon": "road"},
            {"id": "permits_licenses", "name": "Permits & Licenses", "icon": "id-card"},
            {"id": "parking", "name": "Parking", "icon": "parking"},
            {"id": "driver_meals", "name": "Driver Meals/Per Diem", "icon": "utensils"},
            {"id": "lodging", "name": "Lodging", "icon": "bed"},
            {"id": "scale_fees", "name": "Scale/Weigh Station Fees", "icon": "balance-scale"},
            {"id": "lumper_fees", "name": "Lumper Fees", "icon": "dolly"},
            {"id": "detention_fees", "name": "Detention Fees", "icon": "clock"},
            {"id": "insurance", "name": "Insurance", "icon": "shield-alt"},
            {"id": "registration", "name": "Registration", "icon": "file-alt"},
            {"id": "cleaning", "name": "Cleaning", "icon": "broom"},
            {"id": "communication", "name": "Communication", "icon": "phone"},
            {"id": "office_supplies", "name": "Office Supplies", "icon": "paperclip"},
            {"id": "professional_services", "name": "Professional Services", "icon": "briefcase"},
            {"id": "other", "name": "Other", "icon": "ellipsis-h"}
        ]
    }


# ==================== RECEIPT PARSING & AUTO-ENTRY ====================

@router.post("/parse-and-create")
async def parse_and_create_entry(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Parse receipt image using AI, determine treatment (Expense vs AP), 
    and automatically create the appropriate entry with receipt attached.
    """
    try:
        # Read the file
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode('utf-8')
        
        # Determine mime type
        content_type = file.content_type or 'image/jpeg'
        file_extension = file.filename.split('.')[-1] if file.filename else 'jpg'
        
        # Use OpenAI Vision API to parse the receipt with decision-making
        try:
            try:
                from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
            except ImportError:
                raise HTTPException(
                    status_code=503,
                    detail="Receipt parsing requires emergentintegrations package (not installed)."
                )
            import os
            import json
            import re
            
            # Get the Emergent LLM key
            emergent_key = os.environ.get('EMERGENT_LLM_KEY', 'sk-emergent-73b04E1E4779758EfC')
            
            # Initialize chat with GPT-4o for vision
            chat = LlmChat(
                api_key=emergent_key,
                session_id=f"receipt-{str(uuid.uuid4())[:8]}",
                system_message="""You are an expert accountant for a trucking/transport company. 
                Analyze receipts and invoices to extract financial data and determine the correct accounting treatment.
                You must decide if this is an EXPENSE (already paid) or ACCOUNTS_PAYABLE (to be paid later)."""
            ).with_model("openai", "gpt-4o")
            
            prompt = """Analyze this receipt/invoice image for a trucking/transport company.
            
            Extract information AND determine the accounting treatment:
            
            {
                "vendor_name": "Name of the vendor/business",
                "amount": 0.00,
                "expense_date": "YYYY-MM-DD",
                "receipt_number": "Receipt/Invoice number if visible",
                "description": "Brief description of items/services",
                "category": "fuel/repairs_maintenance/tires/parts_supplies/tolls/permits_licenses/parking/driver_meals/lodging/scale_fees/lumper_fees/detention_fees/insurance/other",
                "payment_method": "cash/card/check/fleet_card/ach/credit/other",
                "payment_status": "paid/unpaid/unknown",
                "treatment": "expense/accounts_payable",
                "treatment_reason": "Brief explanation of why this treatment was chosen",
                "line_items": [{"description": "item", "quantity": 1, "unit_price": 0.00, "total": 0.00}],
                "gallons": null,
                "price_per_gallon": null,
                "odometer": null,
                "vehicle_number": null,
                "driver_name": null,
                "due_date": "YYYY-MM-DD or null if already paid",
                "tax_amount": null
            }
            
            TREATMENT DECISION RULES:
            1. If the receipt shows "PAID", "CASH", "CARD PAYMENT", "THANK YOU" → treatment: "expense"
            2. If it's an INVOICE with "DUE DATE", "PAYMENT TERMS", "NET 30" → treatment: "accounts_payable"
            3. Gas station receipts, restaurant receipts, toll receipts → typically "expense" (paid at point of sale)
            4. Repair shop invoices, parts invoices with balance due → typically "accounts_payable"
            5. If payment_method is cash/card/fleet_card → "expense"
            6. If payment_method is credit/terms/invoice → "accounts_payable"
            
            Return ONLY valid JSON, no other text."""
            
            # Create image content
            image_content = ImageContent(image_base64=base64_image)
            
            # Send message with image
            user_message = UserMessage(
                text=prompt,
                file_contents=[image_content]
            )
            
            response = await chat.send_message(user_message)
            
            # Parse the response
            response_text = response.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
                response_text = re.sub(r'\s*```$', '', response_text)
            
            parsed_data = json.loads(response_text)
            
            # Validate and normalize category
            category = parsed_data.get('category', 'other')
            if category not in EXPENSE_CATEGORIES:
                category = 'other'
            
            # Determine treatment
            treatment = parsed_data.get('treatment', 'expense').lower()
            if treatment not in ['expense', 'accounts_payable']:
                # Default based on payment method
                payment_method = parsed_data.get('payment_method', '').lower()
                if payment_method in ['cash', 'card', 'fleet_card', 'debit']:
                    treatment = 'expense'
                else:
                    treatment = 'accounts_payable'
            
            # Store the receipt image
            receipt_id = str(uuid.uuid4())
            receipt_record = {
                "id": receipt_id,
                "company_id": current_user.id,
                "filename": file.filename or f"receipt_{receipt_id}.{file_extension}",
                "content_type": content_type,
                "image_base64": base64_image,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "uploaded_by": current_user.id
            }
            await db.receipt_images.insert_one(receipt_record)
            
            # Create the appropriate entry based on AI decision
            entry_created = None
            entry_type = None
            
            if treatment == 'expense':
                # Create Expense entry (for already paid items)
                expense_entry = {
                    "id": str(uuid.uuid4()),
                    "company_id": current_user.id,
                    "vendor_name": parsed_data.get('vendor_name') or 'Unknown Vendor',
                    "expense_date": parsed_data.get('expense_date') or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "amount": parsed_data.get('amount') or 0,
                    "category": category,
                    "receipt_number": parsed_data.get('receipt_number'),
                    "description": parsed_data.get('description'),
                    "payment_method": parsed_data.get('payment_method'),
                    "driver_name": parsed_data.get('driver_name'),
                    "vehicle_name": parsed_data.get('vehicle_number'),
                    "line_items": parsed_data.get('line_items') or [],
                    "receipt_id": receipt_id,
                    "receipt_image_url": f"/api/accounting/receipts/{receipt_id}/image",
                    "status": "pending",  # Goes to expense ledger for approval
                    "ai_treatment": treatment,
                    "ai_treatment_reason": parsed_data.get('treatment_reason'),
                    "created_by": current_user.id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                await db.expenses.insert_one(expense_entry)
                entry_created = expense_entry
                entry_type = "expense"
                
            else:
                # Create Accounts Payable entry (for unpaid invoices)
                bill_number = f"BILL-{parsed_data.get('receipt_number') or str(uuid.uuid4())[:8].upper()}"
                due_date = parsed_data.get('due_date') or (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
                
                ap_entry = {
                    "id": str(uuid.uuid4()),
                    "company_id": current_user.id,
                    "vendor_name": parsed_data.get('vendor_name') or 'Unknown Vendor',
                    "vendor_email": "",
                    "bill_number": bill_number,
                    "amount": parsed_data.get('amount') or 0,
                    "amount_paid": 0,
                    "due_date": due_date,
                    "description": parsed_data.get('description') or f"{category.replace('_', ' ').title()} - {parsed_data.get('vendor_name')}",
                    "category": category,
                    "receipt_id": receipt_id,
                    "receipt_image_url": f"/api/accounting/receipts/{receipt_id}/image",
                    "status": "pending",
                    "ai_treatment": treatment,
                    "ai_treatment_reason": parsed_data.get('treatment_reason'),
                    "created_by": current_user.id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "auto_generated": True,
                    "source": "receipt_ai"
                }
                await db.accounts_payable.insert_one(ap_entry)
                entry_created = ap_entry
                entry_type = "accounts_payable"
            
            # Remove _id from response
            if entry_created:
                entry_created.pop("_id", None)
            
            return {
                "success": True,
                "parsed_data": parsed_data,
                "ai_decision": {
                    "treatment": treatment,
                    "reason": parsed_data.get('treatment_reason', 'Based on payment indicators on receipt'),
                    "entry_type": entry_type
                },
                "entry_created": entry_created,
                "receipt_id": receipt_id,
                "receipt_url": f"/api/accounting/receipts/{receipt_id}/image",
                "message": f"Receipt processed and {'Expense' if treatment == 'expense' else 'AP Bill'} entry created successfully!"
            }
            
        except ImportError as e:
            raise HTTPException(
                status_code=500, 
                detail=f"AI integration not configured: {str(e)}"
            )
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse AI response: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process receipt: {str(e)}")


@router.get("/receipts/{receipt_id}/image")
async def get_receipt_image(
    receipt_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get receipt image by ID"""
    from fastapi.responses import Response
    
    receipt = await db.receipt_images.find_one({
        "id": receipt_id,
        "company_id": current_user.id
    })
    
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt image not found")
    
    image_data = base64.b64decode(receipt.get("image_base64", ""))
    content_type = receipt.get("content_type", "image/jpeg")
    
    return Response(content=image_data, media_type=content_type)


@router.post("/parse-receipt")
async def parse_receipt(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Parse receipt image using AI to extract expense data (preview only, no entry created)"""
    try:
        # Read the file
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode('utf-8')
        
        # Determine mime type
        content_type = file.content_type or 'image/jpeg'
        
        # Use OpenAI Vision API to parse the receipt
        try:
            try:
                from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
            except ImportError:
                raise HTTPException(
                    status_code=503,
                    detail="Receipt parsing requires emergentintegrations package (not installed)."
                )
            import os
            import json
            import re
            
            # Get the Emergent LLM key
            emergent_key = os.environ.get('EMERGENT_LLM_KEY', 'sk-emergent-73b04E1E4779758EfC')
            
            # Initialize chat with GPT-4o for vision
            chat = LlmChat(
                api_key=emergent_key,
                session_id=f"receipt-preview-{str(uuid.uuid4())[:8]}",
                system_message="You are an expert at parsing trucking and transportation expense receipts."
            ).with_model("openai", "gpt-4o")
            
            prompt = """Analyze this receipt/invoice image for a trucking/transport company.
            Extract the following information in JSON format:
            {
                "vendor_name": "Name of the vendor/business on the receipt",
                "amount": 0.00,
                "expense_date": "YYYY-MM-DD",
                "receipt_number": "Receipt/Invoice number if visible",
                "description": "Brief description of items/services purchased",
                "category": "fuel/repairs_maintenance/tires/parts_supplies/tolls/permits_licenses/parking/driver_meals/lodging/scale_fees/lumper_fees/detention_fees/insurance/other",
                "payment_method": "cash/card/check/fleet_card/ach/credit/other",
                "payment_status": "paid/unpaid",
                "treatment": "expense/accounts_payable",
                "treatment_reason": "Why this treatment was chosen",
                "line_items": [{"description": "item", "quantity": 1, "unit_price": 0.00, "total": 0.00}],
                "gallons": null,
                "price_per_gallon": null,
                "vehicle_number": null,
                "driver_name": null,
                "due_date": null
            }
            
            TREATMENT RULES:
            - "PAID", cash/card receipts → treatment: "expense"
            - "INVOICE", "DUE DATE", "NET 30" → treatment: "accounts_payable"
            
            Return ONLY valid JSON."""
            
            # Create image content and send
            image_content = ImageContent(image_base64=base64_image)
            user_message = UserMessage(text=prompt, file_contents=[image_content])
            response = await chat.send_message(user_message)
            
            # Parse response
            response_text = response.strip()
            if response_text.startswith('```'):
                response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
                response_text = re.sub(r'\s*```$', '', response_text)
            
            parsed_data = json.loads(response_text)
            
            # Validate category
            category = parsed_data.get('category', 'other')
            if category not in EXPENSE_CATEGORIES:
                category = 'other'
            parsed_data['category'] = category
            
            return {
                "parsed_data": parsed_data,
                "ai_decision": {
                    "treatment": parsed_data.get('treatment', 'expense'),
                    "reason": parsed_data.get('treatment_reason', 'Based on receipt analysis')
                },
                "message": "Receipt parsed. Review and confirm to create entry."
            }
            
        except ImportError as e:
            raise HTTPException(status_code=500, detail=f"AI integration error: {str(e)}")
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process receipt: {str(e)}")


class ReceiptConfirmation(BaseModel):
    """Model for confirming AI-parsed receipt and creating entry"""
    treatment: str  # 'expense' or 'accounts_payable'
    vendor_name: str
    amount: float
    expense_date: Optional[str] = None
    due_date: Optional[str] = None
    receipt_number: Optional[str] = None
    bill_number: Optional[str] = None
    description: Optional[str] = None
    category: str = "other"
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    line_items: Optional[List[dict]] = None
    # Optional linking
    load_reference: Optional[str] = None
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    vehicle_id: Optional[str] = None
    vehicle_name: Optional[str] = None
    # Receipt image
    receipt_image_url: Optional[str] = None
    # AI decision context
    ai_treatment_reason: Optional[str] = None


@router.post("/confirm-receipt")
async def confirm_receipt_entry(
    data: ReceiptConfirmation,
    current_user: User = Depends(get_current_user)
):
    """
    Confirm AI-parsed receipt and create appropriate entry.
    Based on treatment, creates either:
    - Expense entry (for paid receipts)
    - Accounts Payable entry (for unpaid invoices/bills)
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        
        if data.treatment == "expense":
            # Create expense entry
            expense = {
                "id": str(uuid.uuid4()),
                "company_id": current_user.id,
                "vendor_name": data.vendor_name,
                "expense_date": data.expense_date or now[:10],
                "amount": data.amount,
                "category": data.category if data.category in EXPENSE_CATEGORIES else "other",
                "receipt_number": data.receipt_number,
                "description": data.description,
                "payment_method": data.payment_method,
                "load_reference": data.load_reference,
                "driver_id": data.driver_id,
                "driver_name": data.driver_name,
                "vehicle_id": data.vehicle_id,
                "vehicle_name": data.vehicle_name,
                "line_items": data.line_items or [],
                "receipt_image_url": data.receipt_image_url,
                "status": "pending",  # Starts as pending for approval workflow
                "source": "ai_receipt_scan",
                "ai_classification": {
                    "treatment": data.treatment,
                    "reason": data.ai_treatment_reason
                },
                "created_by": current_user.id,
                "created_at": now,
                "updated_at": now
            }
            
            await db.expenses.insert_one(expense)
            expense.pop("_id", None)
            
            return {
                "success": True,
                "entry_type": "expense",
                "message": "Expense entry created successfully from receipt",
                "entry": expense
            }
            
        elif data.treatment == "accounts_payable":
            # Generate bill number if not provided
            bill_number = data.bill_number or data.receipt_number or f"BILL-{str(uuid.uuid4())[:8].upper()}"
            
            # Check for duplicate bill number
            existing = await db.accounts_payable.find_one({
                "bill_number": bill_number,
                "company_id": current_user.id
            })
            if existing:
                # Append random suffix to make unique
                bill_number = f"{bill_number}-{str(uuid.uuid4())[:4].upper()}"
            
            # Calculate due date if not provided (default 30 days from now)
            if not data.due_date:
                due_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
            else:
                due_date = data.due_date
            
            payable = {
                "id": str(uuid.uuid4()),
                "company_id": current_user.id,
                "vendor_name": data.vendor_name,
                "vendor_email": None,
                "bill_number": bill_number,
                "amount": data.amount,
                "amount_paid": 0,
                "due_date": due_date,
                "description": data.description,
                "category": data.category if data.category in EXPENSE_CATEGORIES else "other",
                "load_reference": data.load_reference,
                "line_items": data.line_items or [],
                "receipt_image_url": data.receipt_image_url,
                "status": "pending",
                "source": "ai_receipt_scan",
                "ai_classification": {
                    "treatment": data.treatment,
                    "reason": data.ai_treatment_reason
                },
                "created_by": current_user.id,
                "created_at": now,
                "updated_at": now
            }
            
            await db.accounts_payable.insert_one(payable)
            payable.pop("_id", None)
            
            return {
                "success": True,
                "entry_type": "accounts_payable",
                "message": "Accounts Payable entry created successfully from invoice",
                "entry": payable
            }
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid treatment type: {data.treatment}. Must be 'expense' or 'accounts_payable'"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create entry: {str(e)}")


# ==================== NOTIFICATIONS & ALERTS ====================

class NotificationAlert(BaseModel):
    id: str
    type: str  # 'overdue_ar', 'upcoming_ap', 'payment_due', 'collection_reminder'
    priority: str  # 'high', 'medium', 'low'
    title: str
    message: str
    amount: float
    due_date: str
    days_overdue: int = 0
    related_id: str
    related_type: str  # 'ar' or 'ap'
    created_at: str

@router.get("/alerts")
async def get_accounting_alerts(
    current_user: User = Depends(get_current_user)
):
    """Get notifications and alerts for overdue invoices and upcoming payments"""
    company_id = current_user.id
    today = datetime.now(timezone.utc)
    alerts = []
    
    def parse_due_date(date_val):
        """Parse due date from various formats"""
        if date_val is None:
            return None
        if isinstance(date_val, datetime):
            return date_val.replace(tzinfo=timezone.utc) if date_val.tzinfo is None else date_val
        if isinstance(date_val, str):
            # Try simple date format first YYYY-MM-DD
            try:
                return datetime.strptime(date_val[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except:
                pass
            # Try ISO format with timezone
            try:
                dt = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
                return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
            except:
                pass
        return None
    
    # 1. Overdue AR (invoices past due date)
    overdue_ar = await db.accounts_receivable.find({
        "company_id": company_id,
        "status": {"$nin": ["paid", "cancelled"]}
    }, {"_id": 0}).to_list(1000)
    
    for ar in overdue_ar:
        try:
            due_date = parse_due_date(ar.get("due_date"))
            if not due_date:
                continue
            
            days_overdue = (today - due_date).days
            
            if days_overdue > 0:
                priority = "high" if days_overdue > 30 else ("medium" if days_overdue > 14 else "low")
                alerts.append(NotificationAlert(
                    id=str(uuid.uuid4()),
                    type="overdue_ar",
                    priority=priority,
                    title=f"Overdue Invoice: {ar.get('invoice_number')}",
                    message=f"Invoice from {ar.get('customer_name')} is {days_overdue} days overdue. Outstanding: ${(ar.get('amount', 0) - ar.get('amount_paid', 0)):,.2f}",
                    amount=ar.get('amount', 0) - ar.get('amount_paid', 0),
                    due_date=ar.get('due_date'),
                    days_overdue=days_overdue,
                    related_id=ar.get('id'),
                    related_type="ar",
                    created_at=today.isoformat()
                ))
        except Exception as e:
            continue
    
    # 2. Upcoming AP (bills due within 7 days)
    upcoming_ap = await db.accounts_payable.find({
        "company_id": company_id,
        "status": {"$nin": ["paid", "cancelled"]}
    }, {"_id": 0}).to_list(1000)
    
    for ap in upcoming_ap:
        try:
            due_date = parse_due_date(ap.get("due_date"))
            if not due_date:
                continue
            
            days_until = (due_date - today).days
            
            if days_until <= 7 and days_until >= 0:
                priority = "high" if days_until <= 2 else ("medium" if days_until <= 5 else "low")
                alerts.append(NotificationAlert(
                    id=str(uuid.uuid4()),
                    type="upcoming_ap",
                    priority=priority,
                    title=f"Payment Due Soon: {ap.get('bill_number')}",
                    message=f"Payment to {ap.get('vendor_name')} is due in {days_until} days. Amount: ${(ap.get('amount', 0) - ap.get('amount_paid', 0)):,.2f}",
                    amount=ap.get('amount', 0) - ap.get('amount_paid', 0),
                    due_date=ap.get('due_date'),
                    days_overdue=-days_until,  # Negative means future
                    related_id=ap.get('id'),
                    related_type="ap",
                    created_at=today.isoformat()
                ))
            elif days_until < 0:
                # Overdue AP
                days_overdue = abs(days_until)
                priority = "high"
                alerts.append(NotificationAlert(
                    id=str(uuid.uuid4()),
                    type="overdue_ap",
                    priority=priority,
                    title=f"Overdue Payment: {ap.get('bill_number')}",
                    message=f"Payment to {ap.get('vendor_name')} is {days_overdue} days overdue! Amount: ${(ap.get('amount', 0) - ap.get('amount_paid', 0)):,.2f}",
                    amount=ap.get('amount', 0) - ap.get('amount_paid', 0),
                    due_date=ap.get('due_date'),
                    days_overdue=days_overdue,
                    related_id=ap.get('id'),
                    related_type="ap",
                    created_at=today.isoformat()
                ))
        except Exception as e:
            continue
    
    # 3. Collection reminders (AR with partial payment but not fully paid after 60+ days)
    for ar in overdue_ar:
        try:
            due_date = parse_due_date(ar.get("due_date"))
            if not due_date:
                continue
            
            days_overdue = (today - due_date).days
            amount_paid = ar.get('amount_paid', 0) or 0
            total_amount = ar.get('amount', 0)
            
            if days_overdue > 60 and amount_paid > 0 and amount_paid < total_amount:
                alerts.append(NotificationAlert(
                    id=str(uuid.uuid4()),
                    type="collection_reminder",
                    priority="high",
                    title=f"Collection Follow-up: {ar.get('invoice_number')}",
                    message=f"Partial payment received from {ar.get('customer_name')} but ${(total_amount - amount_paid):,.2f} still outstanding after {days_overdue} days.",
                    amount=total_amount - amount_paid,
                    due_date=ar.get('due_date'),
                    days_overdue=days_overdue,
                    related_id=ar.get('id'),
                    related_type="ar",
                    created_at=today.isoformat()
                ))
        except Exception as e:
            continue
    
    # Sort alerts by priority (high first) and days_overdue
    priority_order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda x: (priority_order.get(x.priority, 3), -x.days_overdue))
    
    # Summary stats
    high_priority = sum(1 for a in alerts if a.priority == "high")
    medium_priority = sum(1 for a in alerts if a.priority == "medium")
    low_priority = sum(1 for a in alerts if a.priority == "low")
    
    total_ar_overdue = sum(a.amount for a in alerts if a.type in ["overdue_ar", "collection_reminder"])
    total_ap_upcoming = sum(a.amount for a in alerts if a.type in ["upcoming_ap", "overdue_ap"])
    
    return {
        "alerts": [a.dict() for a in alerts],
        "summary": {
            "total_alerts": len(alerts),
            "high_priority": high_priority,
            "medium_priority": medium_priority,
            "low_priority": low_priority,
            "total_ar_overdue": total_ar_overdue,
            "total_ap_upcoming": total_ap_upcoming
        }
    }

@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user)
):
    """Dismiss an alert (mark as read/acknowledged)"""
    # Store dismissed alerts in the database
    dismissed_alert = {
        "id": str(uuid.uuid4()),
        "alert_id": alert_id,
        "user_id": current_user.id,
        "dismissed_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.dismissed_alerts.insert_one(dismissed_alert)
    
    return {"message": "Alert dismissed", "alert_id": alert_id}
