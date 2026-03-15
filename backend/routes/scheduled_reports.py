"""
Scheduled Reports Service
Handles scheduling, managing, and executing automated analytics report emails.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, validator
from fastapi import APIRouter, Depends, HTTPException, Query
from database import db
from auth import get_current_user, require_platform_admin
import uuid
import logging
import io
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard/reports", tags=["Scheduled Reports"])

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


# ============================================================================
# MODELS
# ============================================================================

class ScheduleCreate(BaseModel):
    """Create a new scheduled report"""
    frequency: str = Field(..., description="daily, weekly, monthly")
    email: EmailStr = Field(..., description="Email to send report to")
    report_type: str = Field(default="full", description="full, summary, kpi_only")
    day_of_week: Optional[int] = Field(default=1, ge=0, le=6, description="0=Mon, 6=Sun (for weekly)")
    day_of_month: Optional[int] = Field(default=1, ge=1, le=28, description="Day of month (for monthly)")
    time: str = Field(default="09:00", description="Time in HH:MM format")
    timezone: str = Field(default="UTC", description="Timezone for scheduling")
    include_csv: bool = Field(default=False, description="Attach CSV data files")
    report_days: int = Field(default=7, ge=1, le=90, description="Days of data to include")
    
    @validator('frequency')
    def validate_frequency(cls, v):
        if v not in ['daily', 'weekly', 'monthly']:
            raise ValueError('Frequency must be daily, weekly, or monthly')
        return v
    
    @validator('report_type')
    def validate_report_type(cls, v):
        if v not in ['full', 'summary', 'kpi_only']:
            raise ValueError('Report type must be full, summary, or kpi_only')
        return v
    
    @validator('time')
    def validate_time(cls, v):
        try:
            datetime.strptime(v, '%H:%M')
        except ValueError:
            raise ValueError('Time must be in HH:MM format')
        return v


class ScheduleResponse(BaseModel):
    """Response model for scheduled reports"""
    id: str
    frequency: str
    email: str
    report_type: str
    day_of_week: Optional[int]
    day_of_month: Optional[int]
    time: str
    timezone: str
    include_csv: bool
    report_days: int
    is_active: bool
    created_at: str
    created_by: str
    last_sent: Optional[str]
    next_run: Optional[str]


# ============================================================================
# SCHEDULER FUNCTIONS
# ============================================================================

def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler instance"""
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
        scheduler.start()
        logger.info("APScheduler started")
    return scheduler


def get_cron_trigger(schedule: dict) -> CronTrigger:
    """Create a cron trigger from schedule config"""
    hour, minute = schedule['time'].split(':')
    
    if schedule['frequency'] == 'daily':
        return CronTrigger(hour=int(hour), minute=int(minute), timezone=schedule.get('timezone', 'UTC'))
    elif schedule['frequency'] == 'weekly':
        # day_of_week: 0=Monday, 6=Sunday (APScheduler uses same convention)
        return CronTrigger(
            day_of_week=schedule.get('day_of_week', 0),
            hour=int(hour), 
            minute=int(minute),
            timezone=schedule.get('timezone', 'UTC')
        )
    elif schedule['frequency'] == 'monthly':
        return CronTrigger(
            day=schedule.get('day_of_month', 1),
            hour=int(hour), 
            minute=int(minute),
            timezone=schedule.get('timezone', 'UTC')
        )
    else:
        raise ValueError(f"Unknown frequency: {schedule['frequency']}")


