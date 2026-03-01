"""
Product Bundle Routes - Subscription Management
Handles CRUD operations for product bundles and subscription assignments
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from database import db
from models import User, PLANS
from auth import get_current_user
import uuid

router = APIRouter(prefix="/bundles", tags=["Product Bundles"])

# Pydantic Models
class ProductInBundle(BaseModel):
    product_id: str
    product_name: Optional[str] = None
    included_seats: int = 5
    included_storage_gb: int = 10

class BundleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    products: List[ProductInBundle]
    monthly_price: float
    original_price: Optional[float] = None  # Sum of individual product prices
    discount_percentage: Optional[float] = None
    is_active: bool = True
    features: Optional[List[str]] = []

class BundleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    products: Optional[List[ProductInBundle]] = None
    monthly_price: Optional[float] = None
    original_price: Optional[float] = None
    discount_percentage: Optional[float] = None
    is_active: Optional[bool] = None
    features: Optional[List[str]] = None

class SubscriptionAssignment(BaseModel):
    bundle_id: str
    entity_type: str  # "user" or "company"
    entity_id: str
    start_date: Optional[str] = None
    notes: Optional[str] = None

# Helper to check if user is admin
def require_admin(current_user: User):
    if current_user.role not in ["platform_admin", "company_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")

# Get all available products (from PLANS)
@router.get('/products')
async def get_available_products(current_user: User = Depends(get_current_user)):
    """Get all available products that can be added to bundles"""
    require_admin(current_user)
    
    products = []
    for plan in PLANS:
        products.append({
            "id": plan["id"],
            "name": plan.get("tier", plan.get("label", plan["id"])),
            "label": plan.get("label", ""),
            "price": plan.get("price", 0),
            "default_seats": plan.get("default_seats", 5),
            "description": plan.get("description", ""),
            "features": plan.get("features", []),
            "status": plan.get("status", "active")
        })
    
    return {"products": products}

# Subscription Assignment Operations - Must be before /{bundle_id} routes
@router.get('/assignments')
async def get_assignments(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    bundle_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get all subscription assignments"""
    require_admin(current_user)
    
    query = {}
    if entity_type:
        query["entity_type"] = entity_type
    if entity_id:
        query["entity_id"] = entity_id
    if bundle_id:
        query["bundle_id"] = bundle_id
    if status:
        query["status"] = status
    
    assignments = await db.subscription_assignments.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    
    return {"assignments": assignments, "total": len(assignments)}

