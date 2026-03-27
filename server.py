from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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
from routes import integrations_routes
from routes import route_mate_routes
from routes import user_management_routes
from routes import tms_chat_routes
from routes import driver_app_routes
from routes import driver_mobile_routes
from routes import driver_ai_routes
from routes import sales_routes
from routes import fmcsa_routes
from routes import bundle_routes
from routes import accounting_routes
from routes import analytics_routes
from routes import marketing_routes
from routes import customer_analytics_routes
from routes import dashboard_routes
from routes import scheduled_reports
from routes import history_routes

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# WebSocket Manager
manager = ConnectionManager()

# Set websocket manager for customer analytics real-time updates
customer_analytics_routes.set_websocket_manager(manager)

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
api_router.include_router(integrations_routes.router)
api_router.include_router(route_mate_routes.router)
api_router.include_router(user_management_routes.router, prefix="/admin", tags=["User Management"])
api_router.include_router(tms_chat_routes.router)
api_router.include_router(driver_app_routes.router)
api_router.include_router(driver_mobile_routes.router)
api_router.include_router(driver_ai_routes.router)
api_router.include_router(sales_routes.router)
api_router.include_router(fmcsa_routes.router)
api_router.include_router(bundle_routes.router)
api_router.include_router(accounting_routes.router)
api_router.include_router(analytics_routes.router)
api_router.include_router(marketing_routes.router)
api_router.include_router(customer_analytics_routes.router)
api_router.include_router(dashboard_routes.router)
api_router.include_router(scheduled_reports.router)
api_router.include_router(history_routes.router)

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

# WebSocket endpoint for real-time analytics dashboard
@api_router.websocket("/ws/analytics")
async def analytics_websocket_endpoint(websocket: WebSocket, token: str = None):
    """WebSocket endpoint for real-time analytics dashboard updates"""
    await manager.connect_analytics(websocket)
    try:
        while True:
            # Keep connection alive, handle any incoming messages
            data = await websocket.receive_text()
            # Echo back for ping/pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_analytics(websocket)

# CORS Middleware - must be added before routes
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Root endpoint
@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "server is running"}

# Include the API router in the main app
app.include_router(api_router)

# Serve API documentation files
DOCS_DIR = ROOT_DIR / "static" / "docs"
if DOCS_DIR.exists():
    @app.get("/api/docs/download/pdf")
    async def download_api_docs_pdf():
        """Download API documentation as PDF"""
        return FileResponse(
            DOCS_DIR / "API_DOCUMENTATION.pdf",
            media_type="application/pdf",
            filename="TMS_API_Documentation.pdf"
        )
    
    @app.get("/api/docs/download/txt")
    async def download_api_docs_txt():
        """Download API documentation as TXT"""
        return FileResponse(
            DOCS_DIR / "API_DOCUMENTATION.txt",
            media_type="text/plain",
            filename="TMS_API_Documentation.txt"
        )
    
    @app.get("/api/docs/download/md")
    async def download_api_docs_md():
        """Download API documentation as Markdown"""
        return FileResponse(
            DOCS_DIR / "API_DOCUMENTATION.md",
            media_type="text/markdown",
            filename="TMS_API_Documentation.md"
        )
    
    @app.get("/api/docs/download/frontend-guide")
    async def download_frontend_guide():
        """Download complete Frontend Developer Guide"""
        return FileResponse(
            DOCS_DIR / "FRONTEND_DEVELOPER_GUIDE.md",
            media_type="text/markdown",
            filename="TMS_Frontend_Developer_Guide.md"
        )
    
    @app.get("/api/docs/download/frontend-guide-txt")
    async def download_frontend_guide_txt():
        """Download Frontend Developer Guide as TXT"""
        return FileResponse(
            DOCS_DIR / "FRONTEND_DEVELOPER_GUIDE.txt",
            media_type="text/plain",
            filename="TMS_Frontend_Developer_Guide.txt"
        )
    
    @app.get("/api/docs/download/user-management-pdf")
    async def download_user_management_pdf():
        """Download User Management Structure diagram"""
        return FileResponse(
            DOCS_DIR / "USER_MANAGEMENT_STRUCTURE.pdf",
            media_type="application/pdf",
            filename="TMS_User_Management_Structure.pdf"
        )
    
    @app.get("/api/docs/list")
    async def list_available_docs():
        """List all available documentation files"""
        return {
            "documents": [
                {
                    "name": "Frontend Developer Guide",
                    "description": "Complete guide for frontend developers including API reference, data models, and UI/UX requirements",
                    "formats": ["md", "txt"],
                    "download_urls": {
                        "md": "/api/docs/download/frontend-guide",
                        "txt": "/api/docs/download/frontend-guide-txt"
                    }
                },
                {
                    "name": "API Documentation",
                    "description": "Detailed API endpoint reference",
                    "formats": ["pdf", "md", "txt"],
                    "download_urls": {
                        "pdf": "/api/docs/download/pdf",
                        "md": "/api/docs/download/md",
                        "txt": "/api/docs/download/txt"
                    }
                },
                {
                    "name": "User Management Structure",
                    "description": "Role hierarchy and workspace access diagram",
                    "formats": ["pdf"],
                    "download_urls": {
                        "pdf": "/api/docs/download/user-management-pdf"
                    }
                }
            ]
        }

# Serve marketing website static files under /api/site
MARKETING_DIR = ROOT_DIR / "marketing-static"
if MARKETING_DIR.exists():
    app.mount("/api/site/static", StaticFiles(directory=str(MARKETING_DIR / "static")), name="marketing-static")
    
    @app.get("/api/site/{full_path:path}")
    async def serve_marketing_site(full_path: str = ""):
        """Serve marketing website - SPA fallback to index.html"""
        file_path = MARKETING_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(MARKETING_DIR / "index.html")
    
    @app.get("/api/site")
    async def serve_marketing_root():
        """Serve marketing website root"""
        return FileResponse(MARKETING_DIR / "index.html")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_seed_admin():
    """Seed platform admin on startup for production deployments"""
    try:
        from models import User, UserRole, RegistrationStatus
        from auth import hash_password
        
        # Check if platform admin exists
        admin_email = os.environ.get('PLATFORM_ADMIN_EMAIL', 'aminderpro@gmail.com')
        admin_password = os.environ.get('PLATFORM_ADMIN_PASSWORD', 'Admin@123!')
        
        existing = await db.users.find_one({"email": admin_email})
        
        if not existing:
            # Create platform admin
            hashed_password = hash_password(admin_password)
            user = User(
                email=admin_email,
                full_name="Platform Admin",
                phone="0000000000",
                role=UserRole.PLATFORM_ADMIN,
                email_verified=True,
                registration_status=RegistrationStatus.VERIFIED,
            ).dict()
            user["password_hash"] = hashed_password
            await db.users.insert_one(user)
            logging.info(f"✅ Platform admin seeded: {admin_email}")
        else:
            logging.info(f"✅ Platform admin already exists: {admin_email}")
    except Exception as e:
        logging.error(f"⚠️ Failed to seed platform admin: {str(e)}")

@app.on_event("startup")
async def startup_scheduler():
    """Initialize the scheduled reports scheduler"""
    try:
        await scheduled_reports.init_scheduler()
        logging.info("✅ Scheduled reports scheduler initialized")
    except Exception as e:
        logging.error(f"⚠️ Failed to initialize scheduler: {str(e)}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
    logger.info("Database connection closed")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
