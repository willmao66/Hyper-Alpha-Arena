"""
Hyper AI Service - Main Agent for Full-Site AI Intelligence

Hyper AI is the master agent that:
- Guides users through onboarding to collect trading preferences
- Maintains user profile and memory across conversations
- Orchestrates sub-agents (Prompt AI, Program AI, Signal AI, Attribution AI)
- Implements context compression for long conversations
- Supports multiple LLM providers with user selection

Architecture:
- StreamBuffer-based async streaming (same as other AI services)
- Memory retrieval via tools, not context injection
- Mem0-style deduplication for memory management
- Context compression at 80% of context window
"""
import json
import logging
import os
import random
import time
from typing import Any, Dict, Generator, List, Optional

import requests
from sqlalchemy.orm import Session

from database.models import (
    HyperAiProfile,
    HyperAiMemory,
    HyperAiConversation,
    HyperAiMessage
)
from services.ai_decision_service import (
    build_chat_completion_endpoints,
    detect_api_format,
    _extract_text_from_message,
    get_max_tokens
)
from services.ai_stream_service import (
    get_buffer_manager,
    generate_task_id,
    run_ai_task_in_background,
    format_sse_event
)
from services.hyper_ai_llm_providers import get_provider, get_all_providers
from utils.encryption import decrypt_private_key

logger = logging.getLogger(__name__)

# Retry configuration
API_MAX_RETRIES = 5
API_BASE_DELAY = 1.0
API_MAX_DELAY = 16.0
RETRYABLE_STATUS_CODES = {502, 503, 504, 429}

# System prompt paths
SYSTEM_PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "hyper_ai_system_prompt.md"
)
ONBOARDING_PROMPT_EN_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "hyper_ai_onboarding_prompt.md"
)
ONBOARDING_PROMPT_ZH_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "hyper_ai_onboarding_prompt_zh.md"
)


def _should_retry_api(status_code: Optional[int], error: Optional[str]) -> bool:
    """Check if API error is retryable."""
    if status_code and status_code in RETRYABLE_STATUS_CODES:
        return True
    if error and any(x in error.lower() for x in ['timeout', 'connection', 'reset']):
        return True
    return False


def _get_retry_delay(attempt: int) -> float:
    """Calculate retry delay with exponential backoff and jitter."""
    delay = min(API_BASE_DELAY * (2 ** attempt), API_MAX_DELAY)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


