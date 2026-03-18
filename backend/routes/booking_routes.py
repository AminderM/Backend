from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, BackgroundTasks
from models import User, Booking, BookingCreate, DispatchUpdate, UserRole
from auth import get_current_user
from database import db
from datetime import datetime, timezone, timedelta
from typing import List, Literal, Optional
from email_service import send_booking_confirmation_emails
from pydantic import BaseModel
import base64
import logging
import traceback
import os
import json
import uuid

router = APIRouter(prefix="/bookings", tags=["Bookings"])
logger = logging.getLogger(__name__)

# Pydantic model for creating load from quote
class LoadFromQuote(BaseModel):
    pickup_location: str = ""
    pickup_city: str = ""
    pickup_state: str = ""
    pickup_country: str = "USA"
    delivery_location: str = ""
    delivery_city: str = ""
    delivery_state: str = ""
    delivery_country: str = "USA"
    shipper_name: str = ""
    shipper_address: str = ""
    commodity: str = ""
    weight: Optional[float] = None
    cubes: Optional[float] = None
    confirmed_rate: float = 0  # Carrier rate (what you pay carrier)
    customer_rate: Optional[float] = None  # Customer rate (what customer pays, includes margin)
    notes: str = ""
    source_quote_id: Optional[str] = None
    source_quote_number: Optional[str] = None

@router.post("/from-quote", response_model=dict)
async def create_load_from_quote(load_data: LoadFromQuote, current_user: User = Depends(get_current_user)):
    """Create a new load/booking from a rate quote without requiring equipment"""
    
    # Generate order number
    order_number = f"LD-{str(uuid.uuid4())[:8].upper()}"
    
    # Create load record
    load_dict = {
        "id": str(uuid.uuid4()),
        "order_number": order_number,
        "requester_id": current_user.id,
        "equipment_owner_id": current_user.id,  # Same as requester for self-created loads
        "equipment_id": None,  # No equipment assigned yet
        "pickup_location": load_data.pickup_location,
        "pickup_city": load_data.pickup_city,
        "pickup_state": load_data.pickup_state,
        "pickup_country": load_data.pickup_country,
        "delivery_location": load_data.delivery_location,
        "delivery_city": load_data.delivery_city,
        "delivery_state": load_data.delivery_state,
        "delivery_country": load_data.delivery_country,
        "shipper_name": load_data.shipper_name,
        "shipper_address": load_data.shipper_address,
        "commodity": load_data.commodity,
        "weight": load_data.weight,
        "cubes": load_data.cubes,
        "confirmed_rate": load_data.confirmed_rate,  # Carrier rate (for AP)
        "customer_rate": load_data.customer_rate or load_data.confirmed_rate,  # Customer rate (for AR) - defaults to confirmed_rate if not provided
        "total_cost": load_data.confirmed_rate,
        "notes": load_data.notes,
        "source_quote_id": load_data.source_quote_id,
        "source_quote_number": load_data.source_quote_number,
        "status": "pending",
        "start_date": datetime.now(timezone.utc).isoformat(),
        "end_date": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.id
    }
    
    await db.bookings.insert_one(load_dict)
    
    return {
        "message": "Load created successfully",
        "load_id": load_dict["id"],
        "order_number": order_number
    }

