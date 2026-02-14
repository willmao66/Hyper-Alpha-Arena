#!/usr/bin/env python3
"""
Test script for get_max_tokens() function
"""
import sys
sys.path.insert(0, '/home/wwwroot/hyper-alpha-arena-prod/backend')

from services.ai_decision_service import get_max_tokens

# Test cases from user's model list
test_cases = [
    ("gpt-4-turbo", 4000),
    ("gpt-4-turbo-2024-04-09", 4000),
    ("gpt-4o", 8000),
    ("gpt-4o-mini", 8000),
    ("gpt-4o-2024-11-20", 8000),
    ("gpt-4.1", 16000),
    ("o1", 16000),
    ("o1-mini", 12000),
    ("o1-preview", 16000),
    ("deepseek-chat", 8000),
    ("deepseek-reasoner", 16000),
    ("claude-3-5-sonnet-20241022", 12000),
    ("claude-4-opus", 12000),
    ("qwen-max", 8000),
    ("qwen3-max", 16000),
    ("unknown-model-xyz", 4000),
]

print("Testing get_max_tokens() function:")
print("=" * 60)

all_passed = True
for model, expected in test_cases:
    result = get_max_tokens(model)
    status = "✓" if result == expected else "✗"
    if result != expected:
        all_passed = False
    print(f"{status} {model:40s} -> {result:5d} (expected: {expected})")

print("=" * 60)
if all_passed:
    print("✓ All tests passed!")
else:
    print("✗ Some tests failed!")
    sys.exit(1)