def load_system_prompt() -> str:
    """Load the Hyper AI system prompt from markdown file."""
    try:
        with open(SYSTEM_PROMPT_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load Hyper AI system prompt: {e}")
        return "You are Hyper AI, an intelligent trading assistant."


def load_onboarding_prompt(lang: str = "en") -> str:
    """Load the onboarding-specific system prompt based on language."""
    prompt_path = ONBOARDING_PROMPT_ZH_PATH if lang == "zh" else ONBOARDING_PROMPT_EN_PATH
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load onboarding prompt ({lang}): {e}")
        if lang == "zh":
            return DEFAULT_ONBOARDING_PROMPT_ZH
        return DEFAULT_ONBOARDING_PROMPT_EN


DEFAULT_ONBOARDING_PROMPT_EN = """You are Hyper AI, a friendly trading assistant helping a new user get started.

Your goal is to have a natural conversation to learn about the user's trading background and preferences.

Information to collect (through natural conversation, not interrogation):
- Trading experience level (beginner/intermediate/advanced)
- Risk preference (conservative/moderate/aggressive)
- Trading style (day trading/swing trading/position trading/scalping)
- Preferred trading symbols (BTC, ETH, SOL, etc.)

Be warm, conversational, and helpful. Ask follow-up questions naturally.
When you have enough information, let the user know they're all set to explore the system.
"""

DEFAULT_ONBOARDING_PROMPT_ZH = """你是 Hyper AI，一个友好的交易助手，正在帮助新用户入门。

你的目标是通过自然的对话了解用户的交易背景和偏好。

需要收集的信息（通过自然对话，而不是审问）：
- 交易经验水平（新手/有一定经验/资深）
- 风险偏好（保守/稳健/激进）
- 交易风格（日内交易/波段交易/趋势交易/超短线）
- 偏好的交易品种（BTC、ETH、SOL 等）

保持温暖、对话式的风格，自然地提出后续问题。
当你收集到足够的信息后，告诉用户他们已经准备好探索系统了。
"""


def get_or_create_profile(db: Session) -> HyperAiProfile:
    """Get existing profile or create a new one (single-user system)."""
    profile = db.query(HyperAiProfile).first()
    if not profile:
        profile = HyperAiProfile()
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def get_llm_config(db: Session) -> Dict[str, Any]:
    """Get LLM configuration from user profile."""
    profile = get_or_create_profile(db)

    if not profile.llm_provider:
        return {"configured": False}

    # Get provider preset or use custom config
    provider = get_provider(profile.llm_provider)
    base_url = profile.llm_base_url or (provider.base_url if provider else "")
    model = profile.llm_model or (provider.models[0] if provider and provider.models else "")

    # Decrypt API key
    api_key = None
    if profile.llm_api_key_encrypted:
        try:
            api_key = decrypt_private_key(profile.llm_api_key_encrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {e}")

    return {
        "configured": True,
        "provider": profile.llm_provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "api_format": provider.api_format if provider else "openai"
    }


def save_llm_config(
    db: Session,
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None
) -> HyperAiProfile:
    """Save LLM configuration to user profile."""
    from utils.encryption import encrypt_private_key

    profile = get_or_create_profile(db)
    profile.llm_provider = provider
    profile.llm_model = model
    profile.llm_base_url = base_url

    if api_key:
        profile.llm_api_key_encrypted = encrypt_private_key(api_key)

    db.commit()
    db.refresh(profile)
    return profile


def get_or_create_conversation(
    db: Session,
    conversation_id: Optional[int] = None,
    is_onboarding: bool = False
) -> HyperAiConversation:
    """Get existing conversation or create a new one."""
    if conversation_id:
        conv = db.query(HyperAiConversation).filter(
            HyperAiConversation.id == conversation_id
        ).first()
        if conv:
            return conv

    # Create new conversation
    conv = HyperAiConversation(title="Hyper AI Chat", is_onboarding=is_onboarding)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation_messages(
    db: Session,
    conversation_id: int,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get recent messages from a conversation."""
    messages = db.query(HyperAiMessage).filter(
        HyperAiMessage.conversation_id == conversation_id
    ).order_by(HyperAiMessage.created_at.desc()).limit(limit).all()

    return [
        {
            "role": msg.role,
            "content": msg.content,
            "reasoning_snapshot": msg.reasoning_snapshot,
            "tool_calls_log": msg.tool_calls_log,
            "is_complete": msg.is_complete,
            "created_at": msg.created_at.isoformat() if msg.created_at else None
        }
        for msg in reversed(messages)
    ]


def save_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    reasoning_snapshot: Optional[str] = None,
    tool_calls_log: Optional[str] = None,
    is_complete: bool = True,
    interrupt_reason: Optional[str] = None
) -> HyperAiMessage:
    """Save a message to the conversation."""
    message = HyperAiMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        reasoning_snapshot=reasoning_snapshot,
        tool_calls_log=tool_calls_log,
        is_complete=is_complete,
        interrupt_reason=interrupt_reason
    )
    db.add(message)

    # Update conversation message count
    conv = db.query(HyperAiConversation).filter(
        HyperAiConversation.id == conversation_id
    ).first()
    if conv:
        conv.message_count = (conv.message_count or 0) + 1

    db.commit()
    db.refresh(message)
    return message


def build_messages_for_api(
    db: Session,
    conversation_id: int,
    user_message: str,
    api_config: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Build message list for LLM API call with automatic compression."""
    from services.ai_context_compression_service import compress_messages

    messages = []

    # System prompt
    system_prompt = load_system_prompt()
    messages.append({"role": "system", "content": system_prompt})

    # Get profile context for personalization
    profile = get_or_create_profile(db)
    if profile.onboarding_completed:
        profile_context = _build_profile_context(profile)
        if profile_context:
            messages.append({
                "role": "system",
                "content": f"User Profile:\n{profile_context}"
            })

    # Conversation history (get more messages, compression will handle limits)
    history = get_conversation_messages(db, conversation_id, limit=100)
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Current user message
    messages.append({"role": "user", "content": user_message})

    # Apply compression if needed
    messages = compress_messages(messages, api_config, db=db)

    return messages


def _build_profile_context(profile: HyperAiProfile) -> str:
    """Build profile context string for system prompt."""
    parts = []
    if profile.trading_style:
        parts.append(f"Trading Style: {profile.trading_style}")
    if profile.risk_preference:
        parts.append(f"Risk Preference: {profile.risk_preference}")
    if profile.experience_level:
        parts.append(f"Experience Level: {profile.experience_level}")
    if profile.preferred_symbols:
        parts.append(f"Preferred Symbols: {profile.preferred_symbols}")
    if profile.preferred_timeframe:
        parts.append(f"Preferred Timeframe: {profile.preferred_timeframe}")
    if profile.capital_scale:
        parts.append(f"Capital Scale: {profile.capital_scale}")
    return "\n".join(parts)


def stream_chat_response(
    db: Session,
    conversation_id: int,
    user_message: str
) -> Generator[str, None, None]:
    """
    Stream chat response from LLM.
    Yields SSE-formatted events.
    """
    # Get LLM config
    llm_config = get_llm_config(db)
    if not llm_config.get("configured"):
        yield format_sse_event("error", {
            "message": "LLM not configured. Please complete onboarding first."
        })
        return

    # Save user message
    save_message(db, conversation_id, "user", user_message)

    # Build messages (with automatic compression)
    messages = build_messages_for_api(db, conversation_id, user_message, llm_config)

    # Prepare API call
    base_url = llm_config["base_url"]
    model = llm_config["model"]
    api_key = llm_config["api_key"]
    api_format = llm_config.get("api_format", "openai")

    # Build endpoints
    endpoints = build_chat_completion_endpoints(base_url, model)
    if not endpoints:
        yield format_sse_event("error", {"message": "Invalid API endpoint"})
        return

    # Prepare request
    headers = {
        "Content-Type": "application/json",
    }

    if api_format == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    max_tokens = get_max_tokens(model)

    # Build request body based on API format
    if api_format == "anthropic":
        # Extract system message
        system_content = ""
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content += msg["content"] + "\n"
            else:
                api_messages.append(msg)

        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_content.strip(),
            "messages": api_messages,
            "stream": True
        }
    else:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": True
        }

    # Make API call with retry
    response = None
    last_error = None

    for attempt in range(API_MAX_RETRIES):
        for endpoint in endpoints:
            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=body,
                    stream=True,
                    timeout=120
                )

                if response.status_code == 200:
                    break
                elif _should_retry_api(response.status_code, None):
                    last_error = f"HTTP {response.status_code}"
                    continue
                else:
                    yield format_sse_event("error", {
                        "message": f"API error: {response.status_code}"
                    })
                    return

            except requests.exceptions.RequestException as e:
                last_error = str(e)
                if _should_retry_api(None, str(e)):
                    continue
                yield format_sse_event("error", {"message": str(e)})
                return

        if response and response.status_code == 200:
            break

        delay = _get_retry_delay(attempt)
        time.sleep(delay)

    if not response or response.status_code != 200:
        yield format_sse_event("error", {
            "message": f"API failed after retries: {last_error}"
        })
        return

    # Stream response
    yield from _process_stream_response(
        db, conversation_id, response, api_format
    )


