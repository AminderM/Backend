from fastapi import APIRouter, Depends
from datetime import datetime, timedelta, timezone
from typing import Optional
from bson import ObjectId
from database import db

router = APIRouter(prefix="/analytics", tags=["analytics"])


def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict"""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == '_id':
                result['id'] = str(value)
            elif isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = serialize_doc(value)
            elif isinstance(value, list):
                result[key] = [serialize_doc(v) if isinstance(v, dict) else v for v in value]
            else:
                result[key] = value
        return result
    return doc


@router.get("/dispatch/kpis")
async def get_dispatch_kpis(company_id: Optional[str] = None):
    """Get dispatch KPIs including load counts, revenue, and delivery rates"""
    
    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Build query filter
    query = {}
    if company_id:
        query["company_id"] = company_id
    
    # Get all bookings using async cursor
    bookings = await db.bookings.find(query).to_list(length=None)
    
    # Status categorization
    active_statuses = ['pending', 'planned', 'in_transit_pickup', 'at_pickup', 'in_transit_delivery', 'at_delivery']
    delivered_statuses = ['delivered', 'paid', 'invoiced']
    
    # Calculate metrics
    total_loads = len(bookings)
    active_loads = 0
    delivered_loads = 0
    pending_loads = 0
    overdue_loads = 0
    total_revenue = 0
    loads_this_month = 0
    loads_this_week = 0
    
    for booking in bookings:
        status = booking.get('status', 'pending')
        
        # Count by status category
        if status in active_statuses:
            active_loads += 1
        if status in delivered_statuses:
            delivered_loads += 1
        if status == 'pending':
            pending_loads += 1
        if status == 'payment_overdue':
            overdue_loads += 1
        
        # Revenue
        rate = booking.get('confirmed_rate') or booking.get('total_cost') or 0
        total_revenue += rate
        
        # Time-based counts
        created_at = booking.get('created_at')
        if created_at:
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except:
                    continue
            elif created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            if created_at >= start_of_month:
                loads_this_month += 1
            if created_at >= start_of_week:
                loads_this_week += 1
    
    # Calculate completion rate
    completion_rate = (delivered_loads / total_loads * 100) if total_loads > 0 else 0
    
    return {
        "totalLoads": total_loads,
        "activeLoads": active_loads,
        "deliveredLoads": delivered_loads,
        "pendingLoads": pending_loads,
        "overdueLoads": overdue_loads,
        "totalRevenue": round(total_revenue, 2),
        "loadsThisMonth": loads_this_month,
        "loadsThisWeek": loads_this_week,
        "completionRate": round(completion_rate, 1),
        "avgDeliveryTime": 0  # TODO: Calculate actual average delivery time
    }


@router.get("/dispatch/status-distribution")
async def get_status_distribution(company_id: Optional[str] = None):
    """Get load status distribution for pie chart"""
    
    query = {}
    if company_id:
        query["company_id"] = company_id
    
    # Aggregate by status
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}}
    ]
    
    results = await db.bookings.aggregate(pipeline).to_list(length=None)
    total = sum(r["count"] for r in results) if results else 0
    
    # Status labels mapping
    status_labels = {
        'pending': 'Pending',
        'planned': 'Planned',
        'in_transit_pickup': 'In Transit (Pickup)',
        'at_pickup': 'At Pickup',
        'in_transit_delivery': 'In Transit (Delivery)',
        'at_delivery': 'At Delivery',
        'delivered': 'Delivered',
        'invoiced': 'Invoiced',
        'payment_overdue': 'Overdue',
        'paid': 'Paid'
    }
    
    distribution = []
    for result in results:
        status = result["_id"] or "pending"
        count = result["count"]
        distribution.append({
            "status": status_labels.get(status, status.replace('_', ' ').title()),
            "rawStatus": status,
            "count": count,
            "percentage": round((count / total * 100), 1) if total > 0 else 0
        })
    
    return distribution


@router.get("/dispatch/monthly-trend")
async def get_monthly_trend(months: int = 6, company_id: Optional[str] = None):
    """Get monthly load trend for the last N months"""
    
    now = datetime.now(timezone.utc)
    trends = []
    
    for i in range(months - 1, -1, -1):
        # Calculate month start and end
        target_month = now.month - i
        target_year = now.year
        
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        
        month_start = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
        
        if target_month == 12:
            month_end = datetime(target_year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            month_end = datetime(target_year, target_month + 1, 1, tzinfo=timezone.utc)
        
        # Build query
        query = {
            "created_at": {
                "$gte": month_start,
                "$lt": month_end
            }
        }
        if company_id:
            query["company_id"] = company_id
        
        count = await db.bookings.count_documents(query)
        
        trends.append({
            "month": month_start.strftime("%b"),
            "year": month_start.year,
            "count": count
        })
    
    return trends


@router.get("/dispatch/recent-activity")
async def get_recent_activity(limit: int = 5, company_id: Optional[str] = None):
    """Get recent load activity"""
    
    query = {}
    if company_id:
        query["company_id"] = company_id
    
    bookings = await db.bookings.find(query).sort("created_at", -1).limit(limit).to_list(length=limit)
    
    activity = []
    for booking in bookings:
        created_at = booking.get('created_at')
        if isinstance(created_at, datetime):
            created_str = created_at.strftime("%m/%d/%Y")
        elif isinstance(created_at, str):
            created_str = created_at[:10]
        else:
            created_str = "N/A"
        
        activity.append({
            "id": booking.get('order_number', str(booking.get('_id', ''))),
            "status": booking.get('status', 'pending'),
            "created": created_str,
            "rate": booking.get('confirmed_rate') or booking.get('total_cost') or 0,
            "shipper": booking.get('shipper', {}).get('name', 'N/A') if isinstance(booking.get('shipper'), dict) else booking.get('shipper', 'N/A'),
            "consignee": booking.get('consignee', {}).get('name', 'N/A') if isinstance(booking.get('consignee'), dict) else booking.get('consignee', 'N/A')
        })
    
    return activity


@router.get("/dispatch/summary")
async def get_dispatch_summary(company_id: Optional[str] = None):
    """Get complete dispatch analytics summary in one call"""
    kpis = await get_dispatch_kpis(company_id)
    status_distribution = await get_status_distribution(company_id)
    monthly_trend = await get_monthly_trend(6, company_id)
    recent_activity = await get_recent_activity(5, company_id)
    
    return {
        "kpis": kpis,
        "statusDistribution": status_distribution,
        "monthlyTrend": monthly_trend,
        "recentActivity": recent_activity
    }


@router.get("/dispatch/driver-performance")
async def get_driver_performance(company_id: Optional[str] = None, limit: int = 10):
    """Get driver performance metrics"""
    
    # Get all drivers
    driver_query = {"role": "driver"}
    if company_id:
        driver_query["company_id"] = company_id
    
    drivers = await db.users.find(driver_query, {"_id": 1, "full_name": 1, "email": 1, "status": 1}).to_list(length=None)
    
    performance = []
    for driver in drivers:
        driver_id = str(driver["_id"])
        
        # Count loads assigned to this driver
        loads_query = {"assigned_driver_id": driver_id}
        total_loads = await db.bookings.count_documents(loads_query)
        
        # Count delivered loads
        delivered_query = {
            "assigned_driver_id": driver_id,
            "status": {"$in": ["delivered", "paid", "invoiced"]}
        }
        delivered_loads = await db.bookings.count_documents(delivered_query)
        
        # Calculate delivery rate
        delivery_rate = (delivered_loads / total_loads * 100) if total_loads > 0 else 0
        
        performance.append({
            "driverId": driver_id,
            "name": driver.get("full_name", "Unknown"),
            "email": driver.get("email", ""),
            "status": driver.get("status", "active"),
            "totalLoads": total_loads,
            "deliveredLoads": delivered_loads,
            "deliveryRate": round(delivery_rate, 1)
        })
    
    # Sort by total loads descending
    performance.sort(key=lambda x: x["totalLoads"], reverse=True)
    
    return performance[:limit]


@router.get("/dispatch/revenue-breakdown")
async def get_revenue_breakdown(company_id: Optional[str] = None):
    """Get revenue breakdown by status"""
    
    query = {}
    if company_id:
        query["company_id"] = company_id
    
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$status",
            "totalRevenue": {
                "$sum": {
                    "$ifNull": ["$confirmed_rate", {"$ifNull": ["$total_cost", 0]}]
                }
            },
            "count": {"$sum": 1}
        }},
        {"$sort": {"totalRevenue": -1}}
    ]
    
    results = await db.bookings.aggregate(pipeline).to_list(length=None)
    
    status_labels = {
        'pending': 'Pending',
        'planned': 'Planned',
        'delivered': 'Delivered',
        'invoiced': 'Invoiced',
        'paid': 'Paid',
        'payment_overdue': 'Overdue'
    }
    
    breakdown = []
    for result in results:
        status = result["_id"] or "pending"
        breakdown.append({
            "status": status_labels.get(status, status.replace('_', ' ').title()),
            "rawStatus": status,
            "revenue": round(result["totalRevenue"], 2),
            "count": result["count"]
        })
    
    return breakdown
