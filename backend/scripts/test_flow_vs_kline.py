#!/usr/bin/env python3
"""
Test script to compare OHLC data from:
1. CryptoKline table (standard K-line data)
2. MarketTradesAggregated table (15-second flow data aggregated)

This validates whether we can use flow data to calculate price metrics
instead of relying on closed K-lines.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hyper_arena")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def get_kline_ohlc(db, symbol: str, period: str, timestamp_ms: int):
    """Get OHLC from CryptoKline table"""
    # CryptoKline.timestamp is in seconds
    timestamp_sec = timestamp_ms // 1000

    result = db.execute(text("""
        SELECT open_price, high_price, low_price, close_price, volume
        FROM crypto_klines
        WHERE symbol = :symbol
          AND period = :period
          AND timestamp = :timestamp
          AND environment = 'mainnet'
        LIMIT 1
    """), {"symbol": symbol, "period": period, "timestamp": timestamp_sec}).fetchone()

    if result:
        return {
            "open": float(result[0]) if result[0] else None,
            "high": float(result[1]) if result[1] else None,
            "low": float(result[2]) if result[2] else None,
            "close": float(result[3]) if result[3] else None,
            "volume": float(result[4]) if result[4] else None,
        }
    return None


def get_flow_aggregated_ohlc(db, symbol: str, period_ms: int, start_ts_ms: int):
    """
    Aggregate OHLC from MarketTradesAggregated (15-second data)

    Args:
        symbol: Trading symbol (e.g., "BTC")
        period_ms: Period in milliseconds (e.g., 3600000 for 1h)
        start_ts_ms: Start timestamp of the period in milliseconds
    """
    end_ts_ms = start_ts_ms + period_ms

    # Query all 15-second records within this period
    records = db.execute(text("""
        SELECT timestamp, vwap, high_price, low_price,
               taker_buy_notional + taker_sell_notional as total_notional
        FROM market_trades_aggregated
        WHERE symbol = :symbol
          AND timestamp >= :start_ts
          AND timestamp < :end_ts
        ORDER BY timestamp ASC
    """), {"symbol": symbol.upper(), "start_ts": start_ts_ms, "end_ts": end_ts_ms}).fetchall()

    if not records:
        return None

    # Aggregate OHLC
    first_vwap = None
    last_vwap = None
    high = None
    low = None
    total_volume = Decimal("0")

    for ts, vwap, high_price, low_price, notional in records:
        if vwap is not None:
            if first_vwap is None:
                first_vwap = float(vwap)
            last_vwap = float(vwap)

        if high_price is not None:
            if high is None or float(high_price) > high:
                high = float(high_price)

        if low_price is not None:
            if low is None or float(low_price) < low:
                low = float(low_price)

        if notional:
            total_volume += notional

    return {
        "open": first_vwap,
        "high": high,
        "low": low,
        "close": last_vwap,
        "volume": float(total_volume) if total_volume else None,
        "record_count": len(records),
    }


def compare_ohlc(kline: dict, flow: dict) -> dict:
    """Calculate percentage difference between kline and flow OHLC"""
    def pct_diff(a, b):
        if a is None or b is None or a == 0:
            return None
        return round((b - a) / a * 100, 4)

    return {
        "open_diff_pct": pct_diff(kline["open"], flow["open"]),
        "high_diff_pct": pct_diff(kline["high"], flow["high"]),
        "low_diff_pct": pct_diff(kline["low"], flow["low"]),
        "close_diff_pct": pct_diff(kline["close"], flow["close"]),
    }


PERIOD_MS = {
    "1m": 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
}


def run_comparison(symbol: str = "BTC", period: str = "1h", num_periods: int = 10):
    """
    Compare K-line vs Flow-aggregated OHLC for multiple periods.

    Args:
        symbol: Trading symbol
        period: K-line period (1m, 5m, 15m, 1h)
        num_periods: Number of historical periods to compare
    """
    db = Session()
    period_ms = PERIOD_MS.get(period)
    if not period_ms:
        print(f"Unsupported period: {period}")
        return

    # Get recent closed K-line timestamps
    klines = db.execute(text("""
        SELECT timestamp
        FROM crypto_klines
        WHERE symbol = :symbol
          AND period = :period
          AND environment = 'mainnet'
        ORDER BY timestamp DESC
        LIMIT :limit
    """), {"symbol": symbol, "period": period, "limit": num_periods}).fetchall()

    if not klines:
        print(f"No K-line data found for {symbol} {period}")
        db.close()
        return

    print(f"\n{'='*80}")
    print(f"Comparing {symbol} {period} K-line vs Flow-aggregated OHLC")
    print(f"{'='*80}\n")

    results = []
    for (ts_sec,) in klines:
        ts_ms = ts_sec * 1000
        dt = datetime.utcfromtimestamp(ts_sec)

        kline = get_kline_ohlc(db, symbol, period, ts_ms)
        flow = get_flow_aggregated_ohlc(db, symbol, period_ms, ts_ms)

        if kline and flow:
            diff = compare_ohlc(kline, flow)
            results.append(diff)

            print(f"Time: {dt.strftime('%Y-%m-%d %H:%M')}")
            print(f"  K-line:  O={kline['open']:.2f}  H={kline['high']:.2f}  "
                  f"L={kline['low']:.2f}  C={kline['close']:.2f}")
            print(f"  Flow:    O={flow['open']:.2f}  H={flow['high']:.2f}  "
                  f"L={flow['low']:.2f}  C={flow['close']:.2f}  "
                  f"(records: {flow['record_count']})")
            print(f"  Diff(%): O={diff['open_diff_pct']}  H={diff['high_diff_pct']}  "
                  f"L={diff['low_diff_pct']}  C={diff['close_diff_pct']}")
            print()
        else:
            print(f"Time: {dt.strftime('%Y-%m-%d %H:%M')} - Missing data")
            print(f"  K-line: {kline}")
            print(f"  Flow: {flow}")
            print()

    # Summary statistics
    if results:
        print(f"\n{'='*80}")
        print("Summary Statistics (absolute % difference)")
        print(f"{'='*80}")

        for field in ["open_diff_pct", "high_diff_pct", "low_diff_pct", "close_diff_pct"]:
            values = [abs(r[field]) for r in results if r[field] is not None]
            if values:
                avg = sum(values) / len(values)
                max_val = max(values)
                print(f"  {field.replace('_diff_pct', '').upper():6}: "
                      f"avg={avg:.4f}%  max={max_val:.4f}%")

    db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compare K-line vs Flow OHLC")
    parser.add_argument("--symbol", default="BTC", help="Trading symbol")
    parser.add_argument("--period", default="1h", help="K-line period")
    parser.add_argument("--num", type=int, default=10, help="Number of periods")
    args = parser.parse_args()

    run_comparison(args.symbol, args.period, args.num)
