"""
TMS Vehicles Models - Phase 4
Restructure equipment → vehicles with Canadian trucking standards
VIN, license plates, inspections, maintenance tracking
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone, date
import uuid


# =============================================================================
# ENUMS - Vehicle Types & Status
# =============================================================================

class VehicleType(str, Enum):
    """Type of vehicle - Power units and trailers"""
    # Power Units (Tractors)
    TRACTOR_SLEEPER = "tractor_sleeper"       # Sleeper cab
    TRACTOR_DAY_CAB = "tractor_day_cab"       # Day cab
    STRAIGHT_TRUCK = "straight_truck"          # Box truck with cab
    SPRINTER_VAN = "sprinter_van"             # Cargo van
    BOX_TRUCK = "box_truck"                   # Cube van
    PICKUP_TRUCK = "pickup_truck"             # Pickup with trailer hitch
    
    # Trailers
    DRY_VAN_TRAILER = "dry_van_trailer"       # Standard 53' dry van
    REEFER_TRAILER = "reefer_trailer"         # Refrigerated trailer
    FLATBED_TRAILER = "flatbed_trailer"       # Flatbed
    STEP_DECK_TRAILER = "step_deck_trailer"   # Step deck/drop deck
    LOWBOY_TRAILER = "lowboy_trailer"         # Lowboy for heavy equipment
    CONESTOGA_TRAILER = "conestoga_trailer"   # Curtain side
    TANKER_TRAILER = "tanker_trailer"         # Liquid tanker
    HOPPER_TRAILER = "hopper_trailer"         # Grain/bulk hopper
    DUMP_TRAILER = "dump_trailer"             # End dump
    INTERMODAL_CHASSIS = "intermodal_chassis" # Container chassis
    
    # Other
    OTHER = "other"


class VehicleCategory(str, Enum):
    """Category of vehicle"""
    POWER_UNIT = "power_unit"                 # Tractors, trucks
    TRAILER = "trailer"                       # All trailer types


class VehicleStatus(str, Enum):
    """Current status of vehicle"""
    ACTIVE = "active"                         # In service
    AVAILABLE = "available"                   # Ready, not assigned
    IN_USE = "in_use"                        # Currently on a load
    MAINTENANCE = "maintenance"               # In shop
    OUT_OF_SERVICE = "out_of_service"        # OOS - failed inspection
    INACTIVE = "inactive"                     # Not in use
    SOLD = "sold"                            # No longer owned


class OwnershipType(str, Enum):
    """Vehicle ownership type"""
    COMPANY_OWNED = "company_owned"           # Owned by the company
    LEASED = "leased"                        # Leased vehicle
    OWNER_OPERATOR = "owner_operator"         # Owned by O/O contractor
    RENTAL = "rental"                        # Short-term rental
    INTERCHANGED = "interchanged"            # Interchanged from another carrier


class FuelType(str, Enum):
    """Fuel type"""
    DIESEL = "diesel"
    GASOLINE = "gasoline"
    ELECTRIC = "electric"
    HYBRID = "hybrid"
    CNG = "cng"                              # Compressed Natural Gas
    LNG = "lng"                              # Liquefied Natural Gas


# =============================================================================
# CANADIAN INSPECTION & COMPLIANCE
# =============================================================================

class InspectionType(str, Enum):
    """Types of vehicle inspections"""
    # Canadian
    CVIP = "cvip"                            # Commercial Vehicle Inspection Program (annual)
    NSC_13 = "nsc_13"                        # NSC Standard 13 Trip Inspection
    PRE_TRIP = "pre_trip"                    # Driver pre-trip inspection
    POST_TRIP = "post_trip"                  # Driver post-trip inspection
    
    # US
    DOT_ANNUAL = "dot_annual"                # DOT annual inspection
    ROADSIDE = "roadside"                    # CVSA roadside inspection
    
    # Maintenance
    PM_SERVICE = "pm_service"                # Preventive maintenance
    BRAKE_INSPECTION = "brake_inspection"    # Brake-specific inspection


class InspectionResult(str, Enum):
    """Result of inspection"""
    PASSED = "passed"
    FAILED = "failed"
    CONDITIONAL = "conditional"              # Minor issues, can operate
    OUT_OF_SERVICE = "out_of_service"       # Cannot operate until fixed


class InspectionRecord(BaseModel):
    """Record of a vehicle inspection"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    vehicle_id: str
    
    # Inspection details
    inspection_type: InspectionType
    inspection_date: date
    expiry_date: Optional[date] = None       # For annual inspections
    
    # Location
    location: Optional[str] = None           # Where inspection was done
    inspector_name: Optional[str] = None
    inspector_license: Optional[str] = None   # Inspector certification #
    
    # Result
    result: InspectionResult
    defects_found: List[str] = []            # List of defects
    defects_corrected: List[str] = []        # Defects fixed
    
    # Documents
    inspection_report_url: Optional[str] = None
    sticker_number: Optional[str] = None      # CVIP/DOT sticker number
    
    # Cost
    cost: Optional[float] = None
    
    # Notes
    notes: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None


