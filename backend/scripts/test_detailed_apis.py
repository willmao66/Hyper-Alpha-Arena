#!/usr/bin/env python3
"""
Detailed test for all MarketData APIs - outputs full results.
"""

import requests
import json

API_URL = "http://localhost:8802/api/programs/test-run"

# Test code that outputs detailed results
TEST_CODE = '''
class DetailedTest:
    def should_trade(self, data: MarketData) -> Decision:
        output = []

        # 1. Properties
        output.append("=== PROPERTIES ===")
        output.append(f"prices={data.prices}")
        output.append(f"trigger_symbol={data.trigger_symbol}")
        output.append(f"trigger_type={data.trigger_type}")
        output.append(f"available_balance={data.available_balance}")
        output.append(f"total_equity={data.total_equity}")
        output.append(f"used_margin={data.used_margin}")
        output.append(f"margin_usage_percent={data.margin_usage_percent}")
        output.append(f"positions={data.positions}")

        # 2. Indicators
        output.append("=== INDICATORS ===")
        for ind in ["RSI14", "RSI7", "MA5", "MA10", "MA20", "EMA20", "MACD", "BOLL", "ATR14"]:
            val = data.get_indicator("BTC", ind, "1h")
            output.append(f"{ind}={val}")

        # 3. Flow
        output.append("=== FLOW ===")
        for metric in ["CVD", "OI", "OI_DELTA", "TAKER", "FUNDING"]:
            val = data.get_flow("BTC", metric, "1h")
            output.append(f"{metric}={val}")

        # 4. Klines
        output.append("=== KLINES ===")
        klines = data.get_klines("BTC", "1h", count=3)
        output.append(f"klines_count={len(klines) if klines else 0}")
        if klines:
            k = klines[-1]
            output.append(f"last_kline: O={k.open} H={k.high} L={k.low} C={k.close} V={k.volume}")

        # 5. Regime & Price Change
        output.append("=== REGIME & CHANGE ===")
        regime = data.get_regime("BTC", "1h")
        change = data.get_price_change("BTC", "1h")
        output.append(f"regime={regime}")
        output.append(f"price_change={change}")

        # 6. Math
        output.append("=== MATH ===")
        output.append(f"sqrt(16)={math.sqrt(16)}")
        output.append(f"log10(100)={math.log10(100)}")
        output.append(f"floor(3.7)={math.floor(3.7)}")

        # 7. Edge cases
        output.append("=== EDGE CASES ===")
        invalid_ind = data.get_indicator("INVALID", "RSI14", "1h")
        output.append(f"invalid_symbol_indicator={invalid_ind}")
        invalid_flow = data.get_flow("BTC", "INVALID", "1h")
        output.append(f"invalid_flow_type={invalid_flow}")

        log("Test completed successfully")

        return Decision(
            operation="hold",
            symbol="BTC",
            reason="|||".join(output)
        )
'''

def main():
    print("=" * 70)
    print("  Detailed MarketData API Test")
    print("=" * 70)

    payload = {"code": TEST_CODE, "symbol": "BTC", "period": "1h"}
    resp = requests.post(API_URL, json=payload, timeout=30)
    result = resp.json()

    print(f"\nSuccess: {result.get('success')}")
    print(f"Execution time: {result.get('execution_time_ms', 0):.2f}ms")

    if result.get('success'):
        reason = result.get('decision', {}).get('reason', '')
        parts = reason.split("|||")
        print("\n--- DETAILED RESULTS ---")
        for part in parts:
            print(part)
    else:
        print(f"\nError: {result.get('error_message')}")
        if result.get('error_traceback'):
            print(f"\nTraceback:\n{result.get('error_traceback')}")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
