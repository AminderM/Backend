from fastapi import APIRouter, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from database import db
from auth import get_current_user, require_platform_admin
from bson import ObjectId
import uuid
import json
import asyncio

router = APIRouter(prefix="/customer-analytics", tags=["Customer Analytics"])

# ============================================================================
# MODELS
# ============================================================================

class PageViewEvent(BaseModel):
    """Track page view events from the website"""
    page_url: str
    page_title: Optional[str] = None
    referrer: Optional[str] = None
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None
    user_agent: Optional[str] = None
    screen_resolution: Optional[str] = None
    viewport_size: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None

class ClickEvent(BaseModel):
    """Track click events for heatmap data"""
    page_url: str
    element_id: Optional[str] = None
    element_class: Optional[str] = None
    element_tag: Optional[str] = None
    element_text: Optional[str] = None
    x_position: int
    y_position: int
    viewport_width: int
    viewport_height: int
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None

class ScrollEvent(BaseModel):
    """Track scroll depth for engagement analysis"""
    page_url: str
    scroll_depth_percent: int  # 0-100
    max_scroll_depth: int  # Maximum scroll depth reached
    time_on_page: int  # Seconds
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None

class FormInteractionEvent(BaseModel):
    """Track form interactions"""
    page_url: str
    form_id: Optional[str] = None
    form_name: Optional[str] = None
    event_type: str  # focus, blur, submit, abandon
    field_name: Optional[str] = None
    time_spent: Optional[int] = None  # Seconds spent on field
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None
    form_data: Optional[Dict[str, Any]] = None  # For submit events (sanitized)

class ConversionEvent(BaseModel):
    """Track conversion events"""
    event_name: str
    event_category: str  # demo_request, signup, contact, download, etc.
    event_value: Optional[float] = None
    page_url: Optional[str] = None
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class CustomEvent(BaseModel):
    """Track custom events configured by admin"""
    event_name: str
    event_data: Optional[Dict[str, Any]] = None
    page_url: Optional[str] = None
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None

class SessionStart(BaseModel):
    """Initialize a new session"""
    visitor_id: Optional[str] = None
    user_agent: Optional[str] = None
    referrer: Optional[str] = None
    landing_page: str
    screen_resolution: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None

class CustomEventConfig(BaseModel):
    """Configuration for custom event tracking"""
    name: str
    description: Optional[str] = None
    event_selector: Optional[str] = None  # CSS selector for auto-tracking
    event_type: str = "click"  # click, submit, view, custom
    category: str = "custom"
    is_conversion: bool = False
    conversion_value: Optional[float] = None
    is_active: bool = True


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

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


