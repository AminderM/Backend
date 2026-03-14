from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from models import *
from auth import get_current_user, require_platform_admin
from database import db
from datetime import datetime, timezone
import csv
import io
from typing import Optional
import uuid

router = APIRouter(prefix="/admin/crm", tags=["CRM"])

# Helper function to log CRM activities
async def log_crm_activity(user, action: str, entity_type: str, entity_id: str, entity_name: str, details: dict = None):
    try:
        activity_log = {
            "id": str(uuid.uuid4()),
            "user_id": user.id,
            "user_name": user.full_name if hasattr(user, 'full_name') else user.email,
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

@router.get('/contacts')
async def get_crm_contacts(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    contacts = await db.crm_contacts.find({}, {"_id": 0}).to_list(length=None)
    return contacts

@router.post('/contacts')
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

@router.put('/contacts/{contact_id}')
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

@router.delete('/contacts/{contact_id}')
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

@router.post('/contacts/upload')
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

@router.get('/activity-logs')
async def get_crm_activity_logs(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    # Get activity logs sorted by most recent first
    logs = await db.crm_activity_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(length=200)
    return logs

@router.get('/deals')
async def get_crm_deals(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    deals = await db.crm_deals.find({}, {"_id": 0}).to_list(length=None)
    return deals

@router.post('/deals')
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

@router.put('/deals/{deal_id}')
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

@router.delete('/deals/{deal_id}')
async def delete_crm_deal(deal_id: str, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    await db.crm_deals.delete_one({"id": deal_id})
    return {"message": "Deal deleted"}

@router.get('/activities')
async def get_crm_activities(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    activities = await db.crm_activities.find({}, {"_id": 0}).to_list(length=None)
    return activities

@router.post('/activities')
async def create_crm_activity(activity: CRMActivity, current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    activity.owner_id = current_user.id
    activity_dict = activity.dict()
    activity_dict['created_at'] = activity_dict['created_at'].isoformat()
    if activity_dict.get('due_date'):
        activity_dict['due_date'] = activity_dict['due_date'].isoformat()
    await db.crm_activities.insert_one(activity_dict)
    return activity

@router.get('/dashboard')
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
@router.get('/companies')
async def get_crm_companies(current_user: User = Depends(get_current_user)):
    require_platform_admin(current_user)
    companies = await db.crm_companies.find({}, {"_id": 0}).to_list(length=None)
    return companies

@router.post('/companies')
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

@router.put('/companies/{company_id}')
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

@router.delete('/companies/{company_id}')
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

@router.post('/companies/upload')
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

