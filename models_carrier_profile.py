"""
Carrier Profile Models - TMS Backend
Defines data structures for the 5-step carrier profile wizard
"""

from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Literal
from datetime import datetime, timezone
from enum import Enum
import uuid


# =============================================================================
# ENUMS
# =============================================================================

class BusinessType(str, Enum):
    SOLE_PROPRIETORSHIP = "sole_proprietorship"
    PARTNERSHIP = "partnership"
    CORPORATION = "corporation"
    LLC = "llc"
    COOPERATIVE = "cooperative"


class PaymentTerms(str, Enum):
    NET_15 = "net_15"
    NET_30 = "net_30"
    NET_45 = "net_45"
    NET_60 = "net_60"
    DUE_ON_RECEIPT = "due_on_receipt"


class PaymentMethod(str, Enum):
    EFT = "eft"
    CHEQUE = "cheque"
    WIRE = "wire"
    ACH = "ach"


class EquipmentTypeEnum(str, Enum):
    DRY_VAN = "dry_van"
    REEFER = "reefer"
    FLATBED = "flatbed"
    STEP_DECK = "step_deck"
    LOWBOY = "lowboy"
    TANKER = "tanker"
    INTERMODAL = "intermodal"
    CAR_HAULER = "car_hauler"
    LIVESTOCK = "livestock"
    BULK = "bulk"
    CONTAINER = "container"
    DUMP = "dump"
    HOPPER = "hopper"


class LaneFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BI_WEEKLY = "bi_weekly"
    MONTHLY = "monthly"
    AS_NEEDED = "as_needed"


class DocumentStatus(str, Enum):
    VALID = "valid"
    EXPIRING_SOON = "expiring_soon"  # Within 60 days
    EXPIRED = "expired"
    MISSING = "missing"


class ProfileStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


# =============================================================================
# ADDRESS MODELS
# =============================================================================

class Address(BaseModel):
    street: str
    city: str
    province_state: str
    postal_code: str
    country: str = "CA"  # CA or US


# =============================================================================
# STEP 1: COMPANY INFO
# =============================================================================

class CompanyInfoUpdate(BaseModel):
    company_name: str
    legal_name: Optional[str] = None
    dba_name: Optional[str] = None  # Doing Business As
    business_type: Optional[BusinessType] = None
    year_established: Optional[int] = None
    address: Optional[Address] = None
    mailing_address: Optional[Address] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[EmailStr] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None


class CompanyInfo(CompanyInfoUpdate):
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# STEP 2: COMPLIANCE DOCUMENTS
# =============================================================================

class InsuranceDocument(BaseModel):
    policy_number: Optional[str] = None
    provider: Optional[str] = None
    coverage_amount: Optional[float] = None
    expiry_date: Optional[str] = None  # ISO date string
    document_url: Optional[str] = None
    status: DocumentStatus = DocumentStatus.MISSING


class ClearanceDocument(BaseModel):
    certificate_number: Optional[str] = None
    expiry_date: Optional[str] = None
    document_url: Optional[str] = None
    status: DocumentStatus = DocumentStatus.MISSING


class CanadianDocuments(BaseModel):
    cargo_insurance: Optional[InsuranceDocument] = None
    liability_insurance: Optional[InsuranceDocument] = None
    wsib_clearance: Optional[ClearanceDocument] = None  # Ontario
    wcb_clearance: Optional[ClearanceDocument] = None   # Other provinces
    cvor_abstract: Optional[ClearanceDocument] = None   # Ontario specific
    nsc_certificate: Optional[ClearanceDocument] = None


class USDocuments(BaseModel):
    cargo_insurance: Optional[InsuranceDocument] = None
    liability_insurance: Optional[InsuranceDocument] = None
    workers_comp: Optional[InsuranceDocument] = None
    boc_3_filing: Optional[ClearanceDocument] = None
    ucr_registration: Optional[ClearanceDocument] = None


class ComplianceDocumentsUpdate(BaseModel):
    operating_country: Literal["CA", "US", "BOTH"] = "CA"
    canadian_documents: Optional[CanadianDocuments] = None
    us_documents: Optional[USDocuments] = None


class ComplianceDocuments(ComplianceDocumentsUpdate):
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# STEP 3: REGULATORY NUMBERS
# =============================================================================

class CanadianRegulatoryNumbers(BaseModel):
    nsc_number: Optional[str] = None          # National Safety Code
    cvor_number: Optional[str] = None         # Commercial Vehicle Operator Registration (ON)
    carrier_code: Optional[str] = None
    ifta_account: Optional[str] = None        # International Fuel Tax Agreement
    irp_account: Optional[str] = None         # International Registration Plan
    ctpat_number: Optional[str] = None        # Customs-Trade Partnership


class USRegulatoryNumbers(BaseModel):
    usdot_number: Optional[str] = None
    mc_number: Optional[str] = None
    scac_code: Optional[str] = None           # Standard Carrier Alpha Code
    ifta_account: Optional[str] = None
    irp_account: Optional[str] = None
    ctpat_number: Optional[str] = None
    hazmat_permit: Optional[str] = None


