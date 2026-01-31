#!/usr/bin/env python3
"""
Test script for Anthropic streaming response parsing.
"""
import json
import sys
sys.path.append('/home/wwwroot/hyper-alpha-arena-prod/backend')

def test_parse_streaming_response():
    """Test parsing of simulated Anthropic streaming response."""

    # Simulate Anthropic SSE stream data (what we'd receive line by line)
    # This simulates a response with text + tool_use
    stream_lines = [
        'event: message_start',
        'data: {"type":"message_start","message":{"id":"msg_123","type":"message","role":"assistant","content":[],"model":"claude-3-5-sonnet-20241022"}}',
        '',
        'event: content_block_start',
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
        '',
        'event: content_block_delta',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"I\'ll help you "}}',
        '',
        'event: content_block_delta',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"create a strategy."}}',
        '',
        'event: content_block_stop',
        'data: {"type":"content_block_stop","index":0}',
        '',
        'event: content_block_start',
        'data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_abc123","name":"query_market_data","input":{}}}',
        '',
        'event: content_block_delta',
        'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\\"symbol\\""}}',
        '',
        'event: content_block_delta',
        'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":": \\"BTC\\"}"}}',
        '',
        'event: content_block_stop',
        'data: {"type":"content_block_stop","index":1}',
        '',
        'event: message_delta',
        'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"}}',
        '',
        'event: message_stop',
        'data: {"type":"message_stop"}',
    ]

    # Parse the stream (simulating what _call_anthropic_streaming does)
    content_blocks = []
    current_block = None
    stop_reason = None

    for line in stream_lines:
        if not line:
            continue
        if line.startswith("event:"):
            continue
        if not line.startswith("data:"):
            continue

        data_str = line[5:].strip()
        if data_str == "[DONE]":
            break

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        event_type = data.get("type", "")

        if event_type == "content_block_start":
            block_data = data.get("content_block", {})
            block_type = block_data.get("type", "")

            if block_type == "text":
                current_block = {"type": "text", "text": ""}
            elif block_type == "tool_use":
                current_block = {
                    "type": "tool_use",
                    "id": block_data.get("id", ""),
                    "name": block_data.get("name", ""),
                    "input": ""
                }

        elif event_type == "content_block_delta":
            delta = data.get("delta", {})
            delta_type = delta.get("type", "")

            if delta_type == "text_delta" and current_block:
                current_block["text"] += delta.get("text", "")
            elif delta_type == "input_json_delta" and current_block:
                current_block["input"] += delta.get("partial_json", "")

        elif event_type == "content_block_stop":
            if current_block:
                if current_block.get("type") == "tool_use":
                    input_str = current_block.get("input", "")
                    if input_str:
                        try:
                            current_block["input"] = json.loads(input_str)
                        except json.JSONDecodeError:
                            current_block["input"] = {}
                    else:
                        current_block["input"] = {}
                content_blocks.append(current_block)
                current_block = None

        elif event_type == "message_delta":
            delta = data.get("delta", {})
            stop_reason = delta.get("stop_reason")

    result = {
        "content": content_blocks,
        "stop_reason": stop_reason
    }

    # Validate result
    print("=== Parsed Result ===")
    print(json.dumps(result, indent=2))

    print("\n=== Validation ===")
    errors = []

    # Check we got 2 content blocks
    if len(content_blocks) != 2:
        errors.append(f"Expected 2 content blocks, got {len(content_blocks)}")

    # Check text block
    if content_blocks[0].get("type") != "text":
        errors.append(f"First block should be text, got {content_blocks[0].get('type')}")
    if content_blocks[0].get("text") != "I'll help you create a strategy.":
        errors.append(f"Text content mismatch: {content_blocks[0].get('text')}")

    # Check tool_use block
    if content_blocks[1].get("type") != "tool_use":
        errors.append(f"Second block should be tool_use, got {content_blocks[1].get('type')}")
    if content_blocks[1].get("name") != "query_market_data":
        errors.append(f"Tool name mismatch: {content_blocks[1].get('name')}")
    if content_blocks[1].get("input") != {"symbol": "BTC"}:
        errors.append(f"Tool input mismatch: {content_blocks[1].get('input')}")
    if content_blocks[1].get("id") != "toolu_abc123":
        errors.append(f"Tool id mismatch: {content_blocks[1].get('id')}")

    # Check stop_reason
    if stop_reason != "tool_use":
        errors.append(f"Stop reason should be 'tool_use', got {stop_reason}")

    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("All validations passed!")
        return True


def test_empty_tool_input():
    """Test tool_use with empty input."""
    stream_lines = [
        'event: content_block_start',
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"toolu_xyz","name":"get_current_code","input":{}}}',
        '',
        'event: content_block_stop',
        'data: {"type":"content_block_stop","index":0}',
        '',
        'event: message_delta',
        'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"}}',
    ]

    content_blocks = []
    current_block = None

    for line in stream_lines:
        if not line or line.startswith("event:"):
            continue
        if not line.startswith("data:"):
            continue
        data_str = line[5:].strip()
        try:
            data = json.loads(data_str)
        except:
            continue

        event_type = data.get("type", "")

        if event_type == "content_block_start":
            block_data = data.get("content_block", {})
            if block_data.get("type") == "tool_use":
                current_block = {
                    "type": "tool_use",
                    "id": block_data.get("id", ""),
                    "name": block_data.get("name", ""),
                    "input": ""
                }
        elif event_type == "content_block_stop":
            if current_block and current_block.get("type") == "tool_use":
                input_str = current_block.get("input", "")
                if input_str:
                    try:
                        current_block["input"] = json.loads(input_str)
                    except:
                        current_block["input"] = {}
                else:
                    current_block["input"] = {}
                content_blocks.append(current_block)
                current_block = None

    print("\n=== Empty Input Test ===")
    print(f"Result: {content_blocks}")

    if len(content_blocks) == 1 and content_blocks[0].get("input") == {}:
        print("Empty input test passed!")
        return True
    else:
        print("Empty input test FAILED!")
        return False


if __name__ == "__main__":
    success1 = test_parse_streaming_response()
    success2 = test_empty_tool_input()

    print("\n" + "="*50)
    if success1 and success2:
        print("ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED!")
        sys.exit(1)
