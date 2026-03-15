"""
Integrated Route Mate API Routes
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from models import User
from auth import get_current_user
from database import db
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from models_route_mate import (
    # Territory
    Territory, TerritoryCreate, TerritoryUpdate,
    # Route
    Route, RouteCreate, RouteUpdate, RouteStatus,
    # Customer
    RouteMateCustomer, RouteMateCustomerCreate,
    # Vehicle
    RouteMateVehicle, RouteMateVehicleCreate,
    # Driver
    RouteMateDriver, RouteMateDriverCreate,
    # Optimization
    OptimizationJob, OptimizationJobCreate, OptimizationInputParams,
    OptimizationResult,
    # Order
    Order, OrderImport,
    # Exception
    RouteException, RouteExceptionCreate
)

from route_optimizer import route_optimizer

router = APIRouter(prefix="/route-mate", tags=["Integrated Route Mate"])

# ==================== TERRITORIES ====================

@router.get("/territories")
async def list_territories(current_user: User = Depends(get_current_user)):
    """List all territories for tenant"""
    territories = await db.route_mate_territories.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0}
    ).to_list(length=100)
    return territories

@router.post("/territories")
async def create_territory(
    payload: TerritoryCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new territory"""
    territory = Territory(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        name=payload.name,
        type=payload.type,
        status="draft",
        boundaries=payload.boundaries,
        assigned_to=payload.assigned_to,
        target_metrics=payload.target_metrics or {
            "stops_per_day": 100,
            "max_distance_miles": 200,
            "revenue_target": 500000
        },
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat()
    )
    
    await db.route_mate_territories.insert_one(territory.dict())
    return territory

