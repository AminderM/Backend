"""
Invoice Routes - Phase 5
Invoice generation, PDF export, payment tracking
Canadian tax compliance with GST/HST/PST/QST
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
from datetime import datetime, timezone, date, timedelta
from models import User
from models_invoices import (
    Invoice, InvoiceCreate, InvoiceUpdate, InvoiceResponse,
    InvoiceStatus, InvoiceType, InvoiceLineItem,
    PaymentCreate, Payment, PaymentMethod,
    ARSummary,
    calculate_due_date, is_invoice_overdue, get_days_overdue, get_aging_bucket
)
from models_master_data import calculate_canadian_tax, CANADIAN_TAX_RATES
from services.pdf_generator import generate_invoice_pdf
from auth import (
    get_current_user,
    require_admin,
    require_billing,
    is_platform_admin,
    is_billing_user,
    check_tenant_access
)
from database import db
from io import BytesIO

router = APIRouter(tags=["Invoices"])


# =============================================================================
# INVOICE CRUD ENDPOINTS
# =============================================================================

@router.post("/invoices", response_model=dict)
async def create_invoice(
    data: InvoiceCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new invoice
    Automatically calculates taxes based on customer province
    """
    # Check tenant access
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant != data.tenant_id:
            raise HTTPException(status_code=403, detail="Cannot create invoice for another tenant")
    
    # Get customer info
    customer = await db.customers.find_one({"id": data.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Prepare invoice data - exclude line_items and override customer fields
    invoice_data = data.dict(exclude={'line_items'})
    invoice_data['customer_name'] = customer.get('company_name')
    invoice_data['customer_email'] = customer.get('contact_email')
    invoice_data['created_by'] = current_user.id
    
    # Create invoice
    invoice = Invoice(**invoice_data)
    
    # Set billing address from customer if not provided
    if not data.billing_address_line1:
        billing_addr = customer.get('billing_address', {})
        if billing_addr:
            invoice.billing_address_line1 = billing_addr.get('address_line1')
            invoice.billing_address_line2 = billing_addr.get('address_line2')
            invoice.billing_city = billing_addr.get('city')
            invoice.billing_province = billing_addr.get('state_province')
            invoice.billing_postal_code = billing_addr.get('postal_code')
            invoice.billing_country = billing_addr.get('country', 'CA')
    
    # Calculate due date
    if not data.due_date:
        invoice.due_date = calculate_due_date(invoice.invoice_date, invoice.payment_terms_days)
    
    # Process line items and calculate totals
    subtotal = 0.0
    line_items = []
    
    for idx, item in enumerate(data.line_items):
        item.sequence = idx + 1
        item.calculate_total()
        line_items.append(item)
        if item.is_taxable:
            subtotal += item.line_total
    
    invoice.line_items = line_items
    invoice.subtotal = round(subtotal, 2)
    
    # Calculate tax
    tax_province = customer.get('tax_province') or invoice.billing_province
    invoice.tax_province = tax_province
    invoice.is_tax_exempt = customer.get('is_tax_exempt', False)
    invoice.tax_exemption_number = customer.get('tax_exemption_number')
    
    if not invoice.is_tax_exempt and tax_province and tax_province.upper() in CANADIAN_TAX_RATES:
        tax_calc = calculate_canadian_tax(subtotal, tax_province)
        invoice.gst_rate = tax_calc.gst_rate
        invoice.gst_amount = tax_calc.gst_amount
        invoice.pst_rate = tax_calc.pst_rate
        invoice.pst_amount = tax_calc.pst_amount
        invoice.hst_rate = tax_calc.hst_rate
        invoice.hst_amount = tax_calc.hst_amount
        invoice.qst_rate = tax_calc.qst_rate
        invoice.qst_amount = tax_calc.qst_amount
        invoice.total_tax = tax_calc.total_tax_amount
        invoice.grand_total = tax_calc.grand_total
    else:
        invoice.total_tax = 0
        invoice.grand_total = subtotal
    
    invoice.balance_due = invoice.grand_total
    
    # Convert to dict for MongoDB
    doc = invoice.dict()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['invoice_date'] = doc['invoice_date'].isoformat()
    if doc.get('due_date'):
        doc['due_date'] = doc['due_date'].isoformat()
    
    await db.invoices.insert_one(doc)
    
    # Update related orders as invoiced
    if data.order_ids:
        await db.orders.update_many(
            {"id": {"$in": data.order_ids}},
            {"$set": {
                "status": "invoiced",
                "invoice_id": invoice.id,
                "invoiced_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    
    return {
        "message": "Invoice created successfully",
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "subtotal": invoice.subtotal,
        "total_tax": invoice.total_tax,
        "grand_total": invoice.grand_total
    }


@router.post("/invoices/from-orders", response_model=dict)
async def create_invoice_from_orders(
    tenant_id: str,
    customer_id: str,
    order_ids: List[str] = Query(..., description="Order IDs to invoice"),
    current_user: User = Depends(get_current_user)
):
    """
    Create an invoice from one or more orders
    Automatically pulls line items from orders
    """
    # Verify customer
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get orders
    orders = await db.orders.find(
        {"id": {"$in": order_ids}, "customer_id": customer_id},
        {"_id": 0}
    ).to_list(length=100)
    
    if not orders:
        raise HTTPException(status_code=404, detail="No orders found")
    
    # Check if any orders already invoiced
    invoiced_orders = [o for o in orders if o.get('status') == 'invoiced']
    if invoiced_orders:
        raise HTTPException(
            status_code=400,
            detail=f"Orders already invoiced: {[o.get('order_number') for o in invoiced_orders]}"
        )
    
    # Build line items from orders
    line_items = []
    total_amount = 0
    
    for order in orders:
        # Main freight charge
        customer_rate = order.get('customer_rate', 0) or 0
        if customer_rate > 0:
            line_item = InvoiceLineItem(
                description=f"Freight - {order.get('commodity', 'General Freight')}",
                item_type="freight",
                order_id=order.get('id'),
                order_number=order.get('order_number'),
                origin=f"{order.get('origin_city', '')}, {order.get('origin_state_province', '')}",
                destination=f"{order.get('destination_city', '')}, {order.get('destination_state_province', '')}",
                pickup_date=order.get('requested_pickup_date'),
                delivery_date=order.get('requested_delivery_date'),
                quantity=1,
                unit_price=customer_rate,
                unit="load"
            )
            line_item.calculate_total()
            line_items.append(line_item)
            total_amount += line_item.line_total
        
        # Fuel surcharge
        fuel_surcharge = order.get('fuel_surcharge', 0) or 0
        if fuel_surcharge > 0:
            fuel_item = InvoiceLineItem(
                description=f"Fuel Surcharge - {order.get('order_number')}",
                item_type="fuel_surcharge",
                order_id=order.get('id'),
                order_number=order.get('order_number'),
                quantity=1,
                unit_price=fuel_surcharge,
                unit="flat"
            )
            fuel_item.calculate_total()
            line_items.append(fuel_item)
            total_amount += fuel_item.line_total
        
        # Accessorials
        for acc in order.get('accessorials', []):
            acc_item = InvoiceLineItem(
                description=f"{acc.get('description', 'Accessorial')} - {order.get('order_number')}",
                item_type="accessorial",
                order_id=order.get('id'),
                order_number=order.get('order_number'),
                quantity=1,
                unit_price=acc.get('amount', 0),
                unit="flat"
            )
            acc_item.calculate_total()
            line_items.append(acc_item)
            total_amount += acc_item.line_total
    
    # Create invoice data
    invoice_data = InvoiceCreate(
        tenant_id=tenant_id,
        customer_id=customer_id,
        invoice_type=InvoiceType.STANDARD,
        order_ids=order_ids,
        line_items=line_items
    )
    
    # Use the create_invoice function
    return await create_invoice(invoice_data, current_user)


@router.get("/invoices", response_model=List[dict])
async def list_invoices(
    status: Optional[InvoiceStatus] = None,
    customer_id: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    overdue_only: bool = False,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List invoices with filtering"""
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
        query["invoice_date"] = {"$gte": from_date.isoformat()}
    
    if to_date:
        if "invoice_date" in query:
            query["invoice_date"]["$lte"] = to_date.isoformat()
        else:
            query["invoice_date"] = {"$lte": to_date.isoformat()}
    
    if overdue_only:
        today = date.today().isoformat()
        query["due_date"] = {"$lt": today}
        query["status"] = {"$nin": ["paid", "cancelled", "written_off"]}
    
    invoices = await db.invoices.find(query, {"_id": 0}).sort("invoice_date", -1).skip(skip).limit(limit).to_list(length=limit)
    
    # Add computed fields
    for inv in invoices:
        due_date = inv.get('due_date')
        if due_date:
            if isinstance(due_date, str):
                due_date = date.fromisoformat(due_date)
            inv['is_overdue'] = is_invoice_overdue(due_date, InvoiceStatus(inv.get('status', 'draft')))
            inv['days_overdue'] = get_days_overdue(due_date) if inv['is_overdue'] else 0
    
    return invoices


@router.get("/invoices/{invoice_id}", response_model=dict)
async def get_invoice(
    invoice_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific invoice with full details"""
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if not check_tenant_access(current_user, invoice.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get customer details
    customer = await db.customers.find_one(
        {"id": invoice.get("customer_id")},
        {"_id": 0, "id": 1, "company_name": 1, "contact_email": 1}
    )
    
    # Add computed fields
    due_date = invoice.get('due_date')
    if due_date:
        if isinstance(due_date, str):
            due_date = date.fromisoformat(due_date)
        invoice['is_overdue'] = is_invoice_overdue(due_date, InvoiceStatus(invoice.get('status', 'draft')))
        invoice['days_overdue'] = get_days_overdue(due_date) if invoice['is_overdue'] else 0
        invoice['aging_bucket'] = get_aging_bucket(invoice.get('days_overdue', 0))
    
    return {
        **invoice,
        "customer": customer
    }


@router.put("/invoices/{invoice_id}", response_model=dict)
async def update_invoice(
    invoice_id: str,
    data: InvoiceUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update an invoice"""
    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if not check_tenant_access(current_user, invoice.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Don't allow editing paid or cancelled invoices
    if invoice.get('status') in ['paid', 'cancelled', 'written_off']:
        raise HTTPException(status_code=400, detail=f"Cannot edit invoice with status: {invoice.get('status')}")
    
    # Build update dict
    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = current_user.id
    
    # Handle date fields
    if 'invoice_date' in update_data and update_data['invoice_date']:
        update_data['invoice_date'] = update_data['invoice_date'].isoformat()
    if 'due_date' in update_data and update_data['due_date']:
        update_data['due_date'] = update_data['due_date'].isoformat()
    
    await db.invoices.update_one({"id": invoice_id}, {"$set": update_data})
    
    return {"message": "Invoice updated successfully", "id": invoice_id}


@router.post("/invoices/{invoice_id}/send", response_model=dict)
async def send_invoice(
    invoice_id: str,
    email: Optional[str] = Query(None, description="Override email address"),
    current_user: User = Depends(get_current_user)
):
    """Mark invoice as sent (email integration can be added later)"""
    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if not check_tenant_access(current_user, invoice.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    recipient_email = email or invoice.get('customer_email')
    if not recipient_email:
        raise HTTPException(status_code=400, detail="No email address available")
    
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "sent_to": recipient_email,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        "message": "Invoice marked as sent",
        "id": invoice_id,
        "sent_to": recipient_email
    }


@router.post("/invoices/{invoice_id}/cancel", response_model=dict)
async def cancel_invoice(
    invoice_id: str,
    reason: str = Query(None, description="Cancellation reason"),
    current_user: User = Depends(require_billing)
):
    """Cancel an invoice"""
    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if not check_tenant_access(current_user, invoice.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if invoice.get('status') in ['paid']:
        raise HTTPException(status_code=400, detail="Cannot cancel a paid invoice")
    
    if invoice.get('amount_paid', 0) > 0:
        raise HTTPException(status_code=400, detail="Cannot cancel invoice with payments. Create a credit note instead.")
    
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {
            "status": "cancelled",
            "internal_notes": f"{invoice.get('internal_notes', '')} | CANCELLED: {reason or 'No reason'}",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": current_user.id
        }}
    )
    
    # Update related orders
    if invoice.get('order_ids'):
        await db.orders.update_many(
            {"id": {"$in": invoice.get('order_ids')}},
            {"$set": {
                "status": "completed",  # Revert to completed
                "invoice_id": None,
                "invoiced_at": None
            }}
        )
    
    return {"message": "Invoice cancelled", "id": invoice_id}


# =============================================================================
# PAYMENT ENDPOINTS
# =============================================================================

@router.post("/invoices/{invoice_id}/payments", response_model=dict)
async def record_payment(
    invoice_id: str,
    data: PaymentCreate,
    current_user: User = Depends(get_current_user)
):
    """Record a payment against an invoice"""
    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if not check_tenant_access(current_user, invoice.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if invoice.get('status') in ['cancelled', 'written_off']:
        raise HTTPException(status_code=400, detail=f"Cannot record payment for {invoice.get('status')} invoice")
    
    # Create payment record
    payment = Payment(
        invoice_id=invoice_id,
        amount=data.amount,
        payment_method=data.payment_method,
        payment_date=data.payment_date,
        reference_number=data.reference_number,
        notes=data.notes,
        recorded_by=current_user.id
    )
    
    # Calculate new totals
    current_paid = invoice.get('amount_paid', 0)
    new_paid = current_paid + data.amount
    new_balance = invoice.get('grand_total', 0) - new_paid
    
    # Determine new status
    new_status = invoice.get('status')
    if new_balance <= 0:
        new_status = 'paid'
    elif new_paid > 0:
        new_status = 'partially_paid'
    
    # Update invoice
    payment_record = payment.dict()
    payment_record['payment_date'] = payment_record['payment_date'].isoformat()
    payment_record['recorded_at'] = payment_record['recorded_at'].isoformat()
    
    await db.invoices.update_one(
        {"id": invoice_id},
        {
            "$set": {
                "amount_paid": round(new_paid, 2),
                "balance_due": round(max(0, new_balance), 2),
                "status": new_status,
                "paid_at": datetime.now(timezone.utc).isoformat() if new_status == 'paid' else None,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$push": {"payments": payment_record}
        }
    )
    
    # Update related orders if fully paid
    if new_status == 'paid' and invoice.get('order_ids'):
        await db.orders.update_many(
            {"id": {"$in": invoice.get('order_ids')}},
            {"$set": {"status": "paid"}}
        )
    
    return {
        "message": "Payment recorded successfully",
        "payment_id": payment.id,
        "amount": data.amount,
        "new_balance": round(max(0, new_balance), 2),
        "status": new_status
    }


@router.get("/invoices/{invoice_id}/payments", response_model=List[dict])
async def get_invoice_payments(
    invoice_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get payment history for an invoice"""
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0, "tenant_id": 1, "payments": 1})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if not check_tenant_access(current_user, invoice.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return invoice.get('payments', [])


# =============================================================================
# PDF GENERATION ENDPOINTS
# =============================================================================

@router.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Generate and download invoice as PDF
    Returns the PDF file directly
    """
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if not check_tenant_access(current_user, invoice.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get company info for header
    tenant_id = invoice.get('tenant_id')
    company = await db.companies.find_one({"id": tenant_id}, {"_id": 0})
    
    company_info = {
        "company_name": company.get('name', 'Your Company') if company else 'Your Company',
        "address_line1": company.get('address', '') if company else '',
        "city": company.get('city', '') if company else '',
        "province": company.get('province', '') if company else '',
        "postal_code": company.get('postal_code', '') if company else '',
        "phone": company.get('phone', '') if company else '',
        "email": company.get('company_email', '') if company else '',
        "gst_number": company.get('gst_number', '') if company else '',
    }
    
    # Generate PDF
    try:
        pdf_buffer = generate_invoice_pdf(invoice, company_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
    
    # Update invoice with PDF generation timestamp
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"pdf_generated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    # Return PDF as downloadable file
    filename = f"Invoice_{invoice.get('invoice_number', invoice_id)}.pdf"
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/invoices/{invoice_id}/pdf/preview")
async def preview_invoice_pdf(
    invoice_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Preview invoice PDF in browser (inline display)
    """
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if not check_tenant_access(current_user, invoice.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get company info
    tenant_id = invoice.get('tenant_id')
    company = await db.companies.find_one({"id": tenant_id}, {"_id": 0})
    
    company_info = {
        "company_name": company.get('name', 'Your Company') if company else 'Your Company',
        "address_line1": company.get('address', '') if company else '',
        "city": company.get('city', '') if company else '',
        "province": company.get('province', '') if company else '',
        "postal_code": company.get('postal_code', '') if company else '',
        "phone": company.get('phone', '') if company else '',
        "email": company.get('company_email', '') if company else '',
        "gst_number": company.get('gst_number', '') if company else '',
    }
    
    # Generate PDF
    try:
        pdf_buffer = generate_invoice_pdf(invoice, company_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
    
    # Return PDF for inline viewing
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline"
        }
    )


# =============================================================================
# ACCOUNTS RECEIVABLE REPORTS
# =============================================================================

@router.get("/invoices/reports/ar-summary", response_model=ARSummary)
async def get_ar_summary(
    customer_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get Accounts Receivable summary with aging buckets"""
    query = {"status": {"$nin": ["cancelled", "written_off", "paid"]}}
    
    # Tenant isolation
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    if customer_id:
        query["customer_id"] = customer_id
    
    invoices = await db.invoices.find(query, {"_id": 0}).to_list(length=1000)
    
    # Calculate aging
    today = date.today()
    current = 0
    days_1_30 = 0
    days_31_60 = 0
    days_61_90 = 0
    days_90_plus = 0
    overdue_count = 0
    
    for inv in invoices:
        balance = inv.get('balance_due', 0)
        due_date = inv.get('due_date')
        
        if due_date:
            if isinstance(due_date, str):
                due_date = date.fromisoformat(due_date)
            
            days_overdue = (today - due_date).days
            
            if days_overdue <= 0:
                current += balance
            elif days_overdue <= 30:
                days_1_30 += balance
                overdue_count += 1
            elif days_overdue <= 60:
                days_31_60 += balance
                overdue_count += 1
            elif days_overdue <= 90:
                days_61_90 += balance
                overdue_count += 1
            else:
                days_90_plus += balance
                overdue_count += 1
        else:
            current += balance
    
    total = current + days_1_30 + days_31_60 + days_61_90 + days_90_plus
    
    return ARSummary(
        total_outstanding=round(total, 2),
        current=round(current, 2),
        days_1_30=round(days_1_30, 2),
        days_31_60=round(days_31_60, 2),
        days_61_90=round(days_61_90, 2),
        days_90_plus=round(days_90_plus, 2),
        total_invoices=len(invoices),
        overdue_invoices=overdue_count
    )


@router.get("/invoices/reports/ar-aging", response_model=List[dict])
async def get_ar_aging_detail(
    customer_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get detailed AR aging report by customer"""
    query = {"status": {"$nin": ["cancelled", "written_off", "paid"]}}
    
    # Tenant isolation
    if not is_platform_admin(current_user):
        user_tenant = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'company_id', None)
        if user_tenant:
            query["tenant_id"] = user_tenant
    
    if customer_id:
        query["customer_id"] = customer_id
    
    invoices = await db.invoices.find(query, {"_id": 0}).to_list(length=1000)
    
    # Group by customer
    customer_aging = {}
    today = date.today()
    
    for inv in invoices:
        cust_id = inv.get('customer_id')
        cust_name = inv.get('customer_name', 'Unknown')
        
        if cust_id not in customer_aging:
            customer_aging[cust_id] = {
                "customer_id": cust_id,
                "customer_name": cust_name,
                "current": 0,
                "days_1_30": 0,
                "days_31_60": 0,
                "days_61_90": 0,
                "days_90_plus": 0,
                "total": 0,
                "invoice_count": 0
            }
        
        balance = inv.get('balance_due', 0)
        due_date = inv.get('due_date')
        
        if due_date:
            if isinstance(due_date, str):
                due_date = date.fromisoformat(due_date)
            
            days_overdue = (today - due_date).days
            
            if days_overdue <= 0:
                customer_aging[cust_id]["current"] += balance
            elif days_overdue <= 30:
                customer_aging[cust_id]["days_1_30"] += balance
            elif days_overdue <= 60:
                customer_aging[cust_id]["days_31_60"] += balance
            elif days_overdue <= 90:
                customer_aging[cust_id]["days_61_90"] += balance
            else:
                customer_aging[cust_id]["days_90_plus"] += balance
        else:
            customer_aging[cust_id]["current"] += balance
        
        customer_aging[cust_id]["total"] += balance
        customer_aging[cust_id]["invoice_count"] += 1
    
    # Sort by total outstanding (descending)
    result = sorted(customer_aging.values(), key=lambda x: x['total'], reverse=True)
    
    return result
