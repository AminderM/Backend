"""
TMS Orders & Shipments Models - Phase 3
Restructure bookings into Orders (sales) and Shipments (operations)
Canada-First Design with US Cross-Border Support
"""

from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone, date
import uuid


# =============================================================================
# ENUMS - Orders & Shipments
# =============================================================================

class OrderStatus(str, Enum):
    """Status of a customer order"""
    DRAFT = "draft"                      # Being created
    QUOTE = "quote"                      # Quote sent to customer
    PENDING = "pending"                  # Awaiting confirmation
    CONFIRMED = "confirmed"              # Customer confirmed
    IN_PROGRESS = "in_progress"          # Shipment(s) active
    COMPLETED = "completed"              # All shipments delivered
    INVOICED = "invoiced"                # Invoice generated
    PAID = "paid"                        # Payment received
    CANCELLED = "cancelled"              # Order cancelled
    ON_HOLD = "on_hold"                  # Temporarily paused


class ShipmentStatus(str, Enum):
    """Status of a shipment/load"""
    # Pre-dispatch
    PENDING = "pending"                  # Awaiting carrier assignment
    PLANNED = "planned"                  # Carrier assigned, not dispatched
    DISPATCHED = "dispatched"            # Dispatched to carrier/driver
    
    # Pickup phase
    EN_ROUTE_PICKUP = "en_route_pickup"  # Driver heading to pickup
    AT_PICKUP = "at_pickup"              # Arrived at pickup
    LOADING = "loading"                  # Being loaded
    LOADED = "loaded"                    # Loaded, ready to depart
    
    # Transit phase
    IN_TRANSIT = "in_transit"            # Moving to delivery
    
    # Delivery phase
    EN_ROUTE_DELIVERY = "en_route_delivery"  # Near delivery location
    AT_DELIVERY = "at_delivery"          # Arrived at delivery
    UNLOADING = "unloading"              # Being unloaded
    
    # Completion
    DELIVERED = "delivered"              # Successfully delivered
    POD_RECEIVED = "pod_received"        # Proof of delivery received
    
    # Exception statuses
    DELAYED = "delayed"                  # Shipment delayed
    EXCEPTION = "exception"              # Problem occurred
    CANCELLED = "cancelled"              # Shipment cancelled
    RETURNED = "returned"                # Returned to shipper


class FreightType(str, Enum):
    """Type of freight/load"""
    FTL = "ftl"                          # Full Truckload
    LTL = "ltl"                          # Less Than Truckload
    PARTIAL = "partial"                  # Partial load
    EXPEDITED = "expedited"              # Expedited/hot shot
    INTERMODAL = "intermodal"            # Rail + truck
    DRAYAGE = "drayage"                  # Port/rail drayage
    FLATBED = "flatbed"                  # Flatbed specific
    REEFER = "reefer"                    # Temperature controlled
    HAZMAT = "hazmat"                    # Hazardous materials


class EquipmentRequirement(str, Enum):
    """Required equipment type"""
    DRY_VAN = "dry_van"
    REEFER = "reefer"
    FLATBED = "flatbed"
    STEP_DECK = "step_deck"
    LOWBOY = "lowboy"
    CONESTOGA = "conestoga"
    POWER_ONLY = "power_only"
    STRAIGHT_TRUCK = "straight_truck"
    SPRINTER_VAN = "sprinter_van"
    BOX_TRUCK = "box_truck"
    TANKER = "tanker"
    HOPPER = "hopper"
    DUMP = "dump"


class TemperatureUnit(str, Enum):
    """Temperature unit"""
    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"


class WeightUnit(str, Enum):
    """Weight unit"""
    LBS = "lbs"
    KG = "kg"


class DistanceUnit(str, Enum):
    """Distance unit"""
    MILES = "miles"
    KM = "km"


class Currency(str, Enum):
    """Currency codes"""
    CAD = "CAD"
    USD = "USD"


# =============================================================================
# STOP MODELS (Multi-stop support)
# =============================================================================

class StopType(str, Enum):
    """Type of stop"""
    PICKUP = "pickup"
    DELIVERY = "delivery"
    STOP_OFF = "stop_off"                # Intermediate stop


class StopStatus(str, Enum):
    """Status of a stop"""
    PENDING = "pending"
    EN_ROUTE = "en_route"
    ARRIVED = "arrived"
    IN_PROGRESS = "in_progress"          # Loading/unloading
    COMPLETED = "completed"
    SKIPPED = "skipped"


