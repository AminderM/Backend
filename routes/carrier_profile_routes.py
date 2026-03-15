"""
Carrier Profile Routes - TMS Backend
5-step wizard for carrier profile completion
"""

from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Query
from typing import Optional
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet
import base64
import json
import os
import tempfile
import shutil

from models import User
from models_carrier_profile import (
    CarrierProfile,
    CarrierProfileResponse,
    CompanyInfoUpdate,
    CompanyInfo,
    ComplianceDocumentsUpdate,
    ComplianceDocuments,
    RegulatoryNumbersUpdate,
    RegulatoryNumbers,
    FleetConfigurationUpdate,
    FleetConfiguration,
    PaymentBankingUpdate,
    PaymentBanking,
    CompletionStatus,
    ValidationResult,
    ValidationError,
    DocumentStatus,
    ProfileStatus,
    InsuranceDocument,
    ClearanceDocument,
)
from auth import get_current_user
from database import db

router = APIRouter(prefix="/carrier-profiles", tags=["Carrier Profiles"])

# =============================================================================
# ENCRYPTION SETUP
# =============================================================================

# Load encryption key for banking info - MUST be set in environment for data persistence
ENCRYPTION_KEY = os.environ.get('CARRIER_ENCRYPTION_KEY')
if not ENCRYPTION_KEY:
    # Generate a key and log warning - in production this should be pre-configured
    import logging
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    logging.warning(
        "CARRIER_ENCRYPTION_KEY not set in environment. Generated temporary key. "
        "Set CARRIER_ENCRYPTION_KEY in .env to persist encrypted banking data across restarts."
    )
    
fernet = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)


def encrypt_data(data: dict) -> str:
    """Encrypt sensitive data"""
    json_data = json.dumps(data)
    encrypted = fernet.encrypt(json_data.encode())
    return encrypted.decode()


