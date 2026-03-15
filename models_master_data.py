"""
TMS Master Data Models - Phase 2
Carriers, Brokers, Shippers, Consignees, Locations
Canada-First Design with US Cross-Border Support
"""

from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone, date
import uuid


# =============================================================================
# ENUMS - Master Data Types
# =============================================================================

class EntityType(str, Enum):
    """Type of carrier/broker entity"""
    CARRIER = "carrier"                # Trucking company with own trucks
    BROKER = "broker"                  # Freight broker (no trucks)
    CARRIER_BROKER = "carrier_broker"  # Both carrier and broker


class EntityStatus(str, Enum):
    """Status of a business entity"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"
    BLACKLISTED = "blacklisted"


class InsuranceType(str, Enum):
    """Types of insurance coverage"""
    LIABILITY = "liability"            # General liability
    CARGO = "cargo"                    # Cargo insurance
    AUTO_LIABILITY = "auto_liability"  # Auto liability
    WORKERS_COMP = "workers_comp"      # Workers compensation
    UMBRELLA = "umbrella"              # Umbrella/excess
    CONTINGENT_CARGO = "contingent_cargo"  # For brokers


class PaymentTerms(str, Enum):
    """Payment terms options"""
    NET_15 = "net_15"
    NET_30 = "net_30"
    NET_45 = "net_45"
    NET_60 = "net_60"
    COD = "cod"                        # Cash on delivery
    QUICK_PAY = "quick_pay"            # Expedited payment (usually 2-7 days)
    FACTORING = "factoring"            # Third-party factoring


class UnloadType(str, Enum):
    """How freight is unloaded at destination"""
    LIVE_UNLOAD = "live_unload"        # Driver waits while unloading
    DROP_AND_HOOK = "drop_and_hook"    # Drop trailer, pick up empty
    DROP_TRAILER = "drop_trailer"      # Drop trailer for later pickup


class LocationType(str, Enum):
    """Type of location/facility"""
    WAREHOUSE = "warehouse"
    DISTRIBUTION_CENTER = "distribution_center"
    TERMINAL = "terminal"
    PORT = "port"
    RAIL_YARD = "rail_yard"
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    CROSS_DOCK = "cross_dock"
    YARD = "yard"
    OTHER = "other"


# =============================================================================
# CANADIAN TAX CONFIGURATION
# =============================================================================

class TaxType(str, Enum):
    """Canadian tax types"""
    GST = "gst"          # Federal Goods & Services Tax (5%)
    HST = "hst"          # Harmonized Sales Tax (GST + Provincial combined)
    PST = "pst"          # Provincial Sales Tax
    QST = "qst"          # Quebec Sales Tax
    EXEMPT = "exempt"    # Tax exempt


# Canadian tax rates by province (as of 2026)
CANADIAN_TAX_RATES = {
    # Province: (GST%, PST/HST%, QST%, Total%, Tax Type, Description)
    "AB": {"gst": 5.0, "pst": 0.0, "hst": 0.0, "qst": 0.0, "total": 5.0, "type": "gst", "name": "Alberta"},
    "BC": {"gst": 5.0, "pst": 7.0, "hst": 0.0, "qst": 0.0, "total": 12.0, "type": "gst_pst", "name": "British Columbia"},
    "MB": {"gst": 5.0, "pst": 7.0, "hst": 0.0, "qst": 0.0, "total": 12.0, "type": "gst_pst", "name": "Manitoba"},
    "NB": {"gst": 0.0, "pst": 0.0, "hst": 15.0, "qst": 0.0, "total": 15.0, "type": "hst", "name": "New Brunswick"},
    "NL": {"gst": 0.0, "pst": 0.0, "hst": 15.0, "qst": 0.0, "total": 15.0, "type": "hst", "name": "Newfoundland and Labrador"},
    "NS": {"gst": 0.0, "pst": 0.0, "hst": 15.0, "qst": 0.0, "total": 15.0, "type": "hst", "name": "Nova Scotia"},
    "NT": {"gst": 5.0, "pst": 0.0, "hst": 0.0, "qst": 0.0, "total": 5.0, "type": "gst", "name": "Northwest Territories"},
    "NU": {"gst": 5.0, "pst": 0.0, "hst": 0.0, "qst": 0.0, "total": 5.0, "type": "gst", "name": "Nunavut"},
    "ON": {"gst": 0.0, "pst": 0.0, "hst": 13.0, "qst": 0.0, "total": 13.0, "type": "hst", "name": "Ontario"},
    "PE": {"gst": 0.0, "pst": 0.0, "hst": 15.0, "qst": 0.0, "total": 15.0, "type": "hst", "name": "Prince Edward Island"},
    "QC": {"gst": 5.0, "pst": 0.0, "hst": 0.0, "qst": 9.975, "total": 14.975, "type": "gst_qst", "name": "Quebec"},
    "SK": {"gst": 5.0, "pst": 6.0, "hst": 0.0, "qst": 0.0, "total": 11.0, "type": "gst_pst", "name": "Saskatchewan"},
    "YT": {"gst": 5.0, "pst": 0.0, "hst": 0.0, "qst": 0.0, "total": 5.0, "type": "gst", "name": "Yukon"},
}

# US States (for cross-border) - no federal sales tax
US_STATES_NO_SALES_TAX = ["DE", "MT", "NH", "OR", "AK"]  # States with no sales tax


class TaxCalculation(BaseModel):
    """Result of a tax calculation"""
    province: str
    province_name: str
    subtotal: float
    gst_rate: float = 0.0
    gst_amount: float = 0.0
    pst_rate: float = 0.0
    pst_amount: float = 0.0
    hst_rate: float = 0.0
    hst_amount: float = 0.0
    qst_rate: float = 0.0
    qst_amount: float = 0.0
    total_tax_rate: float
    total_tax_amount: float
    grand_total: float
    tax_type: str
    breakdown: Dict[str, float] = {}


def calculate_canadian_tax(subtotal: float, province: str) -> TaxCalculation:
    """
    Calculate Canadian taxes for a given subtotal and province
    
    Args:
        subtotal: Pre-tax amount in CAD
        province: Two-letter province code (e.g., "ON", "BC", "QC")
    
    Returns:
        TaxCalculation with full breakdown
    """
    province = province.upper()
    
    if province not in CANADIAN_TAX_RATES:
        raise ValueError(f"Unknown province: {province}")
    
    rates = CANADIAN_TAX_RATES[province]
    tax_type = rates["type"]
    
    gst_amount = 0.0
    pst_amount = 0.0
    hst_amount = 0.0
    qst_amount = 0.0
    breakdown = {}
    
    if tax_type == "gst":
        # GST only (AB, NT, NU, YT)
        gst_amount = round(subtotal * (rates["gst"] / 100), 2)
        breakdown["GST (5%)"] = gst_amount
        
    elif tax_type == "gst_pst":
        # GST + PST (BC, MB, SK)
        gst_amount = round(subtotal * (rates["gst"] / 100), 2)
        pst_amount = round(subtotal * (rates["pst"] / 100), 2)
        breakdown[f"GST ({rates['gst']}%)"] = gst_amount
        breakdown[f"PST ({rates['pst']}%)"] = pst_amount
        
    elif tax_type == "hst":
        # HST combined (ON, NB, NL, NS, PE)
        hst_amount = round(subtotal * (rates["hst"] / 100), 2)
        breakdown[f"HST ({rates['hst']}%)"] = hst_amount
        
    elif tax_type == "gst_qst":
        # Quebec: GST + QST (QST is calculated on GST-inclusive amount)
        gst_amount = round(subtotal * (rates["gst"] / 100), 2)
        # QST is calculated on the GST-inclusive amount
        qst_base = subtotal + gst_amount
        qst_amount = round(qst_base * (rates["qst"] / 100), 2)
        breakdown[f"GST ({rates['gst']}%)"] = gst_amount
        breakdown[f"QST ({rates['qst']}%)"] = qst_amount
    
    total_tax = gst_amount + pst_amount + hst_amount + qst_amount
    grand_total = round(subtotal + total_tax, 2)
    
    return TaxCalculation(
        province=province,
        province_name=rates["name"],
        subtotal=subtotal,
        gst_rate=rates["gst"],
        gst_amount=gst_amount,
        pst_rate=rates["pst"],
        pst_amount=pst_amount,
        hst_rate=rates["hst"],
        hst_amount=hst_amount,
        qst_rate=rates["qst"],
        qst_amount=qst_amount,
        total_tax_rate=rates["total"],
        total_tax_amount=round(total_tax, 2),
        grand_total=grand_total,
        tax_type=tax_type,
        breakdown=breakdown
    )


def get_tax_rates_by_province(province: str) -> Dict[str, Any]:
    """Get tax rate information for a province"""
    province = province.upper()
    if province not in CANADIAN_TAX_RATES:
        raise ValueError(f"Unknown province: {province}")
    return CANADIAN_TAX_RATES[province]


def get_all_tax_rates() -> Dict[str, Dict[str, Any]]:
    """Get all Canadian tax rates"""
    return CANADIAN_TAX_RATES


# =============================================================================
# INSURANCE & COMPLIANCE MODELS
# =============================================================================

class InsuranceCoverage(BaseModel):
    """Insurance coverage details"""
    type: InsuranceType
    provider: str
    policy_number: str
    coverage_amount: float              # Coverage amount in CAD/USD
    deductible: Optional[float] = None
    effective_date: date
    expiry_date: date
    certificate_url: Optional[str] = None  # Link to certificate
    is_verified: bool = False
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None


class ComplianceDocument(BaseModel):
    """Compliance document tracking"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_type: str                   # MC authority, NSC cert, CVOR, etc.
    document_number: Optional[str] = None
    issuing_authority: str               # FMCSA, Transport Canada, MTO, etc.
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    file_url: Optional[str] = None
    is_verified: bool = False
    notes: Optional[str] = None


