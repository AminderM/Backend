from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
import os
import logging
from datetime import datetime, timezone

# Import database connection
from database import db, client

# Import WebSocket manager
from websocket_manager import ConnectionManager

# Import all route modules
from routes import auth_routes
from routes import company_routes
from routes import user_routes
from routes import equipment_routes
from routes import driver_routes
from routes import location_routes
from routes import booking_routes
from routes import admin_routes
from routes import crm_routes
from routes import misc_routes

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# WebSocket Manager
manager = ConnectionManager()

# Create the main app
app = FastAPI(title="Fleet Marketplace API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Include all route modules
api_router.include_router(auth_routes.router)
api_router.include_router(company_routes.router)
api_router.include_router(user_routes.router)
api_router.include_router(equipment_routes.router)
api_router.include_router(driver_routes.router)
api_router.include_router(location_routes.router)
api_router.include_router(booking_routes.router)
api_router.include_router(admin_routes.router)
api_router.include_router(crm_routes.router)
api_router.include_router(misc_routes.router)

# WebSocket endpoint for real-time vehicle tracking
@api_router.websocket("/ws/vehicle/{vehicle_id}")
async def vehicle_websocket_endpoint(websocket: WebSocket, vehicle_id: str):
    await manager.connect_vehicle(websocket, vehicle_id)
    try:
        while True:
            data = await websocket.receive_json()
            # Broadcast location update to all connected clients tracking this vehicle
            await manager.broadcast_to_vehicle(vehicle_id, data)
                
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_vehicle(websocket, vehicle_id)

# Include the API router in the main app
app.include_router(api_router)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
    logger.info("Database connection closed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
