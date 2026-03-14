from fastapi import APIRouter, HTTPException, Depends
from models import *
from auth import get_current_user, require_platform_admin
from database import db
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pydantic import BaseModel
import random
import uuid

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get('/tenants')
async def list_tenants(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    tenants = await db.companies.find({}).to_list(length=None)
    
    def enrich_tenant(c):
        # Calculate total seats and storage across all subscriptions
        subscriptions = c.get("subscriptions", [])
        total_seats_allocated = sum(sub.get("seats_allocated", 0) for sub in subscriptions)
        total_seats_used = sum(sub.get("seats_used", 0) for sub in subscriptions)
        total_storage_allocated = sum(sub.get("storage_allocated_gb", 0) for sub in subscriptions)
        total_storage_used = sum(sub.get("storage_used_gb", 0) for sub in subscriptions)
        
        # Get product labels for active subscriptions
        active_products = []
        for sub in subscriptions:
            if sub.get("status") == "active":
                plan = next((p for p in PLANS if p["id"] == sub.get("product_id")), None)
                if plan:
                    base_price = plan.get("price", 0)
                    discount = sub.get("discount_percentage", 0)
                    discounted_price = base_price * (1 - discount / 100)
                    
                    active_products.append({
                        "id": sub.get("id"),
                        "product_id": sub.get("product_id"),
                        "label": plan.get("label"),
                        "tier": plan.get("tier"),
                        "status": sub.get("status"),
                        "base_price": base_price,
                        "discount_percentage": discount,
                        "discounted_price": discounted_price,
                        "discount_reason": sub.get("discount_reason")
                    })
        
        return {
            "id": c.get("id"),
            "name": c.get("name"),
            "company_email": c.get("company_email"),
            "phone_number": c.get("phone_number"),
            "plan": c.get("plan", "tms_basic"),  # Legacy field
            "seats": c.get("seats", 5),  # Legacy field
            "subscription_status": c.get("subscription_status", "active"),
            "subscriptions": subscriptions,
            "active_products": active_products,
            "total_seats_allocated": total_seats_allocated,
            "total_seats_used": total_seats_used,
            "total_storage_allocated": total_storage_allocated,
            "total_storage_used": total_storage_used,
            "billing_email": c.get("billing_email"),
            "payment_method": c.get("payment_method"),
            "next_billing_date": c.get("next_billing_date"),
            "feature_flags": c.get("feature_flags", {}),
            "created_at": c.get("created_at"),
        }
    return [enrich_tenant(c) for c in tenants]

class TenantCreate(BaseModel):
    name: str
    email: str
    phone: str
    address: Optional[str] = None
    total_seats_allocated: int = 10
    storage_limit_gb: int = 50

@router.post('/tenants')
async def create_tenant(tenant_data: TenantCreate, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    
    # Check if company with same name already exists
    existing = await db.companies.find_one({"name": tenant_data.name})
    if existing:
        raise HTTPException(status_code=400, detail="Company with this name already exists")
    
    # Check if email already exists
    existing_email = await db.companies.find_one({"company_email": tenant_data.email})
    if existing_email:
        raise HTTPException(status_code=400, detail="Company with this email already exists")
    
    # Create new tenant
    new_tenant = {
        "id": str(uuid.uuid4()),
        "name": tenant_data.name,
        "company_email": tenant_data.email,
        "phone_number": tenant_data.phone,
        "address": tenant_data.address or "",
        "city": "",
        "state": "",
        "zip_code": "",
        "billing_email": tenant_data.email,
        "payment_method": "credit_card",
        "subscription_status": "active",
        "plan": "tms_basic",  # Default plan
        "seats": tenant_data.total_seats_allocated,
        "total_seats_allocated": tenant_data.total_seats_allocated,
        "total_seats_used": 0,
        "storage_limit_gb": tenant_data.storage_limit_gb,
        "storage_used_gb": 0,
        "feature_flags": {},
        "subscriptions": [],
        "active_products": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.id
    }
    
    await db.companies.insert_one(new_tenant)
    
    return {
        "message": "Tenant created successfully",
        "tenant": {k: v for k, v in new_tenant.items() if k != "_id"}
    }

class TenantUpdate(BaseModel):
    name: Optional[str] = None
    company_email: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    billing_email: Optional[str] = None
    payment_method: Optional[str] = None
    subscription_status: Optional[str] = None
    plan: Optional[str] = None  # Legacy field
    seats: Optional[int] = None  # Legacy field
    feature_flags: Optional[Dict[str, bool]] = None

@router.put('/tenants/{tenant_id}')
async def update_tenant(tenant_id: str, payload: TenantUpdate, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    updates = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if not updates:
        return {"updated": False}
    await db.companies.update_one({"id": tenant_id}, {"$set": updates})
    tenant = await db.companies.find_one({"id": tenant_id})
    if tenant:
        # Remove MongoDB-specific fields that can't be serialized
        tenant.pop('_id', None)
        return tenant
    else:
        raise HTTPException(status_code=404, detail="Tenant not found")

class SubscriptionCreate(BaseModel):
    product_id: str
    seats_allocated: int = 5
    storage_allocated_gb: int = 10
    status: str = "active"
    discount_percentage: float = 0.0
    discount_reason: Optional[str] = None

class SubscriptionUpdate(BaseModel):
    seats_allocated: Optional[int] = None
    storage_allocated_gb: Optional[int] = None
    status: Optional[str] = None
    schedule_change: bool = True  # If True, changes apply at next billing cycle

@router.post('/tenants/{tenant_id}/subscriptions')
async def add_product_subscription(tenant_id: str, payload: SubscriptionCreate, current_user: User = Depends(get_current_user)):
    """Add a new product subscription to a tenant"""
    require_platform_admin(current_user)
    
    # Verify product exists
    product = next((p for p in PLANS if p["id"] == payload.product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Create subscription object
    subscription = {
        "id": str(uuid.uuid4()),
        "product_id": payload.product_id,
        "status": payload.status,
        "seats_allocated": payload.seats_allocated,
        "seats_used": 0,
        "storage_allocated_gb": payload.storage_allocated_gb,
        "storage_used_gb": 0.0,
        "discount_percentage": payload.discount_percentage,
        "discount_reason": payload.discount_reason,
        "start_date": datetime.now(timezone.utc).isoformat(),
        "next_billing_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "end_date": None,
        "pending_changes": None
    }
    
    # Add subscription to tenant
    await db.companies.update_one(
        {"id": tenant_id},
        {"$push": {"subscriptions": subscription}}
    )
    
    tenant = await db.companies.find_one({"id": tenant_id})
    return {"message": "Subscription added successfully", "subscription": subscription, "tenant": tenant}

@router.put('/tenants/{tenant_id}/subscriptions/{subscription_id}')
async def update_product_subscription(
    tenant_id: str, 
    subscription_id: str, 
    payload: SubscriptionUpdate, 
    current_user: User = Depends(get_current_user)
):
    """Update or schedule changes to a product subscription"""
    require_platform_admin(current_user)
    
    tenant = await db.companies.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    subscriptions = tenant.get("subscriptions", [])
    sub_index = next((i for i, s in enumerate(subscriptions) if s.get("id") == subscription_id), None)
    
    if sub_index is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    updates = payload.dict(exclude_unset=True, exclude={"schedule_change"})
    
    if payload.schedule_change:
        # Schedule changes for next billing cycle
        subscriptions[sub_index]["pending_changes"] = {
            **updates,
            "scheduled_at": datetime.now(timezone.utc).isoformat()
        }
    else:
        # Apply changes immediately
        subscriptions[sub_index].update(updates)
    
    await db.companies.update_one(
        {"id": tenant_id},
        {"$set": {"subscriptions": subscriptions}}
    )
    
    tenant = await db.companies.find_one({"id": tenant_id})
    return {"message": "Subscription updated successfully", "tenant": tenant}

@router.delete('/tenants/{tenant_id}/subscriptions/{subscription_id}')
async def remove_product_subscription(
    tenant_id: str, 
    subscription_id: str, 
    schedule_removal: bool = True,
    current_user: User = Depends(get_current_user)
):
    """Remove or schedule removal of a product subscription"""
    require_platform_admin(current_user)
    
    tenant = await db.companies.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    subscriptions = tenant.get("subscriptions", [])
    sub_index = next((i for i, s in enumerate(subscriptions) if s.get("id") == subscription_id), None)
    
    if sub_index is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if schedule_removal:
        # Schedule cancellation at end of billing period
        subscriptions[sub_index]["status"] = "pending_cancellation"
        subscriptions[sub_index]["pending_changes"] = {
            "action": "cancel",
            "scheduled_at": datetime.now(timezone.utc).isoformat()
        }
        await db.companies.update_one(
            {"id": tenant_id},
            {"$set": {"subscriptions": subscriptions}}
        )
        message = "Subscription cancellation scheduled for end of billing period"
    else:
        # Remove immediately
        await db.companies.update_one(
            {"id": tenant_id},
            {"$pull": {"subscriptions": {"id": subscription_id}}}
        )
        message = "Subscription removed immediately"
    
    tenant = await db.companies.find_one({"id": tenant_id})
    if tenant:
        tenant.pop('_id', None)
    return {"message": message, "tenant": tenant}

@router.get('/plans')
async def get_plans(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    return PLANS

@router.get('/analytics')
async def get_sales_analytics(current_user: User = Depends(get_current_user)):
    """Get comprehensive sales analytics"""
    require_platform_admin(current_user)
    
    tenants = await db.companies.find({}).to_list(length=None)
    
    # Calculate total lifetime revenue
    total_lifetime_revenue = 0
    monthly_revenue = {}
    weekly_revenue = {}
    new_customer_revenue = {}
    repeat_customer_data = {}
    customer_revenue = {}
    
    for tenant in tenants:
        tenant_id = tenant.get('id')
        created_at = tenant.get('created_at')
        subscriptions = tenant.get('subscriptions', [])
        
        if not created_at:
            continue
            
        # Parse creation date
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        # Calculate tenant's total revenue
        tenant_total_revenue = 0
        
        for sub in subscriptions:
            if sub.get('status') in ['active', 'trial']:
                product = next((p for p in PLANS if p['id'] == sub.get('product_id')), None)
                if product:
                    base_price = product.get('price', 0)
                    discount = sub.get('discount_percentage', 0)
                    final_price = base_price * (1 - discount / 100)
                    
                    tenant_total_revenue += final_price
                    total_lifetime_revenue += final_price
                    
                    # Monthly revenue breakdown
                    month_key = created_at.strftime('%Y-%m')
                    monthly_revenue[month_key] = monthly_revenue.get(month_key, 0) + final_price
                    
                    # Weekly revenue breakdown
                    week_key = created_at.strftime('%Y-W%W')
                    weekly_revenue[week_key] = weekly_revenue.get(week_key, 0) + final_price
                    
                    # Track new customer revenue (first month)
                    current_month = datetime.now(timezone.utc).strftime('%Y-%m')
                    if month_key == current_month:
                        new_customer_revenue[month_key] = new_customer_revenue.get(month_key, 0) + final_price
        
        # Store customer revenue for top 5
        if tenant_total_revenue > 0:
            customer_revenue[tenant_id] = {
                'name': tenant.get('name', 'Unknown'),
                'revenue': tenant_total_revenue,
                'subscriptions': len(subscriptions),
                'status': tenant.get('subscription_status', 'active')
            }
    
    # Calculate repeat customers (customers with multiple billing cycles)
    # For demo purposes, we'll track customers by creation month
    repeat_customers_monthly = {}
    for tenant in tenants:
        created_at = tenant.get('created_at')
        if created_at:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            month_key = created_at.strftime('%Y-%m')
            repeat_customers_monthly[month_key] = repeat_customers_monthly.get(month_key, 0) + 1
    
    # Sort monthly revenue by date
    sorted_monthly_revenue = sorted(monthly_revenue.items(), key=lambda x: x[0])
    
    # Get top 5 customers
    top_customers = sorted(customer_revenue.values(), key=lambda x: x['revenue'], reverse=True)[:5]
    
    # Calculate month-on-month growth
    mom_data = []
    for i, (month, revenue) in enumerate(sorted_monthly_revenue):
        growth = 0
        if i > 0:
            prev_revenue = sorted_monthly_revenue[i-1][1]
            if prev_revenue > 0:
                growth = ((revenue - prev_revenue) / prev_revenue) * 100
        
        mom_data.append({
            'month': month,
            'revenue': revenue,
            'growth': round(growth, 2)
        })
    
    return {
        'total_lifetime_revenue': round(total_lifetime_revenue, 2),
        'monthly_revenue': mom_data,
        'new_activations': {
            'monthly': [{'month': k, 'revenue': round(v, 2)} for k, v in sorted(new_customer_revenue.items())],
            'weekly': [{'week': k, 'revenue': round(v, 2)} for k, v in sorted(weekly_revenue.items())]
        },
        'repeat_customers': {
            'monthly': [{'month': k, 'count': v} for k, v in sorted(repeat_customers_monthly.items())],
        },
        'top_customers': top_customers,
        'total_customers': len(tenants),
        'active_customers': len([t for t in tenants if t.get('subscription_status') == 'active'])
    }

# Helper function to log CRM activities
async def log_crm_activity(user, action: str, entity_type: str, entity_id: str, entity_name: str, details: dict = None):
    try:
        activity_log = {
            "id": str(uuid.uuid4()),
            "user_id": user.id,
            "user_name": f"{user.first_name} {user.last_name}" if hasattr(user, 'first_name') else user.email,
            "user_email": user.email,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await db.crm_activity_logs.insert_one(activity_log)
    except Exception as e:
        print(f"Failed to log activity: {e}")

# CRM Endpoints


class IntegrationCreate(BaseModel):
    provider: str
    name: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scopes: Optional[List[str]] = None

@router.get('/tenants/{tenant_id}/integrations')
async def list_integrations(tenant_id: str, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    tenant = await db.companies.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant.get("integrations", {"eld": []})

@router.post('/tenants/{tenant_id}/integrations')
async def add_integration(tenant_id: str, payload: IntegrationCreate, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    integ = payload.dict()
    if integ.get("client_secret"):
        integ["client_secret_masked"] = f"****{integ['client_secret'][-4:]}"
        del integ["client_secret"]
    integ["created_at"] = datetime.now(timezone.utc).isoformat()
    integ["created_by"] = current_user.email
    await db.companies.update_one({"id": tenant_id}, {"$push": {"integrations.eld": integ}})
    tenant = await db.companies.find_one({"id": tenant_id})
    return tenant.get("integrations", {"eld": []})

    if current_user.role != UserRole.FLEET_OWNER:
        raise HTTPException(status_code=403, detail="Only fleet owners can view drivers")
    
    drivers = await db.users.find({"fleet_owner_id": current_user.id}).to_list(length=None)
    return [User(**driver) for driver in drivers]

@router.put("/drivers/{driver_id}", response_model=dict)
async def update_driver(driver_id: str, driver_data: UserBase, current_user: User = Depends(get_current_user)):
    # Only fleet owners can update drivers
    if current_user.role != UserRole.FLEET_OWNER:
        raise HTTPException(status_code=403, detail="Only fleet owners can update drivers")
    
    # Find driver
    driver = await db.users.find_one({"id": driver_id, "fleet_owner_id": current_user.id})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Update driver
    update_data = driver_data.dict(exclude_unset=True)
    if update_data:
        await db.users.update_one(
            {"id": driver_id},
            {"$set": update_data}
        )
    
    return {"message": "Driver updated successfully"}

@router.delete("/drivers/{driver_id}")
async def delete_driver(driver_id: str, current_user: User = Depends(get_current_user)):
    # Only fleet owners can delete drivers
    if current_user.role != UserRole.FLEET_OWNER:
        raise HTTPException(status_code=403, detail="Only fleet owners can delete drivers")
    
    result = await db.users.delete_one({"id": driver_id, "fleet_owner_id": current_user.id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    return {"message": "Driver deleted successfully"}

# Integration Management Routes
class IntegrationData(BaseModel):
    name: str
    description: Optional[str] = None
    service_id: str
    category: str
    enabled: bool = True
    config: dict

@router.get('/integrations')
async def list_all_integrations(current_user: User = Depends(get_current_user)):
    """Get all configured integrations for the current user's company"""
    require_platform_admin(current_user)
    
    # Get company integrations
    company = await db.companies.find_one({"company_email": current_user.email})
    if not company:
        return []
    
    integrations = company.get("integrations_v2", [])
    return integrations

@router.post('/integrations')
async def create_integration(integration: IntegrationData, current_user: User = Depends(get_current_user)):
    """Create a new integration"""
    require_platform_admin(current_user)
    
    # Get company - try multiple lookup methods
    company = await db.companies.find_one({"company_email": current_user.email})
    
    # If not found by company_email, try to find admin's company or create one
    if not company:
        # For platform admins, use their email to find/create a company
        company = await db.companies.find_one({"id": f"admin-company-{current_user.id}"})
        
        if not company:
            # Create a default company for the admin user
            company = {
                "id": f"admin-company-{current_user.id}",
                "name": "Admin Organization",
                "company_email": current_user.email,
                "integrations_v2": [],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.companies.insert_one(company)
    
    # Create integration object
    new_integration = {
        "id": str(uuid.uuid4()),
        "name": integration.name,
        "description": integration.description,
        "service_id": integration.service_id,
        "category": integration.category,
        "enabled": integration.enabled,
        "config": integration.config,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.email
    }
    
    # Add to company integrations
    await db.companies.update_one(
        {"company_email": current_user.email},
        {"$push": {"integrations_v2": new_integration}}
    )
    
    return new_integration

@router.put('/integrations/{integration_id}')
async def update_integration(
    integration_id: str, 
    updates: IntegrationData, 
    current_user: User = Depends(get_current_user)
):
    """Update an existing integration"""
    require_platform_admin(current_user)
    
    # Get company
    company = await db.companies.find_one({"company_email": current_user.email})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Find and update the integration
    integrations = company.get("integrations_v2", [])
    integration_found = False
    
    for i, integ in enumerate(integrations):
        if integ.get("id") == integration_id:
            integrations[i].update({
                "name": updates.name,
                "description": updates.description,
                "enabled": updates.enabled,
                "config": updates.config,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": current_user.email
            })
            integration_found = True
            break
    
    if not integration_found:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Update in database
    await db.companies.update_one(
        {"company_email": current_user.email},
        {"$set": {"integrations_v2": integrations}}
    )
    
    return {"message": "Integration updated successfully"}

@router.delete('/integrations/{integration_id}')
async def delete_integration(integration_id: str, current_user: User = Depends(get_current_user)):
    """Delete an integration"""
    require_platform_admin(current_user)
    
    # Remove integration from company
    result = await db.companies.update_one(
        {"company_email": current_user.email},
        {"$pull": {"integrations_v2": {"id": integration_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    return {"message": "Integration deleted successfully"}

@router.post('/integrations/{integration_id}/toggle')
async def toggle_integration(
    integration_id: str, 
    payload: dict, 
    current_user: User = Depends(get_current_user)
):
    """Enable or disable an integration"""
    require_platform_admin(current_user)
    
    enabled = payload.get("enabled", True)
    
    # Get company
    company = await db.companies.find_one({"company_email": current_user.email})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Find and update the integration
    integrations = company.get("integrations_v2", [])
    integration_found = False
    
    for i, integ in enumerate(integrations):
        if integ.get("id") == integration_id:
            integrations[i]["enabled"] = enabled
            integrations[i]["updated_at"] = datetime.now(timezone.utc).isoformat()
            integration_found = True
            break
    
    if not integration_found:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Update in database
    await db.companies.update_one(
        {"company_email": current_user.email},
        {"$set": {"integrations_v2": integrations}}
    )
    
    return {"message": f"Integration {'enabled' if enabled else 'disabled'} successfully"}

@router.post('/integrations/{integration_id}/test')
async def test_integration(integration_id: str, current_user: User = Depends(get_current_user)):
    """Test an integration configuration"""
    require_platform_admin(current_user)
    
    # Get company
    company = await db.companies.find_one({"company_email": current_user.email})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Find the integration
    integrations = company.get("integrations_v2", [])
    integration = next((i for i in integrations if i.get("id") == integration_id), None)
    
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # For Google Maps, just verify the API key exists
    if integration.get("service_id") == "google_maps":
        api_key = integration.get("config", {}).get("api_key")
        if api_key and len(api_key) > 10:
            return {"success": True, "message": "API key configured"}
        else:
            return {"success": False, "message": "Invalid API key"}
    
    # Default response for other integrations
    return {"success": True, "message": "Configuration looks valid"}

@router.get('/integrations/google-maps/key')
async def get_google_maps_key(current_user: User = Depends(get_current_user)):
    """Get Google Maps API key for the current user's company"""
    
    # Get company
    company = await db.companies.find_one({"company_email": current_user.email})
    if not company:
        return {"api_key": None, "configured": False}
    
    # Find Google Maps integration
    integrations = company.get("integrations_v2", [])
    google_maps = next(
        (i for i in integrations if i.get("service_id") == "google_maps" and i.get("enabled")), 
        None
    )
    
    if not google_maps:
        return {"api_key": None, "configured": False}
    
    api_key = google_maps.get("config", {}).get("api_key")
    return {
        "api_key": api_key,
        "configured": True,
        "integration_name": google_maps.get("name")
    }

# Location Tracking Routes


# ============================================================================
# USER MANAGEMENT ENDPOINTS (Platform Admin Only)
# ============================================================================

# User Types for categorization
USER_TYPES = ["carrier", "broker", "shipper", "driver", "dispatcher", "owner_operator", "other"]

class UserCreateAdmin(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole
    user_type: Optional[str] = "other"  # carrier, broker, shipper, driver, dispatcher, owner_operator, other
    company_id: Optional[str] = None
    phone: Optional[str] = None
    mc_number: Optional[str] = None
    dot_number: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    status: str = "active"  # active, inactive, declined, cancelled
    is_active: bool = True

class UserUpdateAdmin(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    user_type: Optional[str] = None  # carrier, broker, shipper, driver, dispatcher, owner_operator, other
    company_id: Optional[str] = None
    phone: Optional[str] = None
    mc_number: Optional[str] = None
    dot_number: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    status: Optional[str] = None  # active, inactive, declined, cancelled
    is_active: Optional[bool] = None
    password: Optional[str] = None  # Optional password update

class UserCommentCreate(BaseModel):
    content: str

class UserFilterParams(BaseModel):
    company_id: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    search: Optional[str] = None  # Search by name or email

@router.get('/users', response_model=dict)
async def list_all_users(
    company_id: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """List all users with filtering (Platform Admin only)"""
    require_platform_admin(current_user)
    
    # Build query
    query = {}
    
    if company_id:
        query["company_id"] = company_id
    
    if role:
        query["role"] = role
    
    if is_active is not None:
        query["is_active"] = is_active
    
    if search:
        # Search by name or email
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]
    
    # Get users with pagination
    users = await db.users.find(query, {"_id": 0, "password_hash": 0}).skip(skip).limit(limit).to_list(length=limit)
    
    # Enrich with company name
    for user in users:
        if user.get("company_id"):
            company = await db.companies.find_one({"id": user["company_id"]}, {"_id": 0, "name": 1})
            user["company_name"] = company.get("name") if company else "Unknown"
        else:
            user["company_name"] = None
    
    # Get total count
    total_count = await db.users.count_documents(query)
    
    return {
        "users": users,
        "total": total_count,
        "skip": skip,
        "limit": limit
    }

@router.post('/users', response_model=dict)
async def create_user_admin(user_data: UserCreateAdmin, current_user: User = Depends(get_current_user)):
    """Create a new user (Platform Admin only)"""
    require_platform_admin(current_user)
    
    # Check if email already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Validate company if provided
    if user_data.company_id:
        company = await db.companies.find_one({"id": user_data.company_id})
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
    
    # Hash password
    from auth import hash_password
    hashed_password = hash_password(user_data.password)
    
    # Create user object
    user_id = str(uuid.uuid4())
    user_dict = {
        "id": user_id,
        "email": user_data.email,
        "full_name": user_data.full_name,
        "password_hash": hashed_password,
        "role": user_data.role,
        "user_type": user_data.user_type,
        "company_id": user_data.company_id,
        "phone": user_data.phone,
        "mc_number": user_data.mc_number,
        "dot_number": user_data.dot_number,
        "company_name": user_data.company_name,
        "company_website": user_data.company_website,
        "status": user_data.status,
        "is_active": user_data.is_active,
        "email_verified": True,  # Auto-verify admin-created users
        "registration_status": RegistrationStatus.VERIFIED,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.id,
        "comments": [],  # Initialize empty comments array
        "subscriptions": []  # Initialize empty subscriptions array
    }
    
    # Insert user
    await db.users.insert_one(user_dict)
    
    # If user role is 'driver', also create a driver record in the drivers collection
    driver_id = None
    if user_data.role == "driver":
        driver_dict = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "full_name": user_data.full_name,
            "email": user_data.email,
            "phone": user_data.phone or "",
            "status": "available",
            "license_type": "CDL_A",
            "license_number": "",
            "license_state": "",
            "license_expiry": None,
            "hire_date": datetime.now(timezone.utc).isoformat(),
            "current_location": None,
            "assigned_vehicle_id": None,
            "assigned_trailer_id": None,
            "certifications": [],
            "notes": f"Driver account created via Admin Console by {current_user.email}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user.id
        }
        await db.drivers.insert_one(driver_dict)
        driver_id = driver_dict["id"]
    
    return {
        "message": "User created successfully",
        "user_id": user_dict["id"],
        "email": user_dict["email"],
        "driver_id": driver_id
    }

@router.get('/users/{user_id}', response_model=dict)
async def get_user_details(user_id: str, current_user: User = Depends(get_current_user)):
    """Get user details (Platform Admin only)"""
    require_platform_admin(current_user)
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Enrich with company details
    if user.get("company_id"):
        company = await db.companies.find_one({"id": user["company_id"]}, {"_id": 0})
        user["company"] = company
    
    return user

@router.put('/users/{user_id}', response_model=dict)
async def update_user_admin(user_id: str, user_data: UserUpdateAdmin, current_user: User = Depends(get_current_user)):
    """Update user (Platform Admin only)"""
    require_platform_admin(current_user)
    
    # Check if user exists
    existing_user = await db.users.find_one({"id": user_id})
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Build update data
    update_data = {}
    
    if user_data.full_name is not None:
        update_data["full_name"] = user_data.full_name
    
    if user_data.role is not None:
        update_data["role"] = user_data.role
    
    if user_data.user_type is not None:
        update_data["user_type"] = user_data.user_type
    
    if user_data.company_id is not None:
        # Validate company
        company = await db.companies.find_one({"id": user_data.company_id})
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        update_data["company_id"] = user_data.company_id
    
    if user_data.phone is not None:
        update_data["phone"] = user_data.phone
    
    if user_data.mc_number is not None:
        update_data["mc_number"] = user_data.mc_number
    
    if user_data.dot_number is not None:
        update_data["dot_number"] = user_data.dot_number
    
    if user_data.company_name is not None:
        update_data["company_name"] = user_data.company_name
    
    if user_data.company_website is not None:
        update_data["company_website"] = user_data.company_website
    
    if user_data.status is not None:
        update_data["status"] = user_data.status
        # Sync is_active with status
        update_data["is_active"] = user_data.status == "active"
    
    if user_data.is_active is not None:
        update_data["is_active"] = user_data.is_active
    
    if user_data.password is not None:
        # Hash new password
        from auth import hash_password
        update_data["password_hash"] = hash_password(user_data.password)
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Add update metadata
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = current_user.id
    
    # Update user
    await db.users.update_one({"id": user_id}, {"$set": update_data})
    
    return {
        "message": "User updated successfully",
        "user_id": user_id
    }

@router.delete('/users/{user_id}', response_model=dict)
async def delete_user_admin(user_id: str, current_user: User = Depends(get_current_user)):
    """Delete/Deactivate user (Platform Admin only)"""
    require_platform_admin(current_user)
    
    # Check if user exists
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent deleting platform admin
    if user.get("role") == UserRole.PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Cannot delete platform admin user")
    
    # Soft delete - just deactivate the user
    await db.users.update_one(
        {"id": user_id},
        {
            "$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": current_user.id
            }
        }
    )
    
    return {
        "message": "User deactivated successfully",
        "user_id": user_id
    }

class BulkUserAction(BaseModel):
    user_ids: List[str]
    action: str  # "activate" or "deactivate"

@router.post('/users/bulk-action', response_model=dict)
async def bulk_user_action(action_data: BulkUserAction, current_user: User = Depends(get_current_user)):
    """Bulk activate/deactivate users (Platform Admin only)"""
    require_platform_admin(current_user)
    
    if action_data.action not in ["activate", "deactivate"]:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'activate' or 'deactivate'")
    
    is_active = action_data.action == "activate"
    
    # Update all users
    result = await db.users.update_many(
        {"id": {"$in": action_data.user_ids}},
        {
            "$set": {
                "is_active": is_active,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": current_user.id
            }
        }
    )
    
    return {
        "message": f"Successfully {action_data.action}d {result.modified_count} users",
        "modified_count": result.modified_count
    }

@router.get('/users/stats/overview', response_model=dict)
async def get_users_stats(current_user: User = Depends(get_current_user)):
    """Get user statistics overview (Platform Admin only)"""
    require_platform_admin(current_user)
    
    # Total users
    total_users = await db.users.count_documents({})
    
    # Active users
    active_users = await db.users.count_documents({"is_active": True})
    
    # Users by role
    pipeline = [
        {"$group": {"_id": "$role", "count": {"$sum": 1}}}
    ]
    users_by_role = await db.users.aggregate(pipeline).to_list(length=None)
    
    # Users by company
    pipeline = [
        {"$match": {"company_id": {"$ne": None}}},
        {"$group": {"_id": "$company_id", "count": {"$sum": 1}}}
    ]
    users_by_company = await db.users.aggregate(pipeline).to_list(length=None)
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": total_users - active_users,
        "users_by_role": {item["_id"]: item["count"] for item in users_by_role},
        "total_companies_with_users": len(users_by_company)
    }

# Comments endpoints for user management
@router.post('/users/{user_id}/comments', response_model=dict)
async def add_user_comment(user_id: str, comment_data: UserCommentCreate, current_user: User = Depends(get_current_user)):
    """Add a comment to a user's profile (Platform Admin only)"""
    require_platform_admin(current_user)
    
    # Check if user exists
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Create comment object
    comment = {
        "id": str(uuid.uuid4()),
        "content": comment_data.content,
        "created_by": current_user.id,
        "created_by_name": current_user.full_name,
        "created_by_email": current_user.email,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Add comment to user's comments array
    await db.users.update_one(
        {"id": user_id},
        {"$push": {"comments": comment}}
    )
    
    return {
        "message": "Comment added successfully",
        "comment": comment
    }

@router.get('/users/{user_id}/comments')
async def get_user_comments(user_id: str, current_user: User = Depends(get_current_user)):
    """Get all comments for a user (Platform Admin only)"""
    require_platform_admin(current_user)
    
    # Check if user exists
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "comments": 1})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user.get("comments", [])

@router.delete('/users/{user_id}/comments/{comment_id}', response_model=dict)
async def delete_user_comment(user_id: str, comment_id: str, current_user: User = Depends(get_current_user)):
    """Delete a comment from a user's profile (Platform Admin only)"""
    require_platform_admin(current_user)
    
    # Remove comment from user's comments array
    result = await db.users.update_one(
        {"id": user_id},
        {"$pull": {"comments": {"id": comment_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    return {"message": "Comment deleted successfully"}

# Update status endpoint
@router.put('/users/{user_id}/status', response_model=dict)
async def update_user_status(user_id: str, status_data: dict, current_user: User = Depends(get_current_user)):
    """Update user status (Platform Admin only)"""
    require_platform_admin(current_user)
    
    status = status_data.get("status")
    if status not in ["active", "inactive", "declined", "cancelled"]:
        raise HTTPException(status_code=400, detail="Invalid status. Use 'active', 'inactive', 'declined', or 'cancelled'")
    
    # Check if user exists
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    await db.users.update_one(
        {"id": user_id},
        {
            "$set": {
                "status": status,
                "is_active": status == "active",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": current_user.id
            }
        }
    )
    
    return {
        "message": f"User status updated to {status}",
        "user_id": user_id,
        "status": status
    }