# =============================================================================
# ADDRESS MODEL (Reusable)
# =============================================================================

class Address(BaseModel):
    """Standard address format - Canada/US compatible"""
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state_province: str                  # Province code (ON, BC) or State code (CA, TX)
    postal_code: str                     # Canadian postal or US ZIP
    country: str = "CA"                  # CA or US
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    @property
    def is_canadian(self) -> bool:
        return self.country.upper() == "CA"
    
    @property
    def full_address(self) -> str:
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        parts.append(f"{self.city}, {self.state_province} {self.postal_code}")
        parts.append(self.country)
        return ", ".join(parts)


# =============================================================================
# CARRIERS & BROKERS
# =============================================================================

class CarrierBrokerBase(BaseModel):
    """Base fields for carrier/broker"""
    company_name: str
    entity_type: EntityType
    
    # Contact Information
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    
    # Address
    address: Optional[Address] = None
    
    # Canadian Authority Numbers (Primary)
    nsc_number: Optional[str] = None         # National Safety Code number
    cvor_number: Optional[str] = None        # Ontario CVOR
    nir_number: Optional[str] = None         # Quebec NIR
    
    # US Authority Numbers (for cross-border)
    mc_number: Optional[str] = None          # Motor Carrier number (FMCSA)
    dot_number: Optional[str] = None         # USDOT number
    
    # Broker-specific
    broker_authority: bool = False           # Has freight broker license
    surety_bond_amount: Optional[float] = None  # $75,000 required for US brokers
    surety_bond_expiry: Optional[date] = None
    
    # Business Details
    business_number: Optional[str] = None    # Canadian BN (like US EIN)
    gst_number: Optional[str] = None         # GST/HST registration
    
    # Equipment & Capacity (Carriers only)
    fleet_size: Optional[int] = None
    equipment_types: List[str] = []          # dry_van, reefer, flatbed, etc.
    
    # Operating Area
    operating_provinces: List[str] = []      # Canadian provinces
    operating_states: List[str] = []         # US states (cross-border)
    preferred_lanes: List[str] = []          # e.g., "ON-QC", "BC-AB"
    
    # Payment
    payment_terms: PaymentTerms = PaymentTerms.NET_30
    factoring_company: Optional[str] = None


