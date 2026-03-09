"""
TMS Rate Cards & Accessorial Charges - Phase 6
Lane-based pricing, standard accessorial codes, customer-specific rates
Canada-First Design
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone, date
import uuid


# =============================================================================
# ENUMS - Rate Card Types
# =============================================================================

class RateType(str, Enum):
    """Type of rate calculation"""
    PER_MILE = "per_mile"                     # Rate per mile
    PER_KM = "per_km"                         # Rate per kilometer
    FLAT_RATE = "flat_rate"                   # Fixed rate per load
    PER_HUNDRED_WEIGHT = "per_cwt"            # Per 100 lbs (CWT)
    PER_PALLET = "per_pallet"                 # Per pallet
    PER_CUBE = "per_cube"                     # Per cubic foot/meter
    MINIMUM = "minimum"                       # Minimum charge


class AccessorialCode(str, Enum):
    """Standard accessorial charge codes"""
    # Detention & Waiting
    DET_PICKUP = "det_pickup"                 # Detention at pickup
    DET_DELIVERY = "det_delivery"             # Detention at delivery
    LAYOVER = "layover"                       # Layover/overnight wait
    
    # Loading/Unloading
    LUMPER = "lumper"                         # Lumper service
    DRIVER_ASSIST = "driver_assist"           # Driver assist loading/unloading
    HAND_UNLOAD = "hand_unload"               # Hand unload required
    
    # Equipment
    TARPING = "tarping"                       # Tarping charge
    STRAPPING = "strapping"                   # Strapping/securing
    TEMP_CONTROL = "temp_control"             # Temperature control
    TEAM_SERVICE = "team_service"             # Team drivers
    
    # Fuel
    FUEL_SURCHARGE = "fuel_surcharge"         # Fuel surcharge
    
    # Special Services
    HAZMAT = "hazmat"                         # Hazardous materials
    OVERWEIGHT = "overweight"                 # Overweight permit/fees
    OVERDIMENSIONAL = "overdimensional"       # Over-dimensional
    INSIDE_DELIVERY = "inside_delivery"       # Inside delivery
    LIFTGATE = "liftgate"                     # Liftgate service
    RESIDENTIAL = "residential"               # Residential delivery
    APPOINTMENT = "appointment"               # Appointment scheduling
    
    # Canadian Specific
    BORDER_CROSSING = "border_crossing"       # US/Canada border
    PARS_PAPS = "pars_paps"                   # PARS/PAPS customs
    BONDED_CARRIER = "bonded_carrier"         # Bonded carrier service
    
    # Storage
    STORAGE = "storage"                       # Storage fees
    REDELIVERY = "redelivery"                 # Redelivery charge
    
    # Administrative
    STOP_OFF = "stop_off"                     # Additional stop
    BILL_OF_LADING = "bol_fee"                # BOL preparation
    DOCUMENT_FEE = "document_fee"             # Documentation
    
    # Other
    OTHER = "other"                           # Custom/other


class AccessorialChargeType(str, Enum):
    """How accessorial is charged"""
    FLAT = "flat"                             # Flat fee
    PER_HOUR = "per_hour"                     # Per hour
    PER_MILE = "per_mile"                     # Per mile
    PER_KM = "per_km"                         # Per kilometer
    PERCENTAGE = "percentage"                 # Percentage of line haul
    PER_UNIT = "per_unit"                     # Per unit (pallet, piece, etc.)


class RateCardStatus(str, Enum):
    """Status of a rate card"""
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


# =============================================================================
# ACCESSORIAL CHARGE DEFINITIONS
# =============================================================================

class AccessorialDefinitionBase(BaseModel):
    """Base accessorial charge definition"""
    code: AccessorialCode
    name: str
    description: Optional[str] = None
    
    # Pricing
    charge_type: AccessorialChargeType = AccessorialChargeType.FLAT
    default_rate: float = 0.0
    minimum_charge: Optional[float] = None
    maximum_charge: Optional[float] = None
    
    # For hourly charges
    free_time_minutes: Optional[int] = None   # Free time before charges start
    
    # Tax
    is_taxable: bool = True
    
    # Status
    is_active: bool = True


class AccessorialDefinitionCreate(AccessorialDefinitionBase):
    """Create accessorial definition"""
    tenant_id: str


class AccessorialDefinition(AccessorialDefinitionBase):
    """Complete accessorial definition"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


