from fastapi import APIRouter, HTTPException, Depends
from models import User, UserRole
from auth import get_current_user
from database import db
from datetime import datetime, timezone
import os
import uuid

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    EMERGENT_AVAILABLE = True
except ImportError:
    EMERGENT_AVAILABLE = False

router = APIRouter(prefix="/driver-mobile/ai", tags=["Driver AI Assistant"])

# Store chat sessions in memory (for production, use Redis or DB)
chat_sessions = {}

def get_driver_context(loads: list) -> str:
    """Build context string from driver's loads"""
    if not loads:
        return "You have no loads currently assigned."
    
    context = "Here are your current loads:\n\n"
    for load in loads:
        context += f"""
Load {load.get('order_number', load.get('id', 'Unknown')[:8])}:
- Status: {load.get('status', 'Unknown')}
- Pickup: {load.get('pickup_city', 'N/A')}, {load.get('pickup_state', 'N/A')} - {load.get('pickup_location', 'N/A')}
- Delivery: {load.get('delivery_city', 'N/A')}, {load.get('delivery_state', 'N/A')} - {load.get('delivery_location', 'N/A')}
- Equipment: {load.get('equipment_type', 'N/A')}
- Weight: {load.get('weight', 'N/A')} lbs
- Commodity: {load.get('commodity', 'N/A')}
- Pickup Time: {load.get('pickup_time_planned', 'TBD')}
- Delivery Time: {load.get('delivery_time_planned', 'TBD')}
"""
    return context

SYSTEM_PROMPT = """You are an AI Assistant for truck drivers using a TMS (Transportation Management System) mobile app. 

Your role is to:
1. Answer questions about the driver's assigned loads
2. Provide information about routes, pickup/delivery locations, and times
3. Help with load status and requirements
4. Be concise and mobile-friendly in your responses

You have access to the driver's current load information. Be helpful, professional, and brief since drivers are often on the road.

When asked about a specific load (like "ORD-001" or "What's my next pickup?"), refer to the load data provided.

Keep responses SHORT and ACTIONABLE - drivers need quick answers.

{driver_context}
"""

@router.post("/chat")
async def chat_with_assistant(
    message_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Send a message to the AI Assistant"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    user_message = message_data.get("message", "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")
    
    # Get driver's loads for context
    loads = await db.loads.find(
        {"assigned_driver_id": current_user.id},
        {"_id": 0}
    ).to_list(50)
    
    # Also check bookings
    bookings = await db.bookings.find(
        {"driver_id": current_user.id},
        {"_id": 0}
    ).to_list(50)
    
    all_loads = loads + bookings
    driver_context = get_driver_context(all_loads)
    
    # Get or create chat session
    session_id = f"driver_{current_user.id}"
    
    try:
        if not EMERGENT_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="AI assistant is not available (emergentintegrations package not installed). Install it or use OpenAI directly."
            )
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="LLM API key not configured")
        
        # Create chat instance
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=SYSTEM_PROMPT.format(driver_context=driver_context)
        ).with_model("openai", "gpt-5.2")
        
        # Send message
        llm_message = UserMessage(text=user_message)
        response = await chat.send_message(llm_message)
        
        # Store in database for history
        chat_record = {
            "id": str(uuid.uuid4()),
            "driver_id": current_user.id,
            "session_id": session_id,
            "user_message": user_message,
            "assistant_response": response,
            "created_at": datetime.now(timezone.utc)
        }
        await db.driver_ai_chats.insert_one(chat_record)
        
        return {
            "response": response,
            "message_id": chat_record["id"]
        }
        
    except Exception as e:
        print(f"AI Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI Assistant error: {str(e)}")

@router.get("/history")
async def get_chat_history(
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    """Get chat history for the driver"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    history = await db.driver_ai_chats.find(
        {"driver_id": current_user.id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    # Reverse to show oldest first
    return list(reversed(history))

@router.delete("/history")
async def clear_chat_history(current_user: User = Depends(get_current_user)):
    """Clear chat history for the driver"""
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Driver access only")
    
    await db.driver_ai_chats.delete_many({"driver_id": current_user.id})
    return {"message": "Chat history cleared"}