async def get_or_create_visitor(visitor_id: Optional[str] = None) -> str:
    """Get existing visitor or create new one"""
    if visitor_id:
        existing = await db.visitors.find_one({"visitor_id": visitor_id})
        if existing:
            await db.visitors.update_one(
                {"visitor_id": visitor_id},
                {"$set": {"last_seen": datetime.now(timezone.utc).isoformat()}}
            )
            return visitor_id
    
    new_visitor_id = str(uuid.uuid4())
    await db.visitors.insert_one({
        "visitor_id": new_visitor_id,
        "first_seen": datetime.now(timezone.utc).isoformat(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "total_sessions": 0,
        "total_page_views": 0
    })
    return new_visitor_id


# ============================================================================
# PUBLIC TRACKING ENDPOINTS (No Auth Required)
# ============================================================================

@router.post("/track/session/start")
async def start_session(session_data: SessionStart):
    """Start a new tracking session"""
    visitor_id = await get_or_create_visitor(session_data.visitor_id)
    session_id = str(uuid.uuid4())
    
    session_doc = {
        "session_id": session_id,
        "visitor_id": visitor_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_activity": datetime.now(timezone.utc).isoformat(),
        "landing_page": session_data.landing_page,
        "referrer": session_data.referrer,
        "user_agent": session_data.user_agent,
        "screen_resolution": session_data.screen_resolution,
        "language": session_data.language,
        "timezone": session_data.timezone,
        "utm_source": session_data.utm_source,
        "utm_medium": session_data.utm_medium,
        "utm_campaign": session_data.utm_campaign,
        "page_views": 0,
        "events": 0,
        "conversions": 0,
        "is_active": True,
        "pages_visited": [session_data.landing_page],
        "duration_seconds": 0
    }
    
    await db.sessions.insert_one(session_doc)
    
    # Update visitor stats
    await db.visitors.update_one(
        {"visitor_id": visitor_id},
        {"$inc": {"total_sessions": 1}}
    )
    
    return {
        "session_id": session_id,
        "visitor_id": visitor_id,
        "status": "started"
    }


@router.post("/track/pageview")
async def track_pageview(event: PageViewEvent):
    """Track a page view event"""
    visitor_id = await get_or_create_visitor(event.visitor_id)
    
    pageview_doc = {
        "event_type": "pageview",
        "page_url": event.page_url,
        "page_title": event.page_title,
        "referrer": event.referrer,
        "session_id": event.session_id,
        "visitor_id": visitor_id,
        "user_agent": event.user_agent,
        "screen_resolution": event.screen_resolution,
        "viewport_size": event.viewport_size,
        "language": event.language,
        "timezone": event.timezone,
        "utm_source": event.utm_source,
        "utm_medium": event.utm_medium,
        "utm_campaign": event.utm_campaign,
        "utm_term": event.utm_term,
        "utm_content": event.utm_content,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.pageviews.insert_one(pageview_doc)
    
    # Update session
    if event.session_id:
        await db.sessions.update_one(
            {"session_id": event.session_id},
            {
                "$inc": {"page_views": 1},
                "$set": {"last_activity": datetime.now(timezone.utc).isoformat()},
                "$addToSet": {"pages_visited": event.page_url}
            }
        )
    
    # Update visitor stats
    await db.visitors.update_one(
        {"visitor_id": visitor_id},
        {"$inc": {"total_page_views": 1}}
    )
    
    return {"status": "tracked", "visitor_id": visitor_id}


@router.post("/track/click")
async def track_click(event: ClickEvent):
    """Track click events for heatmap analysis"""
    click_doc = {
        "event_type": "click",
        "page_url": event.page_url,
        "element_id": event.element_id,
        "element_class": event.element_class,
        "element_tag": event.element_tag,
        "element_text": event.element_text[:100] if event.element_text else None,
        "x_position": event.x_position,
        "y_position": event.y_position,
        "viewport_width": event.viewport_width,
        "viewport_height": event.viewport_height,
        "session_id": event.session_id,
        "visitor_id": event.visitor_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.click_events.insert_one(click_doc)
    
    # Update session events count
    if event.session_id:
        await db.sessions.update_one(
            {"session_id": event.session_id},
            {
                "$inc": {"events": 1},
                "$set": {"last_activity": datetime.now(timezone.utc).isoformat()}
            }
        )
    
    return {"status": "tracked"}


@router.post("/track/scroll")
async def track_scroll(event: ScrollEvent):
    """Track scroll depth for engagement analysis"""
    scroll_doc = {
        "event_type": "scroll",
        "page_url": event.page_url,
        "scroll_depth_percent": event.scroll_depth_percent,
        "max_scroll_depth": event.max_scroll_depth,
        "time_on_page": event.time_on_page,
        "session_id": event.session_id,
        "visitor_id": event.visitor_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.scroll_events.insert_one(scroll_doc)
    
    return {"status": "tracked"}


@router.post("/track/form")
async def track_form_interaction(event: FormInteractionEvent):
    """Track form interactions"""
    form_doc = {
        "event_type": "form_interaction",
        "page_url": event.page_url,
        "form_id": event.form_id,
        "form_name": event.form_name,
        "interaction_type": event.event_type,
        "field_name": event.field_name,
        "time_spent": event.time_spent,
        "session_id": event.session_id,
        "visitor_id": event.visitor_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Don't store sensitive form data
    if event.event_type == "submit" and event.form_data:
        form_doc["fields_submitted"] = list(event.form_data.keys())
    
    await db.form_events.insert_one(form_doc)
    
    return {"status": "tracked"}


@router.post("/track/conversion")
async def track_conversion(event: ConversionEvent):
    """Track conversion events"""
    conversion_doc = {
        "event_type": "conversion",
        "event_name": event.event_name,
        "event_category": event.event_category,
        "event_value": event.event_value,
        "page_url": event.page_url,
        "session_id": event.session_id,
        "visitor_id": event.visitor_id,
        "metadata": event.metadata,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.conversion_events.insert_one(conversion_doc)
    
    # Update session conversions count
    if event.session_id:
        await db.sessions.update_one(
            {"session_id": event.session_id},
            {
                "$inc": {"conversions": 1},
                "$set": {"last_activity": datetime.now(timezone.utc).isoformat()}
            }
        )
    
    return {"status": "tracked"}


@router.post("/track/custom")
async def track_custom_event(event: CustomEvent):
    """Track custom events"""
    custom_doc = {
        "event_type": "custom",
        "event_name": event.event_name,
        "event_data": event.event_data,
        "page_url": event.page_url,
        "session_id": event.session_id,
        "visitor_id": event.visitor_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.custom_events.insert_one(custom_doc)
    
    return {"status": "tracked"}


@router.post("/track/session/end")
async def end_session(session_id: str, duration_seconds: int = 0):
    """End a tracking session"""
    await db.sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "is_active": False,
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration_seconds
            }
        }
    )
    
    return {"status": "ended"}


# ============================================================================
# ADMIN DASHBOARD ENDPOINTS (Auth Required)
# ============================================================================

@router.get("/dashboard/overview")
async def get_analytics_overview(
    days: int = 30,
    current_user = Depends(get_current_user)
):
    """Get overview analytics for the dashboard"""
    require_platform_admin(current_user)
    
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    start_iso = start_date.isoformat()
    
    # Total visitors
    total_visitors = await db.visitors.count_documents({})
    
    # New visitors in period
    new_visitors = await db.visitors.count_documents({
        "first_seen": {"$gte": start_iso}
    })
    
    # Total sessions in period
    total_sessions = await db.sessions.count_documents({
        "started_at": {"$gte": start_iso}
    })
    
    # Total page views in period
    total_pageviews = await db.pageviews.count_documents({
        "timestamp": {"$gte": start_iso}
    })
    
    # Total conversions in period
    total_conversions = await db.conversion_events.count_documents({
        "timestamp": {"$gte": start_iso}
    })
    
    # Active sessions (last 5 minutes)
    active_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    active_sessions = await db.sessions.count_documents({
        "is_active": True,
        "last_activity": {"$gte": active_cutoff}
    })
    
    # Average session duration
    pipeline = [
        {"$match": {"started_at": {"$gte": start_iso}, "duration_seconds": {"$gt": 0}}},
        {"$group": {"_id": None, "avg_duration": {"$avg": "$duration_seconds"}}}
    ]
    duration_result = await db.sessions.aggregate(pipeline).to_list(1)
    avg_session_duration = duration_result[0]["avg_duration"] if duration_result else 0
    
    # Bounce rate (sessions with only 1 page view)
    single_page_sessions = await db.sessions.count_documents({
        "started_at": {"$gte": start_iso},
        "page_views": 1
    })
    bounce_rate = (single_page_sessions / total_sessions * 100) if total_sessions > 0 else 0
    
    # Conversion rate
    conversion_rate = (total_conversions / total_sessions * 100) if total_sessions > 0 else 0
    
    return {
        "period_days": days,
        "total_visitors": total_visitors,
        "new_visitors": new_visitors,
        "total_sessions": total_sessions,
        "total_pageviews": total_pageviews,
        "total_conversions": total_conversions,
        "active_sessions": active_sessions,
        "avg_session_duration_seconds": round(avg_session_duration, 1),
        "bounce_rate_percent": round(bounce_rate, 1),
        "conversion_rate_percent": round(conversion_rate, 2),
        "pages_per_session": round(total_pageviews / total_sessions, 2) if total_sessions > 0 else 0
    }


@router.get("/dashboard/realtime")
async def get_realtime_stats(current_user = Depends(get_current_user)):
    """Get real-time visitor statistics"""
    require_platform_admin(current_user)
    
    now = datetime.now(timezone.utc)
    
    # Active in last 5 minutes
    cutoff_5min = (now - timedelta(minutes=5)).isoformat()
    active_5min = await db.sessions.count_documents({
        "is_active": True,
        "last_activity": {"$gte": cutoff_5min}
    })
    
    # Active in last 30 minutes
    cutoff_30min = (now - timedelta(minutes=30)).isoformat()
    active_30min = await db.sessions.count_documents({
        "is_active": True,
        "last_activity": {"$gte": cutoff_30min}
    })
    
    # Get current active sessions with details
    active_sessions = await db.sessions.find(
        {"is_active": True, "last_activity": {"$gte": cutoff_5min}},
        {"_id": 0, "session_id": 1, "visitor_id": 1, "landing_page": 1, 
         "pages_visited": 1, "page_views": 1, "started_at": 1, "last_activity": 1,
         "referrer": 1, "utm_source": 1}
    ).sort("last_activity", -1).limit(50).to_list(50)
    
    # Top pages right now
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff_5min}}},
        {"$group": {"_id": "$page_url", "views": {"$sum": 1}}},
        {"$sort": {"views": -1}},
        {"$limit": 10}
    ]
    top_pages = await db.pageviews.aggregate(pipeline).to_list(10)
    
    return {
        "active_visitors_5min": active_5min,
        "active_visitors_30min": active_30min,
        "active_sessions": serialize_doc(active_sessions),
        "top_pages_now": [{"page": p["_id"], "views": p["views"]} for p in top_pages],
        "timestamp": now.isoformat()
    }