async def send_scheduled_report(schedule_id: str):
    """
    Execute a scheduled report - generates PDF and sends email.
    Called by APScheduler at the configured times.
    """
    from email_service import EmailService
    
    logger.info(f"Executing scheduled report: {schedule_id}")
    
    try:
        # Get schedule from database
        schedule = await db.report_schedules.find_one({"id": schedule_id})
        if not schedule or not schedule.get('is_active'):
            logger.warning(f"Schedule {schedule_id} not found or inactive")
            return
        
        # Generate report data
        report_data = await generate_report_data(schedule['report_days'], schedule['report_type'])
        
        # Generate PDF
        pdf_buffer = await generate_pdf_report(report_data, schedule['report_days'])
        
        # Prepare attachments
        attachments = []
        
        # Add PDF
        pdf_buffer.seek(0)
        attachments.append({
            'filename': f"analytics_report_{datetime.now().strftime('%Y%m%d')}.pdf",
            'content': pdf_buffer.read(),
            'content_type': 'application/pdf'
        })
        
        # Add CSV files if requested
        if schedule.get('include_csv'):
            for data_type in ['sessions', 'pageviews', 'conversions']:
                csv_data = await generate_csv_data(data_type, schedule['report_days'])
                if csv_data:
                    attachments.append({
                        'filename': f"analytics_{data_type}_{schedule['report_days']}days.csv",
                        'content': csv_data.encode('utf-8'),
                        'content_type': 'text/csv'
                    })
        
        # Send email
        email_service = EmailService()
        
        if email_service.enabled:
            await email_service.send_email(
                subject=f"Analytics Report - {schedule['frequency'].title()} ({schedule['report_days']} days)",
                recipients=[schedule['email']],
                body=generate_email_body(report_data, schedule),
                attachments=attachments
            )
            logger.info(f"Report email sent to {schedule['email']}")
        else:
            logger.warning("Email not configured - report generated but not sent")
        
        # Update last_sent
        await db.report_schedules.update_one(
            {"id": schedule_id},
            {"$set": {"last_sent": datetime.now(timezone.utc).isoformat()}}
        )
        
    except Exception as e:
        logger.error(f"Error sending scheduled report {schedule_id}: {e}")
        # Record error
        await db.report_schedules.update_one(
            {"id": schedule_id},
            {"$set": {"last_error": str(e), "last_error_at": datetime.now(timezone.utc).isoformat()}}
        )


async def generate_report_data(days: int, report_type: str) -> dict:
    """Generate report data from database"""
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=days)).isoformat()
    
    # KPI Metrics (always included)
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
    
    data = {
        "period_days": days,
        "generated_at": now.isoformat(),
        "kpi": {
            "total_visitors": total_visitors,
            "total_sessions": total_sessions,
            "total_pageviews": total_pageviews,
            "total_conversions": total_conversions,
            "conversion_rate": round(conversion_rate, 2),
            "bounce_rate": round(bounce_rate, 1),
            "avg_session_duration": avg_duration
        }
    }
    
    if report_type == 'kpi_only':
        return data
    
    # Top Pages
    page_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {"_id": "$page_url", "views": {"$sum": 1}}},
        {"$sort": {"views": -1}},
        {"$limit": 10}
    ]
    top_pages = await db.pageviews.aggregate(page_pipeline).to_list(10)
    data["top_pages"] = [{"url": p["_id"], "views": p["views"]} for p in top_pages]
    
    # Traffic Sources
    source_pipeline = [
        {"$match": {"started_at": {"$gte": start_date}}},
        {"$group": {"_id": {"$ifNull": ["$utm_source", "Direct"]}, "sessions": {"$sum": 1}}},
        {"$sort": {"sessions": -1}},
        {"$limit": 10}
    ]
    sources = await db.sessions.aggregate(source_pipeline).to_list(10)
    data["traffic_sources"] = [{"source": s["_id"], "sessions": s["sessions"]} for s in sources]
    
    if report_type == 'summary':
        return data
    
    # Full report includes daily breakdown
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
    
    data["daily_breakdown"] = daily_data
    
    # Conversion breakdown
    conv_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": "$event_category",
            "count": {"$sum": 1},
            "value": {"$sum": {"$ifNull": ["$event_value", 0]}}
        }},
        {"$sort": {"count": -1}}
    ]
    conversions = await db.conversion_events.aggregate(conv_pipeline).to_list(10)
    data["conversion_breakdown"] = [
        {"category": c["_id"] or "Other", "count": c["count"], "value": c["value"]}
        for c in conversions
    ]
    
    return data


