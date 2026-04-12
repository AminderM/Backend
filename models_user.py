"""
TMS User Management Models - Canada First Design
Updated role structure, worker types, and multi-tenancy support
"""

from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict
from enum import Enum
from datetime import datetime, timezone
import uuid


# =============================================================================
# ENUMS - User Roles & Types (Canada First)
# =============================================================================

class UserRole(str, Enum):
    """
    Simplified 7-role structure (down from 17)
    Designed to be extensible for future needs
    """
    # Platform Level - SAAS owner (cross-tenant access)
    PLATFORM_ADMIN = "platform_admin"
    
    # Tenant Level - Administrative
    ADMIN = "admin"                    # Company admin (full tenant access)
    MANAGER = "manager"                # Department management
    
    # Tenant Level - Operational
    DISPATCHER = "dispatcher"          # Load/shipment management
    DRIVER = "driver"                  # Mobile app, load execution
    BILLING = "billing"                # Finance, invoicing, AR/AP
    VIEWER = "viewer"                  # Read-only access
    
    # Website web tools users (separate portal, separate tenancy)
    WEB_TOOLS_USER = "web_tools_user"

    # Legacy roles (kept for backward compatibility - will be auto-migrated)
    COMPANY_ADMIN = "company_admin"    # → maps to ADMIN
    ACCOUNTANT = "accountant"          # → maps to BILLING
    FLEET_OWNER = "fleet_owner"        # → maps to ADMIN
    FLEET_MANAGER = "fleet_manager"    # → maps to MANAGER
    HR_MANAGER = "hr_manager"          # → maps to MANAGER
    SALES_MANAGER = "sales_manager"    # → maps to MANAGER
    ACCOUNTS_RECEIVABLE = "accounts_receivable"  # → maps to BILLING
    ACCOUNTS_PAYABLE = "accounts_payable"        # → maps to BILLING
    HR = "hr"                          # → maps to MANAGER


# Role migration mapping - legacy roles to new roles
ROLE_MIGRATION_MAP = {
    "company_admin": "admin",
    "accountant": "billing",
    "fleet_owner": "admin",
    "fleet_manager": "manager",
    "hr_manager": "manager",
    "sales_manager": "manager",
    "accounts_receivable": "billing",
    "accounts_payable": "billing",
    "hr": "manager",
    # These stay the same
    "web_tools_user": "web_tools_user",
    "platform_admin": "platform_admin",
    "admin": "admin",
    "manager": "manager",
    "dispatcher": "dispatcher",
    "driver": "driver",
    "billing": "billing",
    "viewer": "viewer",
}


def normalize_role(role_value: str) -> str:
    """Normalize legacy roles to new role structure"""
    if not role_value:
        return "viewer"
    return ROLE_MIGRATION_MAP.get(role_value.lower(), role_value.lower())


class UserType(str, Enum):
    """
    Business entity classification - describes what type of business the user represents
    Separate from role (which defines permissions)
    """
    CARRIER = "carrier"                # Trucking company with own trucks
    BROKER = "broker"                  # Freight broker (no trucks)
    CARRIER_BROKER = "carrier_broker"  # Both carrier and broker
    SHIPPER = "shipper"                # Ships goods (manufacturer, warehouse)
    CONSIGNEE = "consignee"            # Receives goods (retailer, DC)
    OWNER_OPERATOR = "owner_operator"  # Independent contractor with own truck
    INTERNAL = "internal"              # Platform staff


class WorkerType(str, Enum):
    """
    Employment/tax classification - Canada First with US equivalents
    Used primarily for drivers and staff
    """
    # Canadian Primary (T4 = employee, T4A = contractor)
    T4_EMPLOYEE = "t4_employee"            # Canadian payroll employee
    T4A_CONTRACTOR = "t4a_contractor"      # Canadian independent contractor (owner-operator)
    
    # US Equivalents (for cross-border operations)
    W2_EMPLOYEE = "w2_employee"            # US payroll employee
    CONTRACTOR_1099 = "1099_contractor"    # US independent contractor


# Worker type display labels
WORKER_TYPE_LABELS = {
    "t4_employee": "T4 Employee",
    "t4a_contractor": "T4A Contractor",
    "w2_employee": "W2 Employee",
    "1099_contractor": "1099 Contractor",
}


class RegistrationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class UserStatus(str, Enum):
    """User account status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"
    DECLINED = "declined"
    CANCELLED = "cancelled"


# =============================================================================
# CANADIAN PROVINCES & US STATES
# =============================================================================

class CanadianProvince(str, Enum):
    """Canadian provinces and territories"""
    AB = "AB"  # Alberta
    BC = "BC"  # British Columbia
    MB = "MB"  # Manitoba
    NB = "NB"  # New Brunswick
    NL = "NL"  # Newfoundland and Labrador
    NS = "NS"  # Nova Scotia
    NT = "NT"  # Northwest Territories
    NU = "NU"  # Nunavut
    ON = "ON"  # Ontario
    PE = "PE"  # Prince Edward Island
    QC = "QC"  # Quebec
    SK = "SK"  # Saskatchewan
    YT = "YT"  # Yukon


PROVINCE_NAMES = {
    "AB": "Alberta",
    "BC": "British Columbia",
    "MB": "Manitoba",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
    "ON": "Ontario",
    "PE": "Prince Edward Island",
    "QC": "Quebec",
    "SK": "Saskatchewan",
    "YT": "Yukon",
}


# =============================================================================
# LICENSE TYPES - Canada First
# =============================================================================

class LicenseClass(str, Enum):
    """
    Canadian driver license classes (varies by province)
    Class 1/A = Heavy trucks (tractor-trailer)
    Class 3/D = Straight trucks
    """
    # Western Canada (BC, AB, SK, MB)
    CLASS_1 = "class_1"      # Tractor-trailer (equivalent to US CDL-A)
    CLASS_2 = "class_2"      # Bus
    CLASS_3 = "class_3"      # Straight truck (equivalent to US CDL-B)
    CLASS_4 = "class_4"      # Taxi, ambulance
    CLASS_5 = "class_5"      # Standard car/light truck
    
    # Eastern Canada (ON, QC) - different naming
    CLASS_A = "class_a"      # Tractor-trailer (same as Class 1)
    CLASS_B = "class_b"      # Bus
    CLASS_C = "class_c"      # Regular bus
    CLASS_D = "class_d"      # Straight truck (same as Class 3)
    CLASS_G = "class_g"      # Standard car
    
    # US CDL Classes (for cross-border)
    CDL_A = "cdl_a"          # Combination vehicles
    CDL_B = "cdl_b"          # Single vehicles over 26,001 lbs
    CDL_C = "cdl_c"          # Vehicles with 16+ passengers or hazmat
    
    # Non-commercial
    NON_CDL = "non_cdl"


LICENSE_CLASS_LABELS = {
    "class_1": "Class 1 (Heavy Truck - Western Canada)",
    "class_2": "Class 2 (Bus - Western Canada)",
    "class_3": "Class 3 (Straight Truck - Western Canada)",
    "class_a": "Class A (Heavy Truck - Ontario/Quebec)",
    "class_d": "Class D (Straight Truck - Ontario/Quebec)",
    "cdl_a": "CDL Class A (US)",
    "cdl_b": "CDL Class B (US)",
    "cdl_c": "CDL Class C (US)",
    "non_cdl": "Non-Commercial",
}


class LicenseEndorsement(str, Enum):
    """License endorsements - Canada & US"""
    # Canadian
    Z_AIR_BRAKE = "z_air_brake"           # Air brake endorsement
    TDG_HAZMAT = "tdg_hazmat"             # Transportation of Dangerous Goods
    
    # US
    H_HAZMAT = "h_hazmat"                 # HazMat endorsement
    N_TANK = "n_tank"                     # Tank vehicles
    P_PASSENGER = "p_passenger"           # Passenger endorsement
    S_SCHOOL_BUS = "s_school_bus"         # School bus
    T_DOUBLE_TRIPLE = "t_double_triple"   # Double/triple trailers
    X_TANK_HAZMAT = "x_tank_hazmat"       # Tank + HazMat combined


# =============================================================================
# USER MODELS
# =============================================================================

class UserBase(BaseModel):
    """Base user fields for creation/update"""
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    role: UserRole = UserRole.VIEWER


class UserCreate(UserBase):
    """User creation with password"""
    password: str
    tenant_id: Optional[str] = None
    user_type: Optional[UserType] = None
    worker_type: Optional[WorkerType] = None
    operating_provinces: List[str] = []


class UserLogin(BaseModel):
    """User login credentials"""
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """User update fields - all optional"""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[UserRole] = None
    user_type: Optional[UserType] = None
    worker_type: Optional[WorkerType] = None
    status: Optional[UserStatus] = None
    is_active: Optional[bool] = None
    operating_provinces: Optional[List[str]] = None
    permissions: Optional[Dict[str, bool]] = None


class User(UserBase):
    """
    Complete User model with all fields
    Canada-first design with multi-tenancy support
    """
    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Authentication
    password_hash: Optional[str] = None
    email_verified: bool = False
    registration_status: RegistrationStatus = RegistrationStatus.PENDING
    verification_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None

    # Social / OAuth providers
    auth_provider: str = "email"        # "email" | "google" | "apple"
    google_id: Optional[str] = None
    apple_id: Optional[str] = None

    # Email OTP
    otp_code: Optional[str] = None      # SHA-256 hashed 6-digit code
    otp_expires_at: Optional[datetime] = None
    otp_attempts: int = 0

    # Portal identification — which product this user belongs to
    portal: str = "tms"                      # "tms" | "website" | "admin"

    # Multi-Tenancy
    tenant_id: Optional[str] = None          # FK to companies/tenants
    fleet_owner_id: Optional[str] = None     # Legacy - for backward compatibility
    
    # Business Classification
    user_type: Optional[UserType] = None     # carrier, broker, shipper, etc.
    worker_type: Optional[WorkerType] = None  # T4/T4A/W2/1099
    
    # Access Control
    assigned_products: List[str] = []        # Product/module access
    permissions: Dict[str, bool] = Field(default_factory=dict)  # Granular permissions
    
    # Geographic Operations (Canada-first)
    operating_provinces: List[str] = []      # Provinces where user operates
    primary_province: Optional[str] = None   # Main province of operation
    
    # Status
    status: UserStatus = UserStatus.ACTIVE
    is_active: bool = True
    last_login_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    # Audit
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    # Admin Notes
    comments: List[dict] = Field(default_factory=list)


class UserResponse(BaseModel):
    """User response model (excludes sensitive fields)"""
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str
    user_type: Optional[str] = None
    worker_type: Optional[str] = None
    tenant_id: Optional[str] = None
    status: str
    is_active: bool
    operating_provinces: List[str] = []
    created_at: datetime
    last_login_at: Optional[datetime] = None


# =============================================================================
# WORKSPACE ACCESS CONTROL
# =============================================================================

class Workspace(str, Enum):
    """Available workspaces/modules in the TMS application"""
    DASHBOARD = "dashboard"
    DISPATCH = "dispatch"              # Dispatch Operations
    SALES = "sales"                    # Sales / CRM
    ACCOUNTING = "accounting"          # Accounting / Billing
    HR = "hr"                          # HR / User Management
    FLEET = "fleet"                    # Fleet Management
    REPORTS = "reports"                # Reporting / Analytics
    SETTINGS = "settings"              # Settings / Configuration
    DRIVER_APP = "driver_app"          # Driver Mobile App
    RATE_CARDS = "rate_cards"          # Rate Cards / Pricing


# Workspace access by role - controls what users can SEE
WORKSPACE_ACCESS_MAP = {
    "platform_admin": [
        Workspace.DASHBOARD, Workspace.DISPATCH, Workspace.SALES,
        Workspace.ACCOUNTING, Workspace.HR, Workspace.FLEET,
        Workspace.REPORTS, Workspace.SETTINGS, Workspace.DRIVER_APP,
        Workspace.RATE_CARDS
    ],
    "admin": [
        Workspace.DASHBOARD, Workspace.DISPATCH, Workspace.SALES,
        Workspace.ACCOUNTING, Workspace.HR, Workspace.FLEET,
        Workspace.REPORTS, Workspace.SETTINGS, Workspace.RATE_CARDS
    ],
    "manager": [
        Workspace.DASHBOARD, Workspace.DISPATCH, Workspace.SALES,
        Workspace.ACCOUNTING, Workspace.HR, Workspace.FLEET,
        Workspace.REPORTS, Workspace.RATE_CARDS
    ],
    "dispatcher": [
        Workspace.DASHBOARD, Workspace.DISPATCH, Workspace.FLEET,
        Workspace.DRIVER_APP
    ],
    "billing": [
        Workspace.DASHBOARD, Workspace.ACCOUNTING, Workspace.REPORTS,
        Workspace.RATE_CARDS
    ],
    "driver": [
        Workspace.DRIVER_APP
    ],
    "viewer": [
        Workspace.DASHBOARD, Workspace.REPORTS
    ],
}


def get_user_workspaces(role: str) -> List[str]:
    """Get list of workspaces a user can access based on their role"""
    normalized_role = normalize_role(role)
    workspaces = WORKSPACE_ACCESS_MAP.get(normalized_role, [])
    return [ws.value for ws in workspaces]


def has_workspace_access(role: str, workspace: str) -> bool:
    """Check if a role has access to a specific workspace"""
    allowed = get_user_workspaces(role)
    return workspace in allowed


# =============================================================================
# PERMISSION DEFINITIONS
# =============================================================================

# Default permissions by role
DEFAULT_ROLE_PERMISSIONS = {
    "platform_admin": {
        "view_all_tenants": True,
        "manage_all_tenants": True,
        "manage_all_users": True,
        "view_platform_analytics": True,
        "manage_platform_settings": True,
        "manage_subscriptions": True,
        "view_billing": True,
        "manage_billing": True,
    },
    "admin": {
        "view_tenant_data": True,
        "manage_tenant_data": True,
        "manage_tenant_users": True,
        "view_tenant_analytics": True,
        "manage_tenant_settings": True,
        "view_billing": True,
        "manage_billing": True,
        "manage_integrations": True,
    },
    "manager": {
        "view_tenant_data": True,
        "manage_department_data": True,
        "manage_department_users": True,
        "view_department_analytics": True,
    },
    "dispatcher": {
        "view_loads": True,
        "manage_loads": True,
        "view_drivers": True,
        "assign_drivers": True,
        "view_tracking": True,
        "send_messages": True,
    },
    "driver": {
        "view_assigned_loads": True,
        "update_load_status": True,
        "upload_documents": True,
        "update_location": True,
        "view_messages": True,
        "send_messages": True,
    },
    "billing": {
        "view_tenant_data": True,
        "view_billing": True,
        "manage_billing": True,
        "view_invoices": True,
        "manage_invoices": True,
        "view_reports": True,
    },
    "viewer": {
        "view_tenant_data": True,
    },
}


def get_user_permissions(role: str, custom_permissions: Dict[str, bool] = None) -> Dict[str, bool]:
    """
    Get effective permissions for a user based on role and custom overrides
    """
    # Normalize legacy roles
    normalized_role = normalize_role(role)
    
    # Get default permissions for role
    base_permissions = DEFAULT_ROLE_PERMISSIONS.get(normalized_role, {}).copy()
    
    # Apply custom permission overrides
    if custom_permissions:
        base_permissions.update(custom_permissions)
    
    return base_permissions


def has_permission(user: User, permission: str) -> bool:
    """Check if user has a specific permission"""
    effective_permissions = get_user_permissions(user.role.value, user.permissions)
    return effective_permissions.get(permission, False)


# =============================================================================
# DRIVER-SPECIFIC MODELS
# =============================================================================

class DriverCreate(BaseModel):
    """Create a new driver with extended fields"""
    # Basic info
    email: EmailStr
    full_name: str
    phone: str
    password: str
    
    # Employment type (Canada-first)
    worker_type: WorkerType = WorkerType.T4_EMPLOYEE
    
    # License info (Canada-first)
    license_number: Optional[str] = None
    license_class: Optional[LicenseClass] = None       # Class 1/A, Class 3/D, etc.
    license_province: Optional[str] = None             # Issuing province
    license_expiry: Optional[str] = None
    endorsements: List[str] = []                       # Z, TDG, etc.
    
    # Medical
    medical_card_expiry: Optional[str] = None
    
    # Employment
    hire_date: Optional[str] = None
    home_terminal: Optional[str] = None
    
    # Emergency contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    
    # Status
    driver_status: str = "available"
    
    # Owner-Operator specific (T4A Contractors)
    oo_company_name: Optional[str] = None              # Business name
    oo_business_number: Optional[str] = None           # Canadian BN (like US EIN)
    oo_gst_number: Optional[str] = None                # GST/HST registration
    oo_insurance_expiry: Optional[str] = None          # Own insurance
    oo_vehicle_id: Optional[str] = None                # Their own truck
    
    # Operating area
    operating_provinces: List[str] = []
    
    # Notes
    notes: Optional[str] = None


class DriverUpdate(BaseModel):
    """Update driver fields"""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    worker_type: Optional[WorkerType] = None
    license_number: Optional[str] = None
    license_class: Optional[LicenseClass] = None
    license_province: Optional[str] = None
    license_expiry: Optional[str] = None
    endorsements: Optional[List[str]] = None
    medical_card_expiry: Optional[str] = None
    driver_status: Optional[str] = None
    operating_provinces: Optional[List[str]] = None
    # Owner-operator fields
    oo_company_name: Optional[str] = None
    oo_business_number: Optional[str] = None
    oo_gst_number: Optional[str] = None
    oo_insurance_expiry: Optional[str] = None
    oo_vehicle_id: Optional[str] = None
    notes: Optional[str] = None