# =============================================================================
# MAINTENANCE TRACKING
# =============================================================================

class MaintenanceType(str, Enum):
    """Types of maintenance"""
    PREVENTIVE = "preventive"                # Scheduled PM
    CORRECTIVE = "corrective"                # Repair after failure
    EMERGENCY = "emergency"                  # Breakdown repair
    RECALL = "recall"                        # Manufacturer recall
    UPGRADE = "upgrade"                      # Enhancement/upgrade


class MaintenanceStatus(str, Enum):
    """Status of maintenance work order"""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    WAITING_PARTS = "waiting_parts"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MaintenanceRecord(BaseModel):
    """Record of vehicle maintenance"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    vehicle_id: str
    
    # Work order details
    work_order_number: Optional[str] = None
    maintenance_type: MaintenanceType
    status: MaintenanceStatus = MaintenanceStatus.SCHEDULED
    
    # Description
    description: str
    service_items: List[str] = []            # List of services performed
    parts_used: List[Dict[str, Any]] = []    # Parts with costs
    
    # Scheduling
    scheduled_date: Optional[date] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Odometer/Hours
    odometer_at_service: Optional[int] = None     # km or miles
    engine_hours_at_service: Optional[float] = None
    
    # Location & Vendor
    shop_name: Optional[str] = None
    shop_location: Optional[str] = None
    technician_name: Optional[str] = None
    
    # Cost
    labor_cost: float = 0.0
    parts_cost: float = 0.0
    total_cost: float = 0.0
    
    # Documents
    invoice_url: Optional[str] = None
    work_order_url: Optional[str] = None
    
    # Notes
    notes: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None


# =============================================================================
# VEHICLE MODELS
# =============================================================================

class VehicleBase(BaseModel):
    """Base vehicle fields"""
    # Identification
    unit_number: str                          # Fleet unit number (e.g., "T-101", "TR-205")
    vehicle_type: VehicleType
    category: VehicleCategory = VehicleCategory.POWER_UNIT
    
    # VIN & Registration
    vin: Optional[str] = None                 # Vehicle Identification Number (17 chars)
    license_plate: Optional[str] = None
    license_plate_province: Optional[str] = None   # Province/state of registration
    license_plate_expiry: Optional[date] = None
    
    # Vehicle Details
    year: Optional[int] = None
    make: Optional[str] = None                # e.g., "Freightliner", "Kenworth", "Volvo"
    model: Optional[str] = None               # e.g., "Cascadia", "T680", "VNL"
    color: Optional[str] = None
    
    # Specifications
    fuel_type: FuelType = FuelType.DIESEL
    gross_vehicle_weight_kg: Optional[int] = None   # GVW in kg
    gross_vehicle_weight_lbs: Optional[int] = None  # GVW in lbs
    axle_count: Optional[int] = None
    sleeper: bool = False                     # Has sleeper cab (for tractors)
    
    # For trailers
    trailer_length_ft: Optional[int] = None   # 53, 48, 28, etc.
    trailer_width_ft: Optional[float] = None
    trailer_height_ft: Optional[float] = None
    reefer_unit_make: Optional[str] = None    # For reefer: Carrier, Thermo King
    reefer_unit_model: Optional[str] = None
    reefer_unit_serial: Optional[str] = None
    
    # Ownership
    ownership_type: OwnershipType = OwnershipType.COMPANY_OWNED
    owner_operator_id: Optional[str] = None   # If owned by O/O
    lease_company: Optional[str] = None       # If leased
    lease_end_date: Optional[date] = None
    
    # Financial
    purchase_date: Optional[date] = None
    purchase_price: Optional[float] = None
    current_value: Optional[float] = None     # Book value
    
    # Insurance
    insurance_policy_number: Optional[str] = None
    insurance_expiry: Optional[date] = None
    
    # Odometer / Hours
    current_odometer_km: Optional[int] = None
    current_odometer_miles: Optional[int] = None
    engine_hours: Optional[float] = None
    
    # Assignment
    assigned_driver_id: Optional[str] = None  # Primary driver
    co_driver_id: Optional[str] = None        # Co-driver for team
    
    # Home terminal
    home_terminal: Optional[str] = None       # Home base location
    
    # GPS/ELD
    eld_provider: Optional[str] = None        # Keep Truckin, Samsara, etc.
    eld_device_id: Optional[str] = None
    gps_device_id: Optional[str] = None
    
    # Current location
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    last_location_update: Optional[datetime] = None
    
    # Notes
    notes: Optional[str] = None


class VehicleCreate(VehicleBase):
    """Create a new vehicle"""
    tenant_id: str
    carrier_id: Optional[str] = None          # Which carrier owns/operates


class VehicleUpdate(BaseModel):
    """Update vehicle fields"""
    unit_number: Optional[str] = None
    vehicle_type: Optional[VehicleType] = None
    vin: Optional[str] = None
    license_plate: Optional[str] = None
    license_plate_province: Optional[str] = None
    license_plate_expiry: Optional[date] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    fuel_type: Optional[FuelType] = None
    gross_vehicle_weight_kg: Optional[int] = None
    ownership_type: Optional[OwnershipType] = None
    owner_operator_id: Optional[str] = None
    assigned_driver_id: Optional[str] = None
    co_driver_id: Optional[str] = None
    current_odometer_km: Optional[int] = None
    current_odometer_miles: Optional[int] = None
    engine_hours: Optional[float] = None
    status: Optional[VehicleStatus] = None
    eld_provider: Optional[str] = None
    eld_device_id: Optional[str] = None
    home_terminal: Optional[str] = None
    notes: Optional[str] = None


class Vehicle(VehicleBase):
    """Complete vehicle model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    carrier_id: Optional[str] = None          # FK to carriers_brokers
    
    # Status
    status: VehicleStatus = VehicleStatus.AVAILABLE
    
    # Inspection tracking
    last_cvip_date: Optional[date] = None     # Last annual inspection
    cvip_expiry_date: Optional[date] = None   # When CVIP expires
    cvip_sticker_number: Optional[str] = None
    last_pm_date: Optional[date] = None       # Last preventive maintenance
    next_pm_due_date: Optional[date] = None
    next_pm_due_km: Optional[int] = None      # Or by odometer
    
    # Compliance alerts
    is_cvip_expired: bool = False
    is_registration_expired: bool = False
    is_insurance_expired: bool = False
    days_until_cvip_expiry: Optional[int] = None
    
    # Performance metrics
    total_miles: int = 0
    total_loads: int = 0
    average_mpg: Optional[float] = None       # Fuel efficiency
    
    # Current load (if in use)
    current_shipment_id: Optional[str] = None
    
    # Documents
    registration_document_url: Optional[str] = None
    insurance_document_url: Optional[str] = None
    lease_agreement_url: Optional[str] = None
    photos: List[str] = []
    
    # Legacy compatibility (from old equipment model)
    is_available: bool = True                 # Maps to status == available
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


