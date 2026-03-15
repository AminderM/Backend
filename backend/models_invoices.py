"""
TMS Invoice Models - Phase 5
Invoice generation with Canadian tax compliance
PDF export with professional formatting
"""

from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone, date, timedelta
import uuid


# =============================================================================
# ENUMS - Invoice Status & Types
# =============================================================================

class InvoiceStatus(str, Enum):
    """Status of an invoice"""
    DRAFT = "draft"                      # Being created
    PENDING = "pending"                  # Ready to send
    SENT = "sent"                        # Sent to customer
    VIEWED = "viewed"                    # Customer viewed
    PARTIALLY_PAID = "partially_paid"   # Partial payment received
    PAID = "paid"                        # Fully paid
    OVERDUE = "overdue"                  # Past due date
    DISPUTED = "disputed"                # Customer disputed
    CANCELLED = "cancelled"              # Invoice cancelled
    WRITTEN_OFF = "written_off"          # Bad debt


class InvoiceType(str, Enum):
    """Type of invoice"""
    STANDARD = "standard"                # Normal invoice
    CREDIT_NOTE = "credit_note"          # Credit/refund
    DEBIT_NOTE = "debit_note"            # Additional charges
    PROFORMA = "proforma"                # Proforma/quote
    RECURRING = "recurring"              # Recurring invoice


class PaymentMethod(str, Enum):
    """Payment methods"""
    BANK_TRANSFER = "bank_transfer"      # Wire/EFT
    CHECK = "check"                      # Cheque
    CREDIT_CARD = "credit_card"
    INTERAC = "interac"                  # Canadian Interac e-Transfer
    CASH = "cash"
    FACTORING = "factoring"              # Third-party factoring
    CREDIT_APPLIED = "credit_applied"    # Applied from credit balance


# =============================================================================
# LINE ITEM MODELS
# =============================================================================

class InvoiceLineItem(BaseModel):
    """Individual line item on an invoice"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = 1
    
    # Item details
    description: str
    item_type: str = "freight"           # freight, fuel_surcharge, accessorial, adjustment
    
    # Reference (for freight charges)
    order_id: Optional[str] = None
    order_number: Optional[str] = None
    shipment_id: Optional[str] = None
    shipment_number: Optional[str] = None
    
    # Load details (for freight items)
    origin: Optional[str] = None          # "Toronto, ON"
    destination: Optional[str] = None     # "Montreal, QC"
    pickup_date: Optional[str] = None
    delivery_date: Optional[str] = None
    pro_number: Optional[str] = None
    
    # Pricing
    quantity: float = 1
    unit_price: float
    unit: str = "load"                   # load, mile, km, hour, etc.
    
    # Calculated
    line_total: float = 0.0
    
    # Tax
    is_taxable: bool = True
    
    def calculate_total(self):
        self.line_total = round(self.quantity * self.unit_price, 2)
        return self.line_total


class AccessorialCharge(BaseModel):
    """Accessorial/extra charge"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str                             # e.g., "DET", "LUMPER", "FUEL"
    description: str
    amount: float
    is_taxable: bool = True


# =============================================================================
# INVOICE MODELS
# =============================================================================

class InvoiceBase(BaseModel):
    """Base invoice fields"""
    # Customer
    customer_id: str
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    
    # Billing Address
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_province: Optional[str] = None
    billing_postal_code: Optional[str] = None
    billing_country: str = "CA"
    
    # Invoice details
    invoice_type: InvoiceType = InvoiceType.STANDARD
    currency: str = "CAD"
    
    # Dates
    invoice_date: date = Field(default_factory=date.today)
    due_date: Optional[date] = None
    
    # Payment terms
    payment_terms_days: int = 30          # Net 30, etc.
    
    # Related orders
    order_ids: List[str] = []
    
    # Notes
    notes: Optional[str] = None           # Customer-visible notes
    internal_notes: Optional[str] = None  # Internal notes
    terms_and_conditions: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    """Create a new invoice"""
    tenant_id: str
    line_items: List[InvoiceLineItem] = []


class InvoiceUpdate(BaseModel):
    """Update invoice fields"""
    customer_email: Optional[EmailStr] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    payment_terms_days: Optional[int] = None
    notes: Optional[str] = None
    internal_notes: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    status: Optional[InvoiceStatus] = None