class CarrierBrokerCreate(CarrierBrokerBase):
    """Create a new carrier/broker"""
    tenant_id: str


class CarrierBrokerUpdate(BaseModel):
    """Update carrier/broker fields"""
    company_name: Optional[str] = None
    entity_type: Optional[EntityType] = None
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    address: Optional[Address] = None
    nsc_number: Optional[str] = None
    cvor_number: Optional[str] = None
    mc_number: Optional[str] = None
    dot_number: Optional[str] = None
    broker_authority: Optional[bool] = None
    surety_bond_amount: Optional[float] = None
    fleet_size: Optional[int] = None
    equipment_types: Optional[List[str]] = None
    operating_provinces: Optional[List[str]] = None
    operating_states: Optional[List[str]] = None
    preferred_lanes: Optional[List[str]] = None
    payment_terms: Optional[PaymentTerms] = None
    status: Optional[EntityStatus] = None


class CarrierBroker(CarrierBrokerBase):
    """Complete carrier/broker model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Status
    status: EntityStatus = EntityStatus.PENDING_VERIFICATION
    
    # Insurance (multiple coverages)
    insurance_coverages: List[InsuranceCoverage] = []
    
    # Compliance Documents
    compliance_documents: List[ComplianceDocument] = []
    
    # Safety Rating
    safety_rating: Optional[str] = None      # Satisfactory, Conditional, etc.
    csa_score: Optional[float] = None        # US CSA score
    nsc_safety_rating: Optional[str] = None  # Canadian NSC rating
    
    # Performance Metrics
    on_time_pickup_rate: Optional[float] = None
    on_time_delivery_rate: Optional[float] = None
    claim_ratio: Optional[float] = None
    loads_completed: int = 0
    
    # Financial
    credit_limit: Optional[float] = None
    current_balance: float = 0.0
    
    # Notes
    internal_notes: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


# =============================================================================
# LOCATIONS
# =============================================================================

class OperatingHours(BaseModel):
    """Operating hours for a location"""
    day: str                             # mon, tue, wed, thu, fri, sat, sun
    open_time: Optional[str] = None      # HH:MM format
    close_time: Optional[str] = None     # HH:MM format
    is_closed: bool = False


class LocationBase(BaseModel):
    """Base location fields"""
    location_name: str
    location_type: LocationType = LocationType.WAREHOUSE
    
    # Address
    address: Address
    
    # Contact
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    
    # Operating Hours
    operating_hours: List[OperatingHours] = []
    timezone: str = "America/Toronto"
    
    # Appointment Requirements
    appointment_required: bool = False
    appointment_lead_time_hours: Optional[int] = None  # How far in advance
    
    # Facility Details
    dock_count: Optional[int] = None
    has_forklift: bool = False
    has_loading_dock: bool = True
    max_trailer_length_ft: Optional[int] = None
    
    # Special Requirements
    special_instructions: Optional[str] = None
    hazmat_certified: bool = False


class LocationCreate(LocationBase):
    """Create a new location"""
    tenant_id: str


class LocationUpdate(BaseModel):
    """Update location fields"""
    location_name: Optional[str] = None
    location_type: Optional[LocationType] = None
    address: Optional[Address] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    operating_hours: Optional[List[OperatingHours]] = None
    appointment_required: Optional[bool] = None
    special_instructions: Optional[str] = None
    is_active: Optional[bool] = None


class Location(LocationBase):
    """Complete location model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Status
    is_active: bool = True
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


