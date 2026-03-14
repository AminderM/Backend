"""
Carrier Profile Routes for TMS
9 API endpoints for carrier profile management
"""
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Query
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet
import os
import base64
import uuid

from models import User, UserRole
from models_carrier_profile import (
    CarrierProfile, CarrierProfileUpdate, CarrierDocument, 
    DocumentStatus, CarrierPackage, CarrierPackageCreate,
    Payment, CompanyInfo, Regulatory, Fleet, PreferredLane
)
from auth import get_current_user
from database import db

router = APIRouter(prefix="/carrier-profiles", tags=["Carrier Profiles"])

# === Encryption Setup ===
# Get or generate Fernet key for banking encryption
FERNET_KEY = os.environ.get('FERNET_KEY')
if not FERNET_KEY:
    # Generate a key if not provided (in production, this should be set in .env)
    FERNET_KEY = Fernet.generate_key().decode()
    
fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)


def encrypt_value(value: str) -> str:
    """Encrypt a sensitive value using Fernet"""
    if not value:
        return None
    return fernet.encrypt(value.encode()).decode()


def decrypt_value(encrypted_value: str) -> str:
    """Decrypt a Fernet-encrypted value"""
    if not encrypted_value:
        return None
    try:
        return fernet.decrypt(encrypted_value.encode()).decode()
    except Exception:
        return None


def mask_value(value: str, show_last: int = 4) -> str:
    """Mask a sensitive value, showing only last N characters"""
    if not value or len(value) <= show_last:
        return "*" * 8
    return "*" * (len(value) - show_last) + value[-show_last:]


def calculate_profile_completion(profile: dict) -> int:
    """Calculate profile completion percentage"""
    total_fields = 0
    filled_fields = 0
    
    # Company Info (weight: 25%)
    company_info = profile.get("company_info", {})
    company_fields = ["legal_name", "company_type", "country", "phone", "email"]
    for field in company_fields:
        total_fields += 1
        if company_info.get(field):
            filled_fields += 1
    
    # Regulatory (weight: 25%)
    regulatory = profile.get("regulatory", {})
    reg_fields = ["nsc_number", "usdot_number", "mc_number"]
    for field in reg_fields:
        total_fields += 1
        if regulatory.get(field):
            filled_fields += 1
    
    # Fleet (weight: 25%)
    fleet = profile.get("fleet", {})
    fleet_fields = ["number_of_trucks", "equipment_types"]
    for field in fleet_fields:
        total_fields += 1
        val = fleet.get(field)
        if val and (not isinstance(val, list) or len(val) > 0):
            filled_fields += 1
    
    # Documents (weight: 15%)
    documents = profile.get("documents", [])
    total_fields += 1
    if len(documents) > 0:
        filled_fields += 1
    
    # Payment (weight: 10%)
    payment = profile.get("payment", {})
    total_fields += 1
    if payment.get("payment_method"):
        filled_fields += 1
    
    return int((filled_fields / total_fields) * 100) if total_fields > 0 else 0


def mask_payment_info(payment: dict) -> dict:
    """Return payment info with sensitive fields masked"""
    masked = {
        "payment_method": payment.get("payment_method"),
        "factoring_company_name": payment.get("factoring_company_name"),
        "bank_name": payment.get("bank_name"),
        "account_type": payment.get("account_type"),
        "currency": payment.get("currency"),
        "payment_terms": payment.get("payment_terms"),
    }
    
    # Mask encrypted fields
    if payment.get("transit_number_encrypted"):
        decrypted = decrypt_value(payment["transit_number_encrypted"])
        masked["transit_number_masked"] = mask_value(decrypted) if decrypted else None
        masked["has_transit_number"] = True
    else:
        masked["has_transit_number"] = False
        
    if payment.get("institution_number_encrypted"):
        decrypted = decrypt_value(payment["institution_number_encrypted"])
        masked["institution_number_masked"] = mask_value(decrypted, 2) if decrypted else None
        masked["has_institution_number"] = True
    else:
        masked["has_institution_number"] = False
        
    if payment.get("aba_routing_number_encrypted"):
        decrypted = decrypt_value(payment["aba_routing_number_encrypted"])
        masked["aba_routing_number_masked"] = mask_value(decrypted) if decrypted else None
        masked["has_aba_routing_number"] = True
    else:
        masked["has_aba_routing_number"] = False
        
    if payment.get("account_number_encrypted"):
        decrypted = decrypt_value(payment["account_number_encrypted"])
        masked["account_number_masked"] = mask_value(decrypted) if decrypted else None
        masked["has_account_number"] = True
    else:
        masked["has_account_number"] = False
    
    return masked


