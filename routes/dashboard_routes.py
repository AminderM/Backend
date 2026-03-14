"""
Dashboard API Routes - Formatted for Frontend Web Analytics Dashboard
These endpoints provide data in the exact format expected by the frontend.
"""
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone, timedelta
from typing import Optional
from database import db
from auth import get_current_user, require_platform_admin
import random

router = APIRouter(prefix="/dashboard", tags=["Dashboard Analytics"])


def get_day_name(days_ago: int) -> str:
    """Get day name for N days ago"""
    day = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return day.strftime("%a")


@router.get("/overview")
async def get_dashboard_overview(
    days: int = 7,
    current_user = Depends(get_current_user)
):
    """
    Get KPI metrics for the analytics dashboard.
    Returns visitor counts, conversions, bounce rate, session duration, and daily traffic.
    """
    require_platform_admin(current_user)
    
    now = datetime.now(timezone.utc)
    current_period_start = (now - timedelta(days=days)).isoformat()
    previous_period_start = (now - timedelta(days=days*2)).isoformat()
    previous_period_end = current_period_start
    
    # Current period metrics
    current_visitors = len(await db.sessions.distinct("visitor_id", {
        "started_at": {"$gte": current_period_start}
    }))
    
    current_sessions = await db.sessions.count_documents({
        "started_at": {"$gte": current_period_start}
    })
    
    current_conversions = await db.conversion_events.count_documents({
        "timestamp": {"$gte": current_period_start}
    })
    
    current_pageviews = await db.pageviews.count_documents({
        "timestamp": {"$gte": current_period_start}
    })
    
    # Single page sessions for bounce rate
    single_page_sessions = await db.sessions.count_documents({
        "started_at": {"$gte": current_period_start},
        "page_views": 1
    })
    
    # Average session duration
    duration_pipeline = [
        {"$match": {"started_at": {"$gte": current_period_start}, "duration_seconds": {"$gt": 0}}},
        {"$group": {"_id": None, "avg_duration": {"$avg": "$duration_seconds"}}}
    ]
    duration_result = await db.sessions.aggregate(duration_pipeline).to_list(1)
    avg_session_duration = int(duration_result[0]["avg_duration"]) if duration_result else 0
    
    # Previous period metrics for comparison
    previous_visitors = len(await db.sessions.distinct("visitor_id", {
        "started_at": {"$gte": previous_period_start, "$lt": previous_period_end}
    }))
    
    previous_conversions = await db.conversion_events.count_documents({
        "timestamp": {"$gte": previous_period_start, "$lt": previous_period_end}
    })
    
    previous_single_page = await db.sessions.count_documents({
        "started_at": {"$gte": previous_period_start, "$lt": previous_period_end},
        "page_views": 1
    })
    previous_sessions = await db.sessions.count_documents({
        "started_at": {"$gte": previous_period_start, "$lt": previous_period_end}
    })
    
    prev_duration_result = await db.sessions.aggregate([
        {"$match": {"started_at": {"$gte": previous_period_start, "$lt": previous_period_end}, "duration_seconds": {"$gt": 0}}},
        {"$group": {"_id": None, "avg_duration": {"$avg": "$duration_seconds"}}}
    ]).to_list(1)
    prev_avg_duration = int(prev_duration_result[0]["avg_duration"]) if prev_duration_result else 0
    
    # Calculate percentage changes
    def calc_change(current, previous):
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)
    
    current_bounce_rate = (single_page_sessions / current_sessions * 100) if current_sessions > 0 else 0
    previous_bounce_rate = (previous_single_page / previous_sessions * 100) if previous_sessions > 0 else 0
    
    visitors_change = calc_change(current_visitors, previous_visitors)
    conversions_change = calc_change(current_conversions, previous_conversions)
    bounce_rate_change = round(current_bounce_rate - previous_bounce_rate, 1)  # Negative is better
    session_duration_change = calc_change(avg_session_duration, prev_avg_duration)
    
    # Daily traffic for the last N days
    daily_traffic = []
    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_start_iso = day_start.isoformat()
        day_end_iso = day_end.isoformat()
        
        day_visitors = len(await db.sessions.distinct("visitor_id", {
            "started_at": {"$gte": day_start_iso, "$lt": day_end_iso}
        }))
        
        day_pageviews = await db.pageviews.count_documents({
            "timestamp": {"$gte": day_start_iso, "$lt": day_end_iso}
        })
        
        day_conversions = await db.conversion_events.count_documents({
            "timestamp": {"$gte": day_start_iso, "$lt": day_end_iso}
        })
        
        daily_traffic.append({
            "date": day_start.strftime("%a"),
            "visitors": day_visitors,
            "pageviews": day_pageviews,
            "conversions": day_conversions
        })
    
    return {
        "total_visitors": current_visitors,
        "visitors_change": visitors_change,
        "conversions": current_conversions,
        "conversions_change": conversions_change,
        "bounce_rate": round(current_bounce_rate, 1),
        "bounce_rate_change": bounce_rate_change,
        "avg_session_duration": avg_session_duration,
        "session_duration_change": session_duration_change,
        "daily_traffic": daily_traffic
    }


