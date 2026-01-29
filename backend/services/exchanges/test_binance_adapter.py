"""
Test script for Binance adapter.
Run: python -m backend.services.exchanges.test_binance_adapter
"""

import sys
sys.path.insert(0, "/home/wwwroot/hyper-alpha-arena-prod")

from backend.services.exchanges.binance_adapter import BinanceAdapter
from backend.services.exchanges.symbol_mapper import SymbolMapper


def test_symbol_mapper():
    """Test symbol mapping."""
    print("=== Testing Symbol Mapper ===")

    # Internal to Binance
    assert SymbolMapper.to_exchange("BTC", "binance") == "BTCUSDT"
    assert SymbolMapper.to_exchange("ETH", "binance") == "ETHUSDT"
    assert SymbolMapper.to_exchange("SOL", "binance") == "SOLUSDT"

    # Binance to Internal
    assert SymbolMapper.to_internal("BTCUSDT", "binance") == "BTC"
    assert SymbolMapper.to_internal("ETHUSDT", "binance") == "ETH"

    # Hyperliquid (no conversion)
    assert SymbolMapper.to_exchange("BTC", "hyperliquid") == "BTC"
    assert SymbolMapper.to_internal("BTC", "hyperliquid") == "BTC"

    print("Symbol mapper tests passed!")


def test_binance_adapter():
    """Test Binance adapter data fetching."""
    print("\n=== Testing Binance Adapter ===")

    adapter = BinanceAdapter(environment="mainnet")

    # Test K-lines
    print("\n1. Fetching BTC 1m K-lines...")
    klines = adapter.fetch_klines("BTC", "1m", limit=3)
    print(f"   Got {len(klines)} klines")
    if klines:
        k = klines[0]
        print(f"   First: ts={k.timestamp}, O={k.open_price}, H={k.high_price}, "
              f"L={k.low_price}, C={k.close_price}, V={k.volume}")
        print(f"   Taker buy={k.taker_buy_volume}, sell={k.taker_sell_volume}")

    # Test Orderbook
    print("\n2. Fetching BTC orderbook...")
    ob = adapter.fetch_orderbook("BTC", depth=10)
    print(f"   Best bid={ob.best_bid}, ask={ob.best_ask}, spread={ob.spread_bps:.2f}bps")
    print(f"   Bid depth={ob.bid_depth_sum}, Ask depth={ob.ask_depth_sum}")

    # Test Funding Rate
    print("\n3. Fetching BTC funding rate...")
    funding = adapter.fetch_funding_rate("BTC")
    print(f"   Rate={funding.funding_rate}, time={funding.timestamp}")

    # Test Open Interest
    print("\n4. Fetching BTC open interest...")
    oi = adapter.fetch_open_interest("BTC")
    print(f"   OI={oi.open_interest}")

    # Test Sentiment (Long/Short Ratio)
    print("\n5. Fetching BTC sentiment...")
    sentiment = adapter.fetch_sentiment("BTC")
    if sentiment:
        print(f"   Long={sentiment.long_ratio}, Short={sentiment.short_ratio}, "
              f"Ratio={sentiment.long_short_ratio}")

    # Test Historical OI
    print("\n6. Fetching BTC OI history...")
    oi_hist = adapter.fetch_open_interest_history("BTC", "5m", limit=3)
    print(f"   Got {len(oi_hist)} records")

    # Test Historical Funding
    print("\n7. Fetching BTC funding history...")
    funding_hist = adapter.fetch_funding_history("BTC", limit=3)
    print(f"   Got {len(funding_hist)} records")

    print("\n=== All tests passed! ===")


if __name__ == "__main__":
    test_symbol_mapper()
    test_binance_adapter()
