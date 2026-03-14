from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal, Dict
from enum import Enum
from datetime import datetime, timezone
import uuid

# Enums
class UserRole(str, Enum):
    PLATFORM_ADMIN = "platform_admin"  # Platform owner (SAAS provider)
    COMPANY_ADMIN = "company_admin"    # Customer company admin
    MANAGER = "manager"                # Company manager
    DISPATCHER = "dispatcher"          # Dispatcher role
    ACCOUNTANT = "accountant"          # Accountant role
    HR_MANAGER = "hr_manager"          # HR Manager role
    SALES_MANAGER = "sales_manager"    # Sales Manager role
    DRIVER = "driver"                  # Driver role
    FLEET_MANAGER = "fleet_manager"    # Fleet Manager role
    # Legacy roles (keep for backward compatibility)
    FLEET_OWNER = "fleet_owner"        # Legacy - maps to COMPANY_ADMIN
    MANUFACTURER = "manufacturer"
    CONSTRUCTION_COMPANY = "construction_company"
    WAREHOUSE = "warehouse"
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    ACCOUNTS_PAYABLE = "accounts_payable"
    HR = "hr"

class CompanyType(str, Enum):
    TRUCKING = "trucking"
    MANUFACTURING = "manufacturing"
    CONSTRUCTION = "construction"
    WAREHOUSE = "warehouse"
    EQUIPMENT_RENTAL = "equipment_rental"

class EquipmentType(str, Enum):
    BOX_TRUCK = "box_truck"
    SPRINTER_VAN = "sprinter_van"
    HVAC_TRUCK = "hvac_truck"
    CRANE = "crane"
    FLATBED_TRUCK = "flatbed_truck"
    DRY_VAN = "dry_van"
    REEFER = "reefer"
    BIG_RIG = "big_rig"
    FORKLIFT = "forklift"
    EXCAVATOR = "excavator"
    TRACTOR = "tractor"

class RegistrationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"

# User Models
class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: str
    role: UserRole
    
class UserCreate(UserBase):
    password: str