@router.get("/dashboard/traffic-sources")
async def get_traffic_sources(
    days: int = 30,
    current_user = Depends(get_current_user)
):
    """Get traffic source breakdown"""
    require_platform_admin(current_user)
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # By referrer domain
    pipeline = [
        {"$match": {"started_at": {"$gte": start_date}}},
        {"$group": {
            "_id": "$referrer",
            "sessions": {"$sum": 1},
            "conversions": {"$sum": "$conversions"}
        }},
        {"$sort": {"sessions": -1}},
        {"$limit": 20}
    ]
    referrer_data = await db.sessions.aggregate(pipeline).to_list(20)
    
    # By UTM source
    pipeline = [
        {"$match": {"started_at": {"$gte": start_date}, "utm_source": {"$ne": None}}},
        {"$group": {
            "_id": "$utm_source",
            "sessions": {"$sum": 1},
            "conversions": {"$sum": "$conversions"}
        }},
        {"$sort": {"sessions": -1}},
        {"$limit": 20}
    ]
    utm_source_data = await db.sessions.aggregate(pipeline).to_list(20)
    
    # By UTM campaign
    pipeline = [
        {"$match": {"started_at": {"$gte": start_date}, "utm_campaign": {"$ne": None}}},
        {"$group": {
            "_id": "$utm_campaign",
            "sessions": {"$sum": 1},
            "conversions": {"$sum": "$conversions"}
        }},
        {"$sort": {"sessions": -1}},
        {"$limit": 20}
    ]
    utm_campaign_data = await db.sessions.aggregate(pipeline).to_list(20)
    
    # Categorize traffic
    direct_sessions = await db.sessions.count_documents({
        "started_at": {"$gte": start_date},
        "referrer": {"$in": [None, "", "direct"]}
    })
    
    total_sessions = await db.sessions.count_documents({
        "started_at": {"$gte": start_date}
    })
    
    return {
        "by_referrer": [{"source": r["_id"] or "Direct", "sessions": r["sessions"], "conversions": r["conversions"]} for r in referrer_data],
        "by_utm_source": [{"source": u["_id"], "sessions": u["sessions"], "conversions": u["conversions"]} for u in utm_source_data],
        "by_campaign": [{"campaign": c["_id"], "sessions": c["sessions"], "conversions": c["conversions"]} for c in utm_campaign_data],
        "traffic_breakdown": {
            "direct": direct_sessions,
            "referral": total_sessions - direct_sessions,
            "total": total_sessions
        }
    }