# Default accessorial charges (Canadian standard)
DEFAULT_ACCESSORIALS = [
    {
        "code": "det_pickup",
        "name": "Detention at Pickup",
        "description": "Waiting time at pickup location beyond free time",
        "charge_type": "per_hour",
        "default_rate": 75.00,
        "free_time_minutes": 120,
        "is_taxable": True
    },
    {
        "code": "det_delivery",
        "name": "Detention at Delivery",
        "description": "Waiting time at delivery location beyond free time",
        "charge_type": "per_hour",
        "default_rate": 75.00,
        "free_time_minutes": 120,
        "is_taxable": True
    },
    {
        "code": "layover",
        "name": "Layover",
        "description": "Overnight layover due to shipper/receiver delay",
        "charge_type": "flat",
        "default_rate": 350.00,
        "is_taxable": True
    },
    {
        "code": "lumper",
        "name": "Lumper Service",
        "description": "Third-party loading/unloading service",
        "charge_type": "flat",
        "default_rate": 0.00,  # Pass-through at cost
        "is_taxable": True
    },
    {
        "code": "driver_assist",
        "name": "Driver Assist",
        "description": "Driver assistance with loading/unloading",
        "charge_type": "flat",
        "default_rate": 100.00,
        "is_taxable": True
    },
    {
        "code": "fuel_surcharge",
        "name": "Fuel Surcharge",
        "description": "Variable fuel surcharge based on fuel index",
        "charge_type": "percentage",
        "default_rate": 10.0,  # 10% of line haul
        "is_taxable": True
    },
    {
        "code": "stop_off",
        "name": "Stop-Off Charge",
        "description": "Additional pickup or delivery stop",
        "charge_type": "flat",
        "default_rate": 150.00,
        "is_taxable": True
    },
    {
        "code": "hazmat",
        "name": "Hazardous Materials",
        "description": "Hazmat handling and documentation",
        "charge_type": "flat",
        "default_rate": 250.00,
        "is_taxable": True
    },
    {
        "code": "temp_control",
        "name": "Temperature Control",
        "description": "Reefer temperature monitoring and control",
        "charge_type": "flat",
        "default_rate": 150.00,
        "is_taxable": True
    },
    {
        "code": "team_service",
        "name": "Team Service",
        "description": "Team drivers for expedited delivery",
        "charge_type": "per_mile",
        "default_rate": 0.35,  # Additional per mile
        "is_taxable": True
    },
    {
        "code": "liftgate",
        "name": "Liftgate Service",
        "description": "Liftgate required at pickup or delivery",
        "charge_type": "flat",
        "default_rate": 75.00,
        "is_taxable": True
    },
    {
        "code": "residential",
        "name": "Residential Delivery",
        "description": "Delivery to residential address",
        "charge_type": "flat",
        "default_rate": 100.00,
        "is_taxable": True
    },
    {
        "code": "inside_delivery",
        "name": "Inside Delivery",
        "description": "Delivery inside building beyond dock",
        "charge_type": "flat",
        "default_rate": 150.00,
        "is_taxable": True
    },
    {
        "code": "appointment",
        "name": "Appointment Fee",
        "description": "Scheduled appointment delivery",
        "charge_type": "flat",
        "default_rate": 50.00,
        "is_taxable": True
    },
    {
        "code": "border_crossing",
        "name": "Border Crossing",
        "description": "US/Canada border crossing fee",
        "charge_type": "flat",
        "default_rate": 200.00,
        "is_taxable": True
    },
    {
        "code": "pars_paps",
        "name": "PARS/PAPS Processing",
        "description": "Customs pre-arrival processing",
        "charge_type": "flat",
        "default_rate": 50.00,
        "is_taxable": True
    },
    {
        "code": "tarping",
        "name": "Tarping",
        "description": "Tarping flatbed loads",
        "charge_type": "flat",
        "default_rate": 100.00,
        "is_taxable": True
    },
    {
        "code": "redelivery",
        "name": "Redelivery",
        "description": "Redelivery due to customer issue",
        "charge_type": "flat",
        "default_rate": 200.00,
        "is_taxable": True
    },
    {
        "code": "storage",
        "name": "Storage",
        "description": "Daily storage fee",
        "charge_type": "flat",
        "default_rate": 50.00,  # Per day
        "is_taxable": True
    }
]


