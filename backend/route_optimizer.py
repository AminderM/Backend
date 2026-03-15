"""
Route Optimization Engine
Basic VRP Solver for MVP
"""

import math
from typing import List, Dict, Tuple, Optional
from models_route_mate import (
    Order, RouteStop, Route, RouteMetrics, 
    OptimizationScore, Location, RouteMateVehicle
)
import uuid
from datetime import datetime, timezone

class RouteOptimizer:
    """
    Basic Vehicle Routing Problem (VRP) solver
    MVP implementation using nearest neighbor + 2-opt improvement
    """
    
    def __init__(self):
        self.EARTH_RADIUS_MILES = 3959.0
    
    def calculate_distance(self, loc1: Location, loc2: Location) -> float:
        """
        Calculate distance between two locations using Haversine formula
        Returns distance in miles
        """
        lat1, lon1 = math.radians(loc1.lat), math.radians(loc1.lng)
        lat2, lon2 = math.radians(loc2.lat), math.radians(loc2.lng)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return self.EARTH_RADIUS_MILES * c
    
    def create_distance_matrix(self, locations: List[Location]) -> List[List[float]]:
        """Create distance matrix between all locations"""
        n = len(locations)
        matrix = [[0.0] * n for _ in range(n)]
        
        for i in range(n):
            for j in range(i + 1, n):
                dist = self.calculate_distance(locations[i], locations[j])
                matrix[i][j] = dist
                matrix[j][i] = dist
        
        return matrix
    
    def nearest_neighbor_route(
        self, 
        orders: List[Order], 
        start_location: Location,
        vehicle: RouteMateVehicle
    ) -> List[Order]:
        """
        Create initial route using nearest neighbor algorithm
        """
        unvisited = orders.copy()
        route = []
        current_location = start_location
        current_capacity = 0.0
        
        while unvisited:
            # Find nearest unvisited order that fits in vehicle
            nearest = None
            nearest_dist = float('inf')
            
            for order in unvisited:
                # Check capacity constraint
                order_weight = sum(item.weight for item in order.items)
                if current_capacity + order_weight > vehicle.capacity.weight_lbs:
                    continue
                
                dist = self.calculate_distance(current_location, order.location)
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest = order
            
            if nearest is None:
                # Can't fit any more orders in this vehicle
                break
            
            route.append(nearest)
            current_location = nearest.location
            current_capacity += sum(item.weight for item in nearest.items)
            unvisited.remove(nearest)
        
        return route
    
    def two_opt_improvement(self, route: List[Order], distance_matrix: List[List[float]], order_to_idx: Dict[str, int]) -> List[Order]:
        """
        Improve route using 2-opt local search
        """
        improved = True
        best_route = route.copy()
        
        while improved:
            improved = False
            
            for i in range(1, len(best_route) - 1):
                for j in range(i + 1, len(best_route)):
                    # Get indices in distance matrix
                    idx_i_minus_1 = order_to_idx[best_route[i-1].id]
                    idx_i = order_to_idx[best_route[i].id]
                    idx_j_minus_1 = order_to_idx[best_route[j-1].id]
                    idx_j = order_to_idx[best_route[j].id] if j < len(best_route) else 0
                    
                    # Current distance
                    current_dist = (
                        distance_matrix[idx_i_minus_1][idx_i] +
                        distance_matrix[idx_j_minus_1][idx_j]
                    )
                    
                    # New distance after swap
                    new_dist = (
                        distance_matrix[idx_i_minus_1][idx_j_minus_1] +
                        distance_matrix[idx_i][idx_j]
                    )
                    
                    # If improvement found, reverse the segment
                    if new_dist < current_dist:
                        best_route[i:j] = reversed(best_route[i:j])
                        improved = True
        
        return best_route
    
    def calculate_route_metrics(
        self, 
        stops: List[RouteStop], 
        vehicle: RouteMateVehicle
    ) -> RouteMetrics:
        """Calculate route metrics"""
        total_distance = 0.0
        total_duration = 0
        
        for i in range(len(stops) - 1):
            dist = self.calculate_distance(stops[i].location, stops[i+1].location)
            total_distance += dist
            total_duration += stops[i].planned_duration
            # Add travel time (assume 30 mph average)
            total_duration += int((dist / 30.0) * 60)
        
        # Add last stop service time
        if stops:
            total_duration += stops[-1].planned_duration
        
        # Calculate cost
        fuel_cost = total_distance * (vehicle.specifications.cost_per_mile / vehicle.specifications.mpg)
        driver_cost = (total_duration / 60.0) * 25.0  # Assume $25/hour
        estimated_cost = fuel_cost + driver_cost
        
        return RouteMetrics(
            total_distance_miles=round(total_distance, 2),
            total_duration_minutes=total_duration,
            total_stops=len(stops),
            estimated_cost=round(estimated_cost, 2),
            fuel_consumption_gallons=round(total_distance / vehicle.specifications.mpg, 2),
            avg_stop_time=stops[0].planned_duration if stops else 0
        )
    
    def calculate_optimization_score(
        self, 
        route: Route,
        all_routes: List[Route],
        weights: Dict[str, float]
    ) -> OptimizationScore:
        """
        Calculate multi-factor optimization score
        """
        scores = {}
        
        # 1. Distance Efficiency (compare to straight-line distance)
        if route.stops:
            straight_line = sum(
                self.calculate_distance(route.stops[i].location, route.stops[i+1].location)
                for i in range(len(route.stops) - 1)
            )
            optimal_distance = straight_line * 1.2  # Realistic minimum with roads
            scores['distance'] = min(100, (optimal_distance / route.metrics.total_distance_miles) * 100)
        else:
            scores['distance'] = 100
        
        # 2. Time Efficiency (8 hours target)
        target_duration = 480  # 8 hours
        scores['time'] = max(0, min(100, (target_duration / max(route.metrics.total_duration_minutes, 1)) * 100))
        
        # 3. Capacity Utilization (assume 80% is optimal)
        # For MVP, simplified calculation
        scores['capacity'] = 80.0  # Default for MVP
        
        # 4. Time Window Compliance (MVP: assume 100% if no violations)
        scores['time_windows'] = 100.0
        
        # 5. Stop Density (more stops per mile is better)
        if route.metrics.total_distance_miles > 0:
            density = route.metrics.total_stops / route.metrics.total_distance_miles
            scores['density'] = min(100, density * 20)  # Scale to 0-100
        else:
            scores['density'] = 0
        
        # 6. Driver Balance (compare to average stops across all routes)
        if all_routes:
            avg_stops = sum(r.metrics.total_stops for r in all_routes) / len(all_routes)
            variance = abs(route.metrics.total_stops - avg_stops) / max(avg_stops, 1) * 100
            scores['balance'] = max(0, 100 - variance)
        else:
            scores['balance'] = 100
        
        # Calculate weighted total score
        total_score = sum(scores[factor] * weights.get(factor, 0) for factor in scores)
        
        # Assign grade
        if total_score >= 90:
            grade = 'A'
        elif total_score >= 80:
            grade = 'B'
        elif total_score >= 70:
            grade = 'C'
        elif total_score >= 60:
            grade = 'D'
        else:
            grade = 'F'
        
        return OptimizationScore(
            total_score=round(total_score, 1),
            distance_score=round(scores['distance'], 1),
            time_score=round(scores['time'], 1),
            capacity_score=round(scores['capacity'], 1),
            time_window_score=round(scores['time_windows'], 1),
            density_score=round(scores['density'], 1),
            balance_score=round(scores['balance'], 1),
            grade=grade
        )
    
    def optimize_routes(
        self,
        orders: List[Order],
        vehicles: List[RouteMateVehicle],
        start_location: Location,
        optimization_weights: Dict[str, float],
        tenant_id: str,
        route_date: str
    ) -> List[Route]:
        """
        Main optimization function
        Distributes orders across vehicles and creates optimized routes
        """
        routes = []
        remaining_orders = orders.copy()
        
        # Create distance matrix for all order locations
        all_locations = [order.location for order in orders]
        order_to_idx = {order.id: idx for idx, order in enumerate(orders)}
        distance_matrix = self.create_distance_matrix(all_locations)
        
        for idx, vehicle in enumerate(vehicles):
            if not remaining_orders:
                break
            
            # Create route using nearest neighbor
            route_orders = self.nearest_neighbor_route(
                remaining_orders,
                start_location,
                vehicle
            )
            
            if not route_orders:
                continue
            
            # Improve route using 2-opt
            improved_orders = self.two_opt_improvement(
                route_orders,
                distance_matrix,
                order_to_idx
            )
            
            # Convert orders to route stops
            stops = []
            for seq, order in enumerate(improved_orders, start=1):
                stop = RouteStop(
                    sequence=seq,
                    customer_id=order.customer_id,
                    location=order.location,
                    planned_duration=15,  # Default 15 minutes
                    time_window=order.time_window,
                    service_type=order.service_type,
                    items=[item.dict() for item in order.items],
                    notes=order.notes,
                    special_requirements=order.special_requirements
                )
                stops.append(stop)
            
            # Create route
            route = Route(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                name=f"Route {idx + 1}",
                route_date=route_date,
                status="optimized",
                vehicle_id=vehicle.id,
                stops=stops,
                metrics=self.calculate_route_metrics(stops, vehicle),
                created_at=datetime.now(timezone.utc).isoformat(),
                optimized_at=datetime.now(timezone.utc).isoformat()
            )
            
            routes.append(route)
            
            # Remove assigned orders
            for order in improved_orders:
                if order in remaining_orders:
                    remaining_orders.remove(order)
        
        # Calculate optimization scores for all routes
        for route in routes:
            route.optimization_score = self.calculate_optimization_score(
                route,
                routes,
                optimization_weights
            )
        
        return routes

# Global optimizer instance
route_optimizer = RouteOptimizer()
