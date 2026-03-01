from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, BackgroundTasks
from models import *
from auth import get_current_user
from database import db
from datetime import datetime, timezone
from email_service import send_company_verification_email
import tempfile
import shutil
import base64
import os
from typing import Literal

router = APIRouter(prefix="/companies", tags=["Companies"])

@router.post("", response_model=dict)
async def create_company(company_data: CompanyCreate, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    # Check if user's email is verified
    if not current_user.email_verified:
        raise HTTPException(status_code=400, detail="Please verify your email address first")
    
    # Check if user already has a company
    existing_company = await db.companies.find_one({"owner_id": current_user.id})
    if existing_company:
        raise HTTPException(status_code=400, detail="User already has a company registered")
    
    # Create company
    company_dict = company_data.dict()
    company_dict["owner_id"] = current_user.id
    company_obj = Company(**company_dict)
    
    # Insert company
    await db.companies.insert_one(company_obj.dict())
    
    # For demo purposes, auto-verify the company and send notification
    await db.companies.update_one(
        {"id": company_obj.id},
        {"$set": {"verification_status": RegistrationStatus.VERIFIED}}
    )
    
    # Send company verification email
    await send_company_verification_email(
        background_tasks,
        current_user.email,
        current_user.full_name,
        company_data.name
    )
    
    return {
        "message": "Company registered and verified successfully! Check your email for confirmation.", 
        "company_id": company_obj.id, 
        "status": "verified"
    }

@router.get("/my", response_model=Company)
async def get_my_company(current_user: User = Depends(get_current_user)):
    company = await db.companies.find_one({"owner_id": current_user.id})
    if not company:
        raise HTTPException(status_code=404, detail="No company found for this user")
    return Company(**company)

@router.put("/my", response_model=Company)
async def update_my_company(
    company_update: CompanyUpdate,
    current_user: User = Depends(get_current_user)
):
    # Only fleet owners can update company
    if current_user.role != UserRole.FLEET_OWNER:
        raise HTTPException(status_code=403, detail="Only company admins can update company profile")
    
    company = await db.companies.find_one({"owner_id": current_user.id})
    if not company:
        raise HTTPException(status_code=404, detail="No company found for this user")
    
    # Update company with only provided fields
    update_data = company_update.dict(exclude_unset=True)
    
    if update_data:
        await db.companies.update_one(
            {"id": company["id"]},
            {"$set": update_data}
        )
    

@router.get("/current", response_model=Company)
async def get_current_company(current_user: User = Depends(get_current_user)):
    """Return the company associated with the current user.
    - For fleet_owner: company where owner_id == current_user.id
    - For driver: company where owner_id == fleet_owner_id
    - For other roles (dispatcher, AR/AP/HR): company by user's company_id
    """
    # Fleet owner
    if current_user.role == UserRole.FLEET_OWNER:
        company = await db.companies.find_one({"owner_id": current_user.id})
        if not company:
            raise HTTPException(status_code=404, detail="No company found for this user")
        return Company(**company)

    # Load full user record to access company_id/fleet_owner_id
    user_record = await db.users.find_one({"id": current_user.id})
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")

    company = None
    # Drivers are linked via fleet_owner_id
    if user_record.get("fleet_owner_id"):
        company = await db.companies.find_one({"owner_id": user_record["fleet_owner_id"]})
    # Other roles use company_id
    if not company and user_record.get("company_id"):
        company = await db.companies.find_one({"id": user_record["company_id"]})

    if not company:
        raise HTTPException(status_code=404, detail="No company found for this user")

    return Company(**company)

    updated_company = await db.companies.find_one({"id": company["id"]})
    return Company(**updated_company)

@router.post("/my/upload-logo")
async def upload_company_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    # Only fleet owners can upload logo
    if current_user.role != UserRole.FLEET_OWNER:
        raise HTTPException(status_code=403, detail="Only company admins can upload logo")
    
    company = await db.companies.find_one({"owner_id": current_user.id})
    if not company:
        raise HTTPException(status_code=404, detail="No company found")
    
    # Validate file type
    allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only image files (JPEG, PNG, WebP) are supported")
    
    import tempfile
    import shutil
    import base64
    
    # Save file temporarily and convert to base64 for storage
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_file_path = temp_file.name
    
    try:
        # Read file and convert to base64
        with open(temp_file_path, 'rb') as f:
            file_data = f.read()
            base64_data = base64.b64encode(file_data).decode('utf-8')
            logo_url = f"data:{file.content_type};base64,{base64_data}"
        
        # Update company with logo URL
        await db.companies.update_one(
            {"id": company["id"]},
            {"$set": {"logo_url": logo_url}}
        )
        
        return {"message": "Logo uploaded successfully", "logo_url": logo_url}
    finally:
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

@router.post("/my/upload-document")
async def upload_company_document(
    document_type: Literal["mc_authority", "insurance_certificate", "w9"],
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    # Only fleet owners can upload documents
    if current_user.role != UserRole.FLEET_OWNER:
        raise HTTPException(status_code=403, detail="Only company admins can upload documents")
    
    company = await db.companies.find_one({"owner_id": current_user.id})
    if not company:
        raise HTTPException(status_code=404, detail="No company found")
    
    # Validate file type
    allowed_types = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only PDF and image files are supported")
    
    import tempfile
    import shutil
    import base64
    
    # Read file content to check size
    file_content = await file.read()
    file_size = len(file_content)
    
    # Check file size limit (10MB = 10 * 1024 * 1024 bytes)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File size exceeds 10MB limit. Current size: {file_size / (1024 * 1024):.2f}MB")
    
    # Reset file pointer for reading
    await file.seek(0)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_file_path = temp_file.name
    
    try:
        with open(temp_file_path, 'rb') as f:
            file_data = f.read()
            base64_data = base64.b64encode(file_data).decode('utf-8')
            doc_url = f"data:{file.content_type};base64,{base64_data}"
        
        # Create document version entry
        document_version = {
            "url": doc_url,
            "filename": file.filename,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_by": current_user.id,
            "file_size": file_size
        }
        
        # Get current company documents or initialize
        company_docs = company.get("company_documents", {
            "mc_authority": [],
            "insurance_certificate": [],
            "w9": []
        })
        
        # Add new version to document history
        if document_type not in company_docs:
            company_docs[document_type] = []
        
        company_docs[document_type].append(document_version)
        
        # Update company with new document version
        await db.companies.update_one(
            {"id": company["id"]},
            {"$set": {"company_documents": company_docs}}
        )
        
        return {
            "message": f"{document_type.replace('_', ' ').title()} uploaded successfully",
            "version": len(company_docs[document_type]),
            "document": document_version
        }
    finally:
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

# User Management Routes