class Stop(BaseModel):
    """Individual stop in a shipment"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int                         # Order of stops (1, 2, 3...)
    stop_type: StopType
    status: StopStatus = StopStatus.PENDING
    
    # Location reference (FK to locations, shippers, or consignees)
    location_id: Optional[str] = None
    shipper_id: Optional[str] = None      # For pickup stops
    consignee_id: Optional[str] = None    # For delivery stops
    
    # Address (can override or be standalone)
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "CA"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Scheduling
    appointment_required: bool = False
    appointment_number: Optional[str] = None
    scheduled_date: Optional[date] = None
    scheduled_time_from: Optional[str] = None   # HH:MM
    scheduled_time_to: Optional[str] = None     # HH:MM
    
    # Actual times
    arrived_at: Optional[datetime] = None
    started_at: Optional[datetime] = None       # Loading/unloading started
    completed_at: Optional[datetime] = None
    departed_at: Optional[datetime] = None
    
    # Cargo at this stop
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: WeightUnit = WeightUnit.LBS
    
    # Special instructions
    instructions: Optional[str] = None
    
    # Documents (BOL, POD, etc.)
    documents: List[str] = []                   # Document IDs


# =============================================================================
# ORDER MODELS (Sales/Customer facing)
# =============================================================================

class OrderBase(BaseModel):
    """Base order fields - represents a customer order"""
    # Customer reference
    customer_id: str                      # FK to customers
    
    # Order details
    customer_reference: Optional[str] = None   # Customer's PO/reference number
    
    # Origin/Destination (high-level)
    origin_city: str
    origin_state_province: str
    origin_country: str = "CA"
    destination_city: str
    destination_state_province: str
    destination_country: str = "CA"
    
    # Shipper/Consignee references
    shipper_id: Optional[str] = None      # FK to shippers
    consignee_id: Optional[str] = None    # FK to consignees
    
    # Dates
    requested_pickup_date: Optional[date] = None
    requested_delivery_date: Optional[date] = None
    
    # Freight details
    freight_type: FreightType = FreightType.FTL
    equipment_type: EquipmentRequirement = EquipmentRequirement.DRY_VAN
    
    # Cargo
    commodity: Optional[str] = None
    commodity_description: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: WeightUnit = WeightUnit.LBS
    dimensions_length: Optional[float] = None
    dimensions_width: Optional[float] = None
    dimensions_height: Optional[float] = None
    dimensions_unit: str = "in"           # in or cm
    cube: Optional[float] = None          # Cubic feet/meters
    
    # Special requirements
    hazmat: bool = False
    hazmat_class: Optional[str] = None
    hazmat_un_number: Optional[str] = None
    temperature_controlled: bool = False
    temperature_min: Optional[float] = None
    temperature_max: Optional[float] = None
    temperature_unit: TemperatureUnit = TemperatureUnit.CELSIUS
    team_required: bool = False           # Team drivers needed
    high_value: bool = False
    
    # Pricing (customer-facing)
    currency: Currency = Currency.CAD
    customer_rate: Optional[float] = None     # What customer pays (sell rate)
    fuel_surcharge: Optional[float] = None
    accessorials: List[Dict[str, Any]] = []   # Extra charges
    
    # Notes
    special_instructions: Optional[str] = None
    internal_notes: Optional[str] = None


class OrderCreate(OrderBase):
    """Create a new order"""
    tenant_id: str


class OrderUpdate(BaseModel):
    """Update order fields"""
    customer_id: Optional[str] = None
    customer_reference: Optional[str] = None
    origin_city: Optional[str] = None
    origin_state_province: Optional[str] = None
    destination_city: Optional[str] = None
    destination_state_province: Optional[str] = None
    shipper_id: Optional[str] = None
    consignee_id: Optional[str] = None
    requested_pickup_date: Optional[date] = None
    requested_delivery_date: Optional[date] = None
    freight_type: Optional[FreightType] = None
    equipment_type: Optional[EquipmentRequirement] = None
    commodity: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    customer_rate: Optional[float] = None
    fuel_surcharge: Optional[float] = None
    accessorials: Optional[List[Dict[str, Any]]] = None
    special_instructions: Optional[str] = None
    internal_notes: Optional[str] = None
    status: Optional[OrderStatus] = None


class Order(OrderBase):
    """Complete order model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Order identification
    order_number: str = Field(default_factory=lambda: f"ORD-{str(uuid.uuid4())[:8].upper()}")
    
    # Status
    status: OrderStatus = OrderStatus.DRAFT
    
    # Related shipments (one order can have multiple shipments)
    shipment_ids: List[str] = []
    
    # Calculated totals
    total_amount: float = 0.0             # Total including all charges
    tax_amount: float = 0.0               # Calculated tax
    tax_province: Optional[str] = None    # Province for tax calculation
    grand_total: float = 0.0              # Total + tax
    
    # Margin tracking (internal)
    total_cost: float = 0.0               # Sum of shipment costs (buy rate)
    margin_amount: float = 0.0            # customer_rate - total_cost
    margin_percentage: float = 0.0
    
    # Invoice reference
    invoice_id: Optional[str] = None
    invoiced_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Audit
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    sales_rep_id: Optional[str] = None    # Sales person who booked


