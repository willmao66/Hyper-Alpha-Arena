#!/usr/bin/env python3
"""
Test script to validate Anthropic message format conversion.
This simulates the multi-round tool calling scenario that causes 504 errors.
"""
import json
import sys
sys.path.append('/home/wwwroot/hyper-alpha-arena-prod/backend')

from services.ai_program_service import _convert_messages_to_anthropic, PROGRAM_TOOLS_ANTHROPIC

def test_multi_round_conversion():
    """Simulate a multi-round conversation with tool calls."""

    # Round 1: Initial messages
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Help me create a trading strategy."}
    ]

    system, anthropic_msgs = _convert_messages_to_anthropic(messages)
    print("=== Round 1 (Initial) ===")
    print(f"System: {system[:100]}...")
    print(f"Messages count: {len(anthropic_msgs)}")
    for i, m in enumerate(anthropic_msgs):
        print(f"  [{i}] role={m['role']}, content type={type(m['content']).__name__}")
    print()

    # Round 2: After assistant responds with tool_use
    # Simulate what happens after Anthropic returns a tool_use response
    assistant_response_blocks = [
        {"type": "text", "text": "I'll help you create a strategy."},
        {"type": "tool_use", "id": "toolu_123", "name": "get_current_code", "input": {}}
    ]

    messages.append({
        "role": "assistant",
        "content": "I'll help you create a strategy.",
        "tool_use_blocks": assistant_response_blocks  # Store raw blocks
    })

    # Add tool result (OpenAI format)
    messages.append({
        "role": "tool",
        "tool_call_id": "toolu_123",
        "content": "def should_trade(data): return None"
    })

    # Round 3: Assistant calls MULTIPLE tools at once
    assistant_response_blocks_2 = [
        {"type": "text", "text": "Let me query market data."},
        {"type": "tool_use", "id": "toolu_456", "name": "query_market_data", "input": {"symbol": "BTC"}},
        {"type": "tool_use", "id": "toolu_789", "name": "query_market_data", "input": {"symbol": "ETH"}}
    ]

    messages.append({
        "role": "assistant",
        "content": "Let me query market data.",
        "tool_use_blocks": assistant_response_blocks_2
    })

    # Add MULTIPLE tool results (this is where issues might occur)
    messages.append({
        "role": "tool",
        "tool_call_id": "toolu_456",
        "content": "BTC price: 100000"
    })
    messages.append({
        "role": "tool",
        "tool_call_id": "toolu_789",
        "content": "ETH price: 3500"
    })

    system, anthropic_msgs = _convert_messages_to_anthropic(messages)
    print("=== Round 2 (After tool call) ===")
    print(f"Messages count: {len(anthropic_msgs)}")
    for i, m in enumerate(anthropic_msgs):
        content = m['content']
        if isinstance(content, list):
            print(f"  [{i}] role={m['role']}, content=[{len(content)} blocks]")
            for j, block in enumerate(content):
                if isinstance(block, dict):
                    print(f"       block[{j}]: type={block.get('type')}, keys={list(block.keys())}")
        else:
            print(f"  [{i}] role={m['role']}, content type={type(content).__name__}, len={len(str(content))}")
    print()

    # Validate Anthropic format requirements
    print("=== Validation ===")
    errors = []

    for i, m in enumerate(anthropic_msgs):
        role = m.get('role')
        content = m.get('content')

        # Check 1: Role must be 'user' or 'assistant'
        if role not in ['user', 'assistant']:
            errors.append(f"msg[{i}]: Invalid role '{role}'")

        # Check 2: Content must be string or list of content blocks
        if not isinstance(content, (str, list)):
            errors.append(f"msg[{i}]: Content must be str or list, got {type(content)}")

        # Check 3: If content is list, each block must have 'type'
        if isinstance(content, list):
            for j, block in enumerate(content):
                if not isinstance(block, dict):
                    errors.append(f"msg[{i}].content[{j}]: Block must be dict, got {type(block)}")
                elif 'type' not in block:
                    errors.append(f"msg[{i}].content[{j}]: Block missing 'type' field")

        # Check 4: Alternating roles (Anthropic requirement)
        if i > 0:
            prev_role = anthropic_msgs[i-1].get('role')
            if role == prev_role:
                errors.append(f"msg[{i}]: Consecutive {role} messages (prev was also {prev_role})")

    if errors:
        print("ERRORS FOUND:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("All validations passed!")

    # Print the actual payload that would be sent
    print("\n=== Actual Payload (JSON) ===")
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 4096,
        "system": system,
        "messages": anthropic_msgs,
        "tools": PROGRAM_TOOLS_ANTHROPIC[:1]  # Just first tool for brevity
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:2000])

    return errors


