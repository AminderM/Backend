from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from fastapi import BackgroundTasks, WebSocket
from typing import List, Optional, Dict
from pydantic import EmailStr
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import os
import logging
import json

logger = logging.getLogger(__name__)

# Check if email is configured
EMAIL_CONFIGURED = bool(
    os.environ.get('MAIL_USERNAME') and 
    os.environ.get('MAIL_PASSWORD') and 
    os.environ.get('MAIL_FROM')
)

# Email configuration - only create if properly configured
conf = None
if EMAIL_CONFIGURED:
    try:
        conf = ConnectionConfig(
            MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
            MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),
            MAIL_FROM=os.environ.get('MAIL_FROM'),
            MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
            MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
            MAIL_FROM_NAME=os.environ.get('MAIL_FROM_NAME', 'Fleet Marketplace'),
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True,
            TEMPLATE_FOLDER=Path(__file__).parent / 'templates'
        )
    except Exception as e:
        logger.error(f"Failed to configure email: {e}")
        EMAIL_CONFIGURED = False

# Jinja2 environment for email templates
templates_dir = Path(__file__).parent / 'templates'
env = Environment(loader=FileSystemLoader(str(templates_dir)))

class EmailService:
    def __init__(self):
        self.fastmail = FastMail(conf) if conf else None
        self.enabled = EMAIL_CONFIGURED
        
    async def send_email(
        self, 
        recipients: List[EmailStr], 
        subject: str, 
        body: str = "",
        template_name: Optional[str] = None,
        template_body: Optional[dict] = None
    ):
        """Send email with optional template"""
        if not self.enabled:
            logger.warning(f"Email not configured. Would send: {subject} to {recipients}")
            return
            
        try:
            if template_name and template_body:
                message = MessageSchema(
                    subject=subject,
                    recipients=recipients,
                    template_body=template_body,
                    subtype=MessageType.html
                )
                await self.fastmail.send_message(message, template_name=template_name)
            else:
                message = MessageSchema(
                    subject=subject,
                    recipients=recipients,
                    body=body,
                    subtype=MessageType.html
                )
                await self.fastmail.send_message(message)
                
            logger.info(f"Email sent successfully to {len(recipients)} recipients: {subject}")
        except Exception as e:
            logger.error(f"Failed to send email '{subject}': {str(e)}")
            raise
    
    def send_in_background(
        self,
        background_tasks: BackgroundTasks,
        recipients: List[EmailStr], 
        subject: str, 
        body: str = "",
        template_name: Optional[str] = None,
        template_body: Optional[dict] = None
    ):
        """Schedule email to be sent in background"""
        background_tasks.add_task(
            self.send_email,
            recipients,
            subject,
            body,
            template_name,
            template_body
        )

# Global email service instance
email_service = EmailService()

