"""
AI Context Compression Service - Shared context management for all AI assistants

This module provides:
1. Token estimation for messages
2. Context window management with compression triggers
3. Conversation summarization using the user's configured LLM
4. Memory extraction during compression

Architecture:
- Trigger compression at 80% of context window
- Generate summary of older messages
- Extract important insights to Memory table
- Replace old messages with summary in conversation context

Usage:
    from services.ai_context_compression_service import (
        estimate_tokens,
        should_compress,
        compress_conversation
    )
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Model context window sizes (conservative estimates)
MODEL_CONTEXT_WINDOWS = {
    # OpenAI
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "o1": 200000,
    "o1-mini": 128000,
    # Anthropic
    "claude-3": 200000,
    "claude-sonnet": 200000,
    "claude-opus": 200000,
    # Google
    "gemini-2": 1000000,
    "gemini-1.5": 1000000,
    # Deepseek
    "deepseek-chat": 64000,
    "deepseek-reasoner": 64000,
    # Qwen
    "qwen-max": 32000,
    "qwen-plus": 131072,
    "qwen-turbo": 131072,
    # Moonshot
    "moonshot-v1-128k": 128000,
    "moonshot-v1-32k": 32000,
    "moonshot-v1-8k": 8000,
    # GLM
    "glm-4": 128000,
}

# Compression threshold (80% of context window)
COMPRESSION_THRESHOLD = 0.8

# Reserved tokens for system prompt and response
RESERVED_TOKENS = 4000


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.
    Uses a simple heuristic: ~4 characters per token for English,
    ~2 characters per token for Chinese.
    """
    if not text:
        return 0

    # Count Chinese characters
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    other_chars = len(text) - chinese_chars

    # Chinese: ~1.5 tokens per char, English: ~0.25 tokens per char
    estimated = int(chinese_chars * 1.5 + other_chars * 0.25)
    return max(estimated, 1)


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate total tokens for a list of messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    total += estimate_tokens(item["text"])
        # Add overhead for role and formatting
        total += 4
    return total


def get_context_window(model: str) -> int:
    """Get context window size for a model."""
    model_lower = model.lower()

    # Check exact matches first
    for key, size in MODEL_CONTEXT_WINDOWS.items():
        if key in model_lower:
            return size

    # Default fallback
    return 32000


def should_compress(
    messages: List[Dict[str, Any]],
    model: str,
    threshold: float = COMPRESSION_THRESHOLD
) -> Tuple[bool, int, int]:
    """
    Check if conversation should be compressed.

    Returns:
        (should_compress, current_tokens, max_tokens)
    """
    context_window = get_context_window(model)
    max_tokens = int(context_window * threshold) - RESERVED_TOKENS
    current_tokens = estimate_messages_tokens(messages)

    return (current_tokens > max_tokens, current_tokens, max_tokens)


def find_compression_point(
    messages: List[Dict[str, Any]],
    target_tokens: int
) -> int:
    """
    Find the index where to split messages for compression.
    Keep recent messages, compress older ones.

    Returns index of first message to keep (messages before this will be compressed).
    """
    if not messages:
        return 0

    # Calculate tokens from the end
    tokens_from_end = 0
    keep_from_index = len(messages)

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        content = msg.get("content", "")
        msg_tokens = estimate_tokens(content) if isinstance(content, str) else 100
        msg_tokens += 4  # overhead

        if tokens_from_end + msg_tokens > target_tokens:
            break
        tokens_from_end += msg_tokens
        keep_from_index = i

    # Keep at least the last 2 messages
    return min(keep_from_index, len(messages) - 2)


COMPRESSION_PROMPT = """You are a conversation summarizer. Your task is to create a concise summary of the conversation history.

Instructions:
1. Summarize the key topics discussed
2. Note any important decisions or conclusions
3. Preserve critical context needed for continuing the conversation
4. Keep the summary under 500 words
5. Use bullet points for clarity

Conversation to summarize:
{conversation}

Provide a clear, structured summary:"""