@router.post('/assign')
async def assign_subscription(
    assignment: SubscriptionAssignment, 
    current_user: User = Depends(get_current_user)
):
    """Assign a bundle subscription to a user or company"""
    require_admin(current_user)
    
    # Validate bundle exists
    bundle = await db.product_bundles.find_one({"id": assignment.bundle_id})
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    
    if not bundle.get("is_active"):
        raise HTTPException(status_code=400, detail="Cannot assign inactive bundle")
    
    # Validate entity exists
    if assignment.entity_type == "user":
        entity = await db.users.find_one({"id": assignment.entity_id})
        if not entity:
            raise HTTPException(status_code=404, detail="User not found")
        entity_name = entity.get("full_name", entity.get("email", "Unknown"))
    elif assignment.entity_type == "company":
        entity = await db.companies.find_one({"id": assignment.entity_id})
        if not entity:
            raise HTTPException(status_code=404, detail="Company not found")
        entity_name = entity.get("name", "Unknown")
    else:
        raise HTTPException(status_code=400, detail="Invalid entity_type. Use 'user' or 'company'")
    
    # Check for existing active assignment
    existing = await db.subscription_assignments.find_one({
        "bundle_id": assignment.bundle_id,
        "entity_type": assignment.entity_type,
        "entity_id": assignment.entity_id,
        "status": "active"
    })
    
    if existing:
        raise HTTPException(status_code=400, detail="Entity already has an active subscription to this bundle")
    
    # Create assignment
    start_date = assignment.start_date or datetime.now(timezone.utc).isoformat()
    
    assignment_dict = {
        "id": str(uuid.uuid4()),
        "bundle_id": assignment.bundle_id,
        "bundle_name": bundle.get("name"),
        "entity_type": assignment.entity_type,
        "entity_id": assignment.entity_id,
        "entity_name": entity_name,
        "monthly_price": bundle.get("monthly_price"),
        "status": "active",
        "start_date": start_date,
        "next_billing_date": start_date,  # Will be updated by billing system
        "notes": assignment.notes,
        "assigned_by": current_user.id,
        "assigned_by_name": current_user.full_name,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.subscription_assignments.insert_one(assignment_dict)
    
    # Update bundle assignment count
    await db.product_bundles.update_one(
        {"id": assignment.bundle_id},
        {"$inc": {"assignments_count": 1}}
    )
    
    # Update entity with subscription reference
    if assignment.entity_type == "user":
        await db.users.update_one(
            {"id": assignment.entity_id},
            {"$push": {"subscriptions": {
                "assignment_id": assignment_dict["id"],
                "bundle_id": assignment.bundle_id,
                "bundle_name": bundle.get("name"),
                "status": "active",
                "start_date": start_date
            }}}
        )
    else:
        await db.companies.update_one(
            {"id": assignment.entity_id},
            {"$push": {"subscriptions": {
                "assignment_id": assignment_dict["id"],
                "bundle_id": assignment.bundle_id,
                "bundle_name": bundle.get("name"),
                "status": "active",
                "start_date": start_date
            }}}
        )
    
    return {
        "message": f"Bundle assigned to {assignment.entity_type} successfully",
        "assignment_id": assignment_dict["id"]
    }

@router.put('/assignments/{assignment_id}/cancel')
async def cancel_assignment(assignment_id: str, current_user: User = Depends(get_current_user)):
    """Cancel a subscription assignment"""
    require_admin(current_user)
    
    assignment = await db.subscription_assignments.find_one({"id": assignment_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    await db.subscription_assignments.update_one(
        {"id": assignment_id},
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "cancelled_by": current_user.id
            }
        }
    )
    
    # Update bundle assignment count
    await db.product_bundles.update_one(
        {"id": assignment.get("bundle_id")},
        {"$inc": {"assignments_count": -1}}
    )
    
    # Update entity subscription status
    if assignment.get("entity_type") == "user":
        await db.users.update_one(
            {"id": assignment.get("entity_id"), "subscriptions.assignment_id": assignment_id},
            {"$set": {"subscriptions.$.status": "cancelled"}}
        )
    else:
        await db.companies.update_one(
            {"id": assignment.get("entity_id"), "subscriptions.assignment_id": assignment_id},
            {"$set": {"subscriptions.$.status": "cancelled"}}
        )
    
    return {"message": "Subscription cancelled successfully"}

@router.get('/stats/overview')
async def get_bundle_stats(current_user: User = Depends(get_current_user)):
    """Get overview statistics for bundles and subscriptions"""
    require_admin(current_user)
    
    total_bundles = await db.product_bundles.count_documents({})
    active_bundles = await db.product_bundles.count_documents({"is_active": True})
    total_assignments = await db.subscription_assignments.count_documents({})
    active_assignments = await db.subscription_assignments.count_documents({"status": "active"})
    
    # Calculate MRR (Monthly Recurring Revenue)
    pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": None, "mrr": {"$sum": "$monthly_price"}}}
    ]
    mrr_result = await db.subscription_assignments.aggregate(pipeline).to_list(1)
    mrr = mrr_result[0]["mrr"] if mrr_result else 0
    
    # Assignments by entity type
    user_assignments = await db.subscription_assignments.count_documents({"entity_type": "user", "status": "active"})
    company_assignments = await db.subscription_assignments.count_documents({"entity_type": "company", "status": "active"})
    
    return {
        "total_bundles": total_bundles,
        "active_bundles": active_bundles,
        "total_assignments": total_assignments,
        "active_assignments": active_assignments,
        "mrr": mrr,
        "user_subscriptions": user_assignments,
        "company_subscriptions": company_assignments
    }

# Bundle CRUD Operations
@router.get('')
async def get_bundles(
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_user)
):
    """Get all product bundles"""
    require_admin(current_user)
    
    query = {}
    if is_active is not None:
        query["is_active"] = is_active
    
    bundles = await db.product_bundles.find(query, {"_id": 0}).to_list(100)
    
    # Enrich with product details
    for bundle in bundles:
        enriched_products = []
        for prod in bundle.get("products", []):
            plan = next((p for p in PLANS if p["id"] == prod.get("product_id")), None)
            if plan:
                prod["product_name"] = plan.get("tier", plan.get("label", prod.get("product_id")))
                prod["product_price"] = plan.get("price", 0)
            enriched_products.append(prod)
        bundle["products"] = enriched_products
    
    return {"bundles": bundles, "total": len(bundles)}

