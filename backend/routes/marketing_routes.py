from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone
from typing import Optional, List
from database import db
from auth import get_current_user
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketing", tags=["Marketing"])

# Models
class DemoRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    company: str
    phone: Optional[str] = None
    role: Optional[str] = None
    fleet_size: Optional[str] = None
    message: Optional[str] = None

class DemoRequestResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    company: str
    phone: Optional[str]
    role: Optional[str]
    fleet_size: Optional[str]
    message: Optional[str]
    status: str
    created_at: str
    notes: Optional[str]

class WebsiteContent(BaseModel):
    section: str
    content: dict

class WebsiteContentUpdate(BaseModel):
    content: dict

# Email notification function (simple implementation)
async def send_demo_notification(demo_data: dict):
    """Send email notification for new demo request"""
    notification_email = os.environ.get('DEMO_NOTIFICATION_EMAIL', 'aminderpro@gmail.com')
    
    try:
        # For now, log the notification. Email integration can be added later
        logger.info(f"New demo request notification for {notification_email}")
        logger.info(f"Demo request from: {demo_data.get('first_name')} {demo_data.get('last_name')}")
        logger.info(f"Company: {demo_data.get('company')}")
        logger.info(f"Email: {demo_data.get('email')}")
        
        # Store notification in database for the admin to see
        await db.demo_notifications.insert_one({
            "demo_request_id": demo_data.get('id'),
            "notification_email": notification_email,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "status": "logged"  # Change to "sent" when email is integrated
        })
        
    except Exception as e:
        logger.error(f"Failed to send demo notification: {str(e)}")


# Public Endpoints (no auth required)

@router.post("/demo-request", response_model=dict)
async def submit_demo_request(request: DemoRequest, background_tasks: BackgroundTasks):
    """Submit a demo request from the marketing website"""
    try:
        demo_doc = {
            "first_name": request.first_name,
            "last_name": request.last_name,
            "email": request.email,
            "company": request.company,
            "phone": request.phone,
            "role": request.role,
            "fleet_size": request.fleet_size,
            "message": request.message,
            "status": "new",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "notes": None,
            "assigned_to": None
        }
        
        result = await db.demo_requests.insert_one(demo_doc)
        demo_doc["id"] = str(result.inserted_id)
        
        # Send notification in background
        background_tasks.add_task(send_demo_notification, demo_doc)
        
        return {
            "status": "success",
            "message": "Demo request submitted successfully. Our team will contact you within 24 hours."
        }
        
    except Exception as e:
        logger.error(f"Failed to submit demo request: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to submit demo request")


@router.get("/content/{section}")
async def get_website_content(section: str):
    """Get website content for a specific section (public)"""
    content = await db.website_content.find_one(
        {"section": section},
        {"_id": 0}
    )
    
    if not content:
        # Return default content for the section
        default_content = get_default_content(section)
        return {"section": section, "content": default_content}
    
    return content


# Admin Endpoints (auth required)

@router.get("/admin/demo-requests", response_model=List[DemoRequestResponse])
async def get_demo_requests(
    status: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    """Get all demo requests (admin only)"""
    if current_user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    query = {}
    if status:
        query["status"] = status
    
    requests = await db.demo_requests.find(query).sort("created_at", -1).to_list(500)
    
    return [
        DemoRequestResponse(
            id=str(r["_id"]),
            first_name=r["first_name"],
            last_name=r["last_name"],
            email=r["email"],
            company=r["company"],
            phone=r.get("phone"),
            role=r.get("role"),
            fleet_size=r.get("fleet_size"),
            message=r.get("message"),
            status=r["status"],
            created_at=r["created_at"],
            notes=r.get("notes")
        )
        for r in requests
    ]


@router.put("/admin/demo-requests/{request_id}")
async def update_demo_request(
    request_id: str,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    """Update a demo request status/notes (admin only)"""
    if current_user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    from bson import ObjectId
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if status:
        update_data["status"] = status
    if notes is not None:
        update_data["notes"] = notes
    
    result = await db.demo_requests.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Demo request not found")
    
    return {"status": "success", "message": "Demo request updated"}


@router.get("/admin/content")
async def get_all_website_content(current_user = Depends(get_current_user)):
    """Get all website content sections (admin only)"""
    if current_user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    content = await db.website_content.find({}, {"_id": 0}).to_list(100)
    
    # If no content exists, return defaults
    if not content:
        return get_all_default_content()
    
    return content


@router.put("/admin/content/{section}")
async def update_website_content(
    section: str,
    update: WebsiteContentUpdate,
    current_user = Depends(get_current_user)
):
    """Update website content for a section (admin only)"""
    if current_user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.website_content.update_one(
        {"section": section},
        {
            "$set": {
                "section": section,
                "content": update.content,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": current_user.email
            }
        },
        upsert=True
    )
    
    return {"status": "success", "message": f"Content for '{section}' updated"}


@router.get("/admin/stats")
async def get_marketing_stats(current_user = Depends(get_current_user)):
    """Get marketing statistics (admin only)"""
    if current_user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Count demo requests by status
    total = await db.demo_requests.count_documents({})
    new = await db.demo_requests.count_documents({"status": "new"})
    contacted = await db.demo_requests.count_documents({"status": "contacted"})
    converted = await db.demo_requests.count_documents({"status": "converted"})
    
    # Get recent requests
    recent = await db.demo_requests.find({}).sort("created_at", -1).limit(5).to_list(5)
    
    return {
        "total_requests": total,
        "new_requests": new,
        "contacted": contacted,
        "converted": converted,
        "recent_requests": [
            {
                "id": str(r["_id"]),
                "name": f"{r['first_name']} {r['last_name']}",
                "company": r["company"],
                "created_at": r["created_at"],
                "status": r["status"]
            }
            for r in recent
        ]
    }


def get_default_content(section: str) -> dict:
    """Get default content for a section"""
    defaults = {
        "hero": {
            "title": "Transform Your Logistics Operations",
            "subtitle": "Our Transportation Management System helps freight brokers, fleet owners, and dispatchers streamline operations, reduce costs, and deliver exceptional service.",
            "cta_primary": "Request a Demo",
            "cta_secondary": "Learn More"
        },
        "features": {
            "title": "Powerful Features",
            "subtitle": "Every tool you need to manage your logistics operations."
        },
        "pricing": {
            "title": "Simple, Transparent Pricing",
            "price": "$299",
            "period": "/month"
        },
        "about": {
            "mission": "Empowering Logistics Professionals",
            "description": "We founded Integrated Supply Chain Technologies to transform logistics operations with modern technology."
        },
        "contact": {
            "email": "sales@integratedsct.com",
            "phone": "1-800-555-1234",
            "address": "123 Logistics Way, Suite 500, Chicago, IL 60601"
        }
    }
    return defaults.get(section, {})


def get_all_default_content() -> list:
    """Get all default content sections"""
    sections = ["hero", "features", "pricing", "about", "contact"]
    return [
        {"section": s, "content": get_default_content(s)}
        for s in sections
    ]