def generate_summary(
    messages_to_compress: List[Dict[str, Any]],
    api_config: Dict[str, Any]
) -> Optional[str]:
    """
    Generate a summary of messages using LLM.

    Args:
        messages_to_compress: Messages to summarize
        api_config: LLM configuration with base_url, api_key, model

    Returns:
        Summary text or None if failed
    """
    if not messages_to_compress:
        return None

    # Build conversation text
    conv_parts = []
    for msg in messages_to_compress:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            conv_parts.append(f"{role.upper()}: {content}")

    conversation_text = "\n\n".join(conv_parts)

    # Prepare API call
    base_url = api_config.get("base_url", "")
    api_key = api_config.get("api_key", "")
    model = api_config.get("model", "")
    api_format = api_config.get("api_format", "openai")

    if not all([base_url, api_key, model]):
        logger.warning("Incomplete API config for compression")
        return None

    prompt = COMPRESSION_PROMPT.format(conversation=conversation_text[:8000])

    try:
        from services.ai_decision_service import build_chat_completion_endpoints

        if api_format == "anthropic":
            endpoint = f"{base_url.rstrip('/')}/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
            body = {
                "model": model,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            }
        else:
            endpoints = build_chat_completion_endpoints(base_url, model)
            endpoint = endpoints[0] if endpoints else f"{base_url}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            body = {
                "model": model,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            }

        response = requests.post(endpoint, headers=headers, json=body, timeout=60)

        if response.status_code != 200:
            logger.error(f"Compression API error: {response.status_code}")
            return None

        data = response.json()

        # Extract content based on format
        if api_format == "anthropic":
            content = data.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "")
        else:
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")

    except Exception as e:
        logger.error(f"Compression failed: {e}")

    return None


def compress_messages(
    messages: List[Dict[str, Any]],
    api_config: Dict[str, Any],
    keep_system: bool = True,
    db: Optional[Session] = None,
    extract_memories: bool = True
) -> List[Dict[str, Any]]:
    """
    Compress conversation messages if needed.

    Args:
        messages: Full message list including system prompt
        api_config: LLM configuration
        keep_system: Whether to preserve system messages
        db: Database session (required for memory extraction)
        extract_memories: Whether to extract memories during compression

    Returns:
        Compressed message list with summary replacing old messages
    """
    model = api_config.get("model", "")
    needs_compression, current, max_tokens = should_compress(messages, model)

    if not needs_compression:
        return messages

    logger.info(f"Compressing conversation: {current} tokens > {max_tokens} limit")

    # Separate system messages and conversation
    system_messages = []
    conversation_messages = []

    for msg in messages:
        if msg.get("role") == "system" and keep_system:
            system_messages.append(msg)
        else:
            conversation_messages.append(msg)

    # Find compression point (keep ~40% of max tokens for recent messages)
    target_keep = int(max_tokens * 0.4)
    split_index = find_compression_point(conversation_messages, target_keep)

    if split_index <= 0:
        # Nothing to compress
        return messages

    # Split messages
    to_compress = conversation_messages[:split_index]
    to_keep = conversation_messages[split_index:]

    # Extract memories from messages being compressed
    if extract_memories and db:
        try:
            from services.hyper_ai_memory_service import process_compression_memories
            conv_text = "\n\n".join([
                f"{m.get('role', 'unknown').upper()}: {m.get('content', '')}"
                for m in to_compress
                if isinstance(m.get('content'), str)
            ])
            process_compression_memories(db, conv_text, api_config)
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}")

    # Generate summary
    summary = generate_summary(to_compress, api_config)

    if not summary:
        # Fallback: just truncate without summary
        logger.warning("Summary generation failed, truncating without summary")
        return system_messages + to_keep

    # Build compressed message list
    compressed = system_messages.copy()

    # Add summary as a system message
    compressed.append({
        "role": "system",
        "content": f"[Previous conversation summary]\n{summary}"
    })

    # Add recent messages
    compressed.extend(to_keep)

    new_tokens = estimate_messages_tokens(compressed)
    logger.info(f"Compression complete: {current} -> {new_tokens} tokens")

    return compressed


def prepare_messages_with_compression(
    system_prompt: str,
    history_messages: List[Dict[str, Any]],
    user_message: str,
    api_config: Dict[str, Any],
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Convenience function to prepare messages with automatic compression.

    Args:
        system_prompt: System prompt text
        history_messages: Previous conversation messages
        user_message: Current user message
        api_config: LLM configuration
        db: Database session for memory extraction

    Returns:
        Ready-to-send message list, compressed if needed
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_message})

    return compress_messages(messages, api_config, db=db)