# =============================================================================
# SHIPPERS (Consignors - who sends the freight)
# =============================================================================

class ShipperBase(BaseModel):
    """Base shipper fields"""
    company_name: str
    
    # Contact
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    
    # Address (primary location)
    address: Optional[Address] = None
    
    # Dock Hours
    dock_hours_open: Optional[str] = None   # HH:MM
    dock_hours_close: Optional[str] = None  # HH:MM
    
    # Requirements
    appointment_required: bool = False
    hazmat_certified: bool = False
    
    # Notes
    shipper_notes: Optional[str] = None     # Special pickup instructions


class ShipperCreate(ShipperBase):
    """Create a new shipper"""
    tenant_id: str
    customer_id: Optional[str] = None        # Link to customer if applicable


class ShipperUpdate(BaseModel):
    """Update shipper fields"""
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    address: Optional[Address] = None
    dock_hours_open: Optional[str] = None
    dock_hours_close: Optional[str] = None
    appointment_required: Optional[bool] = None
    hazmat_certified: Optional[bool] = None
    shipper_notes: Optional[str] = None
    is_active: Optional[bool] = None


class Shipper(ShipperBase):
    """Complete shipper model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    customer_id: Optional[str] = None
    
    # Status
    is_active: bool = True
    
    # Statistics
    total_shipments: int = 0
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


# =============================================================================
# CONSIGNEES (Receivers - who receives the freight)
# =============================================================================

class ConsigneeBase(BaseModel):
    """Base consignee fields"""
    company_name: str
    
    # Contact
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    
    # Address
    address: Optional[Address] = None
    
    # Dock Hours
    dock_hours_open: Optional[str] = None   # HH:MM
    dock_hours_close: Optional[str] = None  # HH:MM
    
    # Delivery Requirements
    appointment_required: bool = False
    unload_type: UnloadType = UnloadType.LIVE_UNLOAD
    average_unload_time_minutes: Optional[int] = None  # Estimated wait time
    
    # Special Instructions
    consignee_notes: Optional[str] = None   # e.g., "Call 1hr before arrival"


class ConsigneeCreate(ConsigneeBase):
    """Create a new consignee"""
    tenant_id: str
    customer_id: Optional[str] = None


class ConsigneeUpdate(BaseModel):
    """Update consignee fields"""
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    address: Optional[Address] = None
    dock_hours_open: Optional[str] = None
    dock_hours_close: Optional[str] = None
    appointment_required: Optional[bool] = None
    unload_type: Optional[UnloadType] = None
    average_unload_time_minutes: Optional[int] = None
    consignee_notes: Optional[str] = None
    is_active: Optional[bool] = None


class Consignee(ConsigneeBase):
    """Complete consignee model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    customer_id: Optional[str] = None
    
    # Status
    is_active: bool = True
    
    # Statistics
    total_deliveries: int = 0
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