class VehicleResponse(BaseModel):
    """Vehicle response with computed fields"""
    id: str
    unit_number: str
    vehicle_type: str
    category: str
    vin: Optional[str] = None
    license_plate: Optional[str] = None
    year_make_model: Optional[str] = None     # Combined "2022 Freightliner Cascadia"
    status: str
    assigned_driver_name: Optional[str] = None
    current_location: Optional[str] = None
    last_location_update: Optional[str] = None
    cvip_status: str = "valid"                # valid, expiring_soon, expired
    days_until_cvip_expiry: Optional[int] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_cvip_status(cvip_expiry_date: Optional[date]) -> tuple:
    """
    Calculate CVIP inspection status
    Returns (status, days_until_expiry)
    """
    if not cvip_expiry_date:
        return ("unknown", None)
    
    today = date.today()
    days_until = (cvip_expiry_date - today).days
    
    if days_until < 0:
        return ("expired", days_until)
    elif days_until <= 30:
        return ("expiring_soon", days_until)
    elif days_until <= 60:
        return ("expiring", days_until)
    else:
        return ("valid", days_until)


def format_year_make_model(year: int, make: str, model: str) -> str:
    """Format vehicle year/make/model into single string"""
    parts = []
    if year:
        parts.append(str(year))
    if make:
        parts.append(make)
    if model:
        parts.append(model)
    return " ".join(parts) if parts else "Unknown"


