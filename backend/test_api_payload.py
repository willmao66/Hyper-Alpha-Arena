#!/usr/bin/env python3
"""
Test script to send actual API request and diagnose 504 errors.
"""
import json
import sys
import os
sys.path.append('/home/wwwroot/hyper-alpha-arena-prod/backend')

import requests
from services.ai_program_service import _convert_messages_to_anthropic, PROGRAM_TOOLS_ANTHROPIC

def test_actual_api_call():
    """Send actual API request to diagnose 504 errors."""

    # Simulate a multi-round conversation that might cause issues
    messages = [
        {"role": "system", "content": "You are a helpful trading strategy assistant."},
        {"role": "user", "content": "Help me create a simple BTC trading strategy."},
        # Round 1 response with tool call
        {
            "role": "assistant",
            "content": "I'll help you create a BTC trading strategy. Let me first check the current market data.",
            "tool_use_blocks": [
                {"type": "text", "text": "I'll help you create a BTC trading strategy. Let me first check the current market data."},
                {"type": "tool_use", "id": "toolu_01ABC", "name": "query_market_data", "input": {"symbol": "BTC", "period": "1h"}}
            ]
        },
        # Tool result
        {"role": "tool", "tool_call_id": "toolu_01ABC", "content": '{"symbol": "BTC", "price": 100000, "rsi_14": 55.2, "macd": {"value": 150, "signal": 120}}'},
        # Round 2 response with another tool call
        {
            "role": "assistant",
            "content": "Based on the market data, I'll now get the current code to modify it.",
            "tool_use_blocks": [
                {"type": "text", "text": "Based on the market data, I'll now get the current code to modify it."},
                {"type": "tool_use", "id": "toolu_02DEF", "name": "get_current_code", "input": {}}
            ]
        },
        # Tool result with code
        {"role": "tool", "tool_call_id": "toolu_02DEF", "content": 'def should_trade(data):\n    """Default strategy"""\n    return None'},
    ]

    # Convert to Anthropic format
    system_prompt, anthropic_msgs = _convert_messages_to_anthropic(messages)

    print("=== Converted Messages ===")
    print(f"System prompt length: {len(system_prompt)}")
    print(f"Messages count: {len(anthropic_msgs)}")
    for i, m in enumerate(anthropic_msgs):
        content = m['content']
        if isinstance(content, list):
            print(f"  [{i}] role={m['role']}, content=[{len(content)} blocks]")
            for j, b in enumerate(content):
                btype = b.get('type', '?')
                if btype == 'tool_use':
                    print(f"       [{j}] type={btype}, name={b.get('name')}, input_type={type(b.get('input')).__name__}")
                elif btype == 'tool_result':
                    print(f"       [{j}] type={btype}, tool_use_id={b.get('tool_use_id')}, content_len={len(str(b.get('content', '')))}")
                else:
                    print(f"       [{j}] type={btype}")
        else:
            print(f"  [{i}] role={m['role']}, content_len={len(str(content))}")

    # Build payload
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": anthropic_msgs,
        "tools": PROGRAM_TOOLS_ANTHROPIC
    }

    # Calculate payload size
    payload_json = json.dumps(payload)
    print(f"\n=== Payload Stats ===")
    print(f"Total payload size: {len(payload_json):,} bytes")
    print(f"Tools count: {len(PROGRAM_TOOLS_ANTHROPIC)}")

    # Validate JSON structure
    print("\n=== JSON Validation ===")
    try:
        json.loads(payload_json)
        print("JSON is valid")
    except json.JSONDecodeError as e:
        print(f"JSON ERROR: {e}")
        return

    # Check for common Anthropic API issues
    print("\n=== Anthropic API Validation ===")
    issues = []

    # Check 1: Messages must alternate between user and assistant
    prev_role = None
    for i, m in enumerate(anthropic_msgs):
        role = m.get('role')
        if prev_role == role:
            issues.append(f"msg[{i}]: Consecutive {role} messages")
        prev_role = role

    # Check 2: First message must be from user
    if anthropic_msgs and anthropic_msgs[0].get('role') != 'user':
        issues.append(f"First message must be 'user', got '{anthropic_msgs[0].get('role')}'")

    # Check 3: Content blocks must have valid types
    valid_user_types = {'text', 'image', 'tool_result'}
    valid_assistant_types = {'text', 'tool_use'}
    for i, m in enumerate(anthropic_msgs):
        content = m.get('content')
        role = m.get('role')
        if isinstance(content, list):
            if len(content) == 0:
                issues.append(f"msg[{i}]: Empty content list")
            for j, block in enumerate(content):
                btype = block.get('type')
                if role == 'user' and btype not in valid_user_types:
                    issues.append(f"msg[{i}].content[{j}]: Invalid user block type '{btype}'")
                if role == 'assistant' and btype not in valid_assistant_types:
                    issues.append(f"msg[{i}].content[{j}]: Invalid assistant block type '{btype}'")
                # Check tool_use has required fields
                if btype == 'tool_use':
                    if 'id' not in block:
                        issues.append(f"msg[{i}].content[{j}]: tool_use missing 'id'")
                    if 'name' not in block:
                        issues.append(f"msg[{i}].content[{j}]: tool_use missing 'name'")
                    if 'input' not in block:
                        issues.append(f"msg[{i}].content[{j}]: tool_use missing 'input'")
                    elif not isinstance(block.get('input'), dict):
                        issues.append(f"msg[{i}].content[{j}]: tool_use 'input' must be object, got {type(block.get('input'))}")
                # Check tool_result has required fields
                if btype == 'tool_result':
                    if 'tool_use_id' not in block:
                        issues.append(f"msg[{i}].content[{j}]: tool_result missing 'tool_use_id'")

    if issues:
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("All validations passed!")

    # Print sample of the payload for manual inspection
    print("\n=== Payload Sample (first 3000 chars) ===")
    print(payload_json[:3000])

if __name__ == "__main__":
    test_actual_api_call()