def profile_to_response(profile: dict) -> dict:
    """Convert profile dict to response format with masked payment"""
    response = {
        "id": profile.get("id"),
        "user_id": profile.get("user_id"),
        "company_id": profile.get("company_id"),
        "company_info": profile.get("company_info", {}),
        "documents": profile.get("documents", []),
        "regulatory": profile.get("regulatory", {}),
        "fleet": profile.get("fleet", {}),
        "payment": mask_payment_info(profile.get("payment", {})),
        "profile_completion": profile.get("profile_completion", 0),
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
        "packages": profile.get("packages", []),
    }
    return response


# === API ENDPOINTS ===

# 1. GET /api/carrier-profiles/me - Load carrier profile
@router.get("/me")
async def get_my_carrier_profile(current_user: User = Depends(get_current_user)):
    """Get the current user's carrier profile"""
    profile = await db.carrier_profiles.find_one(
        {"user_id": current_user.id},
        {"_id": 0}
    )
    
    if not profile:
        # Create a new empty profile for the user
        new_profile = CarrierProfile(
            user_id=current_user.id,
            company_id=getattr(current_user, 'company_id', None)
        ).dict()
        
        await db.carrier_profiles.insert_one(new_profile)
        return profile_to_response(new_profile)
    
    return profile_to_response(profile)


# 2. PATCH /api/carrier-profiles/me - Save all form data (PRIMARY ENDPOINT)
@router.patch("/me")
async def update_my_carrier_profile(
    update_data: CarrierProfileUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update the current user's carrier profile (saves all form data)"""
    profile = await db.carrier_profiles.find_one({"user_id": current_user.id})
    
    if not profile:
        # Create new profile if doesn't exist
        new_profile = CarrierProfile(
            user_id=current_user.id,
            company_id=getattr(current_user, 'company_id', None)
        ).dict()
        await db.carrier_profiles.insert_one(new_profile)
        profile = new_profile
    
    # Build update dict
    update_dict = {"updated_at": datetime.now(timezone.utc)}
    
    # Update company_info
    if update_data.company_info:
        existing_company_info = profile.get("company_info", {})
        for key, value in update_data.company_info.dict(exclude_unset=True).items():
            if value is not None:
                existing_company_info[key] = value
        update_dict["company_info"] = existing_company_info
    
    # Update regulatory
    if update_data.regulatory:
        existing_regulatory = profile.get("regulatory", {})
        for key, value in update_data.regulatory.dict(exclude_unset=True).items():
            if value is not None:
                existing_regulatory[key] = value
        update_dict["regulatory"] = existing_regulatory
    
    # Update fleet
    if update_data.fleet:
        existing_fleet = profile.get("fleet", {})
        fleet_data = update_data.fleet.dict(exclude_unset=True)
        for key, value in fleet_data.items():
            if value is not None:
                existing_fleet[key] = value
        update_dict["fleet"] = existing_fleet
    
    # Update payment (with encryption for sensitive fields)
    if update_data.payment:
        existing_payment = profile.get("payment", {})
        payment_data = update_data.payment
        
        # Non-encrypted fields
        non_encrypted_fields = ["payment_method", "factoring_company_name", "bank_name", 
                                "account_type", "currency", "payment_terms"]
        for field in non_encrypted_fields:
            if field in payment_data and payment_data[field] is not None:
                existing_payment[field] = payment_data[field]
        
        # Encrypted fields - encrypt if provided
        encrypted_field_mapping = {
            "transit_number": "transit_number_encrypted",
            "institution_number": "institution_number_encrypted",
            "aba_routing_number": "aba_routing_number_encrypted",
            "account_number": "account_number_encrypted"
        }
        
        for plain_field, encrypted_field in encrypted_field_mapping.items():
            if plain_field in payment_data and payment_data[plain_field]:
                existing_payment[encrypted_field] = encrypt_value(payment_data[plain_field])
        
        update_dict["payment"] = existing_payment
    
    # Calculate profile completion
    merged_profile = {**profile, **update_dict}
    update_dict["profile_completion"] = calculate_profile_completion(merged_profile)
    
    # Perform update
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {"$set": update_dict}
    )
    
    # Fetch and return updated profile
    updated_profile = await db.carrier_profiles.find_one(
        {"user_id": current_user.id},
        {"_id": 0}
    )
    
    return profile_to_response(updated_profile)