@router.post("", response_model=dict)
async def create_booking(booking_data: BookingCreate, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    # Get equipment details
    equipment = await db.equipment.find_one({"id": booking_data.equipment_id})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    
    if not equipment["is_available"]:
        raise HTTPException(status_code=400, detail="Equipment is not available")
    
    # Get equipment owner details
    provider = await db.users.find_one({"id": equipment["owner_id"]})
    if not provider:
        raise HTTPException(status_code=404, detail="Equipment owner not found")
    
    # Calculate total cost
    duration_days = (booking_data.end_date - booking_data.start_date).days
    if duration_days < 1:
        duration_days = 1  # Minimum 1 day
    total_cost = duration_days * equipment["daily_rate"]
    
    # Create booking
    booking_dict = booking_data.dict()
    booking_dict["requester_id"] = current_user.id
    booking_dict["equipment_owner_id"] = equipment["owner_id"]
    booking_dict["total_cost"] = total_cost
    booking_obj = Booking(**booking_dict)
    
    await db.bookings.insert_one(booking_obj.dict())
    
    # Send booking confirmation emails
    booking_details = {
        "equipment_name": equipment["name"],
        "start_date": booking_data.start_date.strftime("%B %d, %Y at %I:%M %p"),
        "end_date": booking_data.end_date.strftime("%B %d, %Y at %I:%M %p"),
        "pickup_location": booking_data.pickup_location,
        "delivery_location": booking_data.delivery_location,
        "total_cost": total_cost,
        "booking_id": booking_obj.id[:8] + "...",
        "notes": booking_data.notes or "No special requirements"
    }
    
    await send_booking_confirmation_emails(
        background_tasks,
        current_user.email,
        current_user.full_name,
        provider["email"],
        provider["full_name"],
        booking_details
    )
    
    return {
        "message": "Booking request created successfully! Confirmation emails sent.", 
        "booking_id": booking_obj.id, 
        "total_cost": total_cost
    }

@router.get("/my", response_model=List[Booking])
async def get_my_bookings(current_user: User = Depends(get_current_user)):
    # Platform admin sees all bookings
    if current_user.role == UserRole.PLATFORM_ADMIN:
        bookings = await db.bookings.find({}, {"_id": 0}).to_list(length=500)
    else:
        bookings = await db.bookings.find({"requester_id": current_user.id}, {"_id": 0}).to_list(length=None)
    return [Booking(**booking) for booking in bookings]

@router.get("/requests")
async def get_booking_requests(current_user: User = Depends(get_current_user)):
    # Get bookings where user is equipment owner OR requester (for self-created loads)
    bookings = await db.bookings.find({
        "$or": [
            {"equipment_owner_id": current_user.id},
            {"requester_id": current_user.id}
        ]
    }, {"_id": 0}).sort("created_at", -1).to_list(length=500)
    return bookings

@router.patch("/{booking_id}/status", response_model=dict)
async def update_booking_status(
    booking_id: str, 
    status: Literal["pending", "planned", "in_transit_pickup", "at_pickup", "in_transit_delivery", "at_delivery", "delivered", "invoiced", "payment_overdue", "paid"],
    current_user: User = Depends(get_current_user)
):
    # Find the booking
    booking = await db.bookings.find_one({"id": booking_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Check if user has permission to update (either requester or equipment owner)
    if booking["requester_id"] != current_user.id and booking["equipment_owner_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this booking")
    
    old_status = booking.get("status", "pending")
    
    # Update the status
    await db.bookings.update_one(
        {"id": booking_id},
        {"$set": {"status": status}}
    )
    
    # Auto-generate AR/AP entries when load is marked as "delivered"
    ar_created = False
    ap_created = False
    if status == "delivered" and old_status != "delivered":
        ar_created, ap_created = await create_ar_ap_for_load(booking, current_user)
    
    response = {"message": "Status updated successfully", "status": status}
    if ar_created or ap_created:
        response["accounting_entries"] = {
            "ar_created": ar_created,
            "ap_created": ap_created
        }
    
    return response


async def create_ar_ap_for_load(booking: dict, current_user: User) -> tuple:
    """
    Auto-generate Accounts Receivable and Accounts Payable entries 
    when a load is marked as delivered.
    Returns: (ar_created: bool, ap_created: bool)
    """
    order_number = booking.get("order_number", "")
    company_id = current_user.id
    
    ar_created = False
    ap_created = False
    
    # Check if AR already exists for this load
    existing_ar = await db.accounts_receivable.find_one({
        "load_reference": order_number,
        "company_id": company_id
    })
    
    # Create Accounts Receivable (Invoice to Customer) if not exists
    if not existing_ar:
        customer_rate = booking.get("customer_rate") or booking.get("confirmed_rate") or booking.get("total_cost") or 0
        if customer_rate > 0:
            # Calculate due date (30 days from delivery)
            due_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
            
            ar_entry = {
                "id": str(uuid.uuid4()),
                "company_id": company_id,
                "customer_name": booking.get("shipper_name") or "Customer",
                "customer_email": "",
                "invoice_number": f"INV-{order_number}",
                "amount": float(customer_rate),
                "amount_paid": 0,
                "due_date": due_date,
                "description": f"Freight charges for load {order_number}",
                "load_reference": order_number,
                "booking_id": booking.get("id"),
                "status": "pending",
                "created_by": current_user.id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "auto_generated": True
            }
            
            await db.accounts_receivable.insert_one(ar_entry)
            ar_created = True
            logger.info(f"Auto-created AR entry for load {order_number}: ${customer_rate}")
    
    # Check if AP already exists for this load
    existing_ap = await db.accounts_payable.find_one({
        "load_reference": order_number,
        "company_id": company_id
    })
    
    # Create Accounts Payable (Bill to Carrier) if not exists and carrier is assigned
    if not existing_ap:
        carrier_rate = booking.get("confirmed_rate") or booking.get("total_cost") or 0
        carrier_name = booking.get("assigned_carrier")
        
        if carrier_rate > 0 and carrier_name:
            # Calculate due date (15 days from delivery for carrier payment)
            due_date = (datetime.now(timezone.utc) + timedelta(days=15)).strftime("%Y-%m-%d")
            
            ap_entry = {
                "id": str(uuid.uuid4()),
                "company_id": company_id,
                "vendor_name": carrier_name,
                "vendor_email": "",
                "bill_number": f"BILL-{order_number}",
                "amount": float(carrier_rate),
                "amount_paid": 0,
                "due_date": due_date,
                "description": f"Carrier payment for load {order_number}",
                "load_reference": order_number,
                "booking_id": booking.get("id"),
                "category": "carrier_payment",
                "status": "pending",
                "created_by": current_user.id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "auto_generated": True
            }
            
            await db.accounts_payable.insert_one(ap_entry)
            ap_created = True
            logger.info(f"Auto-created AP entry for load {order_number}: ${carrier_rate}")
    
    return ar_created, ap_created


@router.patch("/{booking_id}/dispatch", response_model=dict)
async def update_dispatch_info(
    booking_id: str,
    dispatch_data: DispatchUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update dispatch-specific information (carrier, driver, actual times)"""
    # Find the booking
    booking = await db.bookings.find_one({"id": booking_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Check if user has permission to update
    if booking["requester_id"] != current_user.id and booking["equipment_owner_id"] != current_user.id:
        # Also allow platform admin and company admin
        if current_user.role not in ["platform_admin", "company_admin"]:
            raise HTTPException(status_code=403, detail="Not authorized to update this booking")
    
    # Build update data, only including non-None values
    update_data = {}
    for field, value in dispatch_data.dict().items():
        if value is not None:
            if isinstance(value, datetime):
                update_data[field] = value.isoformat()
            else:
                update_data[field] = value
    
    if update_data:
        await db.bookings.update_one(
            {"id": booking_id},
            {"$set": update_data}
        )
    
    return {"message": "Dispatch info updated successfully", "updated_fields": list(update_data.keys())}

@router.post("/{booking_id}/push-to-driver", response_model=dict)
async def push_load_to_driver(
    booking_id: str,
    push_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Push a load to a driver's mobile app"""
    # Find the booking
    booking = await db.bookings.find_one({"id": booking_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    driver_id = push_data.get("driver_id")
    driver_name = push_data.get("driver_name", "")
    
    if not driver_id:
        raise HTTPException(status_code=400, detail="Driver ID is required")
    
    # Verify driver exists
    driver = await db.drivers.find_one({"id": driver_id})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Update booking with driver assignment and status
    update_data = {
        "assigned_driver_id": driver_id,
        "assigned_driver": driver_name or driver.get("full_name", ""),
        "status": "dispatched",
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "dispatched_by": current_user.id
    }
    
    await db.bookings.update_one(
        {"id": booking_id},
        {"$set": update_data}
    )
    
    # Create a driver load assignment record (for driver mobile app to pick up)
    driver_load = {
        "id": str(uuid.uuid4()),
        "booking_id": booking_id,
        "driver_id": driver_id,
        "driver_user_id": driver.get("user_id"),
        "order_number": booking.get("order_number", ""),
        "pickup_location": booking.get("pickup_location", ""),
        "delivery_location": booking.get("delivery_location", ""),
        "pickup_date": booking.get("pickup_date"),
        "delivery_date": booking.get("delivery_date"),
        "commodity": booking.get("commodity", ""),
        "weight": booking.get("weight"),
        "rate": booking.get("rate"),
        "status": "assigned",
        "assigned_at": datetime.now(timezone.utc).isoformat(),
        "assigned_by": current_user.id
    }
    
    await db.driver_loads.insert_one(driver_load)
    
    # Update driver status to on_trip
    await db.drivers.update_one(
        {"id": driver_id},
        {"$set": {"status": "on_trip", "current_load_id": booking_id}}
    )
    
    return {
        "message": f"Load pushed to {driver_name or driver.get('full_name', 'driver')} successfully",
        "driver_load_id": driver_load["id"],
        "booking_id": booking_id
    }

@router.put("/{booking_id}", response_model=Booking)
async def update_booking(
    booking_id: str,
    booking_update: BookingCreate,
    current_user: User = Depends(get_current_user)
):
    # Find the booking
    booking = await db.bookings.find_one({"id": booking_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Check if user has permission to update
    if booking["requester_id"] != current_user.id and booking["equipment_owner_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this booking")
    
    # Only allow editing if status is pending
    if booking.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Only bookings with 'pending' status can be edited")
    
    # Update the booking
    update_data = booking_update.dict(exclude_unset=True)
    
    # Convert datetime fields to ISO format strings for MongoDB
    for field in ['pickup_time_planned', 'delivery_time_planned', 'start_date', 'end_date']:
        if field in update_data and update_data[field]:
            if isinstance(update_data[field], datetime):
                update_data[field] = update_data[field].isoformat()
    
    await db.bookings.update_one(
        {"id": booking_id},
        {"$set": update_data}
    )
    
    # Get updated booking
    updated_booking = await db.bookings.find_one({"id": booking_id})
    return Booking(**updated_booking)

@router.post("/parse-rate-confirmation", response_model=dict)
async def parse_rate_confirmation(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Parse a rate confirmation document using AI to extract order information
    """
    logger.info(f"Parsing rate confirmation: filename={file.filename}, content_type={file.content_type}")
    
    try:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="Rate confirmation parsing requires emergentintegrations package (not installed)."
            )
        import tempfile
        import shutil
        
        # Validate file type
        allowed_types = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg', 'image/webp']
        if file.content_type not in allowed_types:
            logger.error(f"Invalid file type: {file.content_type}")
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}. Only PDF and image files (JPEG, PNG) are supported.")
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name
        
        try:
            # Initialize AI chat with Gemini (supports file attachments)
            # Note: File attachment processing requires Gemini provider
            api_key = os.environ.get('EMERGENT_LLM_KEY')
            if not api_key:
                raise HTTPException(status_code=500, detail="AI service not configured")
            
            chat = LlmChat(
                api_key=api_key,
                session_id=f"rate-conf-{current_user.id}",
                system_message="You are an AI assistant specialized in extracting structured data from shipping and logistics documents, including rate confirmations, bills of lading, and load tenders. Extract all relevant fields accurately and return data in valid JSON format."
            ).with_model("gemini", "gemini-2.0-flash")
            
            # Prepare file for analysis
            file_content = FileContentWithMimeType(
                file_path=temp_file_path,
                mime_type=file.content_type
            )
            
            # Create detailed extraction prompt
            extraction_prompt = """
Analyze this rate confirmation or shipping document and extract the following information. 
Return the data in JSON format with these exact field names:

{
  "shipper_name": "name of the shipper/sender",
  "shipper_address": "full address of shipper",
  "pickup_location": "pickup street address",
  "pickup_city": "pickup city",
  "pickup_state": "pickup state",
  "pickup_country": "pickup country (default USA if not specified)",
  "delivery_location": "delivery street address",
  "delivery_city": "delivery city",
  "delivery_state": "delivery state",
  "delivery_country": "delivery country (default USA if not specified)",
  "commodity": "type of goods being shipped",
  "weight": "weight in pounds (number only)",
  "cubes": "cubic feet (number only)",
  "tractor_number": "tractor number if available",
  "trailer_number": "trailer number if available",
  "driver_name": "driver name if available",
  "driver_id": "driver ID if available",
  "pickup_time_planned": "planned pickup date and time in ISO format (YYYY-MM-DDTHH:MM:SS)",
  "delivery_time_planned": "planned delivery date and time in ISO format (YYYY-MM-DDTHH:MM:SS)",
  "confirmed_rate": "the confirmed rate or total charge amount in dollars (number only, extract from fields like 'Rate', 'Total', 'Charge', 'Amount', or similar)",
  "notes": "any additional notes or special instructions"
}

IMPORTANT: For confirmed_rate, look for monetary values labeled as:
- "Rate"
- "Total Rate"
- "Confirmed Rate" 
- "Total Charge"
- "Amount"
- "Total Amount"
- "Line Haul"
- Any dollar amount that represents the shipping cost

Extract only the numeric value without dollar signs or commas.

If a field is not found in the document, set it to null. 
Return ONLY the JSON object, no additional text or explanation.
"""
            
            # Send message with file
            user_message = UserMessage(
                text=extraction_prompt,
                file_contents=[file_content]
            )
            
            response = await chat.send_message(user_message)
            
            logger.info(f"AI response received, length: {len(response)}")
            
            # Parse the AI response
            response_text = response.strip()
            
            # Try to extract JSON from response
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()
            
            try:
                extracted_data = json.loads(response_text)
                logger.info(f"Successfully extracted data: {list(extracted_data.keys())}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}, response: {response_text[:500]}")
                raise HTTPException(status_code=500, detail=f"Failed to parse AI response as JSON. AI returned: {response_text[:200]}")
            
            return {
                "success": True,
                "data": extracted_data,
                "message": "Document parsed successfully"
            }
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error parsing rate confirmation: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error parsing document: {str(e)}")

