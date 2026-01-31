#!/usr/bin/env python3
"""
Comprehensive test script for all MarketData APIs.
Tests every method and property documented in PROGRAM_DEV_GUIDE.md.

Usage:
    docker exec -it hyper-arena-app python /app/backend/scripts/test_all_market_data_apis.py
"""

import sys
sys.path.insert(0, "/app/backend")

from database.connection import SessionLocal
from program_trader.data_provider import DataProvider
from program_trader.models import MarketData

# Test configuration
TEST_SYMBOLS = ["BTC", "ETH", "SOL"]
TEST_PERIODS = ["1m", "5m", "15m", "1h", "4h"]
TEST_INDICATORS = [
    "RSI14", "RSI7", "MA5", "MA10", "MA20",
    "EMA20", "EMA50", "EMA100", "MACD", "BOLL",
    "ATR14", "VWAP", "STOCH", "OBV"
]
TEST_FLOW_METRICS = ["CVD", "OI", "OI_DELTA", "TAKER", "FUNDING", "DEPTH", "IMBALANCE"]


def test_section(title: str):
    """Print section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_item(name: str, result, error=None):
    """Print test result."""
    if error:
        print(f"  [FAIL] {name}: {error}")
    elif result is None:
        print(f"  [WARN] {name}: None (no data)")
    else:
        # Truncate long results
        result_str = str(result)
        if len(result_str) > 80:
            result_str = result_str[:77] + "..."
        print(f"  [OK]   {name}: {result_str}")


def main():
    print("="*60)
    print("  MarketData API Comprehensive Test")
    print("="*60)

    db = SessionLocal()
    results = {"passed": 0, "failed": 0, "warnings": 0}

    try:
        # Initialize DataProvider
        data_provider = DataProvider(db, account_id=0, environment="mainnet")

        # Build MarketData object
        prices = data_provider.get_prices(TEST_SYMBOLS)
        account_info = data_provider.get_account_info()
        positions = data_provider.get_positions()

        market_data = MarketData(
            available_balance=account_info.get("available_balance", 10000.0),
            total_equity=account_info.get("total_equity", 10000.0),
            used_margin=account_info.get("used_margin", 0.0),
            margin_usage_percent=account_info.get("margin_usage_percent", 0.0),
            maintenance_margin=account_info.get("maintenance_margin", 0.0),
            positions=positions,
            trigger_symbol="BTC",
            trigger_type="manual_test",
            prices=prices,
            _data_provider=data_provider,
        )

        # ============================================================
        # Test 1: MarketData Properties
        # ============================================================
        test_section("1. MarketData Properties")

        # Test prices
        for symbol in TEST_SYMBOLS:
            try:
                price = market_data.prices.get(symbol)
                test_item(f"prices['{symbol}']", price)
                results["passed" if price else "warnings"] += 1
            except Exception as e:
                test_item(f"prices['{symbol}']", None, str(e))
                results["failed"] += 1

        # Test other properties
        props = [
            ("trigger_symbol", market_data.trigger_symbol),
            ("trigger_type", market_data.trigger_type),
            ("available_balance", market_data.available_balance),
            ("total_equity", market_data.total_equity),
            ("used_margin", market_data.used_margin),
            ("margin_usage_percent", market_data.margin_usage_percent),
            ("positions", market_data.positions),
        ]
        for name, value in props:
            test_item(name, value)
            results["passed"] += 1

        # ============================================================
        # Test 2: get_indicator() - All indicators × All periods
        # ============================================================
        test_section("2. get_indicator() - Technical Indicators")

        for symbol in TEST_SYMBOLS[:1]:  # Test with BTC only for speed
            for indicator in TEST_INDICATORS:
                for period in TEST_PERIODS[:3]:  # Test 1m, 5m, 15m
                    try:
                        result = market_data.get_indicator(symbol, indicator, period)
                        test_item(f"get_indicator('{symbol}', '{indicator}', '{period}')", result)
                        results["passed" if result is not None else "warnings"] += 1
                    except Exception as e:
                        test_item(f"get_indicator('{symbol}', '{indicator}', '{period}')", None, str(e))
                        results["failed"] += 1

        # Test invalid indicator
        try:
            result = market_data.get_indicator("BTC", "INVALID_INDICATOR", "1h")
            test_item("get_indicator('BTC', 'INVALID_INDICATOR', '1h')", result)
            results["warnings"] += 1
        except Exception as e:
            test_item("get_indicator('BTC', 'INVALID_INDICATOR', '1h') [expected error]", f"Caught: {type(e).__name__}")
            results["passed"] += 1

        # ============================================================
        # Test 3: get_klines() - K-line data
        # ============================================================
        test_section("3. get_klines() - K-line Data")

        for symbol in TEST_SYMBOLS[:1]:
            for period in TEST_PERIODS[:3]:
                for count in [10, 50, 100]:
                    try:
                        klines = market_data.get_klines(symbol, period, count=count)
                        if klines and len(klines) > 0:
                            k = klines[-1]
                            test_item(
                                f"get_klines('{symbol}', '{period}', {count})",
                                f"{len(klines)} klines, last: O={k.open:.2f} H={k.high:.2f} L={k.low:.2f} C={k.close:.2f}"
                            )
                            results["passed"] += 1
                        else:
                            test_item(f"get_klines('{symbol}', '{period}', {count})", "Empty")
                            results["warnings"] += 1
                    except Exception as e:
                        test_item(f"get_klines('{symbol}', '{period}', {count})", None, str(e))
                        results["failed"] += 1

        # ============================================================
        # Test 4: get_flow() - Order Flow Metrics
        # ============================================================
        test_section("4. get_flow() - Order Flow Metrics")

        for symbol in TEST_SYMBOLS[:1]:
            for metric in TEST_FLOW_METRICS:
                for period in TEST_PERIODS[:2]:
                    try:
                        result = market_data.get_flow(symbol, metric, period)
                        test_item(f"get_flow('{symbol}', '{metric}', '{period}')", result)
                        results["passed" if result is not None else "warnings"] += 1
                    except Exception as e:
                        test_item(f"get_flow('{symbol}', '{metric}', '{period}')", None, str(e))
                        results["failed"] += 1

        # ============================================================
        # Test 5: get_regime() - Market Regime
        # ============================================================
        test_section("5. get_regime() - Market Regime Classification")

        for symbol in TEST_SYMBOLS[:1]:
            for period in TEST_PERIODS[:3]:
                try:
                    result = market_data.get_regime(symbol, period)
                    test_item(f"get_regime('{symbol}', '{period}')", result)
                    results["passed" if result is not None else "warnings"] += 1
                except Exception as e:
                    test_item(f"get_regime('{symbol}', '{period}')", None, str(e))
                    results["failed"] += 1

        # ============================================================
        # Test 6: get_price_change() - Price Change
        # ============================================================
        test_section("6. get_price_change() - Price Change")

        for symbol in TEST_SYMBOLS[:1]:
            for period in TEST_PERIODS:
                try:
                    result = market_data.get_price_change(symbol, period)
                    test_item(f"get_price_change('{symbol}', '{period}')", result)
                    results["passed" if result is not None else "warnings"] += 1
                except Exception as e:
                    test_item(f"get_price_change('{symbol}', '{period}')", None, str(e))
                    results["failed"] += 1

        # ============================================================
        # Test 7: Edge Cases - Invalid Parameters
        # ============================================================
        test_section("7. Edge Cases - Invalid Parameters")

        edge_cases = [
            ("Invalid symbol", lambda: market_data.get_indicator("INVALID_COIN", "RSI14", "1h")),
            ("Invalid period", lambda: market_data.get_indicator("BTC", "RSI14", "invalid")),
            ("Empty symbol", lambda: market_data.get_indicator("", "RSI14", "1h")),
            ("None symbol", lambda: market_data.get_indicator(None, "RSI14", "1h")),
        ]

        for name, test_func in edge_cases:
            try:
                result = test_func()
                test_item(f"{name}", f"Returned: {result}")
                results["warnings"] += 1  # Should probably error
            except Exception as e:
                test_item(f"{name} [expected error]", f"Caught: {type(e).__name__}: {str(e)[:50]}")
                results["passed"] += 1

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        results["failed"] += 1

    finally:
        db.close()

    # ============================================================
    # Summary
    # ============================================================
    test_section("TEST SUMMARY")
    print(f"  Passed:   {results['passed']}")
    print(f"  Warnings: {results['warnings']} (None/empty results)")
    print(f"  Failed:   {results['failed']}")
    print(f"\n  Total:    {sum(results.values())}")

    if results["failed"] > 0:
        print("\n  [!] Some tests FAILED - review errors above")
    elif results["warnings"] > 0:
        print("\n  [!] Some tests returned None - may need data or implementation")
    else:
        print("\n  [OK] All tests passed!")

    print("="*60)


if __name__ == "__main__":
    main()