class DriverCreate(BaseModel):
    email: EmailStr
    full_name: str
    phone: str
    password: str
    # Extended driver fields
    license_number: Optional[str] = None
    license_type: Optional[str] = None  # CDL_A, CDL_B, CDL_C, NON_CDL
    license_state: Optional[str] = None
    license_expiry: Optional[str] = None
    medical_card_expiry: Optional[str] = None
    endorsements: Optional[List[str]] = []
    hire_date: Optional[str] = None
    home_terminal: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    driver_status: Optional[str] = "available"
    notes: Optional[str] = None
    
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(UserBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    registration_status: RegistrationStatus = RegistrationStatus.PENDING
    fleet_owner_id: Optional[str] = None  # For drivers
    email_verified: bool = False
    verification_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    password_hash: Optional[str] = None  # For storing hashed password

# Document Models
class DocumentVersion(BaseModel):
    url: str
    filename: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    uploaded_by: str
    file_size: int  # in bytes

# Company Models
class CompanyBase(BaseModel):
    name: str
    company_type: CompanyType
    address: str
    city: str
    state: str
    zip_code: str
    country: str = "USA"
    tax_id: Optional[str] = None
    # Transportation credentials
    mc_number: Optional[str] = None  # Motor Carrier Number
    dot_number: Optional[str] = None  # Department of Transportation Number
    nsc_number: Optional[str] = None  # National Safety Code (Canadian)
    # Contact information
    phone_number: Optional[str] = None
    company_email: Optional[str] = None  # Linked with MC# account
    correspondence_email: Optional[str] = None
    website: Optional[str] = None
    # Company branding
    logo_url: Optional[str] = None
    theme: Optional[dict] = None
    # Documents with version history
    company_documents: Optional[Dict[str, List[dict]]] = Field(default_factory=lambda: {
        "mc_authority": [],
        "insurance_certificate": [],
        "w9": []
    })
    
class CompanyCreate(CompanyBase):
    pass

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    tax_id: Optional[str] = None
    mc_number: Optional[str] = None
    dot_number: Optional[str] = None
    nsc_number: Optional[str] = None
    phone_number: Optional[str] = None
    company_email: Optional[str] = None
    correspondence_email: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    plan: Optional[str] = None  # accepts id or label
    seats: Optional[int] = None
    feature_flags: Optional[Dict[str, bool]] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: Optional[str] = None
    integrations: Optional[Dict[str, list]] = None
    theme: Optional[dict] = None

class ProductSubscription(BaseModel):
    """Individual product subscription within a tenant"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    product_id: str  # Reference to PLANS
    status: str = "active"  # active, pending, canceled, trial
    seats_allocated: int = 5
    seats_used: int = 0
    storage_allocated_gb: int = 10
    storage_used_gb: float = 0.0
    discount_percentage: float = 0.0  # Percentage discount (0-100)
    discount_reason: Optional[str] = None  # Reason for special pricing
    start_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    next_billing_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    pending_changes: Optional[dict] = None  # Stores scheduled changes for next billing cycle

class Company(CompanyBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Legacy single-plan fields (kept for backward compatibility)
    plan: Optional[str] = "tms_basic"
    seats: Optional[int] = 5
    feature_flags: Dict[str, bool] = Field(default_factory=lambda: {
        "live_tracking": True,
        "eld_integration": False,
        "ai_rate_confirmation": True,
        "docs_versioning": True,
        "apps_marketplace": True,
        "brand_adaptive_theme": True,
        "export_downloads": True,
        "driver_app": False,
    })
    
    # New multi-product subscription model
    subscriptions: List[dict] = Field(default_factory=list)  # List of ProductSubscription dicts
    
    # Billing information
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: Optional[str] = None  # active, past_due, canceled
    billing_email: Optional[str] = None
    payment_method: Optional[str] = None  # card, invoice, etc.
    next_billing_date: Optional[datetime] = None
    
    # System
    integrations: Dict[str, list] = Field(default_factory=lambda: {"eld": []})
    verification_status: RegistrationStatus = RegistrationStatus.PENDING
    verification_documents: List[str] = []

# Equipment Models
class EquipmentBase(BaseModel):
    name: str
    equipment_type: EquipmentType
    description: str
    specifications: dict
    hourly_rate: float
    daily_rate: float
    location_address: str
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    
class EquipmentCreate(EquipmentBase):
    pass

class Equipment(EquipmentBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str
    company_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_available: bool = True
    images: List[str] = []
    insurance_documents: List[str] = []
    maintenance_records: List[str] = []
    current_driver_id: Optional[str] = None

# Location Models
class LocationUpdate(BaseModel):
    equipment_id: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    driver_id: Optional[str] = None
    speed: Optional[float] = Field(None, ge=0)
    heading: Optional[float] = Field(None, ge=0, lt=360)
    accuracy: Optional[float] = None
    
class VehicleStatus(BaseModel):
    vehicle_id: str
    status: Literal["active", "idle", "offline", "maintenance"] = "active"
    battery: Optional[int] = Field(None, ge=0, le=100)
    signal_strength: Optional[int] = Field(None, ge=0, le=100)

# Booking Models
class BookingBase(BaseModel):
    equipment_id: str
    start_date: datetime
    end_date: datetime
    pickup_location: str
    delivery_location: str
    notes: Optional[str] = None
    # Shipper information
    shipper_name: Optional[str] = None
    shipper_address: Optional[str] = None
    # Pickup details
    pickup_city: Optional[str] = None
    pickup_state: Optional[str] = None
    pickup_country: Optional[str] = "USA"
    # Delivery details
    delivery_city: Optional[str] = None
    delivery_state: Optional[str] = None
    delivery_country: Optional[str] = "USA"
    # Cargo information
    commodity: Optional[str] = None
    weight: Optional[float] = None  # in lbs
    cubes: Optional[float] = None  # cubic feet
    # Vehicle and driver information
    tractor_number: Optional[str] = None
    trailer_number: Optional[str] = None
    driver_name: Optional[str] = None
    driver_id: Optional[str] = None
    # Timing information
    pickup_time_planned: Optional[datetime] = None
    pickup_time_actual: Optional[datetime] = None
    pickup_time_actual_in: Optional[datetime] = None
    pickup_time_actual_out: Optional[datetime] = None
    delivery_time_planned: Optional[datetime] = None
    delivery_time_actual: Optional[datetime] = None
    delivery_time_actual_in: Optional[datetime] = None
    delivery_time_actual_out: Optional[datetime] = None
    # Carrier/Driver assignment (for dispatch)
    assigned_carrier: Optional[str] = None
    assigned_driver: Optional[str] = None
    # Rate information
    confirmed_rate: Optional[float] = None  # Rate WITHOUT margin (for Dispatch)
    customer_rate: Optional[float] = None   # Rate WITH margin (for Sales)
    margin_percentage: Optional[float] = None  # Margin % applied
    
class BookingCreate(BookingBase):
    pass

class DispatchUpdate(BaseModel):
    """Model for dispatch-specific updates"""
    assigned_carrier: Optional[str] = None
    assigned_driver: Optional[str] = None
    pickup_time_actual_in: Optional[datetime] = None
    pickup_time_actual_out: Optional[datetime] = None
    delivery_time_actual_in: Optional[datetime] = None
    delivery_time_actual_out: Optional[datetime] = None

class Booking(BookingBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_number: str = Field(default_factory=lambda: f"ORD-{str(uuid.uuid4())[:8].upper()}")
    requester_id: str
    equipment_owner_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["pending", "planned", "in_transit_pickup", "at_pickup", "in_transit_delivery", "at_delivery", "delivered", "invoiced", "payment_overdue", "paid"] = "pending"
    total_cost: Optional[float] = None

# CRM Models
class CRMContact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    ext: Optional[str] = None  # Phone extension
    company: Optional[str] = None
    position: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    status: str = "cold_lead"  # cold_lead, hot_lead, customer
    notes: Optional[str] = None
    source: Optional[str] = None  # referral, website, campaign, etc.
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_id: Optional[str] = None  # User who owns this contact

class CRMDeal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    value: float
    stage: str = "prospecting"  # prospecting, qualification, proposal, negotiation, closed_won, closed_lost
    contact_id: str
    expected_close_date: Optional[datetime] = None
    probability: int = 50  # 0-100
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_id: Optional[str] = None

class CRMActivity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str  # call, email, meeting, note, task
    subject: str
    description: Optional[str] = None
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None
    due_date: Optional[datetime] = None
    completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_id: Optional[str] = None

class CRMNote(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None

class CRMCompany(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    employee_count: Optional[int] = None
    annual_revenue: Optional[float] = None
    company_type: str = "prospect"  # prospect, customer, partner, vendor
    status: str = "active"  # active, inactive, churned
    parent_company: Optional[str] = None
    account_owner: Optional[str] = None
    primary_contact_id: Optional[str] = None
    founded_date: Optional[str] = None
    customer_since: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_id: Optional[str] = None

class CRMActivityLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    user_email: str
    action: str  # created, updated, deleted
    entity_type: str  # contact, company, deal
    entity_id: str
    entity_name: str
    details: Optional[dict] = None  # Stores what changed
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Subscription Plans
PLANS = [
    {
        "id": "tms_basic",
        "label": "Transportation Management System",
        "price": 299,
        "default_seats": 5,
        "status": "active",
        "tier": "TMS Basic",
        "subtitle": "Complete Fleet & Logistics Solution",
        "description": "Manage your entire fleet operations with real-time tracking, order management, and comprehensive analytics. Perfect for trucking companies, fleet owners, and logistics providers.",
        "features": [
            "Real-time GPS Tracking",
            "Order & Booking Management",
            "Fleet & Equipment Management",
            "Driver Management",
            "+ 4 more features"
        ],
        "all_features": [
            "Real-time GPS Tracking",
            "Order & Booking Management",
            "Fleet & Equipment Management",
            "Driver Management",
            "Company Profile",
            "User Management",
            "Document Version History",
            "Brand Adaptive Theming"
        ],
        "feature_flags": {
            "live_tracking": True,
            "eld_integration": False,
            "ai_rate_confirmation": False,
            "docs_versioning": True,
            "apps_marketplace": False,
            "brand_adaptive_theme": True,
            "export_downloads": True,
            "driver_app": False,
            "fleet_management": True,
            "booking_management": True,
            "driver_management": True,
        },
    },
    {
        "id": "tms_pro",
        "label": "Transportation Management System",
        "price": 299,
        "default_seats": 15,
        "status": "active",
        "tier": "TMS Pro",
        "subtitle": "Complete Fleet & Logistics Solution",
        "description": "Manage your entire fleet operations with real-time tracking, order management, and comprehensive analytics. Perfect for trucking companies, fleet owners, and logistics providers.",
        "features": [
            "Real-time GPS Tracking",
            "Order & Booking Management",
            "Fleet & Equipment Management",
            "Driver Management",
            "+ 4 more features"
        ],
        "all_features": [
            "Real-time GPS Tracking",
            "Order & Booking Management",
            "Fleet & Equipment Management",
            "Driver Management",
            "Company Profile",
            "User Management",
            "Document Version History",
            "Brand Adaptive Theming"
        ],
        "feature_flags": {
            "live_tracking": True,
            "eld_integration": True,
            "ai_rate_confirmation": True,
            "docs_versioning": True,
            "apps_marketplace": True,
            "brand_adaptive_theme": True,
            "export_downloads": True,
            "driver_app": True,
            "fleet_management": True,
            "booking_management": True,
            "driver_management": True,
        },
    },
    {
        "id": "tms_enterprise",
        "label": "Transportation Management System",
        "price": 299,
        "default_seats": 50,
        "status": "active",
        "tier": "TMS Enterprise",
        "subtitle": "Complete Fleet & Logistics Solution",
        "description": "Manage your entire fleet operations with real-time tracking, order management, and comprehensive analytics. Perfect for trucking companies, fleet owners, and logistics providers.",
        "features": [
            "Real-time GPS Tracking",
            "Order & Booking Management",
            "Fleet & Equipment Management",
            "Driver Management",
            "+ 4 more features"
        ],
        "all_features": [
            "Real-time GPS Tracking",
            "Order & Booking Management",
            "Fleet & Equipment Management",
            "Driver Management",
            "Company Profile",
            "User Management",
            "Document Version History",
            "Brand Adaptive Theming"
        ],
        "feature_flags": {
            "live_tracking": True,
            "eld_integration": True,
            "ai_rate_confirmation": True,
            "docs_versioning": True,
            "apps_marketplace": True,
            "brand_adaptive_theme": True,
            "export_downloads": True,
            "driver_app": True,
            "fleet_management": True,
            "booking_management": True,
            "driver_management": True,
            "user_management": True,
            "advanced_analytics": True,
            "custom_integrations": True,
            "priority_support": True,
        },
    },
    {
        "id": "heavy_tms",
        "label": "Heavy Transportation Management System",
        "price": 399,
        "default_seats": 15,
        "status": "coming_soon",
        "subtitle": "Specialized Heavy Haul Operations",
        "description": "Purpose-built for oversized loads, heavy equipment hauling, and specialized transportation with permit management and route planning.",
        "features": [
            "Oversized Load Management",
            "Permit Tracking & Management",
            "Route Planning for Heavy Loads",
            "Equipment Specifications",
            "+ 2 more features"
        ],
        "all_features": [
            "Oversized Load Management",
            "Permit Tracking & Management",
            "Route Planning for Heavy Loads",
            "Equipment Specifications",
            "Weight Distribution Analysis",
            "Escort Coordination"
        ],
        "feature_flags": {
            "oversized_load_management": True,
            "permit_tracking": True,
            "route_planning": True,
            "equipment_specs": True,
        },
    },
    {
        "id": "broker_management",
        "label": "Broker Management System",
        "price": 349,
        "default_seats": 10,
        "status": "coming_soon",
        "subtitle": "Freight Brokerage Platform",
        "description": "Streamline freight brokerage operations with carrier management, load matching, and automated workflows for brokers and freight forwarders.",
        "features": [
            "Carrier Network Management",
            "Load Board Integration",
            "Automated Load Matching",
            "Rate Management",
            "+ 2 more features"
        ],
        "all_features": [
            "Carrier Network Management",
            "Load Board Integration",
            "Automated Load Matching",
            "Rate Management",
            "Commission Tracking",
            "Broker Analytics"
        ],
        "feature_flags": {
            "carrier_management": True,
            "load_board": True,
            "auto_matching": True,
            "rate_management": True,
        },
    },
    {
        "id": "dispatch_management",
        "label": "Dispatch Management System",
        "price": 279,
        "default_seats": 8,
        "status": "coming_soon",
        "subtitle": "Intelligent Dispatch Operations",
        "description": "Optimize dispatching with real-time load assignment, driver communication, and route optimization for maximum efficiency.",
        "features": [
            "Real-time Dispatch Board",
            "Load Assignment & Optimization",
            "Driver Communication",
            "Route Optimization",
            "+ 2 more features"
        ],
        "all_features": [
            "Real-time Dispatch Board",
            "Load Assignment & Optimization",
            "Driver Communication",
            "Route Optimization",
            "ETA Tracking",
            "Automated Notifications"
        ],
        "feature_flags": {
            "dispatch_board": True,
            "load_assignment": True,
            "driver_comm": True,
            "route_optimization": True,
        },
    },
    {
        "id": "freight_management",
        "label": "Freight Management System",
        "price": 329,
        "default_seats": 12,
        "status": "coming_soon",
        "subtitle": "End-to-End Freight Operations",
        "description": "Complete freight management solution covering shipment tracking, carrier selection, documentation, and freight audit & payment.",
        "features": [
            "Shipment Tracking & Visibility",
            "Multi-Modal Transportation",
            "Carrier Selection & Rating",
            "BOL & Documentation",
            "+ 2 more features"
        ],
        "all_features": [
            "Shipment Tracking & Visibility",
            "Multi-Modal Transportation",
            "Carrier Selection & Rating",
            "BOL & Documentation",
            "Freight Audit & Payment",
            "Claims Management"
        ],
        "feature_flags": {
            "shipment_tracking": True,
            "multi_modal": True,
            "carrier_selection": True,
            "documentation": True,
        },
    },
    {
        "id": "vehicle_management",
        "label": "Vehicle Management System",
        "price": 249,
        "default_seats": 10,
        "status": "coming_soon",
        "subtitle": "Complete Fleet Maintenance & Asset Management",
        "description": "Comprehensive vehicle lifecycle management including maintenance scheduling, inspections, fuel management, and asset tracking.",
        "features": [
            "Preventive Maintenance Scheduling",
            "Vehicle Inspections (DVIR)",
            "Fuel Management & Tracking",
            "Service History & Records",
            "+ 2 more features"
        ],
        "all_features": [
            "Preventive Maintenance Scheduling",
            "Vehicle Inspections (DVIR)",
            "Fuel Management & Tracking",
            "Service History & Records",
            "Asset Depreciation",
            "Warranty Management"
        ],
        "feature_flags": {
            "maintenance_scheduling": True,
            "vehicle_inspections": True,
            "fuel_tracking": True,
            "service_history": True,
        },
    },
    {
        "id": "safety_compliance",
        "label": "Safety and Compliance System",
        "price": 199,
        "default_seats": 5,
        "status": "coming_soon",
        "subtitle": "DOT Compliance & Safety Management",
        "description": "Ensure full regulatory compliance with DOT, FMCSA, and safety regulations. Manage driver qualifications, HOS, drug testing, and safety programs.",
        "features": [
            "DOT/FMCSA Compliance Tracking",
            "Driver Qualification Files (DQF)",
            "Hours of Service (HOS) Management",
            "Drug & Alcohol Testing Programs",
            "+ 2 more features"
        ],
        "all_features": [
            "DOT/FMCSA Compliance Tracking",
            "Driver Qualification Files (DQF)",
            "Hours of Service (HOS) Management",
            "Drug & Alcohol Testing Programs",
            "Safety Score Monitoring",
            "Violation Management"
        ],
        "feature_flags": {
            "dot_compliance": True,
            "dqf_management": True,
            "hos_management": True,
            "drug_testing": True,
        },
    },
    {
        "id": "integrated_route_mate",
        "label": "Integrated Route Mate",
        "price": 449,
        "default_seats": 20,
        "status": "active",
        "tier": "Territory Planner",
        "subtitle": "AI-Powered Route & Territory Optimization",
        "description": "Plan routes with a comprehensive, pre-emptive approach. Model delivery scenarios and route improvements while managing operations with advanced routing algorithms and historical data. Eliminate tedious manual re-routing and boost productivity.",
        "features": [
            "Advanced Routing Algorithms (VRP/CVRP)",
            "Automated Strategic Re-routing",
            "Historical Data Analysis & Forecasting",
            "Intelligent Route Scoring & Selection",
            "Capacity Balancing Across Routes",
            "Territory Exception Management",
            "+ 6 more features"
        ],
        "all_features": [
            "Advanced Routing Algorithms (VRP/CVRP)",
            "Automated Strategic Re-routing",
            "Historical Data Analysis & Forecasting",
            "Intelligent Route Scoring & Selection",
            "Capacity Balancing Across Routes",
            "Territory Exception Management",
            "Customer-Specific Needs & Constraints",
            "Digestible Route Statistics Dashboard",
            "Configurable Sales/Service/Distribution Reports",
            "Resource Allocation Optimization",
            "Route Change Impact Forecasting",
            "Time Window Optimization"
        ],
        "feature_flags": {
            "route_optimization": True,
            "territory_planning": True,
            "historical_analysis": True,
            "ai_forecasting": True,
            "automated_rerouting": True,
            "capacity_balancing": True,
            "exception_handling": True,
            "custom_reports": True,
            "intelligent_scoring": True,
        },
    },
    {
        "id": "driver_app",
        "label": "Driver App",
        "price": 0,
        "default_seats": 0,
        "status": "active",
        "tier": "Mobile Driver App",
        "subtitle": "Mobile App for Drivers on Android & iOS",
        "description": "Empower your drivers with a mobile app for Android and iOS devices. Drivers receive dispatch assignments, update order status in real-time, and access GPS navigation with turn-by-turn directions. Requires an active TMS subscription.",
        "features": [
            "Receive Dispatch Assignments",
            "Confirm Load Acceptance",
            "Real-time Order Status Updates",
            "GPS Navigation with Route Visualization",
            "+ 2 more features"
        ],
        "all_features": [
            "Receive Dispatch Assignments",
            "Confirm Load Acceptance",
            "Real-time Order Status Updates",
            "GPS Navigation with Route Visualization",
            "Live Turn-by-Turn Directions",
            "Multi-Stop Route Planning",
            "Driver Profile Management",
            "Document Upload (POD, Signatures)"
        ],
        "feature_flags": {
            "dispatch_receive": True,
            "load_confirmation": True,
            "status_updates": True,
            "gps_navigation": True,
            "turn_by_turn": True,
            "multi_stop": True,
            "driver_profile": True,
            "document_upload": True,
        },
        "requirements": {
            "requires_tms": True,
            "platforms": ["Android", "iOS"]
        }
    },
]

PLAN_ID_BY_LABEL = {p["label"].lower(): p["id"] for p in PLANS}
PLANS_BY_ID = {p["id"]: p for p in PLANS}

def normalize_plan(plan_value: str) -> str:
    if not plan_value:
        return "tms_basic"
    v = plan_value.strip().lower()
    # accept either id or label
    if v in PLANS_BY_ID:
        return v
    return PLAN_ID_BY_LABEL.get(v, "tms_basic")