@router.get("/dashboard/top-pages")
async def get_top_pages(
    days: int = 30,
    limit: int = 20,
    current_user = Depends(get_current_user)
):
    """Get top pages by views"""
    require_platform_admin(current_user)
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": "$page_url",
            "views": {"$sum": 1},
            "unique_visitors": {"$addToSet": "$visitor_id"}
        }},
        {"$project": {
            "_id": 1,
            "views": 1,
            "unique_visitors": {"$size": "$unique_visitors"}
        }},
        {"$sort": {"views": -1}},
        {"$limit": limit}
    ]
    
    top_pages = await db.pageviews.aggregate(pipeline).to_list(limit)
    
    # Get average time on page and scroll depth for each
    result = []
    for page in top_pages:
        page_url = page["_id"]
        
        # Average scroll depth
        scroll_pipeline = [
            {"$match": {"page_url": page_url, "timestamp": {"$gte": start_date}}},
            {"$group": {"_id": None, "avg_scroll": {"$avg": "$max_scroll_depth"}}}
        ]
        scroll_result = await db.scroll_events.aggregate(scroll_pipeline).to_list(1)
        avg_scroll = scroll_result[0]["avg_scroll"] if scroll_result else 0
        
        result.append({
            "page_url": page_url,
            "views": page["views"],
            "unique_visitors": page["unique_visitors"],
            "avg_scroll_depth": round(avg_scroll, 1)
        })
    
    return result