# =============================================================================
# SHIPMENT MODELS (Operations/Dispatch facing)
# =============================================================================

class ShipmentBase(BaseModel):
    """Base shipment fields - represents actual freight movement"""
    # Parent order reference
    order_id: str                         # FK to orders
    
    # Carrier assignment
    carrier_id: Optional[str] = None      # FK to carriers_brokers
    
    # Driver assignment
    driver_id: Optional[str] = None       # FK to users (driver role) or drivers
    
    # Vehicle assignment
    vehicle_id: Optional[str] = None      # FK to vehicles/equipment
    tractor_number: Optional[str] = None
    trailer_number: Optional[str] = None
    
    # Multi-stop support
    stops: List[Stop] = []
    
    # Simplified origin/destination (first/last stop)
    origin_city: Optional[str] = None
    origin_state_province: Optional[str] = None
    origin_country: str = "CA"
    destination_city: Optional[str] = None
    destination_state_province: Optional[str] = None
    destination_country: str = "CA"
    
    # Distance and route
    distance_miles: Optional[float] = None
    distance_km: Optional[float] = None
    estimated_transit_hours: Optional[float] = None
    
    # Freight details (can differ from order for split shipments)
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: WeightUnit = WeightUnit.LBS
    
    # Pricing (operational - what we pay carrier)
    currency: Currency = Currency.CAD
    carrier_rate: Optional[float] = None      # What we pay carrier (buy rate)
    carrier_fuel_surcharge: Optional[float] = None
    carrier_accessorials: List[Dict[str, Any]] = []
    total_carrier_cost: float = 0.0
    
    # Driver pay (if company driver)
    driver_pay_type: Optional[str] = None     # per_mile, per_load, hourly
    driver_pay_rate: Optional[float] = None
    driver_pay_amount: Optional[float] = None
    
    # Temperature (if reefer)
    temperature_set: Optional[float] = None
    temperature_unit: TemperatureUnit = TemperatureUnit.CELSIUS
    
    # Special instructions for dispatch
    dispatch_notes: Optional[str] = None
    driver_instructions: Optional[str] = None


class ShipmentCreate(ShipmentBase):
    """Create a new shipment"""
    tenant_id: str


class ShipmentUpdate(BaseModel):
    """Update shipment fields"""
    carrier_id: Optional[str] = None
    driver_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    tractor_number: Optional[str] = None
    trailer_number: Optional[str] = None
    carrier_rate: Optional[float] = None
    carrier_fuel_surcharge: Optional[float] = None
    carrier_accessorials: Optional[List[Dict[str, Any]]] = None
    driver_pay_amount: Optional[float] = None
    temperature_set: Optional[float] = None
    dispatch_notes: Optional[str] = None
    driver_instructions: Optional[str] = None
    status: Optional[ShipmentStatus] = None


class Shipment(ShipmentBase):
    """Complete shipment model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Shipment identification
    shipment_number: str = Field(default_factory=lambda: f"SHP-{str(uuid.uuid4())[:8].upper()}")
    pro_number: Optional[str] = None      # Carrier's PRO/tracking number
    
    # Status
    status: ShipmentStatus = ShipmentStatus.PENDING
    
    # Key timestamps
    dispatched_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    
    # Proof of delivery
    pod_received: bool = False
    pod_received_at: Optional[datetime] = None
    pod_document_id: Optional[str] = None
    pod_signed_by: Optional[str] = None
    
    # Billing status
    carrier_invoiced: bool = False
    carrier_invoice_number: Optional[str] = None
    carrier_paid: bool = False
    carrier_paid_at: Optional[datetime] = None
    
    # Exception tracking
    has_exception: bool = False
    exception_reason: Optional[str] = None
    exception_reported_at: Optional[datetime] = None
    exception_resolved_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    # Audit
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    dispatcher_id: Optional[str] = None   # Dispatcher who handled


# =============================================================================
# SHIPMENT STATUS HISTORY
# =============================================================================

class ShipmentStatusHistory(BaseModel):
    """Track status changes for a shipment"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    shipment_id: str
    
    # Status change
    previous_status: Optional[str] = None
    new_status: str
    
    # Location at time of status change
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None   # City, province
    
    # Details
    notes: Optional[str] = None
    
    # Timestamp
    changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    changed_by: Optional[str] = None      # User ID who changed


