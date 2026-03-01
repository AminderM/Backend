"""
WebSocket connection manager for real-time fleet tracking
"""
from fastapi import WebSocket
from typing import Dict, List, Set
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for fleet tracking"""
    
    def __init__(self):
        # Fleet managers/dashboard connections
        self.fleet_connections: Set[WebSocket] = set()
        
        # Vehicle/driver connections mapped by vehicle_id
        self.vehicle_connections: Dict[str, WebSocket] = {}
    
    async def connect_fleet(self, websocket: WebSocket):
        """Connect a fleet manager/dashboard"""
        await websocket.accept()
        self.fleet_connections.add(websocket)
        logger.info(f"Fleet manager connected. Total fleet connections: {len(self.fleet_connections)}")
    
    def disconnect_fleet(self, websocket: WebSocket):
        """Disconnect a fleet manager/dashboard"""
        self.fleet_connections.discard(websocket)
        logger.info(f"Fleet manager disconnected. Total fleet connections: {len(self.fleet_connections)}")
    
    async def connect_vehicle(self, websocket: WebSocket, vehicle_id: str):
        """Connect a vehicle/driver"""
        await websocket.accept()
        self.vehicle_connections[vehicle_id] = websocket
        logger.info(f"Vehicle {vehicle_id} connected. Total vehicles: {len(self.vehicle_connections)}")
    
    def disconnect_vehicle(self, websocket: WebSocket, vehicle_id: str):
        """Disconnect a vehicle/driver"""
        if vehicle_id in self.vehicle_connections:
            del self.vehicle_connections[vehicle_id]
        logger.info(f"Vehicle {vehicle_id} disconnected. Total vehicles: {len(self.vehicle_connections)}")
    
    async def broadcast_location_update(self, location_data: dict):
        """Broadcast location update to all fleet managers"""
        message = json.dumps({
            "type": "location_update",
            "payload": location_data
        })
        
        disconnected = set()
        for connection in self.fleet_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to fleet connection: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.fleet_connections.discard(connection)
    
    async def broadcast_status_update(self, status_data: dict):
        """Broadcast status update to all fleet managers"""
        message = json.dumps({
            "type": "status_update",
            "payload": status_data
        })
        
        disconnected = set()
        for connection in self.fleet_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting status: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.fleet_connections.discard(connection)
    
    async def send_to_vehicle(self, vehicle_id: str, message: dict):
        """Send a message to a specific vehicle"""
        if vehicle_id in self.vehicle_connections:
            try:
                await self.vehicle_connections[vehicle_id].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending to vehicle {vehicle_id}: {e}")
                del self.vehicle_connections[vehicle_id]
    
    def get_connected_vehicles(self) -> List[str]:
        """Get list of currently connected vehicle IDs"""
        return list(self.vehicle_connections.keys())
    
    def is_vehicle_connected(self, vehicle_id: str) -> bool:
        """Check if a vehicle is currently connected"""
        return vehicle_id in self.vehicle_connections