@router.get("/dashboard/user-journeys")
async def get_user_journeys(
    days: int = 30,
    limit: int = 20,
    current_user = Depends(get_current_user)
):
    """Get common user journey paths"""
    require_platform_admin(current_user)
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Get sessions with page visits
    pipeline = [
        {"$match": {"started_at": {"$gte": start_date}, "page_views": {"$gt": 1}}},
        {"$project": {
            "pages_visited": 1,
            "conversions": 1
        }},
        {"$limit": 1000}  # Limit for performance
    ]
    
    sessions = await db.sessions.aggregate(pipeline).to_list(1000)
    
    # Analyze journey patterns
    journey_counts = {}
    for session in sessions:
        pages = session.get("pages_visited", [])
        if len(pages) >= 2:
            # Create path string (first 5 pages)
            path = " -> ".join(pages[:5])
            if path not in journey_counts:
                journey_counts[path] = {"count": 0, "conversions": 0}
            journey_counts[path]["count"] += 1
            journey_counts[path]["conversions"] += session.get("conversions", 0)
    
    # Sort by frequency
    sorted_journeys = sorted(
        [{"path": k, **v} for k, v in journey_counts.items()],
        key=lambda x: x["count"],
        reverse=True
    )[:limit]
    
    # Entry pages
    entry_pipeline = [
        {"$match": {"started_at": {"$gte": start_date}}},
        {"$group": {"_id": "$landing_page", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    entry_pages = await db.sessions.aggregate(entry_pipeline).to_list(10)
    
    return {
        "common_journeys": sorted_journeys,
        "top_entry_pages": [{"page": e["_id"], "sessions": e["count"]} for e in entry_pages]
    }


@router.get("/dashboard/funnel-analysis")
async def get_funnel_analysis(
    days: int = 30,
    current_user = Depends(get_current_user)
):
    """Get funnel analysis for conversions"""
    require_platform_admin(current_user)
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Define standard funnel stages
    funnel_stages = {
        "visited_site": await db.sessions.count_documents({"started_at": {"$gte": start_date}}),
        "viewed_pricing": await db.pageviews.count_documents({
            "timestamp": {"$gte": start_date},
            "page_url": {"$regex": "pricing|plans", "$options": "i"}
        }),
        "viewed_features": await db.pageviews.count_documents({
            "timestamp": {"$gte": start_date},
            "page_url": {"$regex": "features|product", "$options": "i"}
        }),
        "started_demo_form": await db.form_events.count_documents({
            "timestamp": {"$gte": start_date},
            "interaction_type": "focus",
            "form_name": {"$regex": "demo", "$options": "i"}
        }),
        "submitted_demo_request": await db.conversion_events.count_documents({
            "timestamp": {"$gte": start_date},
            "event_category": "demo_request"
        })
    }
    
    # Calculate conversion rates between stages
    funnel_with_rates = []
    stages = list(funnel_stages.items())
    for i, (stage_name, count) in enumerate(stages):
        rate_from_start = (count / stages[0][1] * 100) if stages[0][1] > 0 else 0
        rate_from_prev = 100 if i == 0 else (count / stages[i-1][1] * 100) if stages[i-1][1] > 0 else 0
        funnel_with_rates.append({
            "stage": stage_name,
            "count": count,
            "rate_from_start": round(rate_from_start, 2),
            "rate_from_previous": round(rate_from_prev, 2)
        })
    
    return {
        "funnel_stages": funnel_with_rates,
        "overall_conversion_rate": round(
            (funnel_stages["submitted_demo_request"] / funnel_stages["visited_site"] * 100) 
            if funnel_stages["visited_site"] > 0 else 0, 2
        )
    }


@router.get("/dashboard/heatmap-data")
async def get_heatmap_data(
    page_url: str,
    days: int = 30,
    current_user = Depends(get_current_user)
):
    """Get click heatmap data for a specific page"""
    require_platform_admin(current_user)
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Get click data
    clicks = await db.click_events.find(
        {
            "page_url": {"$regex": f"^{page_url}", "$options": "i"},
            "timestamp": {"$gte": start_date}
        },
        {"_id": 0, "x_position": 1, "y_position": 1, "viewport_width": 1, 
         "viewport_height": 1, "element_tag": 1, "element_id": 1}
    ).to_list(10000)
    
    # Aggregate click zones
    click_zones = {}
    for click in clicks:
        # Normalize positions to percentage
        x_pct = round(click["x_position"] / click["viewport_width"] * 100, 1)
        y_pct = round(click["y_position"] / click["viewport_height"] * 100, 1)
        zone_key = f"{x_pct},{y_pct}"
        
        if zone_key not in click_zones:
            click_zones[zone_key] = {"x": x_pct, "y": y_pct, "count": 0}
        click_zones[zone_key]["count"] += 1
    
    # Top clicked elements
    element_pipeline = [
        {"$match": {"page_url": {"$regex": f"^{page_url}", "$options": "i"}, "timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": {"tag": "$element_tag", "id": "$element_id"},
            "clicks": {"$sum": 1}
        }},
        {"$sort": {"clicks": -1}},
        {"$limit": 20}
    ]
    top_elements = await db.click_events.aggregate(element_pipeline).to_list(20)
    
    return {
        "page_url": page_url,
        "total_clicks": len(clicks),
        "click_points": list(click_zones.values()),
        "top_clicked_elements": [
            {"element": f"{e['_id']['tag']}#{e['_id']['id']}" if e['_id']['id'] else e['_id']['tag'], 
             "clicks": e["clicks"]} 
            for e in top_elements
        ]
    }


@router.get("/dashboard/form-analytics")
async def get_form_analytics(
    days: int = 30,
    current_user = Depends(get_current_user)
):
    """Get form interaction analytics"""
    require_platform_admin(current_user)
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Form completion rates
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": "$form_name",
            "total_interactions": {"$sum": 1},
            "submits": {
                "$sum": {"$cond": [{"$eq": ["$interaction_type", "submit"]}, 1, 0]}
            },
            "abandons": {
                "$sum": {"$cond": [{"$eq": ["$interaction_type", "abandon"]}, 1, 0]}
            }
        }},
        {"$sort": {"total_interactions": -1}}
    ]
    form_stats = await db.form_events.aggregate(pipeline).to_list(20)
    
    # Field-level analysis
    field_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}, "field_name": {"$ne": None}}},
        {"$group": {
            "_id": {"form": "$form_name", "field": "$field_name"},
            "interactions": {"$sum": 1},
            "avg_time_spent": {"$avg": "$time_spent"}
        }},
        {"$sort": {"interactions": -1}},
        {"$limit": 50}
    ]
    field_stats = await db.form_events.aggregate(field_pipeline).to_list(50)
    
    return {
        "form_completion": [
            {
                "form_name": f["_id"] or "Unknown",
                "total_starts": f["total_interactions"],
                "submits": f["submits"],
                "abandons": f["abandons"],
                "completion_rate": round(f["submits"] / f["total_interactions"] * 100, 1) if f["total_interactions"] > 0 else 0
            }
            for f in form_stats
        ],
        "field_analysis": [
            {
                "form": fs["_id"]["form"],
                "field": fs["_id"]["field"],
                "interactions": fs["interactions"],
                "avg_time_seconds": round(fs["avg_time_spent"] or 0, 1)
            }
            for fs in field_stats
        ]
    }