def _process_stream_response(
    db: Session,
    conversation_id: int,
    response: requests.Response,
    api_format: str
) -> Generator[str, None, None]:
    """Process streaming response from LLM API."""
    content_parts = []
    reasoning_parts = []

    try:
        for line in response.iter_lines():
            if not line:
                continue

            line_str = line.decode('utf-8')
            if not line_str.startswith('data: '):
                continue

            data_str = line_str[6:]
            if data_str == '[DONE]':
                break

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # Extract content based on API format
            if api_format == "anthropic":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        content_parts.append(text)
                        yield format_sse_event("content", {"text": text})
            else:
                # OpenAI format
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        content_parts.append(text)
                        yield format_sse_event("content", {"text": text})

                    # Check for reasoning (some models)
                    reasoning = delta.get("reasoning_content", "")
                    if reasoning:
                        reasoning_parts.append(reasoning)
                        yield format_sse_event("reasoning", {"text": reasoning})

        # Save assistant message
        full_content = "".join(content_parts)
        full_reasoning = "".join(reasoning_parts) if reasoning_parts else None

        if full_content:
            save_message(
                db, conversation_id, "assistant", full_content,
                reasoning_snapshot=full_reasoning,
                is_complete=True
            )

        yield format_sse_event("done", {
            "conversation_id": conversation_id,
            "content_length": len(full_content)
        })

    except Exception as e:
        logger.error(f"Stream processing error: {e}", exc_info=True)
        yield format_sse_event("error", {"message": str(e)})


