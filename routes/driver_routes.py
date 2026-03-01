from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from models import *
from auth import get_current_user, hash_password
from database import db
from datetime import datetime, timezone, timedelta
from typing import List
import uuid

def require_platform_admin(current_user: User):
    if current_user.role != UserRole.PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Platform admin access required")

router = APIRouter(prefix="/drivers", tags=["Drivers"])

@router.post("", response_model=dict)
async def create_driver_account(driver_data: DriverCreate, current_user: User = Depends(get_current_user)):
    # Only fleet owners and platform admins can create driver accounts
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN]:
        raise HTTPException(status_code=403, detail="Only fleet owners and platform admins can create driver accounts")
    
    # Check if email already exists
    existing_user = await db.users.find_one({"email": driver_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create driver account
    hashed_password = hash_password(driver_data.password)
    
    driver_dict = driver_data.dict()
    driver_dict.pop("password")
    driver_dict["password_hash"] = hashed_password
    driver_dict["role"] = UserRole.DRIVER
    driver_dict["fleet_owner_id"] = current_user.id
    driver_dict["registration_status"] = RegistrationStatus.VERIFIED  # Auto-verify drivers
    driver_obj = User(**driver_dict)
    
    await db.users.insert_one(driver_obj.dict())
    
    return {"message": "Driver account created successfully", "driver_id": driver_obj.id}

@router.get("/my", response_model=List[User])
async def get_my_drivers(current_user: User = Depends(get_current_user)):
    drivers = await db.users.find({"fleet_owner_id": current_user.id, "role": UserRole.DRIVER}, {"_id": 0}).to_list(length=None)
    return drivers

@router.get("/all", response_model=list)
async def get_all_drivers(current_user: User = Depends(get_current_user)):
    """Get all drivers from the drivers collection (for dispatch operations)"""
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN, UserRole.COMPANY_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get drivers from the drivers collection (created via User Management)
    drivers_from_collection = await db.drivers.find({}, {"_id": 0}).to_list(length=None)
    
    # Also get drivers from users collection (legacy/direct creation)
    drivers_from_users = await db.users.find({"role": UserRole.DRIVER}, {"_id": 0, "password_hash": 0}).to_list(length=None)
    
    # Combine both sources, avoiding duplicates by email
    seen_emails = set()
    all_drivers = []
    
    # Add drivers from drivers collection first (preferred)
    for driver in drivers_from_collection:
        email = driver.get('email')
        if email and email not in seen_emails:
            seen_emails.add(email)
            all_drivers.append(driver)
    
    # Add remaining drivers from users collection
    for driver in drivers_from_users:
        email = driver.get('email')
        if email and email not in seen_emails:
            seen_emails.add(email)
            # Map user fields to driver fields
            all_drivers.append({
                'id': driver.get('id'),
                'user_id': driver.get('id'),
                'full_name': driver.get('full_name'),
                'email': email,
                'phone': driver.get('phone', ''),
                'status': driver.get('driver_status', 'available'),
                'license_type': driver.get('license_type', 'CDL_A'),
                'license_number': driver.get('license_number', ''),
                'created_at': driver.get('created_at')
            })
    
    return all_drivers

@router.get("/my-loads", response_model=list)
async def get_my_assigned_loads(current_user: User = Depends(get_current_user)):
    """Get loads assigned to the current driver (for driver mobile app)"""
    # Find driver record by user_id or email
    driver = await db.drivers.find_one({
        "$or": [
            {"user_id": current_user.id},
            {"email": current_user.email}
        ]
    })
    
    if not driver:
        # Check if user is a driver by role
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(status_code=403, detail="Only drivers can access this endpoint")
        driver_id = current_user.id
    else:
        driver_id = driver.get("id")
    
    # Get loads from driver_loads collection
    driver_loads = await db.driver_loads.find(
        {"driver_id": driver_id},
        {"_id": 0}
    ).to_list(length=100)
    
    # Also get bookings directly assigned to this driver
    bookings = await db.bookings.find(
        {"$or": [
            {"assigned_driver_id": driver_id},
            {"assigned_driver_id": current_user.id}
        ]},
        {"_id": 0}
    ).to_list(length=100)
    
    # Combine and format loads for the mobile app
    all_loads = []
    seen_booking_ids = set()
    
    # Add loads from driver_loads collection
    for load in driver_loads:
        booking_id = load.get("booking_id")
        if booking_id not in seen_booking_ids:
            seen_booking_ids.add(booking_id)
            all_loads.append({
                "id": load.get("id"),
                "booking_id": booking_id,
                "order_number": load.get("order_number"),
                "pickup_location": load.get("pickup_location"),
                "delivery_location": load.get("delivery_location"),
                "pickup_city": load.get("pickup_location", "").split(",")[0] if load.get("pickup_location") else "",
                "pickup_state": load.get("pickup_location", "").split(",")[-1].strip() if load.get("pickup_location") else "",
                "delivery_city": load.get("delivery_location", "").split(",")[0] if load.get("delivery_location") else "",
                "delivery_state": load.get("delivery_location", "").split(",")[-1].strip() if load.get("delivery_location") else "",
                "pickup_date": load.get("pickup_date"),
                "delivery_date": load.get("delivery_date"),
                "commodity": load.get("commodity"),
                "weight": load.get("weight"),
                "rate": load.get("rate"),
                "status": load.get("status", "assigned"),
                "assigned_at": load.get("assigned_at")
            })
    
    # Add bookings that weren't in driver_loads
    for booking in bookings:
        if booking.get("id") not in seen_booking_ids:
            seen_booking_ids.add(booking.get("id"))
            all_loads.append({
                "id": booking.get("id"),
                "booking_id": booking.get("id"),
                "order_number": booking.get("order_number"),
                "pickup_location": booking.get("pickup_location"),
                "delivery_location": booking.get("delivery_location"),
                "pickup_city": booking.get("pickup_location", "").split(",")[0] if booking.get("pickup_location") else "",
                "pickup_state": booking.get("pickup_location", "").split(",")[-1].strip() if booking.get("pickup_location") else "",
                "delivery_city": booking.get("delivery_location", "").split(",")[0] if booking.get("delivery_location") else "",
                "delivery_state": booking.get("delivery_location", "").split(",")[-1].strip() if booking.get("delivery_location") else "",
                "pickup_date": booking.get("pickup_date"),
                "delivery_date": booking.get("delivery_date"),
                "commodity": booking.get("commodity"),
                "weight": booking.get("weight"),
                "rate": booking.get("rate"),
                "status": booking.get("status", "assigned"),
                "assigned_at": booking.get("dispatched_at")
            })
    
    return all_loads

@router.put("/{driver_id}/status")
async def update_driver_status(driver_id: str, status_data: dict, current_user: User = Depends(get_current_user)):
    """Update driver status (available, on_route, off_duty, on_break, inactive)"""
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN]:
        raise HTTPException(status_code=403, detail="Only fleet owners and platform admins can update driver status")
    
    valid_statuses = ['available', 'on_route', 'off_duty', 'on_break', 'inactive']
    new_status = status_data.get('status')
    
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    # Find and update driver
    result = await db.users.update_one(
        {"id": driver_id, "role": UserRole.DRIVER},
        {"$set": {"driver_status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    return {"message": "Driver status updated successfully", "status": new_status}

@router.get("/{driver_id}")
async def get_driver(driver_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific driver's details"""
    driver = await db.users.find_one({"id": driver_id, "role": UserRole.DRIVER}, {"_id": 0})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return driver

@router.put("/{driver_id}")
async def update_driver(driver_id: str, driver_data: dict, current_user: User = Depends(get_current_user)):
    """Update driver details"""
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN]:
        raise HTTPException(status_code=403, detail="Only fleet owners and platform admins can update drivers")
    
    # Remove fields that shouldn't be updated
    protected_fields = ['id', 'role', 'password_hash', 'created_at']
    update_data = {k: v for k, v in driver_data.items() if k not in protected_fields and v is not None}
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    result = await db.users.update_one(
        {"id": driver_id, "role": UserRole.DRIVER},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    return {"message": "Driver updated successfully"}

# ============= Admin APIs =============

@router.get('/admin/tenants')
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

@router.put('/admin/tenants/{tenant_id}')
async def update_tenant(tenant_id: str, payload: TenantUpdate, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    updates = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if not updates:
        return {"updated": False}
    await db.companies.update_one({"id": tenant_id}, {"$set": updates})
    tenant = await db.companies.find_one({"id": tenant_id})
    return tenant

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

@router.post('/admin/tenants/{tenant_id}/subscriptions')
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

@router.put('/admin/tenants/{tenant_id}/subscriptions/{subscription_id}')
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

@router.delete('/admin/tenants/{tenant_id}/subscriptions/{subscription_id}')
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
    return {"message": message, "tenant": tenant}

@router.get('/admin/plans')
async def get_plans(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    return PLANS

@router.get('/admin/analytics')
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
@router.get('/admin/crm/contacts')
async def get_crm_contacts(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    contacts = await db.crm_contacts.find({}, {"_id": 0}).to_list(length=None)
    return contacts

@router.post('/admin/crm/contacts')
async def create_crm_contact(contact: CRMContact, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    contact.owner_id = current_user.id
    contact_dict = contact.dict()
    contact_dict['created_at'] = contact_dict['created_at'].isoformat()
    contact_dict['updated_at'] = contact_dict['updated_at'].isoformat()
    await db.crm_contacts.insert_one(contact_dict)
    
    # Log activity
    await log_crm_activity(
        current_user, 
        "created", 
        "contact", 
        contact.id, 
        f"{contact.first_name} {contact.last_name}",
        {"company": contact.company, "email": contact.email}
    )
    
    return contact

@router.put('/admin/crm/contacts/{contact_id}')
async def update_crm_contact(contact_id: str, contact: CRMContact, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    contact.updated_at = datetime.now(timezone.utc)
    contact_dict = contact.dict()
    contact_dict['updated_at'] = contact_dict['updated_at'].isoformat()
    if 'created_at' in contact_dict and isinstance(contact_dict['created_at'], datetime):
        contact_dict['created_at'] = contact_dict['created_at'].isoformat()
    await db.crm_contacts.update_one({"id": contact_id}, {"$set": contact_dict})
    
    # Log activity
    await log_crm_activity(
        current_user, 
        "updated", 
        "contact", 
        contact.id, 
        f"{contact.first_name} {contact.last_name}",
        {"status": contact.status, "company": contact.company}
    )
    
    return contact

@router.delete('/admin/crm/contacts/{contact_id}')
async def delete_crm_contact(contact_id: str, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    # Get contact info before deleting
    contact = await db.crm_contacts.find_one({"id": contact_id})
    if contact:
        await log_crm_activity(
            current_user, 
            "deleted", 
            "contact", 
            contact_id, 
            f"{contact.get('first_name', '')} {contact.get('last_name', '')}",
            {"company": contact.get('company'), "email": contact.get('email')}
        )
    await db.crm_contacts.delete_one({"id": contact_id})
    return {"message": "Contact deleted"}

@router.post('/admin/crm/contacts/upload')
async def upload_crm_contacts(file: UploadFile, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    
    # Read CSV file
    import csv
    import io
    
    try:
        contents = await file.read()
        decoded = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(decoded))
        
        contacts_created = 0
        errors = []
        
        for row in csv_reader:
            try:
                contact = {
                    "id": str(uuid.uuid4()),
                    "first_name": row.get('first_name', '').strip(),
                    "last_name": row.get('last_name', '').strip(),
                    "email": row.get('email', '').strip(),
                    "phone": row.get('phone', '').strip() or None,
                    "ext": row.get('ext', '').strip() or None,
                    "company": row.get('company', '').strip() or None,
                    "position": row.get('position', '').strip() or None,
                    "address": row.get('address', '').strip() or None,
                    "city": row.get('city', '').strip() or None,
                    "state": row.get('state', '').strip() or None,
                    "status": row.get('status', 'cold_lead').strip(),
                    "notes": row.get('notes', '').strip() or None,
                    "source": "CSV Import",
                    "tags": [],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "owner_id": current_user.id
                }
                
                if not contact['first_name'] or not contact['last_name'] or not contact['email']:
                    errors.append(f"Skipped row with missing required fields: {row}")
                    continue
                
                await db.crm_contacts.insert_one(contact)
                contacts_created += 1
            except Exception as e:
                errors.append(f"Error processing row: {str(e)}")
        
        return {
            "message": f"Successfully imported {contacts_created} contacts",
            "contacts_created": contacts_created,
            "errors": errors
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process CSV: {str(e)}")

@router.get('/admin/crm/activity-logs')
async def get_crm_activity_logs(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    # Get activity logs sorted by most recent first
    logs = await db.crm_activity_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(length=200)
    return logs

@router.get('/admin/crm/deals')
async def get_crm_deals(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    deals = await db.crm_deals.find({}, {"_id": 0}).to_list(length=None)
    return deals

@router.post('/admin/crm/deals')
async def create_crm_deal(deal: CRMDeal, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    deal.owner_id = current_user.id
    deal_dict = deal.dict()
    deal_dict['created_at'] = deal_dict['created_at'].isoformat()
    deal_dict['updated_at'] = deal_dict['updated_at'].isoformat()
    if deal_dict.get('expected_close_date'):
        deal_dict['expected_close_date'] = deal_dict['expected_close_date'].isoformat()
    await db.crm_deals.insert_one(deal_dict)
    
    # Log activity
    await log_crm_activity(
        current_user, 
        "created", 
        "deal", 
        deal.id, 
        deal.name,
        {"value": deal.value, "stage": deal.stage}
    )
    
    return deal

@router.put('/admin/crm/deals/{deal_id}')
async def update_crm_deal(deal_id: str, deal: CRMDeal, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    deal.updated_at = datetime.now(timezone.utc)
    deal_dict = deal.dict()
    deal_dict['updated_at'] = deal_dict['updated_at'].isoformat()
    if 'created_at' in deal_dict and isinstance(deal_dict['created_at'], datetime):
        deal_dict['created_at'] = deal_dict['created_at'].isoformat()
    if deal_dict.get('expected_close_date') and isinstance(deal_dict['expected_close_date'], datetime):
        deal_dict['expected_close_date'] = deal_dict['expected_close_date'].isoformat()
    await db.crm_deals.update_one({"id": deal_id}, {"$set": deal_dict})
    return deal

@router.delete('/admin/crm/deals/{deal_id}')
async def delete_crm_deal(deal_id: str, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    await db.crm_deals.delete_one({"id": deal_id})
    return {"message": "Deal deleted"}

@router.get('/admin/crm/activities')
async def get_crm_activities(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    activities = await db.crm_activities.find({}, {"_id": 0}).to_list(length=None)
    return activities

@router.post('/admin/crm/activities')
async def create_crm_activity(activity: CRMActivity, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    activity.owner_id = current_user.id
    activity_dict = activity.dict()
    activity_dict['created_at'] = activity_dict['created_at'].isoformat()
    if activity_dict.get('due_date'):
        activity_dict['due_date'] = activity_dict['due_date'].isoformat()
    await db.crm_activities.insert_one(activity_dict)
    return activity

@router.get('/admin/crm/dashboard')
async def get_crm_dashboard(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    
    contacts = await db.crm_contacts.find({}).to_list(length=None)
    deals = await db.crm_deals.find({}).to_list(length=None)
    activities = await db.crm_activities.find({}).to_list(length=None)
    
    # Calculate metrics
    total_contacts = len(contacts)
    leads = len([c for c in contacts if c.get('status') == 'lead'])
    customers = len([c for c in contacts if c.get('status') == 'customer'])
    
    total_deal_value = sum(d.get('value', 0) for d in deals)
    won_deals = [d for d in deals if d.get('stage') == 'closed_won']
    total_won_value = sum(d.get('value', 0) for d in won_deals)
    
    deals_by_stage = {}
    for deal in deals:
        stage = deal.get('stage', 'prospecting')
        deals_by_stage[stage] = deals_by_stage.get(stage, 0) + 1
    
    pending_activities = len([a for a in activities if not a.get('completed')])
    
    return {
        'total_contacts': total_contacts,
        'leads': leads,
        'customers': customers,
        'total_deal_value': total_deal_value,
        'total_won_value': total_won_value,
        'won_deals_count': len(won_deals),
        'deals_by_stage': deals_by_stage,
        'pending_activities': pending_activities,
        'conversion_rate': (customers / total_contacts * 100) if total_contacts > 0 else 0
    }

# CRM Company Endpoints
@router.get('/admin/crm/companies')
async def get_crm_companies(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    companies = await db.crm_companies.find({}, {"_id": 0}).to_list(length=None)
    return companies

@router.post('/admin/crm/companies')
async def create_crm_company(company: CRMCompany, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    company.owner_id = current_user.id
    company_dict = company.dict()
    company_dict['created_at'] = company_dict['created_at'].isoformat()
    company_dict['updated_at'] = company_dict['updated_at'].isoformat()
    await db.crm_companies.insert_one(company_dict)
    
    # Log activity
    await log_crm_activity(
        current_user, 
        "created", 
        "company", 
        company.id, 
        company.company_name,
        {"industry": company.industry, "type": company.company_type}
    )
    
    return company

@router.put('/admin/crm/companies/{company_id}')
async def update_crm_company(company_id: str, company: CRMCompany, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    company.updated_at = datetime.now(timezone.utc)
    company_dict = company.dict()
    company_dict['updated_at'] = company_dict['updated_at'].isoformat()
    if 'created_at' in company_dict and isinstance(company_dict['created_at'], datetime):
        company_dict['created_at'] = company_dict['created_at'].isoformat()
    await db.crm_companies.update_one({"id": company_id}, {"$set": company_dict})
    
    # Log activity
    await log_crm_activity(
        current_user, 
        "updated", 
        "company", 
        company.id, 
        company.company_name,
        {"status": company.status, "type": company.company_type}
    )
    
    return company

@router.delete('/admin/crm/companies/{company_id}')
async def delete_crm_company(company_id: str, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    # Get company info before deleting
    company = await db.crm_companies.find_one({"id": company_id})
    if company:
        await log_crm_activity(
            current_user, 
            "deleted", 
            "company", 
            company_id, 
            company.get('company_name', ''),
            {"industry": company.get('industry'), "type": company.get('company_type')}
        )
    await db.crm_companies.delete_one({"id": company_id})
    return {"message": "Company deleted"}

@router.post('/admin/crm/companies/upload')
async def upload_crm_companies(file: UploadFile, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    
    import csv
    import io
    
    try:
        contents = await file.read()
        decoded = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(decoded))
        
        companies_created = 0
        errors = []
        
        for row in csv_reader:
            try:
                company = {
                    "id": str(uuid.uuid4()),
                    "company_name": row.get('company_name', '').strip(),
                    "industry": row.get('industry', '').strip() or None,
                    "website": row.get('website', '').strip() or None,
                    "phone": row.get('phone', '').strip() or None,
                    "email": row.get('email', '').strip() or None,
                    "address": row.get('address', '').strip() or None,
                    "city": row.get('city', '').strip() or None,
                    "state": row.get('state', '').strip() or None,
                    "zip_code": row.get('zip_code', '').strip() or None,
                    "country": row.get('country', '').strip() or None,
                    "employee_count": int(row.get('employee_count', 0)) if row.get('employee_count', '').strip() else None,
                    "annual_revenue": float(row.get('annual_revenue', 0)) if row.get('annual_revenue', '').strip() else None,
                    "company_type": row.get('company_type', 'prospect').strip(),
                    "status": row.get('status', 'active').strip(),
                    "parent_company": row.get('parent_company', '').strip() or None,
                    "account_owner": row.get('account_owner', '').strip() or None,
                    "founded_date": row.get('founded_date', '').strip() or None,
                    "customer_since": row.get('customer_since', '').strip() or None,
                    "linkedin_url": row.get('linkedin_url', '').strip() or None,
                    "twitter_handle": row.get('twitter_handle', '').strip() or None,
                    "notes": row.get('notes', '').strip() or None,
                    "tags": [],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "owner_id": current_user.id
                }
                
                if not company['company_name']:
                    errors.append(f"Skipped row with missing company name: {row}")
                    continue
                
                await db.crm_companies.insert_one(company)
                companies_created += 1
            except Exception as e:
                errors.append(f"Error processing row: {str(e)}")
        
        return {
            "message": f"Successfully imported {companies_created} companies",
            "companies_created": companies_created,
            "errors": errors
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process CSV: {str(e)}")

class IntegrationCreate(BaseModel):
    provider: str
    name: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scopes: Optional[List[str]] = None

@router.get('/admin/tenants/{tenant_id}/integrations')
async def list_integrations(tenant_id: str, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    tenant = await db.companies.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant.get("integrations", {"eld": []})

@router.post('/admin/tenants/{tenant_id}/integrations')
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

# Location Tracking Routes

# ============== TMS DRIVER LOCATION & MESSAGING (For Dispatch) ==============

@router.get("/{driver_id}/location/latest")
async def get_driver_latest_location(driver_id: str, current_user: User = Depends(get_current_user)):
    """Get a driver's latest location - for dispatchers/fleet owners"""
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Verify driver belongs to fleet owner
    driver = await db.users.find_one({"id": driver_id, "fleet_owner_id": current_user.id})
    if not driver and current_user.role != UserRole.PLATFORM_ADMIN:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    location = await db.driver_locations.find_one(
        {"driver_id": driver_id},
        {"_id": 0},
        sort=[("recorded_at", -1)]
    )
    
    return location or {}

@router.get("/{driver_id}/location/history")
async def get_driver_location_history(
    driver_id: str, 
    hours: int = 24,
    current_user: User = Depends(get_current_user)
):
    """Get driver's location history - for dispatchers/fleet owners"""
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    locations = await db.driver_locations.find(
        {"driver_id": driver_id, "recorded_at": {"$gte": since}},
        {"_id": 0}
    ).sort("recorded_at", -1).to_list(500)
    
    return locations

@router.get("/loads/{load_id}/driver-location/latest")
async def get_load_driver_location(load_id: str, current_user: User = Depends(get_current_user)):
    """Get the assigned driver's latest location for a load"""
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Find load
    load = await db.loads.find_one({"id": load_id})
    if not load:
        load = await db.bookings.find_one({"id": load_id})
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    
    driver_id = load.get("assigned_driver_id") or load.get("driver_id")
    if not driver_id:
        return {"error": "No driver assigned to this load"}
    
    location = await db.driver_locations.find_one(
        {"driver_id": driver_id, "load_id": load_id},
        {"_id": 0},
        sort=[("recorded_at", -1)]
    )
    
    if not location:
        # Fallback to any recent location
        location = await db.driver_locations.find_one(
            {"driver_id": driver_id},
            {"_id": 0},
            sort=[("recorded_at", -1)]
        )
    
    return location or {}

@router.get("/loads/{load_id}/messages")
async def get_load_messages_dispatch(load_id: str, current_user: User = Depends(get_current_user)):
    """Get all messages for a load - for dispatchers"""
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    messages = await db.load_messages.find(
        {"load_id": load_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    
    # Mark as read by dispatch
    await db.load_messages.update_many(
        {"load_id": load_id, "sender_type": "driver", "read_by_dispatch": False},
        {"$set": {"read_by_dispatch": True}}
    )
    
    return messages

@router.post("/loads/{load_id}/messages")
async def send_message_to_driver(
    load_id: str,
    message_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Send a message to driver from dispatch"""
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    message = {
        "id": str(uuid.uuid4()),
        "load_id": load_id,
        "sender_id": current_user.id,
        "sender_name": current_user.full_name,
        "sender_type": "dispatch",
        "content": message_data.get("content", ""),
        "read_by_dispatch": True,
        "read_by_driver": False,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.load_messages.insert_one(message)
    
    return {"message": "Message sent", "data": {k: v for k, v in message.items() if k != "_id"}}

@router.get("/loads/{load_id}/documents")
async def get_load_documents_dispatch(load_id: str, current_user: User = Depends(get_current_user)):
    """Get all documents for a load - for dispatchers"""
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    documents = await db.load_documents.find(
        {"load_id": load_id},
        {"_id": 0, "file_data": 0}  # Exclude file data for list view
    ).sort("uploaded_at", -1).to_list(100)
    
    return documents

@router.get("/documents/{doc_id}")
async def get_document_dispatch(doc_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific document with file data - for dispatchers"""
    if current_user.role not in [UserRole.FLEET_OWNER, UserRole.PLATFORM_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    doc = await db.load_documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return doc