# =============================================================================
# RATE CARD MODELS
# =============================================================================

class LaneRate(BaseModel):
    """Rate for a specific lane (origin-destination pair)"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Origin
    origin_city: Optional[str] = None
    origin_province: Optional[str] = None     # Province/state code
    origin_country: str = "CA"
    origin_radius_km: int = 50                # Radius in km for origin match
    
    # Destination
    destination_city: Optional[str] = None
    destination_province: Optional[str] = None
    destination_country: str = "CA"
    destination_radius_km: int = 50
    
    # Lane identifier (e.g., "ON-QC", "Toronto-Montreal")
    lane_name: Optional[str] = None
    
    # Distance (approximate)
    distance_km: Optional[int] = None
    distance_miles: Optional[int] = None
    
    # Rates by equipment type
    rates: Dict[str, float] = {}              # e.g., {"dry_van": 2500, "reefer": 2800}
    
    # Rate type
    rate_type: RateType = RateType.FLAT_RATE
    
    # Minimum charge
    minimum_charge: Optional[float] = None
    
    # Transit time (business days)
    transit_days: Optional[int] = None


class RateCardBase(BaseModel):
    """Base rate card fields"""
    name: str
    description: Optional[str] = None
    
    # Applicability
    customer_id: Optional[str] = None         # Specific customer (None = default)
    carrier_id: Optional[str] = None          # Specific carrier (for buy rates)
    
    # Type
    is_customer_rate: bool = True             # True = sell rate, False = buy rate
    
    # Effective dates
    effective_date: date
    expiry_date: Optional[date] = None
    
    # Currency
    currency: str = "CAD"
    
    # Default rates (if no lane match)
    default_rate_per_km: Optional[float] = None
    default_rate_per_mile: Optional[float] = None
    default_minimum: Optional[float] = None
    
    # Fuel surcharge
    fuel_surcharge_percentage: float = 0.0    # Default FSC %
    fuel_surcharge_included: bool = False     # Is FSC included in rates?


class RateCardCreate(RateCardBase):
    """Create a rate card"""
    tenant_id: str
    lane_rates: List[LaneRate] = []
    accessorial_overrides: Dict[str, float] = {}  # Override default accessorial rates


class RateCardUpdate(BaseModel):
    """Update rate card fields"""
    name: Optional[str] = None
    description: Optional[str] = None
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    default_rate_per_km: Optional[float] = None
    default_rate_per_mile: Optional[float] = None
    default_minimum: Optional[float] = None
    fuel_surcharge_percentage: Optional[float] = None
    status: Optional[RateCardStatus] = None


class RateCard(RateCardBase):
    """Complete rate card model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Status
    status: RateCardStatus = RateCardStatus.DRAFT
    
    # Lane rates
    lane_rates: List[LaneRate] = []
    
    # Accessorial overrides (code -> rate)
    accessorial_overrides: Dict[str, float] = {}
    
    # Usage tracking
    times_used: int = 0
    last_used_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


# =============================================================================
# RATE CALCULATION HELPERS
# =============================================================================

class RateQuote(BaseModel):
    """Rate quote result"""
    rate_card_id: Optional[str] = None
    rate_card_name: Optional[str] = None
    
    # Lane info
    origin: str
    destination: str
    distance_km: Optional[int] = None
    
    # Rates
    line_haul: float
    rate_type: RateType
    
    # Fuel surcharge
    fuel_surcharge_percentage: float = 0.0
    fuel_surcharge_amount: float = 0.0
    
    # Accessorials
    accessorials: List[Dict[str, Any]] = []
    accessorials_total: float = 0.0
    
    # Totals
    subtotal: float = 0.0
    
    # Notes
    notes: Optional[str] = None


