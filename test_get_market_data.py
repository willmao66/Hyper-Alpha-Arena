#!/usr/bin/env python3
"""
Test script to get real return value from get_ticker_data()
This is used to document the actual API response structure.
"""
import sys
import os
import json

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from services.market_data import get_ticker_data

# Test with BTC on testnet
print("Testing get_ticker_data('BTC', 'CRYPTO', 'testnet')...")
print("=" * 60)

result = get_ticker_data("BTC", "CRYPTO", "testnet")

print(json.dumps(result, indent=2))
print("=" * 60)
print("\nDone! Copy the JSON output above to documentation.")