@router.get("/dashboard/conversion-analytics")
async def get_conversion_analytics(
    days: int = 30,
    current_user = Depends(get_current_user)
):
    """Get conversion analytics"""
    require_platform_admin(current_user)
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Conversions by category
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": "$event_category",
            "count": {"$sum": 1},
            "total_value": {"$sum": {"$ifNull": ["$event_value", 0]}}
        }},
        {"$sort": {"count": -1}}
    ]
    by_category = await db.conversion_events.aggregate(pipeline).to_list(20)
    
    # Conversions over time (daily)
    daily_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": {"$substr": ["$timestamp", 0, 10]},
            "count": {"$sum": 1},
            "value": {"$sum": {"$ifNull": ["$event_value", 0]}}
        }},
        {"$sort": {"_id": 1}}
    ]
    daily_conversions = await db.conversion_events.aggregate(daily_pipeline).to_list(100)
    
    # Top converting pages
    page_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}, "page_url": {"$ne": None}}},
        {"$group": {
            "_id": "$page_url",
            "conversions": {"$sum": 1}
        }},
        {"$sort": {"conversions": -1}},
        {"$limit": 10}
    ]
    top_pages = await db.conversion_events.aggregate(page_pipeline).to_list(10)
    
    return {
        "by_category": [
            {"category": c["_id"], "count": c["count"], "value": c["total_value"]}
            for c in by_category
        ],
        "daily_trend": [
            {"date": d["_id"], "conversions": d["count"], "value": d["value"]}
            for d in daily_conversions
        ],
        "top_converting_pages": [
            {"page": p["_id"], "conversions": p["conversions"]}
            for p in top_pages
        ]
    }


