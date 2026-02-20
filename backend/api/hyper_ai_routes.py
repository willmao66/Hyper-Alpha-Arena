"""
Hyper AI Routes - API endpoints for Hyper AI main agent

Endpoints:
- GET  /api/hyper-ai/providers - List available LLM providers
- GET  /api/hyper-ai/profile - Get user profile and LLM config status
- POST /api/hyper-ai/profile/llm - Save LLM configuration (with connection test)
- POST /api/hyper-ai/test-connection - Test LLM connection without saving
- POST /api/hyper-ai/profile/preferences - Save trading preferences
- GET  /api/hyper-ai/conversations - List conversations
- POST /api/hyper-ai/conversations - Create new conversation
- GET  /api/hyper-ai/conversations/{id}/messages - Get conversation messages
- POST /api/hyper-ai/chat - Start chat (returns task_id for polling)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import HyperAiConversation
from services.hyper_ai_service import (
    get_or_create_profile,
    get_llm_config,
    save_llm_config,
    test_llm_connection,
    get_or_create_conversation,
    get_conversation_messages,
    start_chat_task,
    start_onboarding_chat_task
)
from services.hyper_ai_llm_providers import get_all_providers, get_provider

router = APIRouter(prefix="/api/hyper-ai", tags=["Hyper AI"])


# Request/Response models
class LLMConfigRequest(BaseModel):
    provider: str
    api_key: str
    model: Optional[str] = None
    base_url: Optional[str] = None


class PreferencesRequest(BaseModel):
    trading_style: Optional[str] = None
    risk_preference: Optional[str] = None
    experience_level: Optional[str] = None
    preferred_symbols: Optional[str] = None
    preferred_timeframe: Optional[str] = None
    capital_scale: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    mode: Optional[str] = None  # "onboarding" for profile collection
    lang: Optional[str] = None  # "zh" or "en" for language preference


# Endpoints
@router.get("/providers")
def list_providers():
    """List all available LLM providers with their configurations."""
    return {"providers": get_all_providers()}


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    """Get user profile including LLM config status and trading preferences."""
    profile = get_or_create_profile(db)
    llm_config = get_llm_config(db)

    # Get base_url for display
    base_url = llm_config.get("base_url", "") if llm_config.get("configured") else ""

    return {
        "llm_configured": llm_config.get("configured", False),
        "llm_provider": profile.llm_provider,
        "llm_model": profile.llm_model,
        "llm_base_url": base_url,
        "onboarding_completed": profile.onboarding_completed,
        "nickname": profile.nickname,
        "trading_style": profile.trading_style,
        "risk_preference": profile.risk_preference,
        "experience_level": profile.experience_level,
        "preferred_symbols": profile.preferred_symbols,
        "preferred_timeframe": profile.preferred_timeframe,
        "capital_scale": profile.capital_scale,
    }


class TestConnectionRequest(BaseModel):
    provider: str
    api_key: str
    model: Optional[str] = None
    base_url: Optional[str] = None


@router.post("/test-connection")
def test_connection(request: TestConnectionRequest):
    """Test LLM connection without saving configuration."""
    # Validate provider
    if request.provider != "custom":
        provider = get_provider(request.provider)
        if not provider:
            raise HTTPException(status_code=400, detail="Invalid provider")

    # For custom provider, base_url is required
    if request.provider == "custom" and not request.base_url:
        raise HTTPException(
            status_code=400,
            detail="base_url is required for custom provider"
        )

    # Get default model if not provided
    model = request.model
    if not model and request.provider != "custom":
        provider = get_provider(request.provider)
        if provider and provider.models:
            model = provider.models[0]

    result = test_llm_connection(
        provider=request.provider,
        api_key=request.api_key,
        model=model or "",
        base_url=request.base_url
    )

    return result


@router.post("/profile/llm")
def save_llm_configuration(request: LLMConfigRequest, db: Session = Depends(get_db)):
    """Save LLM provider configuration after testing connection."""
    # Validate provider
    if request.provider != "custom":
        provider = get_provider(request.provider)
        if not provider:
            raise HTTPException(status_code=400, detail="Invalid provider")

    # For custom provider, base_url is required
    if request.provider == "custom" and not request.base_url:
        raise HTTPException(
            status_code=400,
            detail="base_url is required for custom provider"
        )

    # Get default model if not provided
    model = request.model
    if not model and request.provider != "custom":
        provider = get_provider(request.provider)
        if provider and provider.models:
            model = provider.models[0]

    # Test connection before saving
    test_result = test_llm_connection(
        provider=request.provider,
        api_key=request.api_key,
        model=model or "",
        base_url=request.base_url
    )

    if not test_result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=test_result.get("error", "Connection test failed")
        )

    # Save configuration
    profile = save_llm_config(
        db,
        provider=request.provider,
        api_key=request.api_key,
        model=model,
        base_url=request.base_url
    )

    return {"success": True, "provider": profile.llm_provider, "model": profile.llm_model}


@router.post("/profile/preferences")
def save_preferences(request: PreferencesRequest, db: Session = Depends(get_db)):
    """Save trading preferences and mark onboarding as completed."""
    profile = get_or_create_profile(db)

    if request.trading_style is not None:
        profile.trading_style = request.trading_style
    if request.risk_preference is not None:
        profile.risk_preference = request.risk_preference
    if request.experience_level is not None:
        profile.experience_level = request.experience_level
    if request.preferred_symbols is not None:
        profile.preferred_symbols = request.preferred_symbols
    if request.preferred_timeframe is not None:
        profile.preferred_timeframe = request.preferred_timeframe
    if request.capital_scale is not None:
        profile.capital_scale = request.capital_scale

    # Mark onboarding as completed if we have basic info
    if profile.trading_style and profile.risk_preference:
        profile.onboarding_completed = True

    db.commit()
    db.refresh(profile)

    return {
        "success": True,
        "onboarding_completed": profile.onboarding_completed
    }


@router.get("/conversations")
def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List recent conversations (excluding onboarding conversations)."""
    conversations = db.query(HyperAiConversation).filter(
        HyperAiConversation.is_onboarding != True
    ).order_by(
        HyperAiConversation.updated_at.desc()
    ).limit(limit).all()

    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "message_count": c.message_count,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in conversations
        ]
    }