async def generate_pdf_report(data: dict, days: int) -> io.BytesIO:
    """Generate PDF report from data"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.enums import TA_CENTER
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=24, 
                                  spaceAfter=30, alignment=TA_CENTER, textColor=colors.HexColor('#1a1a2e'))
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=14,
                                    spaceBefore=20, spaceAfter=10, textColor=colors.HexColor('#16213e'))
    
    elements = []
    
    # Title
    elements.append(Paragraph("Analytics Report", title_style))
    elements.append(Paragraph(f"Period: Last {days} days | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # KPIs
    elements.append(Paragraph("Key Performance Indicators", section_style))
    kpi = data['kpi']
    kpi_data = [
        ["Metric", "Value"],
        ["Total Visitors", f"{kpi['total_visitors']:,}"],
        ["Total Sessions", f"{kpi['total_sessions']:,}"],
        ["Total Page Views", f"{kpi['total_pageviews']:,}"],
        ["Total Conversions", f"{kpi['total_conversions']:,}"],
        ["Conversion Rate", f"{kpi['conversion_rate']:.2f}%"],
        ["Bounce Rate", f"{kpi['bounce_rate']:.1f}%"],
        ["Avg. Session Duration", f"{kpi['avg_session_duration'] // 60}m {kpi['avg_session_duration'] % 60}s"],
    ]
    
    kpi_table = Table(kpi_data, colWidths=[3*inch, 2*inch])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
    ]))
    elements.append(kpi_table)
    
    # Top Pages
    if 'top_pages' in data and data['top_pages']:
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("Top Pages", section_style))
        pages_data = [["Page URL", "Views"]]
        for p in data['top_pages'][:10]:
            url = p['url'][:50] + '...' if len(p['url']) > 50 else p['url']
            pages_data.append([url, str(p['views'])])
        
        pages_table = Table(pages_data, colWidths=[4*inch, 1*inch])
        pages_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ]))
        elements.append(pages_table)
    
    # Traffic Sources
    if 'traffic_sources' in data and data['traffic_sources']:
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("Traffic Sources", section_style))
        sources_data = [["Source", "Sessions"]]
        for s in data['traffic_sources'][:10]:
            sources_data.append([s['source'], str(s['sessions'])])
        
        sources_table = Table(sources_data, colWidths=[3*inch, 1.5*inch])
        sources_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ]))
        elements.append(sources_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer


async def generate_csv_data(data_type: str, days: int) -> str:
    """Generate CSV string for a data type"""
    import csv
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    configs = {
        "sessions": {
            "collection": db.sessions,
            "fields": ["session_id", "visitor_id", "started_at", "landing_page", "utm_source", "page_views", "duration_seconds"],
            "date_field": "started_at"
        },
        "pageviews": {
            "collection": db.pageviews,
            "fields": ["visitor_id", "session_id", "page_url", "page_title", "timestamp"],
            "date_field": "timestamp"
        },
        "conversions": {
            "collection": db.conversion_events,
            "fields": ["session_id", "event_name", "event_category", "event_value", "timestamp"],
            "date_field": "timestamp"
        }
    }
    
    if data_type not in configs:
        return ""
    
    config = configs[data_type]
    cursor = config["collection"].find(
        {config["date_field"]: {"$gte": start_date}},
        {"_id": 0}
    )
    data = await cursor.to_list(length=10000)
    
    if not data:
        return ""
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=config["fields"], extrasaction='ignore')
    writer.writeheader()
    for row in data:
        writer.writerow({f: row.get(f, "") for f in config["fields"]})
    
    return output.getvalue()


def generate_email_body(data: dict, schedule: dict) -> str:
    """Generate HTML email body"""
    kpi = data['kpi']
    
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h1 style="color: #1a1a2e;">Analytics Report</h1>
        <p style="color: #666;">
            {schedule['frequency'].title()} report for the last {schedule['report_days']} days
        </p>
        
        <h2 style="color: #16213e;">Key Metrics</h2>
        <table style="width: 100%; border-collapse: collapse;">
            <tr style="background: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Visitors</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{kpi['total_visitors']:,}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Sessions</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{kpi['total_sessions']:,}</td>
            </tr>
            <tr style="background: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Page Views</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{kpi['total_pageviews']:,}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Conversions</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{kpi['total_conversions']:,}</td>
            </tr>
            <tr style="background: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Conversion Rate</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{kpi['conversion_rate']:.2f}%</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Bounce Rate</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{kpi['bounce_rate']:.1f}%</td>
            </tr>
        </table>
        
        <p style="color: #666; margin-top: 20px;">
            Full report attached as PDF.
            {'CSV data files also attached.' if schedule.get('include_csv') else ''}
        </p>
        
        <hr style="border: none; border-top: 1px solid #dee2e6; margin: 20px 0;">
        <p style="color: #999; font-size: 12px;">
            This is an automated report. To modify or unsubscribe, visit your dashboard settings.
        </p>
    </body>
    </html>
    """


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/schedule")
async def create_schedule(
    schedule: ScheduleCreate,
    current_user = Depends(get_current_user)
):
    """
    Create a new scheduled report.
    
    Frequencies:
    - daily: Runs every day at specified time
    - weekly: Runs on specified day_of_week (0=Mon, 6=Sun) at specified time
    - monthly: Runs on specified day_of_month at specified time
    
    Report types:
    - full: All data including daily breakdown
    - summary: KPIs, top pages, and traffic sources
    - kpi_only: Just the key metrics
    """
    require_platform_admin(current_user)
    
    schedule_id = str(uuid.uuid4())
    
    schedule_doc = {
        "id": schedule_id,
        "frequency": schedule.frequency,
        "email": schedule.email,
        "report_type": schedule.report_type,
        "day_of_week": schedule.day_of_week,
        "day_of_month": schedule.day_of_month,
        "time": schedule.time,
        "timezone": schedule.timezone,
        "include_csv": schedule.include_csv,
        "report_days": schedule.report_days,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.email,
        "last_sent": None,
        "last_error": None
    }
    
    await db.report_schedules.insert_one(schedule_doc)
    
    # Add job to scheduler
    sched = get_scheduler()
    trigger = get_cron_trigger(schedule_doc)
    
    sched.add_job(
        send_scheduled_report,
        trigger=trigger,
        args=[schedule_id],
        id=schedule_id,
        name=f"report_{schedule.frequency}_{schedule.email}",
        replace_existing=True
    )
    
    # Get next run time
    next_run = sched.get_job(schedule_id)
    next_run_time = next_run.next_run_time.isoformat() if next_run and next_run.next_run_time else None
    
    return {
        "message": "Schedule created successfully",
        "schedule": {
            "id": schedule_id,
            "frequency": schedule.frequency,
            "email": schedule.email,
            "report_type": schedule.report_type,
            "time": schedule.time,
            "next_run": next_run_time
        }
    }


