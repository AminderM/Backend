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



# ============================================================================
# EXPORT ENDPOINTS - CSV & PDF
# ============================================================================

from fastapi.responses import StreamingResponse
import csv
import io


@router.get("/export/csv")
async def export_csv(
    data_type: str = Query(..., description="Type of data: sessions, pageviews, conversions, clicks"),
    days: int = Query(default=30, ge=1, le=365),
    current_user = Depends(get_current_user)
):
    """
    Export analytics data as CSV file.
    
    Supported data types:
    - sessions: Session data with visitor info, duration, bounce rate
    - pageviews: Page view events with URLs and timestamps
    - conversions: Conversion events with categories and values
    - clicks: Click events for heatmap data
    """
    require_platform_admin(current_user)
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Define collection and fields for each data type
    data_configs = {
        "sessions": {
            "collection": db.sessions,
            "fields": ["session_id", "visitor_id", "started_at", "ended_at", "landing_page", 
                      "referrer", "utm_source", "utm_medium", "utm_campaign", "page_views", 
                      "duration_seconds", "is_active", "conversions"],
            "date_field": "started_at",
            "filename": f"analytics_sessions_{days}days.csv"
        },
        "pageviews": {
            "collection": db.pageviews,
            "fields": ["visitor_id", "session_id", "page_url", "page_title", "referrer",
                      "utm_source", "utm_campaign", "timestamp"],
            "date_field": "timestamp",
            "filename": f"analytics_pageviews_{days}days.csv"
        },
        "conversions": {
            "collection": db.conversion_events,
            "fields": ["visitor_id", "session_id", "event_name", "event_category", 
                      "event_value", "page_url", "timestamp"],
            "date_field": "timestamp",
            "filename": f"analytics_conversions_{days}days.csv"
        },
        "clicks": {
            "collection": db.click_events,
            "fields": ["visitor_id", "session_id", "page_url", "element_id", "element_tag",
                      "element_text", "x_position", "y_position", "viewport_width", 
                      "viewport_height", "timestamp"],
            "date_field": "timestamp",
            "filename": f"analytics_clicks_{days}days.csv"
        }
    }
    
    if data_type not in data_configs:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid data_type. Choose from: {list(data_configs.keys())}"
        )
    
    config = data_configs[data_type]
    
    # Query data
    query = {config["date_field"]: {"$gte": start_date}}
    cursor = config["collection"].find(query, {"_id": 0})
    data = await cursor.to_list(length=50000)  # Limit to 50k rows
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=config["fields"], extrasaction='ignore')
    writer.writeheader()
    
    for row in data:
        # Clean row data
        clean_row = {}
        for field in config["fields"]:
            value = row.get(field, "")
            if isinstance(value, list):
                value = "; ".join(str(v) for v in value)
            clean_row[field] = value
        writer.writerow(clean_row)
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={config['filename']}",
            "Content-Type": "text/csv; charset=utf-8"
        }
    )