def start_chat_task(
    db: Session,
    conversation_id: int,
    user_message: str,
    lang: str = None
) -> str:
    """Start a chat task in background and return task_id."""
    task_id = generate_task_id("hyper")
    manager = get_buffer_manager()
    manager.create_task(task_id, conversation_id)

    def generator_func():
        from database.connection import SessionLocal
        task_db = SessionLocal()
        try:
            yield from stream_chat_response(task_db, conversation_id, user_message)
        finally:
            task_db.close()

    run_ai_task_in_background(task_id, generator_func)
    return task_id


def stream_onboarding_response(
    db: Session,
    conversation_id: int,
    user_message: str,
    lang: str = "en"
) -> Generator[str, None, None]:
    """Stream onboarding chat response - simplified version for profile collection."""
    llm_config = get_llm_config(db)
    if not llm_config.get("configured"):
        yield format_sse_event("error", {"message": "LLM not configured"})
        return

    # Handle greeting request - AI initiates conversation
    is_greeting = user_message == "__GREETING__"
    if is_greeting:
        user_message = "Please introduce yourself and start the onboarding conversation."
    else:
        # Save user message (don't save the greeting trigger)
        save_message(db, conversation_id, "user", user_message)

    # Build messages with onboarding prompt (language-specific)
    messages = []
    system_prompt = load_onboarding_prompt(lang)
    messages.append({"role": "system", "content": system_prompt})

    # Get conversation history (skip for greeting)
    if not is_greeting:
        history = get_conversation_messages(db, conversation_id, limit=20)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_message})

    # Make API call (reuse existing logic)
    base_url = llm_config["base_url"]
    model = llm_config["model"]
    api_key = llm_config["api_key"]
    api_format = llm_config.get("api_format", "openai")

    endpoints = build_chat_completion_endpoints(base_url, model)
    if not endpoints:
        yield format_sse_event("error", {"message": "Invalid API endpoint"})
        return

    headers = {"Content-Type": "application/json"}
    if api_format == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    max_tokens = get_max_tokens(model)

    if api_format == "anthropic":
        system_content = ""
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content += msg["content"] + "\n"
            else:
                api_messages.append(msg)
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_content.strip(),
            "messages": api_messages,
            "stream": True
        }
    else:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": True
        }

    response = None
    for attempt in range(API_MAX_RETRIES):
        for endpoint in endpoints:
            try:
                response = requests.post(
                    endpoint, headers=headers, json=body,
                    stream=True, timeout=120
                )
                if response.status_code == 200:
                    break
            except requests.exceptions.RequestException:
                continue
        if response and response.status_code == 200:
            break
        time.sleep(_get_retry_delay(attempt))

    if not response or response.status_code != 200:
        yield format_sse_event("error", {"message": "API request failed"})
        return

    yield from _process_onboarding_stream_response(db, conversation_id, response, api_format)


def start_onboarding_chat_task(
    db: Session,
    conversation_id: int,
    user_message: str,
    lang: str = None
) -> str:
    """Start an onboarding chat task in background."""
    task_id = generate_task_id("onboard")
    manager = get_buffer_manager()
    manager.create_task(task_id, conversation_id)

    # Default to English if not specified
    effective_lang = lang or "en"

    def generator_func():
        from database.connection import SessionLocal
        task_db = SessionLocal()
        try:
            yield from stream_onboarding_response(task_db, conversation_id, user_message, effective_lang)
        finally:
            task_db.close()

    run_ai_task_in_background(task_id, generator_func)
    return task_id