def decrypt_data(encrypted_data: str) -> dict:
    """Decrypt sensitive data"""
    try:
        decrypted = fernet.decrypt(encrypted_data.encode())
        return json.loads(decrypted.decode())
    except Exception:
        return {}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_document_status(expiry_date_str: Optional[str]) -> DocumentStatus:
    """Calculate document status based on expiry date"""
    if not expiry_date_str:
        return DocumentStatus.MISSING
    
    try:
        expiry_date = datetime.fromisoformat(expiry_date_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        days_until_expiry = (expiry_date - now).days
        
        if days_until_expiry < 0:
            return DocumentStatus.EXPIRED
        elif days_until_expiry <= 60:
            return DocumentStatus.EXPIRING_SOON
        else:
            return DocumentStatus.VALID
    except:
        return DocumentStatus.MISSING


def calculate_completion_status(profile: dict) -> CompletionStatus:
    """Calculate which sections are complete"""
    status = CompletionStatus()
    
    # Company Info - complete if name and address are set
    company_info = profile.get('company_info')
    if company_info:
        status.company_info = bool(
            company_info.get('company_name') and 
            company_info.get('address')
        )
    
    # Compliance Documents - complete if at least cargo and liability insurance are set
    compliance = profile.get('compliance_documents')
    if compliance:
        country = compliance.get('operating_country', 'CA')
        if country in ['CA', 'BOTH']:
            can_docs = compliance.get('canadian_documents', {})
            cargo = can_docs.get('cargo_insurance', {}) if can_docs else {}
            liability = can_docs.get('liability_insurance', {}) if can_docs else {}
            status.compliance_documents = bool(
                cargo.get('policy_number') and liability.get('policy_number')
            )
        elif country == 'US':
            us_docs = compliance.get('us_documents', {})
            cargo = us_docs.get('cargo_insurance', {}) if us_docs else {}
            liability = us_docs.get('liability_insurance', {}) if us_docs else {}
            status.compliance_documents = bool(
                cargo.get('policy_number') and liability.get('policy_number')
            )
    
    # Regulatory Numbers - complete if primary numbers are set
    regulatory = profile.get('regulatory_numbers')
    if regulatory:
        regions = regulatory.get('operating_regions', [])
        complete = False
        if 'CA' in regions:
            can = regulatory.get('canadian', {})
            complete = bool(can.get('nsc_number') if can else False)
        if 'US' in regions:
            us = regulatory.get('us', {})
            complete = complete or bool(us.get('usdot_number') if us else False)
        status.regulatory_numbers = complete
    
    # Fleet Configuration - complete if fleet size is set
    fleet = profile.get('fleet_configuration')
    if fleet:
        fleet_size = fleet.get('fleet_size', {})
        status.fleet_configuration = bool(
            fleet_size.get('power_units', 0) > 0 or 
            fleet_size.get('drivers', 0) > 0
        )
    
    # Payment Banking - complete if banking info is set
    payment = profile.get('payment_banking')
    if payment:
        banking = payment.get('banking_info', {})
        status.payment_banking = bool(
            banking.get('bank_name') and banking.get('account_number')
        ) if banking else bool(payment.get('encrypted_banking_info'))
    
    return status


def calculate_completion_percentage(status: CompletionStatus) -> int:
    """Calculate overall completion percentage"""
    sections = [
        status.company_info,
        status.compliance_documents,
        status.regulatory_numbers,
        status.fleet_configuration,
        status.payment_banking
    ]
    completed = sum(1 for s in sections if s)
    return int((completed / len(sections)) * 100)


# =============================================================================
# ROUTES
# =============================================================================

@router.get("", response_model=dict)
async def get_carrier_profile(current_user: User = Depends(get_current_user)):
    """Get the current user's carrier profile or create a new one"""
    
    # Find existing profile
    profile = await db.carrier_profiles.find_one(
        {"user_id": current_user.id},
        {"_id": 0}
    )
    
    if not profile:
        # Create new profile
        new_profile = CarrierProfile(
            user_id=current_user.id,
            company_id=getattr(current_user, 'company_id', None) or getattr(current_user, 'tenant_id', None),
            created_by=current_user.id
        )
        profile = new_profile.dict()
        profile['created_at'] = profile['created_at'].isoformat()
        profile['updated_at'] = profile['updated_at'].isoformat()
        
        await db.carrier_profiles.insert_one(profile)
    
    # Recalculate completion status
    completion_status = calculate_completion_status(profile)
    profile['completion_status'] = completion_status.dict()
    profile['overall_completion_percentage'] = calculate_completion_percentage(completion_status)
    
    # Remove encrypted banking info from response
    if profile.get('payment_banking'):
        profile['payment_banking'].pop('encrypted_banking_info', None)
    
    return profile


@router.put("/company-info", response_model=dict)
async def update_company_info(
    data: CompanyInfoUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update company info (Step 1)"""
    
    # Get or create profile
    profile = await db.carrier_profiles.find_one({"user_id": current_user.id})
    if not profile:
        await get_carrier_profile(current_user)
        profile = await db.carrier_profiles.find_one({"user_id": current_user.id})
    
    # Build company info
    company_info = CompanyInfo(**data.dict())
    company_info_dict = company_info.dict()
    company_info_dict['updated_at'] = company_info_dict['updated_at'].isoformat()
    
    # Convert address to dict if present
    if company_info_dict.get('address'):
        company_info_dict['address'] = dict(company_info_dict['address'])
    if company_info_dict.get('mailing_address'):
        company_info_dict['mailing_address'] = dict(company_info_dict['mailing_address'])
    
    # Update profile
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                "company_info": company_info_dict,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": current_user.id
            }
        }
    )
    
    # Sync with Company collection if company_id exists
    company_id = profile.get('company_id')
    if company_id:
        company_sync_data = {
            "name": data.company_name,
            "phone_number": data.phone,
            "company_email": data.email,
            "website": data.website,
            "logo_url": data.logo_url,
        }
        # Add address fields if present
        if data.address:
            company_sync_data.update({
                "address": data.address.street,
                "city": data.address.city,
                "state": data.address.province_state,
                "zip_code": data.address.postal_code,
                "country": data.address.country,
            })
        # Filter out None values
        company_sync_data = {k: v for k, v in company_sync_data.items() if v is not None}
        if company_sync_data:
            await db.companies.update_one(
                {"id": company_id},
                {"$set": company_sync_data}
            )
    
    return {"message": "Company info updated successfully", "company_info": company_info_dict}


@router.post("/logo", response_model=dict)
async def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload company logo"""
    
    # Validate file type
    allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp', 'image/svg+xml']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only image files are supported")
    
    # Read and convert to base64
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")
    
    base64_data = base64.b64encode(content).decode('utf-8')
    logo_url = f"data:{file.content_type};base64,{base64_data}"
    
    # Update profile
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                "company_info.logo_url": logo_url,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {"message": "Logo uploaded successfully", "logo_url": logo_url}


@router.put("/compliance-documents", response_model=dict)
async def update_compliance_documents(
    data: ComplianceDocumentsUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update compliance documents (Step 2)"""
    
    compliance = ComplianceDocuments(**data.dict())
    compliance_dict = compliance.dict()
    compliance_dict['updated_at'] = compliance_dict['updated_at'].isoformat()
    
    # Calculate document statuses
    def update_doc_status(doc_dict):
        if doc_dict:
            for key, doc in doc_dict.items():
                if doc and isinstance(doc, dict):
                    expiry = doc.get('expiry_date')
                    doc['status'] = calculate_document_status(expiry).value
        return doc_dict
    
    if compliance_dict.get('canadian_documents'):
        compliance_dict['canadian_documents'] = update_doc_status(compliance_dict['canadian_documents'])
    if compliance_dict.get('us_documents'):
        compliance_dict['us_documents'] = update_doc_status(compliance_dict['us_documents'])
    
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                "compliance_documents": compliance_dict,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": current_user.id
            }
        }
    )
    
    return {"message": "Compliance documents updated successfully", "compliance_documents": compliance_dict}


@router.post("/compliance-documents/upload", response_model=dict)
async def upload_compliance_document(
    document_type: str = Query(..., description="Type of document (e.g., cargo_insurance, liability_insurance)"),
    document_country: str = Query("CA", description="Document country (CA or US)"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload a compliance document file"""
    
    # Validate file type
    allowed_types = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only PDF and image files are supported")
    
    # Read and convert to base64
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
    
    base64_data = base64.b64encode(content).decode('utf-8')
    doc_url = f"data:{file.content_type};base64,{base64_data}"
    
    # Determine update path
    if document_country == "CA":
        update_path = f"compliance_documents.canadian_documents.{document_type}.document_url"
    else:
        update_path = f"compliance_documents.us_documents.{document_type}.document_url"
    
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                update_path: doc_url,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        "message": f"{document_type} document uploaded successfully",
        "document_type": document_type,
        "document_url": doc_url[:100] + "..."  # Truncate for response
    }


@router.put("/regulatory-numbers", response_model=dict)
async def update_regulatory_numbers(
    data: RegulatoryNumbersUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update regulatory numbers (Step 3)"""
    
    # Get profile to access company_id
    profile = await db.carrier_profiles.find_one({"user_id": current_user.id})
    
    regulatory = RegulatoryNumbers(**data.dict())
    regulatory_dict = regulatory.dict()
    regulatory_dict['updated_at'] = regulatory_dict['updated_at'].isoformat()
    
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                "regulatory_numbers": regulatory_dict,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": current_user.id
            }
        }
    )
    
    # Sync regulatory numbers with Company collection
    if profile and profile.get('company_id'):
        company_sync_data = {}
        
        # Sync Canadian regulatory numbers
        if data.canadian:
            if data.canadian.nsc_number:
                company_sync_data['nsc_number'] = data.canadian.nsc_number
            if data.canadian.cvor_number:
                company_sync_data['cvor_number'] = data.canadian.cvor_number
        
        # Sync US regulatory numbers
        if data.us:
            if data.us.usdot_number:
                company_sync_data['dot_number'] = data.us.usdot_number
            if data.us.mc_number:
                company_sync_data['mc_number'] = data.us.mc_number
        
        if company_sync_data:
            await db.companies.update_one(
                {"id": profile['company_id']},
                {"$set": company_sync_data}
            )
    
    return {"message": "Regulatory numbers updated successfully", "regulatory_numbers": regulatory_dict}


@router.put("/fleet-configuration", response_model=dict)
async def update_fleet_configuration(
    data: FleetConfigurationUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update fleet configuration (Step 4)"""
    
    fleet = FleetConfiguration(**data.dict())
    fleet_dict = fleet.dict()
    fleet_dict['updated_at'] = fleet_dict['updated_at'].isoformat()
    
    # Convert nested models to dicts
    if fleet_dict.get('fleet_size'):
        fleet_dict['fleet_size'] = dict(fleet_dict['fleet_size'])
    if fleet_dict.get('equipment_types'):
        fleet_dict['equipment_types'] = [dict(e) for e in fleet_dict['equipment_types']]
    if fleet_dict.get('preferred_lanes'):
        fleet_dict['preferred_lanes'] = [
            {
                'origin': dict(lane['origin']),
                'destination': dict(lane['destination']),
                'frequency': lane['frequency']
            }
            for lane in fleet_dict['preferred_lanes']
        ]
    
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                "fleet_configuration": fleet_dict,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": current_user.id
            }
        }
    )
    
    return {"message": "Fleet configuration updated successfully", "fleet_configuration": fleet_dict}