@router.get("/schedules")
async def list_schedules(current_user = Depends(get_current_user)):
    """List all scheduled reports"""
    require_platform_admin(current_user)
    
    schedules = await db.report_schedules.find({}, {"_id": 0}).to_list(100)
    
    # Add next_run times from scheduler
    sched = get_scheduler()
    for schedule in schedules:
        job = sched.get_job(schedule['id'])
        schedule['next_run'] = job.next_run_time.isoformat() if job and job.next_run_time else None
    
    return {"schedules": schedules, "count": len(schedules)}


@router.get("/schedule/{schedule_id}")
async def get_schedule(schedule_id: str, current_user = Depends(get_current_user)):
    """Get a specific scheduled report"""
    require_platform_admin(current_user)
    
    schedule = await db.report_schedules.find_one({"id": schedule_id}, {"_id": 0})
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Add next_run time
    sched = get_scheduler()
    job = sched.get_job(schedule_id)
    schedule['next_run'] = job.next_run_time.isoformat() if job and job.next_run_time else None
    
    return schedule


@router.put("/schedule/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    schedule: ScheduleCreate,
    current_user = Depends(get_current_user)
):
    """Update a scheduled report"""
    require_platform_admin(current_user)
    
    existing = await db.report_schedules.find_one({"id": schedule_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    update_data = {
        "frequency": schedule.frequency,
        "email": schedule.email,
        "report_type": schedule.report_type,
        "day_of_week": schedule.day_of_week,
        "day_of_month": schedule.day_of_month,
        "time": schedule.time,
        "timezone": schedule.timezone,
        "include_csv": schedule.include_csv,
        "report_days": schedule.report_days,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user.email
    }
    
    await db.report_schedules.update_one({"id": schedule_id}, {"$set": update_data})
    
    # Update scheduler job
    sched = get_scheduler()
    sched.remove_job(schedule_id, jobstore=None)
    
    trigger = get_cron_trigger({**existing, **update_data})
    sched.add_job(
        send_scheduled_report,
        trigger=trigger,
        args=[schedule_id],
        id=schedule_id,
        replace_existing=True
    )
    
    return {"message": "Schedule updated successfully"}


@router.delete("/schedule/{schedule_id}")
async def delete_schedule(schedule_id: str, current_user = Depends(get_current_user)):
    """Delete a scheduled report"""
    require_platform_admin(current_user)
    
    result = await db.report_schedules.delete_one({"id": schedule_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Remove from scheduler
    sched = get_scheduler()
    try:
        sched.remove_job(schedule_id)
    except:
        pass
    
    return {"message": "Schedule deleted successfully"}


@router.post("/schedule/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str, current_user = Depends(get_current_user)):
    """Toggle a schedule on/off"""
    require_platform_admin(current_user)
    
    schedule = await db.report_schedules.find_one({"id": schedule_id})
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    new_status = not schedule.get('is_active', True)
    
    await db.report_schedules.update_one(
        {"id": schedule_id},
        {"$set": {"is_active": new_status}}
    )
    
    sched = get_scheduler()
    if new_status:
        # Re-add job
        trigger = get_cron_trigger(schedule)
        sched.add_job(
            send_scheduled_report,
            trigger=trigger,
            args=[schedule_id],
            id=schedule_id,
            replace_existing=True
        )
    else:
        # Remove job
        try:
            sched.remove_job(schedule_id)
        except:
            pass
    
    return {"message": f"Schedule {'activated' if new_status else 'deactivated'}", "is_active": new_status}


@router.post("/schedule/{schedule_id}/send-now")
async def send_report_now(schedule_id: str, current_user = Depends(get_current_user)):
    """Manually trigger a scheduled report to send immediately"""
    require_platform_admin(current_user)
    
    schedule = await db.report_schedules.find_one({"id": schedule_id})
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Execute immediately in background
    import asyncio
    asyncio.create_task(send_scheduled_report(schedule_id))
    
    return {"message": "Report generation started. Email will be sent shortly."}


# ============================================================================
# INITIALIZATION
# ============================================================================

async def init_scheduler():
    """Initialize scheduler and load existing schedules from database"""
    sched = get_scheduler()
    
    # Load all active schedules from database
    schedules = await db.report_schedules.find({"is_active": True}).to_list(100)
    
    for schedule in schedules:
        try:
            trigger = get_cron_trigger(schedule)
            sched.add_job(
                send_scheduled_report,
                trigger=trigger,
                args=[schedule['id']],
                id=schedule['id'],
                replace_existing=True
            )
            logger.info(f"Loaded schedule: {schedule['id']} ({schedule['frequency']})")
        except Exception as e:
            logger.error(f"Error loading schedule {schedule['id']}: {e}")
    
    logger.info(f"Scheduler initialized with {len(schedules)} schedules")