# =============================================================================
# TRACKING EVENTS
# =============================================================================

class TrackingEventType(str, Enum):
    """Types of tracking events"""
    LOCATION_UPDATE = "location_update"
    STATUS_CHANGE = "status_change"
    CHECK_CALL = "check_call"             # Dispatcher check call
    DRIVER_MESSAGE = "driver_message"
    DELAY_REPORTED = "delay_reported"
    ETA_UPDATE = "eta_update"
    EXCEPTION = "exception"
    DOCUMENT_UPLOADED = "document_uploaded"


class TrackingEvent(BaseModel):
    """Real-time tracking event"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    shipment_id: str
    driver_id: Optional[str] = None
    
    # Event type
    event_type: TrackingEventType
    
    # Location
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    
    # Event details
    message: Optional[str] = None
    
    # For ETA updates
    eta_pickup: Optional[datetime] = None
    eta_delivery: Optional[datetime] = None
    
    # Timestamp
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    recorded_by: Optional[str] = None     # User or "driver_app" or "eld"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_order_totals(order: Order, shipments: List[Shipment]) -> dict:
    """
    Calculate order totals based on shipments
    Returns dict with total_cost, margin_amount, margin_percentage
    """
    total_cost = sum(s.total_carrier_cost for s in shipments)
    customer_rate = order.customer_rate or 0
    fuel_surcharge = order.fuel_surcharge or 0
    accessorials_total = sum(a.get('amount', 0) for a in order.accessorials)
    
    total_amount = customer_rate + fuel_surcharge + accessorials_total
    margin_amount = total_amount - total_cost
    margin_percentage = (margin_amount / total_amount * 100) if total_amount > 0 else 0
    
    return {
        "total_cost": round(total_cost, 2),
        "total_amount": round(total_amount, 2),
        "margin_amount": round(margin_amount, 2),
        "margin_percentage": round(margin_percentage, 2)
    }


def create_stop_from_shipper(shipper: dict, sequence: int = 1) -> Stop:
    """Create a pickup stop from a shipper record"""
    address = shipper.get('address', {})
    return Stop(
        sequence=sequence,
        stop_type=StopType.PICKUP,
        shipper_id=shipper.get('id'),
        company_name=shipper.get('company_name'),
        contact_name=shipper.get('contact_name'),
        contact_phone=shipper.get('contact_phone'),
        address_line1=address.get('address_line1') if isinstance(address, dict) else None,
        city=address.get('city') if isinstance(address, dict) else None,
        state_province=address.get('state_province') if isinstance(address, dict) else None,
        postal_code=address.get('postal_code') if isinstance(address, dict) else None,
        country=address.get('country', 'CA') if isinstance(address, dict) else 'CA',
        scheduled_time_from=shipper.get('dock_hours_open'),
        scheduled_time_to=shipper.get('dock_hours_close'),
        appointment_required=shipper.get('appointment_required', False),
        instructions=shipper.get('shipper_notes')
    )


def create_stop_from_consignee(consignee: dict, sequence: int = 2) -> Stop:
    """Create a delivery stop from a consignee record"""
    address = consignee.get('address', {})
    return Stop(
        sequence=sequence,
        stop_type=StopType.DELIVERY,
        consignee_id=consignee.get('id'),
        company_name=consignee.get('company_name'),
        contact_name=consignee.get('contact_name'),
        contact_phone=consignee.get('contact_phone'),
        address_line1=address.get('address_line1') if isinstance(address, dict) else None,
        city=address.get('city') if isinstance(address, dict) else None,
        state_province=address.get('state_province') if isinstance(address, dict) else None,
        postal_code=address.get('postal_code') if isinstance(address, dict) else None,
        country=address.get('country', 'CA') if isinstance(address, dict) else 'CA',
        scheduled_time_from=consignee.get('dock_hours_open'),
        scheduled_time_to=consignee.get('dock_hours_close'),
        appointment_required=consignee.get('appointment_required', False),
        instructions=consignee.get('consignee_notes')
    )