# 3. POST /api/carrier-profiles/me/documents - File uploads
@router.post("/me/documents")
async def upload_carrier_document(
    document_type: str = Query(..., description="Type of document (e.g., nsc_certificate, cvor_abstract)"),
    expiry_date: Optional[str] = Query(None, description="Document expiry date (ISO format)"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload a document to the carrier profile"""
    # Validate file type
    allowed_types = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg', 'image/webp']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only PDF and image files are supported")
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Check file size limit (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400, 
            detail=f"File size exceeds 10MB limit. Current size: {file_size / (1024 * 1024):.2f}MB"
        )
    
    # Convert to base64 for storage (in production, use S3/Cloudinary)
    base64_data = base64.b64encode(file_content).decode('utf-8')
    file_url = f"data:{file.content_type};base64,{base64_data}"
    
    # Parse expiry date
    parsed_expiry = None
    if expiry_date:
        try:
            parsed_expiry = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
        except ValueError:
            pass
    
    # Determine document status
    status = DocumentStatus.UPLOADED
    if parsed_expiry:
        now = datetime.now(timezone.utc)
        if parsed_expiry < now:
            status = DocumentStatus.EXPIRED
        elif parsed_expiry < now + timedelta(days=30):
            status = DocumentStatus.EXPIRING_SOON
    
    # Create document record
    document = CarrierDocument(
        document_type=document_type,
        file_name=file.filename,
        file_url=file_url,
        expiry_date=parsed_expiry,
        status=status
    ).dict()
    
    # Ensure profile exists
    profile = await db.carrier_profiles.find_one({"user_id": current_user.id})
    if not profile:
        new_profile = CarrierProfile(user_id=current_user.id).dict()
        await db.carrier_profiles.insert_one(new_profile)
    
    # Add document to profile
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$push": {"documents": document},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }
    )
    
    # Recalculate profile completion
    updated_profile = await db.carrier_profiles.find_one({"user_id": current_user.id})
    completion = calculate_profile_completion(updated_profile)
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {"$set": {"profile_completion": completion}}
    )
    
    return {
        "message": "Document uploaded successfully",
        "document": document
    }


# 4. DELETE /api/carrier-profiles/me/documents/{document_id} - Delete a document
@router.delete("/me/documents/{document_id}")
async def delete_carrier_document(
    document_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a document from the carrier profile"""
    result = await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$pull": {"documents": {"id": document_id}},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Recalculate profile completion
    updated_profile = await db.carrier_profiles.find_one({"user_id": current_user.id})
    completion = calculate_profile_completion(updated_profile)
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {"$set": {"profile_completion": completion}}
    )
    
    return {"message": "Document deleted successfully"}


# 5. POST /api/carrier-profiles/me/logo - Logo upload
@router.post("/me/logo")
async def upload_carrier_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload company logo for carrier profile"""
    # Validate file type
    allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp', 'image/svg+xml']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only image files (JPEG, PNG, WebP, SVG) are supported")
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Check file size limit (5MB for logos)
    MAX_FILE_SIZE = 5 * 1024 * 1024
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400, 
            detail=f"Logo size exceeds 5MB limit. Current size: {file_size / (1024 * 1024):.2f}MB"
        )
    
    # Convert to base64 for storage
    base64_data = base64.b64encode(file_content).decode('utf-8')
    logo_url = f"data:{file.content_type};base64,{base64_data}"
    
    # Ensure profile exists
    profile = await db.carrier_profiles.find_one({"user_id": current_user.id})
    if not profile:
        new_profile = CarrierProfile(user_id=current_user.id).dict()
        await db.carrier_profiles.insert_one(new_profile)
    
    # Update logo URL in company_info
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                "company_info.logo_url": logo_url,
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )
    
    return {
        "message": "Logo uploaded successfully",
        "logo_url": logo_url
    }


# 6. DELETE /api/carrier-profiles/me/logo - Delete logo
@router.delete("/me/logo")
async def delete_carrier_logo(current_user: User = Depends(get_current_user)):
    """Delete company logo from carrier profile"""
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$set": {
                "company_info.logo_url": None,
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )
    
    return {"message": "Logo deleted successfully"}


# 7. POST /api/carrier-profiles/me/packages - Send profile to recipients
@router.post("/me/packages")
async def send_carrier_package(
    package_data: CarrierPackageCreate,
    current_user: User = Depends(get_current_user)
):
    """Send carrier profile package to recipients"""
    if not package_data.recipients:
        raise HTTPException(status_code=400, detail="At least one recipient is required")
    
    # Create package record
    package = CarrierPackage(
        recipients=[r.dict() for r in package_data.recipients],
        message=package_data.message,
        included_sections=package_data.included_sections,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30)  # 30 day expiry
    ).dict()
    
    # Add package to profile
    await db.carrier_profiles.update_one(
        {"user_id": current_user.id},
        {
            "$push": {"packages": package},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }
    )
    
    # TODO: Send email notifications to recipients
    # For now, just return the package info
    
    return {
        "message": "Package sent successfully",
        "package": package,
        "recipients_count": len(package_data.recipients)
    }


# 8. GET /api/carrier-profiles/me/packages - Get sent packages history
@router.get("/me/packages")
async def get_carrier_packages(current_user: User = Depends(get_current_user)):
    """Get list of sent packages"""
    profile = await db.carrier_profiles.find_one(
        {"user_id": current_user.id},
        {"_id": 0, "packages": 1}
    )
    
    if not profile:
        return {"packages": []}
    
    return {"packages": profile.get("packages", [])}


# 9. GET /api/carrier-profiles/package/{access_token} - Public package view (no auth)
@router.get("/package/{access_token}")
async def get_public_package(access_token: str):
    """Get a carrier profile package by access token (public, no auth required)"""
    # Find profile with matching package token
    profile = await db.carrier_profiles.find_one(
        {"packages.access_token": access_token},
        {"_id": 0}
    )
    
    if not profile:
        raise HTTPException(status_code=404, detail="Package not found or expired")
    
    # Find the specific package
    package = None
    for p in profile.get("packages", []):
        if p.get("access_token") == access_token:
            package = p
            break
    
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    
    # Check expiry
    expires_at = package.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        # Ensure timezone-aware comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Package has expired")
    
    # Build response with only included sections
    included = package.get("included_sections", ["company_info", "documents", "regulatory", "fleet"])
    
    response = {
        "package_info": {
            "sent_at": package.get("sent_at"),
            "message": package.get("message"),
            "expires_at": package.get("expires_at")
        }
    }
    
    if "company_info" in included:
        response["company_info"] = profile.get("company_info", {})
    
    if "documents" in included:
        response["documents"] = profile.get("documents", [])
    
    if "regulatory" in included:
        response["regulatory"] = profile.get("regulatory", {})
    
    if "fleet" in included:
        response["fleet"] = profile.get("fleet", {})
    
    # Never include payment info in public packages
    
    return response