@router.get("/territories/{territory_id}")
async def get_territory(
    territory_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get territory by ID"""
    territory = await db.route_mate_territories.find_one(
        {"id": territory_id, "tenant_id": current_user.tenant_id},
        {"_id": 0}
    )
    if not territory:
        raise HTTPException(status_code=404, detail="Territory not found")
    return territory

@router.put("/territories/{territory_id}")
async def update_territory(
    territory_id: str,
    payload: TerritoryUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update territory"""
    updates = {
        k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None
    }
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.route_mate_territories.update_one(
        {"id": territory_id, "tenant_id": current_user.tenant_id},
        {"$set": updates}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Territory not found")
    
    return {"message": "Territory updated successfully"}

@router.delete("/territories/{territory_id}")
async def delete_territory(
    territory_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete territory"""
    result = await db.route_mate_territories.delete_one(
        {"id": territory_id, "tenant_id": current_user.tenant_id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Territory not found")
    
    return {"message": "Territory deleted successfully"}

# ==================== ROUTES ====================

@router.get("/routes")
async def list_routes(
    route_date: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """List routes with optional filters"""
    query = {"tenant_id": current_user.tenant_id}
    
    if route_date:
        query["route_date"] = route_date
    if status:
        query["status"] = status
    
    routes = await db.route_mate_routes.find(query, {"_id": 0}).to_list(length=200)
    return routes

@router.post("/routes")
async def create_route(
    payload: RouteCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new route manually"""
    route = Route(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        name=payload.name,
        route_date=payload.route_date,
        territory_id=payload.territory_id,
        vehicle_id=payload.vehicle_id,
        driver_id=payload.driver_id,
        stops=payload.stops,
        status="draft",
        created_at=datetime.now(timezone.utc).isoformat()
    )
    
    # Calculate metrics
    if route.stops and payload.vehicle_id:
        vehicle = await db.route_mate_vehicles.find_one(
            {"id": payload.vehicle_id},
            {"_id": 0}
        )
        if vehicle:
            vehicle_obj = RouteMateVehicle(**vehicle)
            route.metrics = route_optimizer.calculate_route_metrics(
                route.stops,
                vehicle_obj
            )
    
    await db.route_mate_routes.insert_one(route.dict())
    return route

@router.get("/routes/{route_id}")
async def get_route(
    route_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get route by ID"""
    route = await db.route_mate_routes.find_one(
        {"id": route_id, "tenant_id": current_user.tenant_id},
        {"_id": 0}
    )
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route

@router.put("/routes/{route_id}")
async def update_route(
    route_id: str,
    payload: RouteUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update route"""
    updates = {
        k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None
    }
    
    result = await db.route_mate_routes.update_one(
        {"id": route_id, "tenant_id": current_user.tenant_id},
        {"$set": updates}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Route not found")
    
    return {"message": "Route updated successfully"}

@router.post("/routes/{route_id}/publish")
async def publish_route(
    route_id: str,
    current_user: User = Depends(get_current_user)
):
    """Publish route to driver"""
    result = await db.route_mate_routes.update_one(
        {"id": route_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "published",
            "published_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Route not found")
    
    # TODO: Send notification to driver
    
    return {
        "message": "Route published successfully",
        "published_at": datetime.now(timezone.utc).isoformat()
    }

@router.delete("/routes/{route_id}")
async def delete_route(
    route_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete route"""
    result = await db.route_mate_routes.delete_one(
        {"id": route_id, "tenant_id": current_user.tenant_id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Route not found")
    
    return {"message": "Route deleted successfully"}

# ==================== OPTIMIZATION ====================

@router.post("/optimize")
async def optimize_routes(
    payload: OptimizationJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Optimize routes from orders
    Creates optimization job and processes in background
    """
    # Create optimization job
    job = OptimizationJob(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        job_type="route_optimization",
        status="processing",
        input_params=payload.input_params,
        created_at=datetime.now(timezone.utc).isoformat()
    )
    
    await db.route_mate_optimization_jobs.insert_one(job.dict())
    
    # Process optimization immediately for MVP (async in production)
    try:
        # Get pending orders for the date
        orders = await db.route_mate_orders.find(
            {
                "tenant_id": current_user.tenant_id,
                "route_date": payload.input_params.date,
                "assigned_route_id": None
            },
            {"_id": 0}
        ).to_list(length=1000)
        
        if not orders:
            raise HTTPException(status_code=400, detail="No orders found for optimization")
        
        order_objects = [Order(**order) for order in orders]
        
        # Get available vehicles
        vehicles = await db.route_mate_vehicles.find(
            {"tenant_id": current_user.tenant_id, "status": "active"},
            {"_id": 0}
        ).to_list(length=100)
        
        if not vehicles:
            raise HTTPException(status_code=400, detail="No active vehicles found")
        
        vehicle_objects = [RouteMateVehicle(**v) for v in vehicles]
        
        # Default start location (depot) - use first vehicle's home depot or default
        start_location = {"lat": 40.7128, "lng": -74.0060}  # Default: NYC
        # TODO: Get actual depot location from database
        
        # Run optimization
        optimized_routes = route_optimizer.optimize_routes(
            orders=order_objects,
            vehicles=vehicle_objects,
            start_location=start_location,
            optimization_weights=payload.input_params.goal_weights,
            tenant_id=current_user.tenant_id,
            route_date=payload.input_params.date
        )
        
        # Save optimized routes
        route_ids = []
        for route in optimized_routes:
            await db.route_mate_routes.insert_one(route.dict())
            route_ids.append(route.id)
            
            # Mark orders as assigned
            stop_customer_ids = [stop.customer_id for stop in route.stops]
            await db.route_mate_orders.update_many(
                {
                    "tenant_id": current_user.tenant_id,
                    "customer_id": {"$in": stop_customer_ids},
                    "route_date": payload.input_params.date
                },
                {"$set": {"assigned_route_id": route.id}}
            )
        
        # Calculate improvement (simplified for MVP)
        avg_score = sum(r.optimization_score.total_score for r in optimized_routes) / len(optimized_routes)
        
        # Update job with results
        result = OptimizationResult(
            routes_generated=len(optimized_routes),
            optimization_score=round(avg_score, 1),
            improvement_vs_baseline="N/A",  # Would need baseline comparison
            routes=route_ids
        )
        
        await db.route_mate_optimization_jobs.update_one(
            {"id": job.id},
            {"$set": {
                "status": "completed",
                "result": result.dict(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "processing_time_seconds": 5  # Placeholder
            }}
        )
        
        return {
            "job_id": job.id,
            "status": "completed",
            "routes_generated": len(optimized_routes),
            "optimization_score": avg_score,
            "routes": route_ids
        }
        
    except Exception as e:
        # Update job with error
        await db.route_mate_optimization_jobs.update_one(
            {"id": job.id},
            {"$set": {
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")

@router.get("/optimization-jobs/{job_id}")
async def get_optimization_job(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get optimization job status"""
    job = await db.route_mate_optimization_jobs.find_one(
        {"id": job_id, "tenant_id": current_user.tenant_id},
        {"_id": 0}
    )
    
    if not job:
        raise HTTPException(status_code=404, detail="Optimization job not found")
    
    return job

# ==================== ORDERS ====================

@router.post("/orders/import")
async def import_orders(
    payload: OrderImport,
    current_user: User = Depends(get_current_user)
):
    """Import orders from CSV or external system"""
    imported_count = 0
    
    for order in payload.orders:
        order_dict = order.dict()
        order_dict["tenant_id"] = current_user.tenant_id
        order_dict["route_date"] = payload.route_date
        order_dict["assigned_route_id"] = None
        order_dict["created_at"] = datetime.now(timezone.utc).isoformat()
        
        await db.route_mate_orders.insert_one(order_dict)
        imported_count += 1
    
    return {
        "message": f"Successfully imported {imported_count} orders",
        "count": imported_count
    }

@router.get("/orders")
async def list_orders(
    route_date: Optional[str] = None,
    unassigned_only: bool = False,
    current_user: User = Depends(get_current_user)
):
    """List orders"""
    query = {"tenant_id": current_user.tenant_id}
    
    if route_date:
        query["route_date"] = route_date
    if unassigned_only:
        query["assigned_route_id"] = None
    
    orders = await db.route_mate_orders.find(query, {"_id": 0}).to_list(length=1000)
    return orders

# ==================== CUSTOMERS ====================

@router.get("/customers")
async def list_customers(current_user: User = Depends(get_current_user)):
    """List all customers"""
    customers = await db.route_mate_customers.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0}
    ).to_list(length=1000)
    return customers

@router.post("/customers")
async def create_customer(
    payload: RouteMateCustomerCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new customer"""
    customer = RouteMateCustomer(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        name=payload.name,
        address=payload.address,
        territory_id=payload.territory_id,
        contact=payload.contact or {},
        service_requirements=payload.service_requirements or {},
        business_data=payload.business_data or {},
        created_at=datetime.now(timezone.utc).isoformat()
    )
    
    await db.route_mate_customers.insert_one(customer.dict())
    return customer

# ==================== VEHICLES ====================

@router.get("/vehicles")
async def list_vehicles(current_user: User = Depends(get_current_user)):
    """List all vehicles"""
    vehicles = await db.route_mate_vehicles.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0}
    ).to_list(length=100)
    return vehicles

@router.post("/vehicles")
async def create_vehicle(
    payload: RouteMateVehicleCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new vehicle"""
    vehicle = RouteMateVehicle(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        vehicle_number=payload.vehicle_number,
        type=payload.type,
        capacity=payload.capacity,
        specifications=payload.specifications or {},
        restrictions=payload.restrictions or {},
        home_depot=payload.home_depot,
        status="active",
        created_at=datetime.now(timezone.utc).isoformat()
    )
    
    await db.route_mate_vehicles.insert_one(vehicle.dict())
    return vehicle

# ==================== DRIVERS ====================

@router.get("/drivers")
async def list_drivers(current_user: User = Depends(get_current_user)):
    """List all drivers"""
    drivers = await db.route_mate_drivers.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0}
    ).to_list(length=100)
    return drivers

@router.post("/drivers")
async def create_driver(
    payload: RouteMateDriverCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new driver"""
    driver = RouteMateDriver(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        employee_number=payload.employee_number,
        name=payload.name,
        user_id=payload.user_id,
        licenses=payload.licenses or [],
        skills=payload.skills or [],
        work_schedule=payload.work_schedule or {},
        status="active",
        created_at=datetime.now(timezone.utc).isoformat()
    )
    
    await db.route_mate_drivers.insert_one(driver.dict())
    return driver

# ==================== ANALYTICS ====================

@router.get("/analytics/dashboard")
async def get_dashboard_analytics(current_user: User = Depends(get_current_user)):
    """Get dashboard analytics"""
    # Get counts
    territories_count = await db.route_mate_territories.count_documents(
        {"tenant_id": current_user.tenant_id}
    )
    routes_count = await db.route_mate_routes.count_documents(
        {"tenant_id": current_user.tenant_id}
    )
    customers_count = await db.route_mate_customers.count_documents(
        {"tenant_id": current_user.tenant_id}
    )
    vehicles_count = await db.route_mate_vehicles.count_documents(
        {"tenant_id": current_user.tenant_id, "status": "active"}
    )
    
    # Get recent routes
    recent_routes = await db.route_mate_routes.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(5).to_list(5)
    
    return {
        "territories": territories_count,
        "routes": routes_count,
        "customers": customers_count,
        "vehicles": vehicles_count,
        "recent_routes": recent_routes
    }

@router.get("/analytics/route-performance")
async def get_route_performance(
    route_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get route performance metrics"""
    query = {"tenant_id": current_user.tenant_id, "status": "completed"}
    
    if route_date:
        query["route_date"] = route_date
    
    routes = await db.route_mate_routes.find(query, {"_id": 0}).to_list(length=100)
    
    if not routes:
        return {
            "avg_distance": 0,
            "avg_duration": 0,
            "avg_stops": 0,
            "avg_score": 0
        }
    
    avg_distance = sum(r.get("metrics", {}).get("total_distance_miles", 0) for r in routes) / len(routes)
    avg_duration = sum(r.get("metrics", {}).get("total_duration_minutes", 0) for r in routes) / len(routes)
    avg_stops = sum(r.get("metrics", {}).get("total_stops", 0) for r in routes) / len(routes)
    avg_score = sum(
        r.get("optimization_score", {}).get("total_score", 0) 
        for r in routes
    ) / len(routes)
    
    return {
        "avg_distance": round(avg_distance, 2),
        "avg_duration": round(avg_duration, 2),
        "avg_stops": round(avg_stops, 2),
        "avg_score": round(avg_score, 2),
        "total_routes": len(routes)
    }