@router.post("/conversations")
def create_conversation(db: Session = Depends(get_db)):
    """Create a new conversation."""
    conv = get_or_create_conversation(db)
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat() if conv.created_at else None
    }


@router.get("/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get messages from a conversation."""
    messages = get_conversation_messages(db, conversation_id, limit)
    return {"messages": messages}


@router.post("/chat")
def start_chat(request: ChatRequest, db: Session = Depends(get_db)):
    """
    Start a chat with Hyper AI.
    Returns task_id for polling via /api/ai-stream/{task_id}.

    mode="onboarding" uses a special prompt for profile collection.
    """
    # Check LLM config
    llm_config = get_llm_config(db)
    if not llm_config.get("configured"):
        raise HTTPException(
            status_code=400,
            detail="LLM not configured. Please complete onboarding first."
        )

    # Get or create conversation (mark as onboarding if in onboarding mode)
    is_onboarding = request.mode == "onboarding"
    conv = get_or_create_conversation(db, request.conversation_id, is_onboarding=is_onboarding)

    # Start background task based on mode
    if is_onboarding:
        task_id = start_onboarding_chat_task(db, conv.id, request.message, request.lang)
    else:
        task_id = start_chat_task(db, conv.id, request.message, request.lang)

    return {
        "task_id": task_id,
        "conversation_id": conv.id
    }


# Memory endpoints
@router.get("/memories")
def list_memories(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List user memories, optionally filtered by category."""
    from services.hyper_ai_memory_service import get_memories, MEMORY_CATEGORIES

    if category and category not in MEMORY_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Valid: {MEMORY_CATEGORIES}")

    memories = get_memories(db, category=category, limit=limit)
    return {"memories": memories, "categories": MEMORY_CATEGORIES}


@router.delete("/memories/{memory_id}")
def delete_memory_endpoint(memory_id: int, db: Session = Depends(get_db)):
    """Delete (deactivate) a memory."""
    from services.hyper_ai_memory_service import delete_memory

    success = delete_memory(db, memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True}