@router.get("/realtime")
async def get_dashboard_realtime(current_user = Depends(get_current_user)):
    """
    Get real-time visitor data including active visitors, sessions by source, and top pages.
    """
    require_platform_admin(current_user)
    
    now = datetime.now(timezone.utc)
    
    # Active in last 5 minutes
    cutoff_5min = (now - timedelta(minutes=5)).isoformat()
    active_visitors = await db.sessions.count_documents({
        "is_active": True,
        "last_activity": {"$gte": cutoff_5min}
    })
    
    # Active sessions (last 30 minutes)
    cutoff_30min = (now - timedelta(minutes=30)).isoformat()
    active_sessions = await db.sessions.count_documents({
        "is_active": True,
        "last_activity": {"$gte": cutoff_30min}
    })
    
    # Visitors timeline (last 24 hours, 2-hour intervals)
    visitors_timeline = []
    for hour in range(0, 24, 2):
        hour_start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if hour_start > now:
            hour_start = hour_start - timedelta(days=1)
        hour_end = hour_start + timedelta(hours=2)
        
        hour_visitors = await db.sessions.count_documents({
            "started_at": {"$gte": hour_start.isoformat(), "$lt": hour_end.isoformat()}
        })
        
        visitors_timeline.append({
            "time": f"{hour:02d}:00",
            "visitors": hour_visitors
        })
    
    # Sessions by source (from referrer/utm_source)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    source_pipeline = [
        {"$match": {"started_at": {"$gte": today_start}}},
        {"$project": {
            "source": {
                "$cond": {
                    "if": {"$and": [{"$ne": ["$utm_source", None]}, {"$ne": ["$utm_source", ""]}]},
                    "then": "$utm_source",
                    "else": {
                        "$cond": {
                            "if": {"$or": [{"$eq": ["$referrer", None]}, {"$eq": ["$referrer", ""]}, {"$eq": ["$referrer", "direct"]}]},
                            "then": "Direct",
                            "else": "$referrer"
                        }
                    }
                }
            }
        }},
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ]
    
    source_results = await db.sessions.aggregate(source_pipeline).to_list(5)
    
    # Map source names
    source_mapping = {
        "google": "Organic",
        "facebook": "Social",
        "twitter": "Social",
        "linkedin": "Social",
        "instagram": "Social",
        "cpc": "Paid",
        "ppc": "Paid",
        "ads": "Paid",
        "Direct": "Direct"
    }
    
    sessions_by_source = []
    for s in source_results:
        source_name = s["_id"] or "Direct"
        # Categorize the source
        if source_name in source_mapping:
            display_name = source_mapping[source_name]
        elif "google" in source_name.lower():
            display_name = "Organic"
        elif any(social in source_name.lower() for social in ["facebook", "twitter", "linkedin", "instagram"]):
            display_name = "Social"
        elif source_name == "Direct":
            display_name = "Direct"
        else:
            display_name = "Referral"
        
        sessions_by_source.append({
            "name": display_name,
            "count": s["count"]
        })
    
    # Aggregate by category
    source_aggregated = {}
    for item in sessions_by_source:
        if item["name"] in source_aggregated:
            source_aggregated[item["name"]] += item["count"]
        else:
            source_aggregated[item["name"]] = item["count"]
    
    sessions_by_source = [{"name": k, "count": v} for k, v in sorted(source_aggregated.items(), key=lambda x: x[1], reverse=True)]
    
    # Top pages right now
    page_pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff_30min}}},
        {"$group": {"_id": "$page_url", "visitors": {"$sum": 1}}},
        {"$sort": {"visitors": -1}},
        {"$limit": 5}
    ]
    
    top_pages_results = await db.pageviews.aggregate(page_pipeline).to_list(5)
    
    top_pages = []
    for p in top_pages_results:
        # Extract path from URL
        page_url = p["_id"] or "/"
        if page_url.startswith("http"):
            try:
                from urllib.parse import urlparse
                path = urlparse(page_url).path or "/"
            except:
                path = page_url
        else:
            path = page_url
        
        top_pages.append({
            "path": path,
            "visitors": p["visitors"]
        })
    
    return {
        "active_visitors": active_visitors,
        "active_sessions": active_sessions,
        "visitors_timeline": visitors_timeline,
        "sessions_by_source": sessions_by_source if sessions_by_source else [
            {"name": "Direct", "count": 0}
        ],
        "top_pages": top_pages if top_pages else [
            {"path": "/", "visitors": 0}
        ]
    }