@router.get("/dashboard/visitor-activity-log")
async def get_visitor_activity_log(
    days: int = 7,
    limit: int = 100,
    current_user = Depends(get_current_user)
):
    """Get detailed visitor activity log"""
    require_platform_admin(current_user)
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Get recent sessions with details
    sessions = await db.sessions.find(
        {"started_at": {"$gte": start_date}},
        {"_id": 0}
    ).sort("started_at", -1).limit(limit).to_list(limit)
    
    return serialize_doc(sessions)


# ============================================================================
# CUSTOM EVENT CONFIGURATION (Admin)
# ============================================================================

@router.get("/config/events")
async def get_event_configs(current_user = Depends(get_current_user)):
    """Get all custom event configurations"""
    require_platform_admin(current_user)
    
    configs = await db.event_configs.find({}, {"_id": 0}).to_list(100)
    return serialize_doc(configs)


@router.post("/config/events")
async def create_event_config(
    config: CustomEventConfig,
    current_user = Depends(get_current_user)
):
    """Create a new custom event configuration"""
    require_platform_admin(current_user)
    
    config_doc = {
        "id": str(uuid.uuid4()),
        "name": config.name,
        "description": config.description,
        "event_selector": config.event_selector,
        "event_type": config.event_type,
        "category": config.category,
        "is_conversion": config.is_conversion,
        "conversion_value": config.conversion_value,
        "is_active": config.is_active,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.email
    }
    
    await db.event_configs.insert_one(config_doc)
    
    return {"message": "Event configuration created", "config": serialize_doc(config_doc)}


