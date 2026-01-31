#!/usr/bin/env python3
"""
Comprehensive test for all MarketData APIs via test-run endpoint.
Tests every variable/method documented in PROGRAM_DEV_GUIDE.md.
"""

import requests
import json

API_URL = "http://localhost:8802/api/programs/test-run"

# Test code that exercises ALL documented APIs (no try-except, sandbox doesn't have Exception)
TEST_CODE = '''
class ComprehensiveTest:
    def should_trade(self, data: MarketData) -> Decision:
        results = []

        # ========== 1. MarketData Properties ==========
        results.append(f"prices: {data.prices}")
        results.append(f"trigger_symbol: {data.trigger_symbol}")
        results.append(f"trigger_type: {data.trigger_type}")
        results.append(f"available_balance: {data.available_balance}")
        results.append(f"total_equity: {data.total_equity}")
        results.append(f"used_margin: {data.used_margin}")
        results.append(f"margin_usage_percent: {data.margin_usage_percent}")
        results.append(f"positions: {data.positions}")

        # ========== 2. Technical Indicators (14 types) ==========
        indicators = ["RSI14", "RSI7", "MA5", "MA10", "MA20", "EMA20", "EMA50",
                      "EMA100", "MACD", "BOLL", "ATR14", "VWAP", "STOCH", "OBV"]
        for ind in indicators:
            val = data.get_indicator("BTC", ind, "1h")
            results.append(f"get_indicator(BTC, {ind}, 1h): {val}")

        # ========== 3. Flow Metrics (7 types) ==========
        flow_metrics = ["CVD", "OI", "OI_DELTA", "TAKER", "FUNDING", "DEPTH", "IMBALANCE"]
        for metric in flow_metrics:
            val = data.get_flow("BTC", metric, "1h")
            results.append(f"get_flow(BTC, {metric}, 1h): {val}")

        # ========== 4. K-lines ==========
        klines = data.get_klines("BTC", "1h", count=10)
        if klines:
            k = klines[-1]
            results.append(f"get_klines: {len(klines)} bars, last: O={k.open} C={k.close}")
        else:
            results.append("get_klines: empty")

        # ========== 5. Market Regime ==========
        regime = data.get_regime("BTC", "1h")
        results.append(f"get_regime: {regime}")

        # ========== 6. Price Change ==========
        change = data.get_price_change("BTC", "1h")
        results.append(f"get_price_change: {change}")

        # ========== 7. Math Functions (via math module) ==========
        results.append(f"math.sqrt(16): {math.sqrt(16)}")
        results.append(f"math.log(10): {math.log(10)}")
        results.append(f"math.log10(100): {math.log10(100)}")
        results.append(f"math.exp(1): {math.exp(1)}")
        results.append(f"math.pow(2, 3): {math.pow(2, 3)}")
        results.append(f"math.floor(3.7): {math.floor(3.7)}")
        results.append(f"math.ceil(3.2): {math.ceil(3.2)}")
        results.append(f"math.fabs(-5): {math.fabs(-5)}")

        # ========== 8. Built-in Functions ==========
        results.append(f"abs(-10): {abs(-10)}")
        results.append(f"min(1,2,3): {min(1,2,3)}")
        results.append(f"max(1,2,3): {max(1,2,3)}")
        results.append(f"sum([1,2,3]): {sum([1,2,3])}")
        results.append(f"len([1,2,3]): {len([1,2,3])}")
        results.append(f"round(3.14159, 2): {round(3.14159, 2)}")

        # ========== 9. Debug log function ==========
        log("Test log message from comprehensive test")
        results.append("log() function: OK")

        # ========== Summary ==========
        summary = f"PASSED: {len(results)} tests"
        return Decision(
            operation="hold",
            symbol="BTC",
            reason=summary + " | " + " | ".join(results[:10])
        )
'''

def main():
    print("=" * 60)
    print("  Comprehensive MarketData API Test via test-run")
    print("=" * 60)

    payload = {
        "code": TEST_CODE,
        "symbol": "BTC",
        "period": "1h"
    }

    resp = requests.post(API_URL, json=payload, timeout=30)
    result = resp.json()

    print(f"\nSuccess: {result.get('success')}")
    print(f"Execution time: {result.get('execution_time_ms', 0):.2f}ms")

    if result.get('success'):
        decision = result.get('decision', {})
        print(f"\nDecision: {decision.get('action')}")
        print(f"Reason: {decision.get('reason')}")
    else:
        print(f"\nError type: {result.get('error_type')}")
        print(f"Error message: {result.get('error_message')}")
        if result.get('error_traceback'):
            print(f"\nTraceback:\n{result.get('error_traceback')}")
        if result.get('suggestions'):
            print(f"\nSuggestions: {result.get('suggestions')}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
