"""
Integrated Route Mate - Data Models
Territory Planning & Route Optimization
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

# ==================== ENUMS ====================

class RouteStatus(str, Enum):
    DRAFT = "draft"
    OPTIMIZED = "optimized"
    PUBLISHED = "published"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TerritoryType(str, Enum):
    SALES = "sales"
    SERVICE = "service"
    DELIVERY = "delivery"

class TerritoryStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"

class OptimizationGoal(str, Enum):
    MINIMIZE_DISTANCE = "minimize_distance"
    MINIMIZE_TIME = "minimize_time"
    BALANCE_WORKLOAD = "balance_workload"
    MAXIMIZE_STOPS = "maximize_stops"
    MINIMIZE_COST = "minimize_cost"

class ServiceType(str, Enum):
    DELIVERY = "delivery"
    PICKUP = "pickup"
    SERVICE_CALL = "service_call"

class ExceptionType(str, Enum):
    ROAD_CLOSURE = "road_closure"
    CUSTOMER_REQUEST = "customer_request"
    VEHICLE_ISSUE = "vehicle_issue"
    WEATHER = "weather"
    TRAFFIC = "traffic"
    OTHER = "other"

# ==================== CORE MODELS ====================

class Location(BaseModel):
    lat: float
    lng: float
    address: Optional[str] = None

class TimeWindow(BaseModel):
    start: str  # HH:MM format
    end: str    # HH:MM format
    day: Optional[str] = None  # Mon-Fri, Sat, Sun, etc.

class VehicleCapacity(BaseModel):
    weight_lbs: float
    volume_cuft: float
    pallet_count: int

class RouteStop(BaseModel):
    sequence: int
    customer_id: str
    location: Location
    planned_arrival: Optional[str] = None  # HH:MM
    planned_duration: int = 15  # minutes
    time_window: Optional[TimeWindow] = None
    service_type: ServiceType = ServiceType.DELIVERY
    items: List[Dict[str, Any]] = []
    notes: Optional[str] = None
    special_requirements: List[str] = []
    # Actual execution data (filled after completion)
    actual_arrival: Optional[str] = None
    actual_duration: Optional[int] = None
    status: Optional[str] = "pending"  # pending, completed, failed, skipped

class RouteMetrics(BaseModel):
    total_distance_miles: float = 0.0
    total_duration_minutes: int = 0
    total_stops: int = 0
    estimated_cost: float = 0.0
    fuel_consumption_gallons: Optional[float] = None
    avg_stop_time: Optional[int] = None

class OptimizationScore(BaseModel):
    total_score: float  # 0-100
    distance_score: float
    time_score: float
    capacity_score: float
    time_window_score: float
    density_score: float
    balance_score: float
    grade: str  # A, B, C, D, F

# ==================== TERRITORY ====================

class Territory(BaseModel):
    id: str
    tenant_id: str
    name: str
    type: TerritoryType
    status: TerritoryStatus = TerritoryStatus.DRAFT
    boundaries: Optional[Dict[str, Any]] = None  # GeoJSON Polygon
    assigned_to: Optional[str] = None  # user_id
    target_metrics: Dict[str, Any] = {
        "stops_per_day": 100,
        "max_distance_miles": 200,
        "revenue_target": 500000
    }
    customer_ids: List[str] = []
    created_at: str
    updated_at: str

class TerritoryCreate(BaseModel):
    name: str
    type: TerritoryType
    boundaries: Optional[Dict[str, Any]] = None
    assigned_to: Optional[str] = None
    target_metrics: Optional[Dict[str, Any]] = None

class TerritoryUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[TerritoryStatus] = None
    boundaries: Optional[Dict[str, Any]] = None
    assigned_to: Optional[str] = None
    target_metrics: Optional[Dict[str, Any]] = None

# ==================== ROUTE ====================

class Route(BaseModel):
    id: str
    tenant_id: str
    territory_id: Optional[str] = None
    name: str
    route_date: str  # YYYY-MM-DD
    status: RouteStatus = RouteStatus.DRAFT
    vehicle_id: Optional[str] = None
    driver_id: Optional[str] = None
    stops: List[RouteStop] = []
    optimization_score: Optional[OptimizationScore] = None
    metrics: RouteMetrics = RouteMetrics()
    created_at: str
    optimized_at: Optional[str] = None
    published_at: Optional[str] = None

class RouteCreate(BaseModel):
    name: str
    route_date: str
    territory_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    driver_id: Optional[str] = None
    stops: List[RouteStop] = []

class RouteUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[RouteStatus] = None
    vehicle_id: Optional[str] = None
    driver_id: Optional[str] = None
    stops: Optional[List[RouteStop]] = None

# ==================== CUSTOMER (Route Mate Specific) ====================

class CustomerServiceRequirements(BaseModel):
    average_service_time: int = 20  # minutes
    time_windows: List[TimeWindow] = []
    special_equipment: List[str] = []
    access_notes: Optional[str] = None

class CustomerBusinessData(BaseModel):
    annual_revenue: float = 0.0
    visit_frequency: str = "weekly"  # daily, weekly, monthly
    priority: str = "medium"  # high, medium, low

class RouteMateCustomer(BaseModel):
    id: str
    tenant_id: str
    name: str
    address: Dict[str, Any]  # includes geocode
    territory_id: Optional[str] = None
    contact: Dict[str, str] = {}
    service_requirements: CustomerServiceRequirements = CustomerServiceRequirements()
    business_data: CustomerBusinessData = CustomerBusinessData()
    created_at: str

class RouteMateCustomerCreate(BaseModel):
    name: str
    address: Dict[str, Any]
    territory_id: Optional[str] = None
    contact: Optional[Dict[str, str]] = None
    service_requirements: Optional[CustomerServiceRequirements] = None
    business_data: Optional[CustomerBusinessData] = None

# ==================== VEHICLE (Route Mate Specific) ====================

class VehicleSpecifications(BaseModel):
    fuel_type: str = "diesel"
    mpg: float = 12.0
    cost_per_mile: float = 1.50
    features: List[str] = []

class VehicleRestrictions(BaseModel):
    max_height_ft: float = 13.5
    max_weight_lbs: float = 80000
    hazmat_certified: bool = False

class RouteMateVehicle(BaseModel):
    id: str
    tenant_id: str
    vehicle_number: str
    type: str  # delivery_van, box_truck, semi
    status: str = "active"  # active, maintenance, inactive
    capacity: VehicleCapacity
    specifications: VehicleSpecifications = VehicleSpecifications()
    restrictions: VehicleRestrictions = VehicleRestrictions()
    home_depot: Optional[str] = None
    created_at: str

class RouteMateVehicleCreate(BaseModel):
    vehicle_number: str
    type: str
    capacity: VehicleCapacity
    specifications: Optional[VehicleSpecifications] = None
    restrictions: Optional[VehicleRestrictions] = None
    home_depot: Optional[str] = None

# ==================== DRIVER (Route Mate Specific) ====================

class WorkSchedule(BaseModel):
    available_days: List[str] = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    shift_start: str = "07:00"
    shift_end: str = "17:00"
    break_duration: int = 30  # minutes

class DriverPerformance(BaseModel):
    average_stops_per_day: float = 0.0
    on_time_percentage: float = 0.0
    customer_rating: float = 0.0

class RouteMateDriver(BaseModel):
    id: str
    tenant_id: str
    user_id: Optional[str] = None  # Link to TMS user
    employee_number: str
    name: str
    status: str = "active"  # active, on_leave, inactive
    licenses: List[str] = []
    skills: List[str] = []
    home_depot: Optional[str] = None
    work_schedule: WorkSchedule = WorkSchedule()
    performance: DriverPerformance = DriverPerformance()
    created_at: str

class RouteMateDriverCreate(BaseModel):
    employee_number: str
    name: str
    user_id: Optional[str] = None
    licenses: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    work_schedule: Optional[WorkSchedule] = None

# ==================== OPTIMIZATION JOB ====================

class OptimizationConstraints(BaseModel):
    max_route_duration: int = 480  # minutes
    enforce_time_windows: bool = True
    allow_split_deliveries: bool = False
    max_stops_per_route: Optional[int] = None

class OptimizationInputParams(BaseModel):
    date: str
    territory_ids: List[str] = []
    optimization_goals: List[OptimizationGoal] = [OptimizationGoal.MINIMIZE_DISTANCE]
    constraints: OptimizationConstraints = OptimizationConstraints()
    goal_weights: Dict[str, float] = {
        "distance": 0.25,
        "time": 0.20,
        "capacity": 0.15,
        "time_windows": 0.25,
        "density": 0.10,
        "balance": 0.05
    }

class OptimizationResult(BaseModel):
    routes_generated: int
    optimization_score: float
    improvement_vs_baseline: Optional[str] = None
    routes: List[str] = []  # route IDs

class OptimizationJob(BaseModel):
    id: str
    tenant_id: str
    job_type: str = "route_optimization"  # route_optimization, territory_design
    status: str = "queued"  # queued, processing, completed, failed
    input_params: OptimizationInputParams
    result: Optional[OptimizationResult] = None
    error_message: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    processing_time_seconds: Optional[int] = None

class OptimizationJobCreate(BaseModel):
    input_params: OptimizationInputParams

# ==================== ROUTE HISTORY ====================

class StopPerformance(BaseModel):
    stop_id: str
    customer_id: str
    planned_arrival: str
    actual_arrival: str
    variance_minutes: int
    service_time_actual: int
    status: str  # completed, failed, skipped

class RouteHistory(BaseModel):
    id: str
    route_id: str
    execution_date: str
    completed_at: str
    actual_metrics: RouteMetrics
    stop_performance: List[StopPerformance] = []
    driver_notes: Optional[str] = None
    customer_feedback: Optional[Dict[str, Any]] = None

# ==================== EXCEPTION ====================

class ExceptionImpact(BaseModel):
    affected_stops: List[str] = []
    estimated_delay_minutes: int = 0

class RouteException(BaseModel):
    id: str
    route_id: str
    type: ExceptionType
    description: str
    impact: ExceptionImpact
    resolution: Optional[str] = None  # manual_reroute, accepted, deferred
    created_at: str
    resolved_at: Optional[str] = None

class RouteExceptionCreate(BaseModel):
    route_id: str
    type: ExceptionType
    description: str
    impact: ExceptionImpact

# ==================== ORDER (FOR ROUTE OPTIMIZATION INPUT) ====================

class OrderItem(BaseModel):
    weight: float  # lbs
    volume: float  # cubic feet
    quantity: int = 1
    description: Optional[str] = None

class Order(BaseModel):
    id: str
    customer_id: str
    location: Location
    time_window: Optional[TimeWindow] = None
    items: List[OrderItem] = []
    service_type: ServiceType = ServiceType.DELIVERY
    priority: str = "medium"  # high, medium, low
    special_requirements: List[str] = []
    notes: Optional[str] = None

class OrderImport(BaseModel):
    orders: List[Order]
    route_date: str
    auto_optimize: bool = False