class Invoice(InvoiceBase):
    """Complete invoice model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Invoice number (auto-generated)
    invoice_number: str = Field(default_factory=lambda: f"INV-{str(uuid.uuid4())[:8].upper()}")
    
    # Status
    status: InvoiceStatus = InvoiceStatus.DRAFT
    
    # Line items
    line_items: List[InvoiceLineItem] = []
    
    # Subtotals
    subtotal: float = 0.0                 # Sum of line items before tax
    
    # Tax breakdown (Canadian)
    tax_province: Optional[str] = None    # Province for tax calculation
    is_tax_exempt: bool = False
    tax_exemption_number: Optional[str] = None
    
    gst_rate: float = 0.0
    gst_amount: float = 0.0
    pst_rate: float = 0.0
    pst_amount: float = 0.0
    hst_rate: float = 0.0
    hst_amount: float = 0.0
    qst_rate: float = 0.0
    qst_amount: float = 0.0
    total_tax: float = 0.0
    
    # Grand total
    grand_total: float = 0.0
    
    # Payment tracking
    amount_paid: float = 0.0
    balance_due: float = 0.0
    
    # Payment history
    payments: List[Dict[str, Any]] = []
    
    # PDF
    pdf_url: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    
    # Email tracking
    sent_at: Optional[datetime] = None
    sent_to: Optional[str] = None
    viewed_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    
    # Audit
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


class InvoiceResponse(BaseModel):
    """Invoice response for listing"""
    id: str
    invoice_number: str
    customer_name: str
    invoice_date: str
    due_date: Optional[str]
    status: str
    subtotal: float
    total_tax: float
    grand_total: float
    amount_paid: float
    balance_due: float
    is_overdue: bool = False


# =============================================================================
# PAYMENT MODELS
# =============================================================================

class PaymentCreate(BaseModel):
    """Record a payment"""
    amount: float
    payment_method: PaymentMethod
    payment_date: date = Field(default_factory=date.today)
    reference_number: Optional[str] = None  # Check number, transaction ID
    notes: Optional[str] = None


class Payment(BaseModel):
    """Payment record"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    invoice_id: str
    amount: float
    payment_method: PaymentMethod
    payment_date: date
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    recorded_by: Optional[str] = None


# =============================================================================
# ACCOUNTS RECEIVABLE SUMMARY
# =============================================================================

class ARAgingBucket(BaseModel):
    """Aging bucket for AR report"""
    bucket: str                           # "current", "1-30", "31-60", "61-90", "90+"
    amount: float
    invoice_count: int


class ARSummary(BaseModel):
    """Accounts Receivable summary"""
    total_outstanding: float
    current: float                        # Not yet due
    days_1_30: float                      # 1-30 days overdue
    days_31_60: float                     # 31-60 days overdue
    days_61_90: float                     # 61-90 days overdue
    days_90_plus: float                   # 90+ days overdue
    total_invoices: int
    overdue_invoices: int


# =============================================================================
# COMPANY BILLING INFO (for invoice header)
# =============================================================================

class CompanyBillingInfo(BaseModel):
    """Company information for invoice header"""
    company_name: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    province: str
    postal_code: str
    country: str = "CA"
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    
    # Canadian tax numbers
    gst_number: Optional[str] = None      # GST/HST registration
    qst_number: Optional[str] = None      # Quebec QST number
    business_number: Optional[str] = None  # BN
    
    # Logo
    logo_url: Optional[str] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_due_date(invoice_date: date, payment_terms_days: int) -> date:
    """Calculate due date based on payment terms"""
    return invoice_date + timedelta(days=payment_terms_days)


def is_invoice_overdue(due_date: date, status: InvoiceStatus) -> bool:
    """Check if invoice is overdue"""
    if status in [InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.WRITTEN_OFF]:
        return False
    return date.today() > due_date


def get_days_overdue(due_date: date) -> int:
    """Get number of days overdue (negative if not yet due)"""
    return (date.today() - due_date).days


def get_aging_bucket(days_overdue: int) -> str:
    """Get aging bucket for AR report"""
    if days_overdue <= 0:
        return "current"
    elif days_overdue <= 30:
        return "1-30"
    elif days_overdue <= 60:
        return "31-60"
    elif days_overdue <= 90:
        return "61-90"
    else:
        return "90+"