# WebSocket Connection Manager for Live Tracking
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.fleet_connections: List[WebSocket] = []
    
    async def connect_vehicle(self, websocket: WebSocket, vehicle_id: str):
        await websocket.accept()
        if vehicle_id not in self.active_connections:
            self.active_connections[vehicle_id] = []
        self.active_connections[vehicle_id].append(websocket)
        logger.info(f"Vehicle {vehicle_id} connected. Total connections: {len(self.active_connections.get(vehicle_id, []))}")
    
    async def connect_fleet(self, websocket: WebSocket):
        await websocket.accept()
        self.fleet_connections.append(websocket)
        logger.info(f"Fleet manager connected. Total fleet connections: {len(self.fleet_connections)}")
    
    def disconnect_vehicle(self, websocket: WebSocket, vehicle_id: str):
        if vehicle_id in self.active_connections:
            self.active_connections[vehicle_id] = [
                ws for ws in self.active_connections[vehicle_id] if ws != websocket
            ]
            if not self.active_connections[vehicle_id]:
                del self.active_connections[vehicle_id]
        logger.info(f"Vehicle {vehicle_id} disconnected")
    
    def disconnect_fleet(self, websocket: WebSocket):
        self.fleet_connections = [ws for ws in self.fleet_connections if ws != websocket]
        logger.info("Fleet manager disconnected")
    
    async def send_to_vehicle(self, message: str, vehicle_id: str):
        if vehicle_id in self.active_connections:
            dead_connections = []
            for connection in self.active_connections[vehicle_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    dead_connections.append(connection)
            
            # Remove dead connections
            for dead_conn in dead_connections:
                self.disconnect_vehicle(dead_conn, vehicle_id)
    
    async def broadcast_to_fleet(self, message: str):
        dead_connections = []
        for connection in self.fleet_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead_connections.append(connection)
        
        # Remove dead connections
        for dead_conn in dead_connections:
            self.disconnect_fleet(dead_conn)
    
    async def broadcast_location_update(self, location_data: dict):
        message = json.dumps({
            "type": "location_update",
            "payload": location_data
        })
        await self.broadcast_to_fleet(message)
    
    async def broadcast_status_update(self, status_data: dict):
        message = json.dumps({
            "type": "vehicle_status", 
            "payload": status_data
        })
        await self.broadcast_to_fleet(message)

# Global connection manager instance
manager = ConnectionManager()

# Helper functions for specific email types
async def send_verification_email(
    background_tasks: BackgroundTasks,
    email: str, 
    name: str, 
    verification_url: str
):
    """Send email verification link"""
    template_data = {
        "name": name,
        "verification_url": verification_url,
        "expiry_hours": 24
    }
    
    email_service.send_in_background(
        background_tasks,
        recipients=[email],
        subject="Verify Your Email Address - Fleet Marketplace",
        template_name="verification_email.html",
        template_body=template_data
    )

async def send_company_verification_email(
    background_tasks: BackgroundTasks,
    email: str, 
    name: str, 
    company_name: str
):
    """Send company verification notification"""
    app_url = os.environ.get('APP_URL', 'http://localhost:3000')
    template_data = {
        "name": name,
        "company_name": company_name,
        "dashboard_url": f"{app_url}/dashboard"
    }
    
    email_service.send_in_background(
        background_tasks,
        recipients=[email],
        subject=f"Company Verified: {company_name} - Fleet Marketplace",
        template_name="company_verified.html",
        template_body=template_data
    )

async def send_booking_confirmation_emails(
    background_tasks: BackgroundTasks,
    customer_email: str,
    customer_name: str,
    provider_email: str,
    provider_name: str,
    booking_details: dict
):
    """Send booking confirmation to both customer and provider"""
    
    # Email to customer
    customer_template_data = {
        "customer_name": customer_name,
        "service_name": booking_details.get("equipment_name", "Equipment"),
        "provider_name": provider_name,
        "booking_date": booking_details.get("start_date", ""),
        "end_date": booking_details.get("end_date", ""),
        "pickup_location": booking_details.get("pickup_location", ""),
        "delivery_location": booking_details.get("delivery_location", ""),
        "total_cost": booking_details.get("total_cost", 0),
        "booking_id": booking_details.get("booking_id", ""),
        "notes": booking_details.get("notes", "No special notes")
    }
    
    email_service.send_in_background(
        background_tasks,
        recipients=[customer_email],
        subject="Booking Confirmation - Your Equipment is Reserved",
        template_name="booking_confirmation_customer.html",
        template_body=customer_template_data
    )
    
    # Email to provider
    provider_template_data = {
        "provider_name": provider_name,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "service_name": booking_details.get("equipment_name", "Equipment"),
        "booking_date": booking_details.get("start_date", ""),
        "end_date": booking_details.get("end_date", ""),
        "pickup_location": booking_details.get("pickup_location", ""),
        "delivery_location": booking_details.get("delivery_location", ""),
        "total_cost": booking_details.get("total_cost", 0),
        "booking_id": booking_details.get("booking_id", ""),
        "notes": booking_details.get("notes", "No special notes")
    }
    
    email_service.send_in_background(
        background_tasks,
        recipients=[provider_email],
        subject="New Equipment Booking Received - Fleet Marketplace",
        template_name="booking_confirmation_provider.html",
        template_body=provider_template_data
    )