@router.put("/payment-banking", response_model=dict)
async def update_payment_banking(
    data: PaymentBankingUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update payment/banking info (Step 5) - Banking info is encrypted"""
    
    payment_dict = data.dict()
    
    # Encrypt banking info if provided
    encrypted_banking = None
    if payment_dict.get('banking_info'):
        banking_info = payment_dict.pop('banking_info')
        if banking_info:
            # Filter out None values
            banking_info = {k: v for k, v in banking_info.items() if v is not None}
            if banking_info:
                encrypted_banking = encrypt_data(banking_info)
    
    payment_dict['encrypted_banking_info'] = encrypted_banking
    payment_dict['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    # Convert tax_info to dict if present
    if payment_dict.get('tax_info'):
        payment_dict['tax_info'] = dict(payment_dict['tax_info'])
    
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                "payment_banking": payment_dict,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": current_user.id
            }
        }
    )
    
    # Remove encrypted data from response
    response_dict = {k: v for k, v in payment_dict.items() if k != 'encrypted_banking_info'}
    response_dict['banking_info_saved'] = encrypted_banking is not None
    
    return {"message": "Payment/banking info updated successfully", "payment_banking": response_dict}


@router.post("/payment-banking/void-cheque", response_model=dict)
async def upload_void_cheque(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload void cheque document"""
    
    allowed_types = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only PDF and image files are supported")
    
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")
    
    base64_data = base64.b64encode(content).decode('utf-8')
    doc_url = f"data:{file.content_type};base64,{base64_data}"
    
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                "payment_banking.void_cheque_url": doc_url,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {"message": "Void cheque uploaded successfully"}


@router.get("/completion-status", response_model=dict)
async def get_completion_status(current_user: User = Depends(get_current_user)):
    """Get profile completion status"""
    
    profile = await db.carrier_profiles.find_one(
        {"user_id": current_user.id},
        {"_id": 0}
    )
    
    if not profile:
        return {
            "company_info": False,
            "compliance_documents": False,
            "regulatory_numbers": False,
            "fleet_configuration": False,
            "payment_banking": False,
            "overall_percentage": 0,
            "document_status": {}
        }
    
    completion_status = calculate_completion_status(profile)
    
    # Calculate document statuses
    document_status = {}
    compliance = profile.get('compliance_documents', {})
    if compliance:
        can_docs = compliance.get('canadian_documents', {})
        us_docs = compliance.get('us_documents', {})
        
        for doc_type in ['cargo_insurance', 'liability_insurance']:
            if can_docs and can_docs.get(doc_type):
                document_status[doc_type] = can_docs[doc_type].get('status', 'missing')
            elif us_docs and us_docs.get(doc_type):
                document_status[doc_type] = us_docs[doc_type].get('status', 'missing')
    
    return {
        **completion_status.dict(),
        "overall_percentage": calculate_completion_percentage(completion_status),
        "document_status": document_status
    }


@router.post("/validate", response_model=dict)
async def validate_profile(current_user: User = Depends(get_current_user)):
    """Validate profile and return errors/warnings"""
    
    profile = await db.carrier_profiles.find_one(
        {"user_id": current_user.id},
        {"_id": 0}
    )
    
    errors = []
    warnings = []
    
    if not profile:
        errors.append(ValidationError(
            section="profile",
            field="profile",
            message="Carrier profile not found"
        ))
        return ValidationResult(is_valid=False, errors=[e.dict() for e in errors]).dict()
    
    # Validate company info
    company_info = profile.get('company_info')
    if not company_info:
        errors.append(ValidationError(
            section="company_info",
            field="company_name",
            message="Company information is required"
        ))
    elif not company_info.get('company_name'):
        errors.append(ValidationError(
            section="company_info",
            field="company_name",
            message="Company name is required"
        ))
    
    # Validate compliance documents
    compliance = profile.get('compliance_documents')
    if compliance:
        country = compliance.get('operating_country', 'CA')
        docs = compliance.get('canadian_documents' if country == 'CA' else 'us_documents', {})
        
        if docs:
            cargo = docs.get('cargo_insurance', {})
            if not cargo or not cargo.get('policy_number'):
                errors.append(ValidationError(
                    section="compliance_documents",
                    field="cargo_insurance",
                    message="Cargo insurance is required"
                ))
            elif cargo.get('status') == 'expiring_soon':
                warnings.append(ValidationError(
                    section="compliance_documents",
                    field="cargo_insurance",
                    message="Cargo insurance expires within 60 days"
                ))
            elif cargo.get('status') == 'expired':
                errors.append(ValidationError(
                    section="compliance_documents",
                    field="cargo_insurance",
                    message="Cargo insurance has expired"
                ))
    else:
        errors.append(ValidationError(
            section="compliance_documents",
            field="compliance_documents",
            message="Compliance documents are required"
        ))
    
    # Validate regulatory numbers
    regulatory = profile.get('regulatory_numbers')
    if regulatory:
        regions = regulatory.get('operating_regions', [])
        if 'CA' in regions:
            can = regulatory.get('canadian', {})
            if not can or not can.get('nsc_number'):
                errors.append(ValidationError(
                    section="regulatory_numbers",
                    field="nsc_number",
                    message="NSC number is required for Canadian carriers"
                ))
        if 'US' in regions:
            us = regulatory.get('us', {})
            if not us or not us.get('usdot_number'):
                errors.append(ValidationError(
                    section="regulatory_numbers",
                    field="usdot_number",
                    message="USDOT number is required for US operations"
                ))
    
    is_valid = len(errors) == 0
    
    return {
        "is_valid": is_valid,
        "errors": [e.dict() for e in errors],
        "warnings": [w.dict() for w in warnings]
    }


@router.post("/submit", response_model=dict)
async def submit_profile(current_user: User = Depends(get_current_user)):
    """Submit profile for review"""
    
    # Validate first
    validation = await validate_profile(current_user)
    if not validation['is_valid']:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Profile has validation errors",
                "errors": validation['errors']
            }
        )
    
    now = datetime.now(timezone.utc)
    
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                "profile_status": ProfileStatus.PENDING_REVIEW.value,
                "submitted_at": now.isoformat(),
                "updated_at": now.isoformat()
            }
        }
    )
    
    return {
        "message": "Profile submitted for review",
        "status": "pending_review",
        "submitted_at": now.isoformat()
    }


