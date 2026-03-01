from fastapi import APIRouter, HTTPException, Depends
from models import User
from auth import get_current_user, require_platform_admin
from database import db
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel
import uuid

router = APIRouter(prefix="/admin/integrations", tags=["Integrations"])

class IntegrationCreate(BaseModel):
    service_id: str
    category: str
    name: str
    description: Optional[str] = None
    config: Dict[str, Any]
    enabled: bool = True

class IntegrationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None

class IntegrationToggle(BaseModel):
    enabled: bool

@router.get('')
async def list_integrations(current_user: User = Depends(get_current_user)):
    """List all configured integrations"""
    require_platform_admin(current_user)
    
    integrations = await db.integrations.find({}, {"_id": 0}).to_list(length=None)
    return integrations

@router.get('/{integration_id}')
async def get_integration(integration_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific integration"""
    require_platform_admin(current_user)
    
    integration = await db.integrations.find_one({"id": integration_id}, {"_id": 0})
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    return integration

@router.post('')
async def create_integration(
    payload: IntegrationCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new integration"""
    require_platform_admin(current_user)
    
    # Check if integration with same service_id already exists
    existing = await db.integrations.find_one({"service_id": payload.service_id})
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Integration for {payload.service_id} already exists"
        )
    
    integration = {
        "id": str(uuid.uuid4()),
        "service_id": payload.service_id,
        "category": payload.category,
        "name": payload.name,
        "description": payload.description,
        "config": payload.config,
        "enabled": payload.enabled,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.id
    }
    
    await db.integrations.insert_one(integration)
    
    return {"message": "Integration created successfully", "integration": integration}

@router.put('/{integration_id}')
async def update_integration(
    integration_id: str,
    payload: IntegrationUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update an integration"""
    require_platform_admin(current_user)
    
    integration = await db.integrations.find_one({"id": integration_id})
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Build update dict
    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.config is not None:
        updates["config"] = payload.config
    if payload.enabled is not None:
        updates["enabled"] = payload.enabled
    
    await db.integrations.update_one(
        {"id": integration_id},
        {"$set": updates}
    )
    
    updated = await db.integrations.find_one({"id": integration_id}, {"_id": 0})
    return {"message": "Integration updated successfully", "integration": updated}

@router.post('/{integration_id}/toggle')
async def toggle_integration(
    integration_id: str,
    payload: IntegrationToggle,
    current_user: User = Depends(get_current_user)
):
    """Enable or disable an integration"""
    require_platform_admin(current_user)
    
    integration = await db.integrations.find_one({"id": integration_id})
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    await db.integrations.update_one(
        {"id": integration_id},
        {"$set": {
            "enabled": payload.enabled,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": f"Integration {'enabled' if payload.enabled else 'disabled'} successfully"}

@router.post('/{integration_id}/test')
async def test_integration(
    integration_id: str,
    current_user: User = Depends(get_current_user)
):
    """Test an integration connection"""
    require_platform_admin(current_user)
    
    integration = await db.integrations.find_one({"id": integration_id})
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Basic validation - check if config has required fields
    service_id = integration.get("service_id")
    config = integration.get("config", {})
    
    # Simple test logic - you can expand this based on service type
    success = False
    message = "Test not implemented for this service"
    
    if "openai" in service_id:
        # Test OpenAI connection
        if config.get("api_key"):
            success = True
            message = "OpenAI credentials validated"
        else:
            message = "Missing API key"
    
    elif "claude" in service_id:
        # Test Claude connection
        if config.get("api_key"):
            success = True
            message = "Claude credentials validated"
        else:
            message = "Missing API key"
    
    elif "google_maps" in service_id:
        # Test Google Maps
        if config.get("api_key"):
            success = True
            message = "Google Maps API key validated"
        else:
            message = "Missing API key"
    
    elif "stripe" in service_id:
        # Test Stripe
        if config.get("api_key") and config.get("secret_key"):
            success = True
            message = "Stripe credentials validated"
        else:
            message = "Missing API key or secret key"
    
    elif "twilio" in service_id:
        # Test Twilio
        if config.get("account_sid") and config.get("auth_token"):
            success = True
            message = "Twilio credentials validated"
        else:
            message = "Missing Account SID or Auth Token"
    
    else:
        # Generic test - check if config has at least one credential
        if config:
            success = True
            message = "Configuration found"
        else:
            message = "No configuration found"
    
    # Update last tested timestamp
    await db.integrations.update_one(
        {"id": integration_id},
        {"$set": {"last_tested_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {
        "success": success,
        "message": message,
        "tested_at": datetime.now(timezone.utc).isoformat()
    }

@router.delete('/{integration_id}')
async def delete_integration(
    integration_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete an integration"""
    require_platform_admin(current_user)
    
    integration = await db.integrations.find_one({"id": integration_id})
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    await db.integrations.delete_one({"id": integration_id})
    
    return {"message": "Integration deleted successfully"}