def find_matching_lane(
    lane_rates: List[LaneRate],
    origin_city: str,
    origin_province: str,
    destination_city: str,
    destination_province: str,
    equipment_type: str = "dry_van"
) -> Optional[LaneRate]:
    """
    Find a matching lane rate for origin/destination
    Returns the most specific match
    """
    best_match = None
    best_score = 0
    
    for lane in lane_rates:
        score = 0
        
        # Check origin match
        if lane.origin_province and lane.origin_province.upper() == origin_province.upper():
            score += 1
            if lane.origin_city and lane.origin_city.lower() == origin_city.lower():
                score += 2
        
        # Check destination match
        if lane.destination_province and lane.destination_province.upper() == destination_province.upper():
            score += 1
            if lane.destination_city and lane.destination_city.lower() == destination_city.lower():
                score += 2
        
        # Check if equipment rate exists
        if equipment_type in lane.rates:
            score += 1
        
        if score > best_score:
            best_score = score
            best_match = lane
    
    return best_match if best_score >= 2 else None


def calculate_rate_quote(
    rate_card: RateCard,
    origin_city: str,
    origin_province: str,
    destination_city: str,
    destination_province: str,
    equipment_type: str = "dry_van",
    distance_km: Optional[int] = None,
    accessorial_codes: List[str] = [],
    accessorial_definitions: Dict[str, AccessorialDefinition] = {}
) -> RateQuote:
    """
    Calculate a rate quote using a rate card
    """
    # Find matching lane
    lane = find_matching_lane(
        rate_card.lane_rates,
        origin_city, origin_province,
        destination_city, destination_province,
        equipment_type
    )
    
    # Calculate line haul
    if lane and equipment_type in lane.rates:
        line_haul = lane.rates[equipment_type]
        rate_type = lane.rate_type
        lane_distance = lane.distance_km
    elif rate_card.default_rate_per_km and distance_km:
        line_haul = rate_card.default_rate_per_km * distance_km
        rate_type = RateType.PER_KM
        lane_distance = distance_km
    elif rate_card.default_minimum:
        line_haul = rate_card.default_minimum
        rate_type = RateType.MINIMUM
        lane_distance = distance_km
    else:
        line_haul = 0
        rate_type = RateType.FLAT_RATE
        lane_distance = distance_km
    
    # Apply minimum
    if lane and lane.minimum_charge and line_haul < lane.minimum_charge:
        line_haul = lane.minimum_charge
    elif rate_card.default_minimum and line_haul < rate_card.default_minimum:
        line_haul = rate_card.default_minimum
    
    # Calculate fuel surcharge
    fsc_percentage = rate_card.fuel_surcharge_percentage
    fsc_amount = 0
    if not rate_card.fuel_surcharge_included and fsc_percentage > 0:
        fsc_amount = round(line_haul * (fsc_percentage / 100), 2)
    
    # Calculate accessorials
    accessorials = []
    accessorials_total = 0
    
    for code in accessorial_codes:
        # Check for override in rate card
        if code in rate_card.accessorial_overrides:
            rate = rate_card.accessorial_overrides[code]
        elif code in accessorial_definitions:
            rate = accessorial_definitions[code].default_rate
        else:
            continue
        
        accessorials.append({
            "code": code,
            "rate": rate
        })
        accessorials_total += rate
    
    # Calculate totals
    subtotal = line_haul + fsc_amount + accessorials_total
    
    return RateQuote(
        rate_card_id=rate_card.id,
        rate_card_name=rate_card.name,
        origin=f"{origin_city}, {origin_province}",
        destination=f"{destination_city}, {destination_province}",
        distance_km=lane_distance,
        line_haul=round(line_haul, 2),
        rate_type=rate_type,
        fuel_surcharge_percentage=fsc_percentage,
        fuel_surcharge_amount=fsc_amount,
        accessorials=accessorials,
        accessorials_total=round(accessorials_total, 2),
        subtotal=round(subtotal, 2)
    )