@router.get('/{bundle_id}')
async def get_bundle(bundle_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific bundle by ID"""
    require_admin(current_user)
    
    bundle = await db.product_bundles.find_one({"id": bundle_id}, {"_id": 0})
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    
    # Enrich with product details
    enriched_products = []
    for prod in bundle.get("products", []):
        plan = next((p for p in PLANS if p["id"] == prod.get("product_id")), None)
        if plan:
            prod["product_name"] = plan.get("tier", plan.get("label", prod.get("product_id")))
            prod["product_price"] = plan.get("price", 0)
        enriched_products.append(prod)
    bundle["products"] = enriched_products
    
    return bundle

@router.post('')
async def create_bundle(bundle_data: BundleCreate, current_user: User = Depends(get_current_user)):
    """Create a new product bundle"""
    require_admin(current_user)
    
    # Validate products exist
    for prod in bundle_data.products:
        plan = next((p for p in PLANS if p["id"] == prod.product_id), None)
        if not plan:
            raise HTTPException(status_code=400, detail=f"Product {prod.product_id} not found")
    
    # Calculate original price if not provided
    original_price = bundle_data.original_price
    if not original_price:
        original_price = sum(
            next((p.get("price", 0) for p in PLANS if p["id"] == prod.product_id), 0)
            for prod in bundle_data.products
        )
    
    # Calculate discount percentage
    discount_percentage = bundle_data.discount_percentage
    if not discount_percentage and original_price > 0:
        discount_percentage = round(((original_price - bundle_data.monthly_price) / original_price) * 100, 1)
    
    # Aggregate features from all products
    features = bundle_data.features or []
    if not features:
        for prod in bundle_data.products:
            plan = next((p for p in PLANS if p["id"] == prod.product_id), None)
            if plan:
                features.extend(plan.get("features", []))
        features = list(set(features))  # Remove duplicates
    
    bundle_dict = {
        "id": str(uuid.uuid4()),
        "name": bundle_data.name,
        "description": bundle_data.description,
        "products": [p.dict() for p in bundle_data.products],
        "monthly_price": bundle_data.monthly_price,
        "original_price": original_price,
        "discount_percentage": discount_percentage,
        "is_active": bundle_data.is_active,
        "features": features,
        "created_by": current_user.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "assignments_count": 0
    }
    
    await db.product_bundles.insert_one(bundle_dict)
    
    # Remove _id from response (MongoDB adds it during insert)
    bundle_dict.pop("_id", None)
    
    return {
        "message": "Bundle created successfully",
        "bundle_id": bundle_dict["id"],
        "bundle": bundle_dict
    }

@router.put('/{bundle_id}')
async def update_bundle(
    bundle_id: str, 
    bundle_data: BundleUpdate, 
    current_user: User = Depends(get_current_user)
):
    """Update a product bundle"""
    require_admin(current_user)
    
    existing = await db.product_bundles.find_one({"id": bundle_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Bundle not found")
    
    update_data = {}
    
    if bundle_data.name is not None:
        update_data["name"] = bundle_data.name
    if bundle_data.description is not None:
        update_data["description"] = bundle_data.description
    if bundle_data.products is not None:
        # Validate products
        for prod in bundle_data.products:
            plan = next((p for p in PLANS if p["id"] == prod.product_id), None)
            if not plan:
                raise HTTPException(status_code=400, detail=f"Product {prod.product_id} not found")
        update_data["products"] = [p.dict() for p in bundle_data.products]
    if bundle_data.monthly_price is not None:
        update_data["monthly_price"] = bundle_data.monthly_price
    if bundle_data.original_price is not None:
        update_data["original_price"] = bundle_data.original_price
    if bundle_data.discount_percentage is not None:
        update_data["discount_percentage"] = bundle_data.discount_percentage
    if bundle_data.is_active is not None:
        update_data["is_active"] = bundle_data.is_active
    if bundle_data.features is not None:
        update_data["features"] = bundle_data.features
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = current_user.id
    
    await db.product_bundles.update_one({"id": bundle_id}, {"$set": update_data})
    
    return {"message": "Bundle updated successfully", "bundle_id": bundle_id}

@router.delete('/{bundle_id}')
async def delete_bundle(bundle_id: str, current_user: User = Depends(get_current_user)):
    """Delete a product bundle"""
    require_admin(current_user)
    
    # Check if bundle has active assignments
    active_assignments = await db.subscription_assignments.count_documents({
        "bundle_id": bundle_id,
        "status": "active"
    })
    
    if active_assignments > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete bundle with {active_assignments} active assignments. Deactivate it instead."
        )
    
    result = await db.product_bundles.delete_one({"id": bundle_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bundle not found")
    
    return {"message": "Bundle deleted successfully"}
