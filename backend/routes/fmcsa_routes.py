"""
FMCSA QCMobile API Integration
Provides carrier data lookup by DOT#, MC#, or company name
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import httpx
import os
from models import User
from auth import get_current_user

router = APIRouter(prefix="/fmcsa", tags=["FMCSA"])

# FMCSA API Configuration
FMCSA_BASE_URL = "https://mobile.fmcsa.dot.gov/qc/services"
FMCSA_API_KEY = os.environ.get("FMCSA_API_KEY", "")

# Response Models
class CarrierBasicInfo(BaseModel):
    dot_number: Optional[str] = None
    mc_number: Optional[str] = None
    legal_name: Optional[str] = None
    dba_name: Optional[str] = None
    physical_address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    allow_to_operate: Optional[str] = None
    out_of_service: Optional[bool] = None

class CarrierFullInfo(CarrierBasicInfo):
    # Company Details
    entity_type: Optional[str] = None
    operating_status: Optional[str] = None
    mcs150_form_date: Optional[str] = None
    
    # Fleet Information
    total_drivers: Optional[int] = None
    total_power_units: Optional[int] = None
    
    # Safety Data
    safety_rating: Optional[str] = None
    safety_rating_date: Optional[str] = None
    
    # BASIC Scores (0-100 percentile, higher = worse)
    unsafe_driving_basic: Optional[str] = None
    hours_of_service_basic: Optional[str] = None
    driver_fitness_basic: Optional[str] = None
    controlled_substances_basic: Optional[str] = None
    vehicle_maintenance_basic: Optional[str] = None
    hazmat_basic: Optional[str] = None
    crash_indicator_basic: Optional[str] = None
    
    # Crash Data
    fatal_crashes: Optional[int] = None
    injury_crashes: Optional[int] = None
    tow_crashes: Optional[int] = None
    total_crashes: Optional[int] = None
    
    # Inspection Data
    vehicle_inspections: Optional[int] = None
    driver_inspections: Optional[int] = None
    vehicle_oos_rate: Optional[float] = None
    driver_oos_rate: Optional[float] = None
    
    # Authority/Insurance
    common_authority: Optional[str] = None
    contract_authority: Optional[str] = None
    broker_authority: Optional[str] = None
    insurance_bipd: Optional[str] = None
    insurance_cargo: Optional[str] = None
    insurance_bond: Optional[str] = None
    
    # Cargo Types
    cargo_carried: Optional[List[str]] = None
    
    # Additional Info
    complaint_count: Optional[int] = None
    mailing_address: Optional[str] = None


def parse_carrier_basic(data: dict) -> CarrierBasicInfo:
    """Parse FMCSA response into basic carrier info"""
    # Handle null content
    if data is None:
        return CarrierBasicInfo()
    
    content = data.get("content")
    if content is None:
        return CarrierBasicInfo()
    
    carrier = content.get("carrier", {}) if isinstance(content, dict) else {}
    if not carrier:
        return CarrierBasicInfo()
    
    # Build physical address
    phy_address_parts = [
        carrier.get("phyStreet", ""),
        carrier.get("phyCity", ""),
        carrier.get("phyState", ""),
        carrier.get("phyZipcode", "")
    ]
    physical_address = ", ".join([p for p in phy_address_parts if p])
    
    return CarrierBasicInfo(
        dot_number=str(carrier.get("dotNumber", "")) if carrier.get("dotNumber") else None,
        mc_number=str(carrier.get("mcNumber", "")) if carrier.get("mcNumber") else None,
        legal_name=carrier.get("legalName"),
        dba_name=carrier.get("dbaName"),
        physical_address=physical_address or None,
        phone=carrier.get("telephone"),
        email=carrier.get("emailAddress"),
        allow_to_operate=carrier.get("allowedToOperate"),
        out_of_service=carrier.get("oosDate") is not None or carrier.get("outOfServiceDate") is not None
    )


def parse_carrier_full(data: dict) -> CarrierFullInfo:
    """Parse FMCSA response into full carrier info"""
    # Handle null content
    if data is None:
        return CarrierFullInfo()
    
    content = data.get("content")
    if content is None:
        return CarrierFullInfo()
    
    carrier = content.get("carrier", {}) if isinstance(content, dict) else {}
    if not carrier:
        return CarrierFullInfo()
    
    # Build addresses
    phy_address_parts = [
        carrier.get("phyStreet", ""),
        carrier.get("phyCity", ""),
        carrier.get("phyState", ""),
        carrier.get("phyZipcode", "")
    ]
    physical_address = ", ".join([p for p in phy_address_parts if p])
    
    mail_address_parts = [
        carrier.get("mailingStreet", ""),
        carrier.get("mailingCity", ""),
        carrier.get("mailingState", ""),
        carrier.get("mailingZipcode", "")
    ]
    mailing_address = ", ".join([p for p in mail_address_parts if p])
    
    # Parse cargo types
    cargo_carried = []
    for i in range(1, 20):
        cargo = carrier.get(f"cargoCarried{i}Desc")
        if cargo:
            cargo_carried.append(cargo)
    
    # Calculate total crashes - crashTotal might be an int or a dict
    crash_total = carrier.get("crashTotal", {})
    if isinstance(crash_total, dict):
        fatal = crash_total.get("fatalCrash", 0) or 0
        injury = crash_total.get("injCrash", 0) or 0
        tow = crash_total.get("towawayCrash", 0) or 0
    else:
        # crashTotal is just an integer
        fatal = carrier.get("fatalCrash", 0) or 0
        injury = carrier.get("injCrash", 0) or 0
        tow = carrier.get("towawayCrash", 0) or 0
    
    return CarrierFullInfo(
        # Basic Info
        dot_number=str(carrier.get("dotNumber", "")) if carrier.get("dotNumber") else None,
        mc_number=str(carrier.get("mcNumber", "")) if carrier.get("mcNumber") else None,
        legal_name=carrier.get("legalName"),
        dba_name=carrier.get("dbaName"),
        physical_address=physical_address or None,
        phone=carrier.get("telephone"),
        email=carrier.get("emailAddress"),
        allow_to_operate=carrier.get("allowedToOperate"),
        out_of_service=carrier.get("oosDate") is not None,
        
        # Company Details
        entity_type=carrier.get("carrierOperation", {}).get("carrierOperationDesc") if isinstance(carrier.get("carrierOperation"), dict) else carrier.get("carrierOperationDesc"),
        operating_status=carrier.get("statusCode"),
        mcs150_form_date=carrier.get("mcs150FormDate"),
        
        # Fleet Information
        total_drivers=carrier.get("totalDrivers"),
        total_power_units=carrier.get("totalPowerUnits"),
        
        # Safety Data
        safety_rating=carrier.get("safetyRating"),
        safety_rating_date=carrier.get("safetyRatingDate"),
        
        # BASIC Scores
        unsafe_driving_basic=carrier.get("unsafeDrivingBasic"),
        hours_of_service_basic=carrier.get("hosBasic"),
        driver_fitness_basic=carrier.get("driverFitnessBasic"),
        controlled_substances_basic=carrier.get("controlledSubstanceBasic"),
        vehicle_maintenance_basic=carrier.get("vehicleMaintenanceBasic"),
        hazmat_basic=carrier.get("hazmatBasic"),
        crash_indicator_basic=carrier.get("crashIndicatorBasic"),
        
        # Crash Data
        fatal_crashes=fatal,
        injury_crashes=injury,
        tow_crashes=tow,
        total_crashes=fatal + injury + tow,
        
        # Inspection Data
        vehicle_inspections=carrier.get("vehicleInsp"),
        driver_inspections=carrier.get("driverInsp"),
        vehicle_oos_rate=carrier.get("vehicleOosRate"),
        driver_oos_rate=carrier.get("driverOosRate"),
        
        # Authority/Insurance
        common_authority=carrier.get("commonAuthorityStatus"),
        contract_authority=carrier.get("contractAuthorityStatus"),
        broker_authority=carrier.get("brokerAuthorityStatus"),
        insurance_bipd=carrier.get("bipdInsuranceOnFile"),
        insurance_cargo=carrier.get("cargoInsuranceOnFile"),
        insurance_bond=carrier.get("bondInsuranceOnFile"),
        
        # Cargo Types
        cargo_carried=cargo_carried if cargo_carried else None,
        
        # Additional Info
        complaint_count=carrier.get("complaintCount"),
        mailing_address=mailing_address or None
    )


@router.get("/carrier/dot/{dot_number}")
async def lookup_by_dot(
    dot_number: str,
    full_details: bool = False,
    current_user: User = Depends(get_current_user)
):
    """Lookup carrier by DOT number"""
    if not FMCSA_API_KEY:
        raise HTTPException(status_code=500, detail="FMCSA API key not configured")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{FMCSA_BASE_URL}/carriers/{dot_number}",
                params={"webKey": FMCSA_API_KEY}
            )
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"No carrier found with DOT# {dot_number}")
            elif response.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid FMCSA API key")
            elif response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="FMCSA API error")
            
            data = response.json()
            
            # Check if content is null (carrier not found)
            if data.get("content") is None:
                raise HTTPException(status_code=404, detail=f"No carrier found with DOT# {dot_number}")
            
            if full_details:
                return {"carrier": parse_carrier_full(data).dict(exclude_none=True)}
            else:
                return {"carrier": parse_carrier_basic(data).dict(exclude_none=True)}
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="FMCSA API timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to connect to FMCSA API: {str(e)}")


@router.get("/carrier/mc/{mc_number}")
async def lookup_by_mc(
    mc_number: str,
    full_details: bool = False,
    current_user: User = Depends(get_current_user)
):
    """Lookup carrier by MC number (docket number)"""
    if not FMCSA_API_KEY:
        raise HTTPException(status_code=500, detail="FMCSA API key not configured")
    
    # Clean MC number (remove MC- prefix if present)
    clean_mc = mc_number.replace("MC-", "").replace("MC", "").strip()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{FMCSA_BASE_URL}/carriers/docket-number/{clean_mc}",
                params={"webKey": FMCSA_API_KEY}
            )
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"No carrier found with MC# {mc_number}")
            elif response.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid FMCSA API key")
            elif response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="FMCSA API error")
            
            data = response.json()
            
            # Check if content is null (carrier not found)
            if data.get("content") is None:
                raise HTTPException(status_code=404, detail=f"No carrier found with MC# {mc_number}")
            
            if full_details:
                return {"carrier": parse_carrier_full(data).dict(exclude_none=True)}
            else:
                return {"carrier": parse_carrier_basic(data).dict(exclude_none=True)}
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="FMCSA API timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to connect to FMCSA API: {str(e)}")


@router.get("/carrier/search")
async def search_by_name(
    name: str = Query(..., min_length=2, description="Company name to search"),
    full_details: bool = False,
    limit: int = Query(default=10, le=50, description="Max results (up to 50)"),
    current_user: User = Depends(get_current_user)
):
    """Search carriers by company name"""
    if not FMCSA_API_KEY:
        raise HTTPException(status_code=500, detail="FMCSA API key not configured")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{FMCSA_BASE_URL}/carriers/name/{name}",
                params={
                    "webKey": FMCSA_API_KEY,
                    "start": 0,
                    "size": limit
                }
            )
            
            if response.status_code == 404:
                return {"carriers": [], "total": 0}
            elif response.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid FMCSA API key")
            elif response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="FMCSA API error")
            
            data = response.json()
            content = data.get("content", [])
            
            if content is None:
                return {"carriers": [], "total": 0}
            
            # Parse results - for search, each item has a 'carrier' key
            carriers = []
            for item in content:
                if item is None:
                    continue
                # Each search result is wrapped in {"carrier": {...}}
                carrier_info = item.get("carrier", {})
                if not carrier_info:
                    continue
                    
                # Build physical address
                phy_address_parts = [
                    carrier_info.get("phyStreet", ""),
                    carrier_info.get("phyCity", ""),
                    carrier_info.get("phyState", ""),
                    carrier_info.get("phyZipcode", "")
                ]
                physical_address = ", ".join([p for p in phy_address_parts if p])
                
                carrier_result = {
                    "dot_number": str(carrier_info.get("dotNumber", "")) if carrier_info.get("dotNumber") else None,
                    "mc_number": str(carrier_info.get("mcNumber", "")) if carrier_info.get("mcNumber") else None,
                    "legal_name": carrier_info.get("legalName"),
                    "dba_name": carrier_info.get("dbaName"),
                    "physical_address": physical_address or None,
                    "phone": carrier_info.get("telephone"),
                    "allow_to_operate": carrier_info.get("allowedToOperate"),
                    "out_of_service": carrier_info.get("oosDate") is not None
                }
                
                if full_details:
                    carrier_result.update({
                        "entity_type": carrier_info.get("carrierOperation", {}).get("carrierOperationDesc") if carrier_info.get("carrierOperation") else None,
                        "operating_status": carrier_info.get("statusCode"),
                        "total_drivers": carrier_info.get("totalDrivers"),
                        "total_power_units": carrier_info.get("totalPowerUnits"),
                        "fatal_crashes": carrier_info.get("fatalCrash"),
                        "injury_crashes": carrier_info.get("injCrash"),
                        "tow_crashes": carrier_info.get("towawayCrash"),
                        "total_crashes": carrier_info.get("crashTotal"),
                    })
                
                # Filter out None values
                carrier_result = {k: v for k, v in carrier_result.items() if v is not None}
                carriers.append(carrier_result)
            
            return {
                "carriers": carriers,
                "total": len(carriers)
            }
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="FMCSA API timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to connect to FMCSA API: {str(e)}")


@router.get("/carrier/lookup")
async def universal_lookup(
    query: str = Query(..., min_length=1, description="DOT#, MC#, or company name"),
    search_type: str = Query(default="auto", description="Search type: auto, dot, mc, name"),
    full_details: bool = False,
    current_user: User = Depends(get_current_user)
):
    """
    Universal carrier lookup - automatically detects search type
    - If query is numeric, tries DOT# first, then MC#
    - If query starts with MC or DOT, uses appropriate lookup
    - Otherwise, searches by company name
    """
    if not FMCSA_API_KEY:
        raise HTTPException(status_code=500, detail="FMCSA API key not configured")
    
    query = query.strip()
    
    # Auto-detect search type
    if search_type == "auto":
        if query.upper().startswith("DOT"):
            search_type = "dot"
            query = query.upper().replace("DOT-", "").replace("DOT", "").strip()
        elif query.upper().startswith("MC"):
            search_type = "mc"
            query = query.upper().replace("MC-", "").replace("MC", "").strip()
        elif query.isdigit():
            search_type = "dot"  # Default to DOT for numeric queries
        else:
            search_type = "name"
    
    if search_type == "dot":
        return await lookup_by_dot(query, full_details, current_user)
    elif search_type == "mc":
        return await lookup_by_mc(query, full_details, current_user)
    else:
        return await search_by_name(query, full_details, 10, current_user)