def test_edge_cases():
    """Test edge cases that might cause 504 errors."""
    print("\n" + "="*60)
    print("=== EDGE CASE TESTS ===")
    print("="*60)

    # Edge case 1: Assistant message with ONLY tool_use (no text)
    print("\n--- Edge Case 1: Assistant with only tool_use (no text) ---")
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Query BTC price."},
        {
            "role": "assistant",
            "content": "",  # Empty content
            "tool_use_blocks": [
                {"type": "tool_use", "id": "toolu_001", "name": "query_market_data", "input": {"symbol": "BTC"}}
            ]
        },
        {"role": "tool", "tool_call_id": "toolu_001", "content": "BTC: 100000"}
    ]
    system, anthropic_msgs = _convert_messages_to_anthropic(messages)
    print(f"Messages: {len(anthropic_msgs)}")
    for i, m in enumerate(anthropic_msgs):
        content = m['content']
        if isinstance(content, list):
            print(f"  [{i}] role={m['role']}, content=[{len(content)} blocks]")
            for j, b in enumerate(content):
                print(f"       [{j}] type={b.get('type')}")
        else:
            print(f"  [{i}] role={m['role']}, content='{content[:50] if content else '(empty)'}...'")

    # Edge case 2: Very long tool result
    print("\n--- Edge Case 2: Very long tool result ---")
    long_result = "x" * 50000  # 50KB result
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Get data."},
        {
            "role": "assistant",
            "content": "Getting data.",
            "tool_use_blocks": [
                {"type": "text", "text": "Getting data."},
                {"type": "tool_use", "id": "toolu_002", "name": "get_current_code", "input": {}}
            ]
        },
        {"role": "tool", "tool_call_id": "toolu_002", "content": long_result}
    ]
    system, anthropic_msgs = _convert_messages_to_anthropic(messages)
    total_size = len(json.dumps({"messages": anthropic_msgs}))
    print(f"Total payload size: {total_size:,} bytes")
    print(f"Tool result size: {len(long_result):,} bytes")

    # Edge case 3: Empty tool_use_blocks list
    print("\n--- Edge Case 3: Empty tool_use_blocks list ---")
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "Hi there!",
            "tool_use_blocks": []  # Empty list
        }
    ]
    system, anthropic_msgs = _convert_messages_to_anthropic(messages)
    print(f"Messages: {len(anthropic_msgs)}")
    for i, m in enumerate(anthropic_msgs):
        content = m['content']
        if isinstance(content, list):
            print(f"  [{i}] role={m['role']}, content=[{len(content)} blocks] - PROBLEM: empty list!")
        else:
            print(f"  [{i}] role={m['role']}, content type={type(content).__name__}")

    # Edge case 4: tool_use with input as empty string (proxy issue)
    print("\n--- Edge Case 4: tool_use with input='' (proxy issue) ---")
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Get code."},
        {
            "role": "assistant",
            "content": "Getting code.",
            "tool_use_blocks": [
                {"type": "text", "text": "Getting code."},
                {"type": "tool_use", "id": "toolu_003", "name": "get_current_code", "input": ""}  # String instead of object
            ]
        },
        {"role": "tool", "tool_call_id": "toolu_003", "content": "code here"}
    ]
    system, anthropic_msgs = _convert_messages_to_anthropic(messages)
    # Check if input was fixed
    for m in anthropic_msgs:
        if isinstance(m['content'], list):
            for b in m['content']:
                if b.get('type') == 'tool_use':
                    input_val = b.get('input')
                    print(f"  tool_use input: {repr(input_val)} (type: {type(input_val).__name__})")
                    if input_val == "":
                        print("  WARNING: input is still empty string, should be {}")


if __name__ == "__main__":
    errors = test_multi_round_conversion()
    test_edge_cases()
    sys.exit(1 if errors else 0)