def _parse_profile_data(content: str) -> Optional[Dict[str, str]]:
    """Parse [PROFILE_DATA]...[COMPLETE] block from AI response with tolerance."""
    import re

    # Try multiple patterns for tolerance (different AI models may vary)
    patterns = [
        r'\[PROFILE_DATA\](.*?)\[COMPLETE\]',
        r'\[PROFILE_DATA\](.*?)\[/COMPLETE\]',
        r'\[PROFILE\](.*?)\[COMPLETE\]',
        r'\[PROFILE\](.*?)\[/PROFILE\]',
        r'```\s*\[PROFILE_DATA\](.*?)\[COMPLETE\]\s*```',  # In code block
    ]

    block = None
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            block = match.group(1).strip()
            break

    if not block:
        return None

    data = {}
    for line in block.split('\n'):
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            # Normalize common key variations
            if key in ['name', 'nickname', 'nick', '称呼', '昵称']:
                key = 'nickname'
            elif key in ['exp', 'experience', '经验', '交易经验']:
                key = 'experience'
            elif key in ['risk', 'risk_preference', '风险', '风险偏好']:
                key = 'risk'
            elif key in ['style', 'trading_style', '风格', '交易风格']:
                key = 'style'
            data[key] = value

    return data if data else None


def _strip_profile_markers(content: str) -> str:
    """Remove [PROFILE_DATA]...[COMPLETE] block from content for display."""
    import re

    # Remove various formats of profile data blocks
    patterns = [
        r'\[PROFILE_DATA\].*?\[COMPLETE\]',
        r'\[PROFILE_DATA\].*?\[/COMPLETE\]',
        r'\[PROFILE\].*?\[COMPLETE\]',
        r'\[PROFILE\].*?\[/PROFILE\]',
        r'```\s*\[PROFILE_DATA\].*?\[COMPLETE\]\s*```',
    ]

    cleaned = content
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Clean up extra whitespace
    cleaned = cleaned.strip()

    return cleaned


def _save_profile_from_onboarding(db: Session, profile_data: Dict[str, str]) -> None:
    """Save parsed profile data to database."""
    profile = get_or_create_profile(db)

    # Save nickname to profile
    nickname = profile_data.get('nickname', '')
    if nickname:
        profile.nickname = nickname

    # Save profile fields (natural language descriptions)
    if profile_data.get('experience'):
        profile.experience_level = profile_data['experience']

    if profile_data.get('risk'):
        profile.risk_preference = profile_data['risk']

    if profile_data.get('style'):
        style = profile_data['style']
        if style.lower() not in ['未提及', 'not mentioned']:
            profile.trading_style = style

    # Mark onboarding as completed
    profile.onboarding_completed = True

    db.commit()
    logger.info(f"Saved onboarding profile: nickname={nickname}, experience={profile.experience_level}")


def _process_onboarding_stream_response(
    db: Session,
    conversation_id: int,
    response: requests.Response,
    api_format: str
) -> Generator[str, None, None]:
    """Process streaming response for onboarding, handling profile data extraction."""
    content_parts = []
    reasoning_parts = []

    try:
        for line in response.iter_lines():
            if not line:
                continue

            line_str = line.decode('utf-8')
            if not line_str.startswith('data: '):
                continue

            data_str = line_str[6:]
            if data_str == '[DONE]':
                break

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # Extract content based on API format
            if api_format == "anthropic":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        content_parts.append(text)
                        yield format_sse_event("content", {"text": text})
            else:
                # OpenAI format
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        content_parts.append(text)
                        yield format_sse_event("content", {"text": text})

                    reasoning = delta.get("reasoning_content", "")
                    if reasoning:
                        reasoning_parts.append(reasoning)
                        yield format_sse_event("reasoning", {"text": reasoning})

        # Process full content
        full_content = "".join(content_parts)
        full_reasoning = "".join(reasoning_parts) if reasoning_parts else None

        # Check for profile data completion
        profile_data = _parse_profile_data(full_content)
        onboarding_complete = False

        if profile_data:
            # Save profile to database
            _save_profile_from_onboarding(db, profile_data)
            onboarding_complete = True

            # Strip markers from content for display
            display_content = _strip_profile_markers(full_content)
        else:
            display_content = full_content

        # Save assistant message (without profile markers)
        if display_content:
            save_message(
                db, conversation_id, "assistant", display_content,
                reasoning_snapshot=full_reasoning,
                is_complete=True
            )

        yield format_sse_event("done", {
            "conversation_id": conversation_id,
            "content_length": len(display_content),
            "onboarding_complete": onboarding_complete
        })

    except Exception as e:
        logger.error(f"Onboarding stream processing error: {e}", exc_info=True)
        yield format_sse_event("error", {"message": str(e)})