# =============================================================================
# CUSTOMERS (Billable parties)
# =============================================================================

class CustomerBase(BaseModel):
    """Base customer fields - the party you invoice"""
    company_name: str
    
    # Contact
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    
    # Billing Address
    billing_address: Optional[Address] = None
    
    # Financial
    credit_limit: Optional[float] = None
    payment_terms: PaymentTerms = PaymentTerms.NET_30
    
    # Tax Information
    tax_province: Optional[str] = None       # For Canadian tax calculation
    is_tax_exempt: bool = False
    tax_exemption_number: Optional[str] = None
    
    # Business Numbers
    business_number: Optional[str] = None    # Canadian BN
    gst_number: Optional[str] = None


class CustomerCreate(CustomerBase):
    """Create a new customer"""
    tenant_id: str


class CustomerUpdate(BaseModel):
    """Update customer fields"""
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    billing_address: Optional[Address] = None
    credit_limit: Optional[float] = None
    payment_terms: Optional[PaymentTerms] = None
    tax_province: Optional[str] = None
    is_tax_exempt: Optional[bool] = None
    is_active: Optional[bool] = None


class Customer(CustomerBase):
    """Complete customer model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Status
    status: EntityStatus = EntityStatus.ACTIVE
    is_active: bool = True
    
    # Financials
    current_balance: float = 0.0            # Outstanding AR
    lifetime_revenue: float = 0.0
    
    # Statistics
    total_orders: int = 0
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