@router.get("/heatmap-data")
async def get_heatmap_data(
    page_url: str = Query(..., description="Page path to get heatmap data for"),
    days: int = 30,
    current_user = Depends(get_current_user)
):
    """
    Get click heatmap data for a specific page.
    Returns click zones, click points, CTR, scroll depth, and engagement score.
    """
    require_platform_admin(current_user)
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Match page URL (handle both full URLs and paths)
    page_query = {
        "$or": [
            {"page_url": page_url},
            {"page_url": {"$regex": f"{page_url}$", "$options": "i"}}
        ],
        "timestamp": {"$gte": start_date}
    }
    
    # Get click data
    clicks = await db.click_events.find(page_query).to_list(10000)
    total_clicks = len(clicks)
    
    # Get pageviews for CTR calculation
    pageview_query = {
        "$or": [
            {"page_url": page_url},
            {"page_url": {"$regex": f"{page_url}$", "$options": "i"}}
        ],
        "timestamp": {"$gte": start_date}
    }
    total_pageviews = await db.pageviews.count_documents(pageview_query)
    
    # Calculate CTR
    ctr = str(round((total_clicks / total_pageviews * 100), 1)) if total_pageviews > 0 else "0.0"
    
    # Get average scroll depth
    scroll_pipeline = [
        {"$match": {
            "$or": [
                {"page_url": page_url},
                {"page_url": {"$regex": f"{page_url}$", "$options": "i"}}
            ],
            "timestamp": {"$gte": start_date}
        }},
        {"$group": {"_id": None, "avg_scroll": {"$avg": "$max_scroll_depth"}}}
    ]
    scroll_result = await db.scroll_events.aggregate(scroll_pipeline).to_list(1)
    avg_scroll_depth = int(scroll_result[0]["avg_scroll"]) if scroll_result else 0
    
    # Aggregate clicks by element
    element_counts = {}
    for click in clicks:
        element_id = click.get("element_id") or ""
        element_tag = click.get("element_tag") or "unknown"
        element_text = (click.get("element_text") or "")[:30]
        
        # Create element identifier
        if element_id:
            element_name = f"{element_tag}#{element_id}"
        elif element_text:
            element_name = f"{element_text}"
        else:
            element_name = element_tag.capitalize()
        
        # Categorize elements
        if "btn" in element_name.lower() or "button" in element_name.lower() or element_tag == "button":
            category = "CTA Button"
        elif "nav" in element_name.lower() or "menu" in element_name.lower():
            category = "Navigation Menu"
        elif "footer" in element_name.lower():
            category = "Footer Links"
        elif "card" in element_name.lower() or "price" in element_name.lower() or "pricing" in element_name.lower():
            category = "Pricing Cards"
        elif "feature" in element_name.lower() or "list" in element_name.lower():
            category = "Feature List"
        elif element_tag == "a":
            category = "Links"
        elif element_tag == "input" or element_tag == "select":
            category = "Form Fields"
        else:
            category = element_name
        
        if category not in element_counts:
            element_counts[category] = 0
        element_counts[category] += 1
    
    # Calculate click zones with percentages
    max_clicks = max(element_counts.values()) if element_counts else 1
    click_zones = []
    for element, count in sorted(element_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        percentage = int((count / total_clicks * 100)) if total_clicks > 0 else 0
        intensity = int((count / max_clicks * 100)) if max_clicks > 0 else 0
        click_zones.append({
            "element": element,
            "clicks": count,
            "percentage": percentage,
            "intensity": intensity
        })
    
    # Generate click points for heatmap overlay
    click_points = []
    point_aggregation = {}
    
    for click in clicks:
        if click.get("viewport_width") and click.get("viewport_height"):
            # Normalize to percentage
            x_pct = round(click["x_position"] / click["viewport_width"] * 100, 1)
            y_pct = round(click["y_position"] / click["viewport_height"] * 100, 1)
            
            # Round to create clusters
            x_key = round(x_pct / 5) * 5
            y_key = round(y_pct / 5) * 5
            key = f"{x_key},{y_key}"
            
            if key not in point_aggregation:
                point_aggregation[key] = {"x": x_key, "y": y_key, "count": 0}
            point_aggregation[key]["count"] += 1
    
    # Convert to click points with intensity
    max_point_count = max([p["count"] for p in point_aggregation.values()]) if point_aggregation else 1
    for point in sorted(point_aggregation.values(), key=lambda x: x["count"], reverse=True)[:50]:
        intensity = int((point["count"] / max_point_count * 100))
        click_points.append({
            "x": point["x"],
            "y": point["y"],
            "intensity": intensity
        })
    
    # Calculate engagement score (combination of scroll depth, CTR, and time on page)
    engagement_score = min(100, int(
        (avg_scroll_depth * 0.4) + 
        (float(ctr) * 5) +  # CTR weighted
        (min(total_clicks / 100, 30))  # Click activity
    ))
    
    return {
        "page_url": page_url,
        "total_clicks": total_clicks,
        "ctr": ctr,
        "avg_scroll_depth": avg_scroll_depth,
        "engagement_score": engagement_score,
        "click_zones": click_zones if click_zones else [
            {"element": "No data", "clicks": 0, "percentage": 0, "intensity": 0}
        ],
        "click_points": click_points
    }