# =============================================================================
# ADMIN ROUTES (Platform Admin)
# =============================================================================

@router.get("/admin/all", response_model=dict)
async def get_all_carrier_profiles(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get all carrier profiles (Platform Admin only)"""
    from auth import require_platform_admin
    require_platform_admin(current_user)
    
    query = {}
    if status:
        query['profile_status'] = status
    
    profiles = await db.carrier_profiles.find(
        query,
        {"_id": 0, "payment_banking.encrypted_banking_info": 0}
    ).skip(skip).limit(limit).to_list(length=limit)
    
    total = await db.carrier_profiles.count_documents(query)
    
    return {
        "profiles": profiles,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.put("/admin/{profile_id}/review", response_model=dict)
async def review_carrier_profile(
    profile_id: str,
    action: str = Query(..., description="approve or reject"),
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Approve or reject a carrier profile (Platform Admin only)"""
    from auth import require_platform_admin
    require_platform_admin(current_user)
    
    if action not in ['approve', 'reject']:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    
    new_status = ProfileStatus.APPROVED if action == 'approve' else ProfileStatus.REJECTED
    now = datetime.now(timezone.utc)
    
    update_data = {
        "profile_status": new_status.value,
        "reviewed_by": current_user.id,
        "review_notes": notes,
        "updated_at": now.isoformat()
    }
    
    if action == 'approve':
        update_data['approved_at'] = now.isoformat()
    
    result = await db.carrier_profiles.update_one(
        {"id": profile_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {
        "message": f"Profile {action}d successfully",
        "profile_id": profile_id,
        "status": new_status.value
    }
