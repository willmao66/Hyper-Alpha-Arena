"""
Integration test for Binance data persistence.
Tests fetching data from Binance and saving to database.

Run inside container: python -m services.exchanges.test_data_persistence
"""

import sys
sys.path.insert(0, "/app/backend")

from database.connection import SessionLocal
from services.exchanges.binance_adapter import BinanceAdapter
from services.exchanges.data_persistence import ExchangeDataPersistence
from database.models import CryptoKline, MarketTradesAggregated, MarketAssetMetrics


def test_kline_persistence():
    """Test fetching and saving K-line data."""
    print("=== Testing K-line Persistence ===")

    adapter = BinanceAdapter()
    db = SessionLocal()

    try:
        # Fetch K-lines from Binance
        print("1. Fetching BTC 1m K-lines from Binance...")
        klines = adapter.fetch_klines("BTC", "1m", limit=5)
        print(f"   Fetched {len(klines)} klines")

        # Save to database
        print("2. Saving to database...")
        persistence = ExchangeDataPersistence(db)
        result = persistence.save_klines(klines)
        print(f"   Result: {result}")

        # Also save taker volumes
        print("3. Saving taker volumes from klines...")
        result2 = persistence.save_taker_volumes_from_klines(klines)
        print(f"   Result: {result2}")

        # Verify data in database
        print("4. Verifying data in database...")
        count = db.query(CryptoKline).filter(
            CryptoKline.exchange == "binance",
            CryptoKline.symbol == "BTC",
        ).count()
        print(f"   Found {count} BTC klines from Binance")

        trade_count = db.query(MarketTradesAggregated).filter(
            MarketTradesAggregated.exchange == "binance",
            MarketTradesAggregated.symbol == "BTC",
        ).count()
        print(f"   Found {trade_count} BTC trade aggregates from Binance")

        print("K-line persistence test PASSED!")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_asset_metrics_persistence():
    """Test fetching and saving OI and funding rate."""
    print("\n=== Testing Asset Metrics Persistence ===")

    adapter = BinanceAdapter()
    db = SessionLocal()

    try:
        persistence = ExchangeDataPersistence(db)

        # Test OI history
        print("1. Fetching BTC OI history...")
        oi_list = adapter.fetch_open_interest_history("BTC", "5m", limit=5)
        print(f"   Fetched {len(oi_list)} OI records")

        print("2. Saving OI to database...")
        result = persistence.save_open_interest_batch(oi_list)
        print(f"   Result: {result}")

        # Test funding rate history
        print("3. Fetching BTC funding rate history...")
        funding_list = adapter.fetch_funding_history("BTC", limit=5)
        print(f"   Fetched {len(funding_list)} funding records")

        print("4. Saving funding rates to database...")
        result2 = persistence.save_funding_rate_batch(funding_list)
        print(f"   Result: {result2}")

        # Verify
        print("5. Verifying data in database...")
        count = db.query(MarketAssetMetrics).filter(
            MarketAssetMetrics.exchange == "binance",
            MarketAssetMetrics.symbol == "BTC",
        ).count()
        print(f"   Found {count} BTC asset metrics from Binance")

        print("Asset metrics persistence test PASSED!")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_orderbook_persistence():
    """Test fetching and saving orderbook snapshot."""
    print("\n=== Testing Orderbook Persistence ===")

    adapter = BinanceAdapter()
    db = SessionLocal()

    try:
        persistence = ExchangeDataPersistence(db)

        print("1. Fetching BTC orderbook...")
        orderbook = adapter.fetch_orderbook("BTC", depth=10)
        print(f"   Best bid={orderbook.best_bid}, ask={orderbook.best_ask}")

        print("2. Saving to database...")
        result = persistence.save_orderbook(orderbook)
        print(f"   Result: {result}")

        print("Orderbook persistence test PASSED!")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_sentiment_persistence():
    """Test fetching and saving sentiment data."""
    print("\n=== Testing Sentiment Persistence ===")

    adapter = BinanceAdapter()
    db = SessionLocal()

    try:
        from database.models import MarketSentimentMetrics
        persistence = ExchangeDataPersistence(db)

        # Test single sentiment
        print("1. Fetching BTC sentiment (top position ratio)...")
        sentiment = adapter.fetch_sentiment("BTC")
        print(f"   Long ratio={sentiment.long_ratio}, Short ratio={sentiment.short_ratio}")

        print("2. Saving to database...")
        result = persistence.save_sentiment(sentiment)
        print(f"   Result: {result}")

        # Test batch sentiment history
        print("3. Fetching BTC sentiment history...")
        sentiment_list = adapter.fetch_sentiment_history("BTC", limit=5)
        print(f"   Fetched {len(sentiment_list)} sentiment records")

        print("4. Saving batch to database...")
        result2 = persistence.save_sentiment_batch(sentiment_list)
        print(f"   Result: {result2}")

        # Verify
        print("5. Verifying data in database...")
        count = db.query(MarketSentimentMetrics).filter(
            MarketSentimentMetrics.exchange == "binance",
            MarketSentimentMetrics.symbol == "BTC",
        ).count()
        print(f"   Found {count} BTC sentiment records from Binance")

        print("Sentiment persistence test PASSED!")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    all_passed = True
    all_passed &= test_kline_persistence()
    all_passed &= test_asset_metrics_persistence()
    all_passed &= test_orderbook_persistence()
    all_passed &= test_sentiment_persistence()

    print("\n" + "=" * 50)
    if all_passed:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED!")
        sys.exit(1)
