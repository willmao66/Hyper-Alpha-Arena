#!/usr/bin/env python3
"""
Integration test for _call_anthropic_streaming function.
Tests actual API call with streaming.
"""
import json
import sys
import os

# Add backend to path
backend_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_path)

from services.ai_program_service import _call_anthropic_streaming, PROGRAM_TOOLS_ANTHROPIC

def test_real_api_call():
    """Test actual API call with streaming (requires valid API key)."""

    # Get API config from database
    from database.connection import SessionLocal
    from database.models import Account

    db = SessionLocal()
    try:
        # Find an Anthropic-format AI account
        account = db.query(Account).filter(
            Account.account_type == "AI",
            Account.base_url.like('%/v1/messages%')
        ).first()

        if not account:
            print("No Anthropic-format AI Trader account found")
            return False

        print(f"Using account: {account.name}")
        print(f"Base URL: {account.base_url}")
        print(f"Model: {account.model}")

        # Build endpoint and headers
        endpoint = account.base_url
        headers = {
            "Content-Type": "application/json",
            "x-api-key": account.api_key,
            "anthropic-version": "2023-06-01"
        }

        # Simple test payload
        payload = {
            "model": account.model,
            "max_tokens": 1024,
            "system": "You are a helpful assistant. Respond briefly.",
            "messages": [
                {"role": "user", "content": "Say hello and call the query_market_data tool with symbol BTC."}
            ],
            "tools": PROGRAM_TOOLS_ANTHROPIC[:1]  # Just query_market_data
        }

        print("\n=== Calling API with streaming ===")
        print(f"Payload size: {len(json.dumps(payload))} bytes")

        try:
            result = _call_anthropic_streaming(endpoint, payload, headers, timeout=60)
            print("\n=== Result ===")
            print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])

            # Validate result structure
            print("\n=== Validation ===")
            if "content" not in result:
                print("ERROR: Missing 'content' field")
                return False

            content_blocks = result.get("content", [])
            print(f"Content blocks: {len(content_blocks)}")

            has_text = any(b.get("type") == "text" for b in content_blocks)
            has_tool_use = any(b.get("type") == "tool_use" for b in content_blocks)

            print(f"Has text block: {has_text}")
            print(f"Has tool_use block: {has_tool_use}")
            print(f"Stop reason: {result.get('stop_reason')}")

            if has_tool_use:
                tool_block = next(b for b in content_blocks if b.get("type") == "tool_use")
                print(f"Tool name: {tool_block.get('name')}")
                print(f"Tool input: {tool_block.get('input')}")
                print(f"Tool id: {tool_block.get('id')}")

            print("\nStreaming API call successful!")
            return True

        except Exception as e:
            print(f"\nERROR: {e}")
            return False

    finally:
        db.close()


if __name__ == "__main__":
    success = test_real_api_call()
    sys.exit(0 if success else 1)