def calculate_next_pm_date(
    last_pm_date: Optional[date],
    pm_interval_days: int = 90,          # Default 90 days
    last_pm_km: Optional[int] = None,
    current_km: Optional[int] = None,
    pm_interval_km: int = 40000          # Default 40,000 km
) -> Optional[date]:
    """
    Calculate next PM due date based on time or mileage
    Returns the earlier of the two
    """
    from datetime import timedelta
    
    next_by_date = None
    next_by_km = None
    
    if last_pm_date:
        next_by_date = last_pm_date + timedelta(days=pm_interval_days)
    
    if last_pm_km and current_km:
        km_remaining = (last_pm_km + pm_interval_km) - current_km
        if km_remaining > 0:
            # Estimate days based on average 500 km/day
            days_remaining = km_remaining // 500
            next_by_km = date.today() + timedelta(days=days_remaining)
        else:
            # Already overdue by mileage
            next_by_km = date.today()
    
    # Return the earlier date
    if next_by_date and next_by_km:
        return min(next_by_date, next_by_km)
    return next_by_date or next_by_km


# =============================================================================
# VEHICLE LOCATION TRACKING
# =============================================================================

class VehicleLocationUpdate(BaseModel):
    """Real-time location update for a vehicle"""
    vehicle_id: str
    latitude: float
    longitude: float
    speed_kmh: Optional[float] = None
    heading: Optional[float] = None           # 0-360 degrees
    odometer_km: Optional[int] = None
    engine_hours: Optional[float] = None
    fuel_level_percent: Optional[float] = None
    ignition_on: bool = True
    source: str = "gps"                       # gps, eld, manual
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VehicleLocationHistory(BaseModel):
    """Historical location record"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    vehicle_id: str
    latitude: float
    longitude: float
    speed_kmh: Optional[float] = None
    heading: Optional[float] = None
    odometer_km: Optional[int] = None
    recorded_at: datetime
    source: str = "gps"


# =============================================================================
# DRIVER-VEHICLE ASSIGNMENT
# =============================================================================

class DriverVehicleAssignment(BaseModel):
    """Track driver-vehicle assignments over time"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    driver_id: str
    vehicle_id: str
    
    # Assignment type
    is_primary: bool = True                   # Primary assignment vs temporary
    
    # Period
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    unassigned_at: Optional[datetime] = None
    
    # Odometer at assignment
    odometer_at_assignment: Optional[int] = None
    odometer_at_unassignment: Optional[int] = None
    
    # Notes
    assignment_reason: Optional[str] = None
    unassignment_reason: Optional[str] = None
    
    # Audit
    assigned_by: Optional[str] = None
    unassigned_by: Optional[str] = None