class RegulatoryNumbersUpdate(BaseModel):
    operating_regions: List[str] = []  # ["CA", "US"]
    canadian: Optional[CanadianRegulatoryNumbers] = None
    us: Optional[USRegulatoryNumbers] = None


class RegulatoryNumbers(RegulatoryNumbersUpdate):
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# STEP 4: FLEET CONFIGURATION
# =============================================================================

class FleetSize(BaseModel):
    power_units: int = 0
    trailers: int = 0
    drivers: int = 0


class EquipmentCount(BaseModel):
    type: EquipmentTypeEnum
    count: int = 0


class LaneLocation(BaseModel):
    city: str
    province_state: str
    country: str = "CA"


class PreferredLane(BaseModel):
    origin: LaneLocation
    destination: LaneLocation
    frequency: LaneFrequency = LaneFrequency.AS_NEEDED


class FleetConfigurationUpdate(BaseModel):
    fleet_size: Optional[FleetSize] = None
    equipment_types: List[EquipmentCount] = []
    preferred_lanes: List[PreferredLane] = []
    service_areas: List[str] = []  # Province/State codes
    special_services: List[str] = []  # ["hazmat", "oversize", "temperature_controlled", etc.]


class FleetConfiguration(FleetConfigurationUpdate):
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# STEP 5: PAYMENT/BANKING
# =============================================================================

class BankingInfo(BaseModel):
    """Banking info - these fields will be encrypted before storage"""
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None
    institution_number: Optional[str] = None  # Canadian 3-digit
    transit_number: Optional[str] = None      # Canadian 5-digit
    account_number: Optional[str] = None
    routing_number: Optional[str] = None      # US 9-digit


class TaxInfo(BaseModel):
    business_number: Optional[str] = None     # Canadian BN
    gst_hst_number: Optional[str] = None
    qst_number: Optional[str] = None          # Quebec only
    ein: Optional[str] = None                 # US Employer ID


class PaymentBankingUpdate(BaseModel):
    payment_terms: Optional[PaymentTerms] = None
    preferred_payment_method: Optional[PaymentMethod] = None
    currency: Literal["CAD", "USD"] = "CAD"
    banking_info: Optional[BankingInfo] = None
    tax_info: Optional[TaxInfo] = None
    void_cheque_url: Optional[str] = None


class PaymentBanking(PaymentBankingUpdate):
    # Encrypted fields stored separately
    encrypted_banking_info: Optional[str] = None  # Fernet encrypted JSON
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# COMPLETION STATUS
# =============================================================================

class CompletionStatus(BaseModel):
    company_info: bool = False
    compliance_documents: bool = False
    regulatory_numbers: bool = False
    fleet_configuration: bool = False
    payment_banking: bool = False


class DocumentStatusSummary(BaseModel):
    cargo_insurance: DocumentStatus = DocumentStatus.MISSING
    liability_insurance: DocumentStatus = DocumentStatus.MISSING
    wsib_clearance: DocumentStatus = DocumentStatus.MISSING
    wcb_clearance: DocumentStatus = DocumentStatus.MISSING
    workers_comp: DocumentStatus = DocumentStatus.MISSING


# =============================================================================
# VALIDATION
# =============================================================================

class ValidationError(BaseModel):
    section: str
    field: str
    message: str


class ValidationResult(BaseModel):
    is_valid: bool = False
    errors: List[ValidationError] = []
    warnings: List[ValidationError] = []


# =============================================================================
# MAIN CARRIER PROFILE MODEL
# =============================================================================

class CarrierProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    company_id: Optional[str] = None
    
    # Profile sections
    company_info: Optional[CompanyInfo] = None
    compliance_documents: Optional[ComplianceDocuments] = None
    regulatory_numbers: Optional[RegulatoryNumbers] = None
    fleet_configuration: Optional[FleetConfiguration] = None
    payment_banking: Optional[PaymentBanking] = None
    
    # Status tracking
    completion_status: CompletionStatus = Field(default_factory=CompletionStatus)
    overall_completion_percentage: int = 0
    profile_status: ProfileStatus = ProfileStatus.DRAFT
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    
    # Audit
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    reviewed_by: Optional[str] = None
    review_notes: Optional[str] = None


class CarrierProfileResponse(BaseModel):
    """Response model excluding sensitive encrypted data"""
    id: str
    user_id: str
    company_id: Optional[str] = None
    company_info: Optional[CompanyInfo] = None
    compliance_documents: Optional[ComplianceDocuments] = None
    regulatory_numbers: Optional[RegulatoryNumbers] = None
    fleet_configuration: Optional[FleetConfiguration] = None
    payment_banking: Optional[PaymentBankingUpdate] = None  # Excludes encrypted field
    completion_status: CompletionStatus
    overall_completion_percentage: int
    profile_status: ProfileStatus
    created_at: datetime
    updated_at: datetime
