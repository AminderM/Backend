from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from models import User
from auth import get_current_user
from database import db
from datetime import datetime, timezone
import uuid
import os
import asyncio
from openai import AsyncOpenAI

router = APIRouter(prefix="/tms-chat", tags=["TMS Chat"])

class ChatMessage(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = "general"  # dispatch, accounting, sales, hr, maintenance, safety

# Role-based access control for departments
ROLE_DEPARTMENT_ACCESS = {
    "dispatcher": ["dispatch"],
    "driver": ["dispatch", "safety"],
    "company_admin": ["dispatch", "accounting", "sales", "hr", "maintenance", "safety"],
    "platform_admin": ["dispatch", "accounting", "sales", "hr", "maintenance", "safety"],
    "fleet_owner": ["dispatch", "accounting", "sales", "hr", "maintenance", "safety"]
}

CONTEXT_SYSTEM_MESSAGES = {
    "dispatch": """You are a TMS Dispatch Operations AI Assistant for authorized dispatch personnel only.
Help ONLY with dispatch-related topics:
- Route planning and optimization
- Load assignment and scheduling
- Driver dispatch and coordination
- Real-time tracking and updates
- Delivery status monitoring

IMPORTANT: If asked about accounting, sales, HR, maintenance, or other non-dispatch topics, politely decline and remind the user you can only help with dispatch operations.
Provide concise, actionable advice for dispatch operations only.""",
    
    "accounting": """You are a TMS Accounting AI Assistant for authorized accounting personnel only.
Help ONLY with accounting and financial topics:
- Invoice generation and management
- Payment tracking and reconciliation
- Financial reporting
- Cost analysis and budgeting
- Expense management

IMPORTANT: If asked about dispatch, sales, HR, or other non-accounting topics, politely decline and remind the user you can only help with accounting matters.
Provide accurate financial guidance for transportation operations only.""",
    
    "sales": """You are a TMS Sales & Business Development AI Assistant for authorized sales personnel only.
Help ONLY with sales and customer-related topics:
- Lead generation strategies
- Customer relationship management (CRM)
- Rate quotes and negotiations
- Market analysis
- Business growth opportunities
- Customer communications

IMPORTANT: If asked about dispatch, accounting, HR, or other non-sales topics, politely decline and remind the user you can only help with sales and CRM matters.
Provide strategic sales and business development advice only.""",
    
    "hr": """You are a TMS Human Resources AI Assistant for authorized HR personnel only.
Help ONLY with human resources topics:
- Driver recruitment and onboarding
- Employee management
- Training and compliance
- Performance evaluation
- Payroll and benefits
- Employee relations

IMPORTANT: If asked about dispatch, accounting, sales, or other non-HR topics, politely decline and remind the user you can only help with HR matters.
Provide HR guidance for transportation workforce management only.""",
    
    "maintenance": """You are a TMS Fleet Maintenance AI Assistant for authorized maintenance personnel only.
Help ONLY with fleet maintenance topics:
- Preventive maintenance scheduling
- Vehicle inspection and repairs
- Maintenance cost tracking
- Equipment lifecycle management
- Breakdown prevention
- Parts inventory

IMPORTANT: If asked about dispatch, accounting, sales, HR, or other non-maintenance topics, politely decline and remind the user you can only help with fleet maintenance.
Provide technical guidance for fleet maintenance operations only.""",
    
    "safety": """You are a TMS Fleet Safety AI Assistant for authorized safety personnel only.
Help ONLY with safety and compliance topics:
- Safety compliance (FMCSA, DOT)
- Accident prevention and investigation
- Driver safety training
- Vehicle safety inspections
- Safety metrics and reporting
- Regulatory compliance

IMPORTANT: If asked about dispatch, accounting, sales, HR, or maintenance topics, politely decline and remind the user you can only help with safety matters.
Provide safety-focused guidance for transportation operations only.""",
    
    "general": """You are a comprehensive TMS (Transportation Management System) AI Assistant. 
You help with dispatch operations, accounting, sales, HR, fleet maintenance, and safety.
Provide helpful, accurate, and actionable advice for transportation and logistics operations."""
}

@router.post("/message")
async def send_chat_message(
    chat_request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """Send a message and get AI response with role-based access control"""
    try:
        # Check role-based access to department
        user_role = current_user.role.lower()
        allowed_departments = ROLE_DEPARTMENT_ACCESS.get(user_role, [])
        
        # Platform admin and company admin have access to all departments
        if user_role not in ["platform_admin", "company_admin", "fleet_owner"]:
            if chat_request.context not in allowed_departments:
                return {
                    "success": False,
                    "error": f"Access denied. Your role ({user_role}) does not have access to {chat_request.context} department. You can only access: {', '.join(allowed_departments)}"
                }
        
        # Lazy import to avoid issues if not installed
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="TMS chat requires emergentintegrations package (not installed)."
            )
        
        # Get or create session ID for this user
        session_id = f"tms-chat-{current_user.id}-{chat_request.context}"
        
        # Get context-specific system message with role enforcement
        system_message = CONTEXT_SYSTEM_MESSAGES.get(
            chat_request.context, 
            CONTEXT_SYSTEM_MESSAGES["general"]
        )
        
        # Add role-specific instruction
        role_instruction = f"\n\nCURRENT USER ROLE: {user_role.upper()}\n"
        if user_role in ["dispatcher", "driver"]:
            role_instruction += "This user has LIMITED access. Only answer questions relevant to their assigned department. Do not provide information from other departments."
        elif user_role in ["company_admin", "fleet_owner", "platform_admin"]:
            role_instruction += "This user has FULL access to all departments and can ask about any aspect of the business."
        
        system_message = system_message + role_instruction
        
        # Get OpenAI API key from environment
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        if not openai_api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        # Initialize OpenAI client
        client = AsyncOpenAI(api_key=openai_api_key)
        
        # Retrieve chat history for context
        history_docs = await db.tms_chat_history.find(
            {"user_id": current_user.id, "session_id": session_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(10).to_list(10)
        
        # Build messages array with history
        messages = [{"role": "system", "content": system_message}]
        
        # Add recent history (reversed to chronological order)
        for doc in reversed(history_docs):
            messages.append({"role": "user", "content": doc["user_message"]})
            messages.append({"role": "assistant", "content": doc["assistant_response"]})
        
        # Add current message
        messages.append({"role": "user", "content": chat_request.message})
        
        # Call OpenAI API with GPT-4o
        completion = await client.chat.completions.create(
            model="gpt-4o",  # Using GPT-4o (latest available model)
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        response = completion.choices[0].message.content
        
        # Save to database
        chat_history_entry = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.id,
            "session_id": session_id,
            "context": chat_request.context,
            "user_message": chat_request.message,
            "assistant_response": response,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await db.tms_chat_history.insert_one(chat_history_entry)
        
        return {
            "success": True,
            "response": response,
            "context": chat_request.context
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

@router.get("/history")
async def get_chat_history(
    context: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get chat history for current user"""
    try:
        query = {"user_id": current_user.id}
        if context:
            query["context"] = context
        
        history = await db.tms_chat_history.find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        
        return {
            "success": True,
            "history": history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching history: {str(e)}")

@router.delete("/history")
async def clear_chat_history(
    context: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Clear chat history for current user"""
    try:
        query = {"user_id": current_user.id}
        if context:
            query["context"] = context
        
        result = await db.tms_chat_history.delete_many(query)
        
        return {
            "success": True,
            "deleted_count": result.deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing history: {str(e)}")
