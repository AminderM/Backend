"""
Carrier Profile Models for TMS
MongoDB schema with exact field names matching frontend
"""
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import datetime, timezone
from enum import Enum
import uuid


# === Enums ===
class CarrierCompanyType(str, Enum):
    TRUCKING_COMPANY = "trucking_company"
    OWNER_OPERATOR = "owner_operator"
    BOTH = "both"


class CarrierCountry(str, Enum):
    CANADA = "Canada"
    USA = "USA"
    BOTH = "Both"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    EXPIRED = "expired"
    EXPIRING_SOON = "expiring_soon"


class EquipmentTypeCarrier(str, Enum):
    DRY_VAN = "dry_van"
    FLATBED = "flatbed"
    REEFER = "reefer"
    TANKER = "tanker"
    STEP_DECK = "step_deck"
    HOTSHOT = "hotshot"
    SPRINTER = "sprinter"
    OTHER = "other"


class PaymentMethod(str, Enum):
    DIRECT_DEPOSIT = "direct_deposit"
    FACTORING = "factoring"
    CHECK = "check"


class AccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"


class Currency(str, Enum):
    CAD = "CAD"
    USD = "USD"


class PaymentTerms(str, Enum):
    NET_15 = "net_15"
    NET_30 = "net_30"
    NET_45 = "net_45"
    QUICK_PAY = "quick_pay"


# === Sub-Models ===
class CompanyInfo(BaseModel):
    legal_name: Optional[str] = None
    dba_name: Optional[str] = None
    company_type: Optional[CarrierCompanyType] = None
    country: Optional[CarrierCountry] = None
    province: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None


class CarrierDocument(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_type: str  # nsc_certificate, cvor_abstract, etc.
    file_name: str
    file_url: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expiry_date: Optional[datetime] = None
    status: DocumentStatus = DocumentStatus.UPLOADED


class Regulatory(BaseModel):
    # Canadian
    nsc_number: Optional[str] = None
    nsc_safety_rating: Optional[str] = None
    cvor_number: Optional[str] = None
    cvor_safety_rating: Optional[str] = None
    cra_business_number: Optional[str] = None
    gst_hst_number: Optional[str] = None
    # US
    usdot_number: Optional[str] = None
    mc_number: Optional[str] = None
    ein: Optional[str] = None
    ifta_account_number: Optional[str] = None
    ifta_base_jurisdiction: Optional[str] = None
    # Cross-border
    cross_border_capable: Optional[bool] = False
    fast_card_enrolled: Optional[bool] = False


class PreferredLane(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    frequency: Optional[str] = None  # daily, weekly, monthly


class Fleet(BaseModel):
    number_of_trucks: Optional[int] = None
    number_of_trailers: Optional[int] = None
    equipment_types: List[str] = Field(default_factory=list)
    hazmat_capable: Optional[bool] = False
    cross_border_capable: Optional[bool] = False
    eld_provider: Optional[str] = None
    preferred_lanes: List[PreferredLane] = Field(default_factory=list)
    is_24x7_dispatch: Optional[bool] = False


class Payment(BaseModel):
    payment_method: Optional[PaymentMethod] = None
    factoring_company_name: Optional[str] = None
    bank_name: Optional[str] = None
    # Encrypted fields (stored as encrypted strings)
    transit_number_encrypted: Optional[str] = None
    institution_number_encrypted: Optional[str] = None
    aba_routing_number_encrypted: Optional[str] = None
    account_number_encrypted: Optional[str] = None
    # Non-encrypted fields
    account_type: Optional[AccountType] = None
    currency: Optional[Currency] = None
    payment_terms: Optional[PaymentTerms] = None


class CarrierPackageRecipient(BaseModel):
    email: EmailStr
    name: Optional[str] = None


class CarrierPackage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    recipients: List[CarrierPackageRecipient] = Field(default_factory=list)
    message: Optional[str] = None
    included_sections: List[str] = Field(default_factory=list)  # company_info, documents, regulatory, fleet
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_token: str = Field(default_factory=lambda: str(uuid.uuid4()))
    expires_at: Optional[datetime] = None


# === Main Carrier Profile Model ===
class CarrierProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # Owner of this profile
    company_id: Optional[str] = None  # Associated company if any
    
    # Step 1: Company Info
    company_info: CompanyInfo = Field(default_factory=CompanyInfo)
    
    # Step 2: Documents
    documents: List[CarrierDocument] = Field(default_factory=list)
    
    # Step 3: Regulatory
    regulatory: Regulatory = Field(default_factory=Regulatory)
    
    # Step 4: Fleet & Lanes
    fleet: Fleet = Field(default_factory=Fleet)
    
    # Step 5: Payment (with encrypted fields)
    payment: Payment = Field(default_factory=Payment)
    
    # Metadata
    profile_completion: int = 0  # 0-100%
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Sent packages history
    packages: List[CarrierPackage] = Field(default_factory=list)


# === Request/Response Models ===
class CarrierProfileUpdate(BaseModel):
    """Model for PATCH /api/carrier-profiles/me"""
    company_info: Optional[CompanyInfo] = None
    regulatory: Optional[Regulatory] = None
    fleet: Optional[Fleet] = None
    payment: Optional[dict] = None  # Dict to handle encryption of sensitive fields


class DocumentUploadResponse(BaseModel):
    id: str
    document_type: str
    file_name: str
    file_url: str
    uploaded_at: datetime
    status: DocumentStatus


class CarrierPackageCreate(BaseModel):
    recipients: List[CarrierPackageRecipient]
    message: Optional[str] = None
    included_sections: List[str] = Field(default_factory=lambda: ["company_info", "documents", "regulatory", "fleet"])


class CarrierProfileResponse(BaseModel):
    """Response model that masks encrypted fields"""
    id: str
    user_id: str
    company_id: Optional[str] = None
    company_info: CompanyInfo
    documents: List[CarrierDocument]
    regulatory: Regulatory
    fleet: Fleet
    payment: dict  # Return masked payment info
    profile_completion: int
    created_at: datetime
    updated_at: datetime
    packages: List[CarrierPackage]