@router.get("/export/pdf")
async def export_pdf(
    days: int = Query(default=30, ge=1, le=365),
    current_user = Depends(get_current_user)
):
    """
    Export analytics summary report as PDF.
    
    Includes:
    - KPI summary (visitors, conversions, bounce rate, session duration)
    - Daily traffic table
    - Top pages
    - Traffic sources
    - Conversion breakdown
    """
    require_platform_admin(current_user)
    
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=days)).isoformat()
    
    # Gather all data
    # 1. KPI Metrics
    total_visitors = len(await db.sessions.distinct("visitor_id", {
        "started_at": {"$gte": start_date}
    }))
    
    total_sessions = await db.sessions.count_documents({
        "started_at": {"$gte": start_date}
    })
    
    total_conversions = await db.conversion_events.count_documents({
        "timestamp": {"$gte": start_date}
    })
    
    total_pageviews = await db.pageviews.count_documents({
        "timestamp": {"$gte": start_date}
    })
    
    single_page_sessions = await db.sessions.count_documents({
        "started_at": {"$gte": start_date},
        "page_views": 1
    })
    bounce_rate = (single_page_sessions / total_sessions * 100) if total_sessions > 0 else 0
    
    duration_pipeline = [
        {"$match": {"started_at": {"$gte": start_date}, "duration_seconds": {"$gt": 0}}},
        {"$group": {"_id": None, "avg_duration": {"$avg": "$duration_seconds"}}}
    ]
    duration_result = await db.sessions.aggregate(duration_pipeline).to_list(1)
    avg_duration = int(duration_result[0]["avg_duration"]) if duration_result else 0
    
    conversion_rate = (total_conversions / total_sessions * 100) if total_sessions > 0 else 0
    
    # 2. Daily Traffic (last 7 days for PDF)
    daily_data = []
    for i in range(min(days, 14) - 1, -1, -1):
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
        
        daily_data.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "visitors": day_visitors,
            "pageviews": day_pageviews,
            "conversions": day_conversions
        })
    
    # 3. Top Pages
    page_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {"_id": "$page_url", "views": {"$sum": 1}}},
        {"$sort": {"views": -1}},
        {"$limit": 10}
    ]
    top_pages = await db.pageviews.aggregate(page_pipeline).to_list(10)
    
    # 4. Traffic Sources
    source_pipeline = [
        {"$match": {"started_at": {"$gte": start_date}}},
        {"$group": {
            "_id": {"$ifNull": ["$utm_source", "Direct"]},
            "sessions": {"$sum": 1}
        }},
        {"$sort": {"sessions": -1}},
        {"$limit": 10}
    ]
    traffic_sources = await db.sessions.aggregate(source_pipeline).to_list(10)
    
    # 5. Conversion Breakdown
    conv_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": "$event_category",
            "count": {"$sum": 1},
            "value": {"$sum": {"$ifNull": ["$event_value", 0]}}
        }},
        {"$sort": {"count": -1}}
    ]
    conversion_breakdown = await db.conversion_events.aggregate(conv_pipeline).to_list(10)
    
    # Generate PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a2e')
    )
    
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.HexColor('#16213e')
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6
    )
    
    elements = []
    
    # Title
    elements.append(Paragraph("Web Analytics Report", title_style))
    elements.append(Paragraph(
        f"Period: {(now - timedelta(days=days)).strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')} ({days} days)",
        normal_style
    ))
    elements.append(Paragraph(f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}", normal_style))
    elements.append(Spacer(1, 20))
    
    # KPI Summary
    elements.append(Paragraph("Key Performance Indicators", section_style))
    
    kpi_data = [
        ["Metric", "Value"],
        ["Total Visitors", f"{total_visitors:,}"],
        ["Total Sessions", f"{total_sessions:,}"],
        ["Total Page Views", f"{total_pageviews:,}"],
        ["Total Conversions", f"{total_conversions:,}"],
        ["Conversion Rate", f"{conversion_rate:.2f}%"],
        ["Bounce Rate", f"{bounce_rate:.1f}%"],
        ["Avg. Session Duration", f"{avg_duration // 60}m {avg_duration % 60}s"],
        ["Pages per Session", f"{(total_pageviews / total_sessions):.2f}" if total_sessions > 0 else "0"]
    ]
    
    kpi_table = Table(kpi_data, colWidths=[3*inch, 2*inch])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 20))
    
    # Daily Traffic Table
    if daily_data:
        elements.append(Paragraph("Daily Traffic", section_style))
        
        traffic_table_data = [["Date", "Visitors", "Page Views", "Conversions"]]
        for day in daily_data:
            traffic_table_data.append([
                day["date"],
                str(day["visitors"]),
                str(day["pageviews"]),
                str(day["conversions"])
            ])
        
        traffic_table = Table(traffic_table_data, colWidths=[1.5*inch, 1.2*inch, 1.2*inch, 1.2*inch])
        traffic_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(traffic_table)
        elements.append(Spacer(1, 20))
    
    # Top Pages
    if top_pages:
        elements.append(Paragraph("Top Pages", section_style))
        
        pages_table_data = [["Page URL", "Views"]]
        for page in top_pages:
            page_url = page["_id"] or "/"
            if len(page_url) > 50:
                page_url = page_url[:47] + "..."
            pages_table_data.append([page_url, str(page["views"])])
        
        pages_table = Table(pages_table_data, colWidths=[4*inch, 1*inch])
        pages_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(pages_table)
        elements.append(Spacer(1, 20))
    
    # Traffic Sources
    if traffic_sources:
        elements.append(Paragraph("Traffic Sources", section_style))
        
        sources_table_data = [["Source", "Sessions"]]
        for source in traffic_sources:
            sources_table_data.append([source["_id"] or "Direct", str(source["sessions"])])
        
        sources_table = Table(sources_table_data, colWidths=[3*inch, 1.5*inch])
        sources_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(sources_table)
        elements.append(Spacer(1, 20))
    
    # Conversion Breakdown
    if conversion_breakdown:
        elements.append(Paragraph("Conversion Breakdown", section_style))
        
        conv_table_data = [["Category", "Count", "Value"]]
        for conv in conversion_breakdown:
            conv_table_data.append([
                conv["_id"] or "Other",
                str(conv["count"]),
                f"${conv['value']:.2f}" if conv["value"] else "-"
            ])
        
        conv_table = Table(conv_table_data, colWidths=[2.5*inch, 1*inch, 1.5*inch])
        conv_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(conv_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"analytics_report_{now.strftime('%Y%m%d')}_{days}days.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "application/pdf"
        }
    )