@router.put("/config/events/{config_id}")
async def update_event_config(
    config_id: str,
    config: CustomEventConfig,
    current_user = Depends(get_current_user)
):
    """Update a custom event configuration"""
    require_platform_admin(current_user)
    
    update_data = config.dict()
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = current_user.email
    
    result = await db.event_configs.update_one(
        {"id": config_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Event configuration not found")
    
    return {"message": "Event configuration updated"}


@router.delete("/config/events/{config_id}")
async def delete_event_config(
    config_id: str,
    current_user = Depends(get_current_user)
):
    """Delete a custom event configuration"""
    require_platform_admin(current_user)
    
    result = await db.event_configs.delete_one({"id": config_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event configuration not found")
    
    return {"message": "Event configuration deleted"}


# ============================================================================
# REPORTS & DATA EXPORT
# ============================================================================

@router.get("/reports/summary")
async def get_summary_report(
    start_date: str = None,
    end_date: str = None,
    current_user = Depends(get_current_user)
):
    """Get comprehensive summary report"""
    require_platform_admin(current_user)
    
    # Default to last 30 days
    if not start_date:
        start_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = datetime.now(timezone.utc).isoformat()
    
    # Gather all metrics
    total_sessions = await db.sessions.count_documents({
        "started_at": {"$gte": start_date, "$lte": end_date}
    })
    
    total_pageviews = await db.pageviews.count_documents({
        "timestamp": {"$gte": start_date, "$lte": end_date}
    })
    
    total_conversions = await db.conversion_events.count_documents({
        "timestamp": {"$gte": start_date, "$lte": end_date}
    })
    
    unique_visitors = await db.sessions.distinct("visitor_id", {
        "started_at": {"$gte": start_date, "$lte": end_date}
    })
    
    # Average session metrics
    session_pipeline = [
        {"$match": {"started_at": {"$gte": start_date, "$lte": end_date}}},
        {"$group": {
            "_id": None,
            "avg_duration": {"$avg": "$duration_seconds"},
            "avg_pageviews": {"$avg": "$page_views"},
            "total_conversions": {"$sum": "$conversions"}
        }}
    ]
    session_stats = await db.sessions.aggregate(session_pipeline).to_list(1)
    session_data = session_stats[0] if session_stats else {"avg_duration": 0, "avg_pageviews": 0}
    
    return {
        "report_period": {
            "start_date": start_date,
            "end_date": end_date
        },
        "visitors": {
            "unique_visitors": len(unique_visitors),
            "total_sessions": total_sessions,
            "sessions_per_visitor": round(total_sessions / len(unique_visitors), 2) if unique_visitors else 0
        },
        "engagement": {
            "total_pageviews": total_pageviews,
            "pages_per_session": round(session_data.get("avg_pageviews", 0), 2),
            "avg_session_duration_seconds": round(session_data.get("avg_duration", 0), 1)
        },
        "conversions": {
            "total_conversions": total_conversions,
            "conversion_rate_percent": round(total_conversions / total_sessions * 100, 2) if total_sessions > 0 else 0
        }
    }


@router.get("/reports/export")
async def export_analytics_data(
    data_type: str = Query(..., description="Type of data: sessions, pageviews, conversions, clicks"),
    start_date: str = None,
    end_date: str = None,
    format: str = "json",
    current_user = Depends(get_current_user)
):
    """Export analytics data"""
    require_platform_admin(current_user)
    
    # Default to last 30 days
    if not start_date:
        start_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = datetime.now(timezone.utc).isoformat()
    
    collection_map = {
        "sessions": db.sessions,
        "pageviews": db.pageviews,
        "conversions": db.conversion_events,
        "clicks": db.click_events,
        "forms": db.form_events
    }
    
    if data_type not in collection_map:
        raise HTTPException(status_code=400, detail=f"Invalid data type. Choose from: {list(collection_map.keys())}")
    
    collection = collection_map[data_type]
    timestamp_field = "started_at" if data_type == "sessions" else "timestamp"
    
    query = {timestamp_field: {"$gte": start_date, "$lte": end_date}}
    data = await collection.find(query, {"_id": 0}).limit(10000).to_list(10000)
    
    return {
        "data_type": data_type,
        "period": {"start": start_date, "end": end_date},
        "count": len(data),
        "data": serialize_doc(data)
    }
