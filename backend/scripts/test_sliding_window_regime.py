"""
Test script: Compare Regime classification accuracy between:
- Method A: Current system logic (get_market_regime at trigger time T)
- Method B: Sliding window (ATR from closed K-lines + price from flow data)
- Ground Truth: Backtest result (get_market_regime at K-line close time)

Goal: Verify if sliding window method makes real-time triggers closer to backtest results.

Usage: python scripts/test_sliding_window_regime.py --symbol BTC --period 5m --num 20
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
import math
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import and_, func

from database.connection import SessionLocal
from database.models import MarketTradesAggregated
from services.market_regime_service import (
    get_market_regime, classify_regime, fetch_kline_data,
    get_default_config, calculate_price_metrics
)
from services.market_flow_indicators import get_flow_indicators_for_prompt
from services.technical_indicators import calculate_indicators


def get_flow_price_data(db, symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
    """Get flow records for sliding window price calculation"""
    records = db.query(MarketTradesAggregated).filter(
        and_(
            MarketTradesAggregated.symbol == symbol,
            MarketTradesAggregated.timestamp >= start_ms,
            MarketTradesAggregated.timestamp <= end_ms
        )
    ).order_by(MarketTradesAggregated.timestamp).all()

    return [{
        'timestamp': r.timestamp,
        'vwap': float(r.vwap) if r.vwap else None,
        'high_price': float(r.high_price) if r.high_price else None,
        'low_price': float(r.low_price) if r.low_price else None,
    } for r in records]


def calc_sliding_window_price(flow_records: List[Dict], atr: float) -> Dict[str, float]:
    """Calculate price_atr and price_range_atr from sliding window flow data"""
    if not flow_records or atr <= 0:
        return {'price_atr': 0.0, 'price_range_atr': 0.0, 'valid': False}

    valid = [r for r in flow_records if r['vwap'] and r['high_price'] and r['low_price']]
    if len(valid) < 2:
        return {'price_atr': 0.0, 'price_range_atr': 0.0, 'valid': False}

    first_vwap = valid[0]['vwap']
    last_vwap = valid[-1]['vwap']
    high = max(r['high_price'] for r in valid)
    low = min(r['low_price'] for r in valid)

    return {
        'price_atr': (last_vwap - first_vwap) / atr,
        'price_range_atr': (high - low) / atr,
        'record_count': len(valid),
        'valid': True
    }


def floor_to_period(ts_ms: int, period_minutes: int) -> int:
    """Floor timestamp to period boundary"""
    interval_ms = period_minutes * 60 * 1000
    return (ts_ms // interval_ms) * interval_ms


def run_test(symbol: str = "BTC", period: str = "5m", num_tests: int = 20):
    """
    Run comparison test:
    - Method A: Current get_market_regime() at trigger time
    - Method B: Sliding window price + closed K-line ATR
    - Ground Truth: get_market_regime() at K-line close time (backtest)
    """
    db = SessionLocal()
    config = get_default_config(db)

    if not config:
        print("Error: No default regime config found")
        return

    period_minutes = int(period[:-1]) if period.endswith('m') else 5
    period_ms = period_minutes * 60 * 1000

    # Get time range
    time_range = db.query(
        func.min(MarketTradesAggregated.timestamp),
        func.max(MarketTradesAggregated.timestamp)
    ).filter(MarketTradesAggregated.symbol == symbol).first()

    min_ts, max_ts = time_range
    if not min_ts or not max_ts:
        print(f"Error: No flow data for {symbol}")
        return

    safe_start = min_ts + 90 * 60 * 1000
    safe_end = max_ts - (period_minutes + 5) * 60 * 1000

    print(f"\n{'='*80}")
    print(f"Regime Test: Current vs Sliding Window vs Backtest")
    print(f"Symbol: {symbol}, Period: {period}")
    print(f"Time: {datetime.fromtimestamp(safe_start/1000)} ~ {datetime.fromtimestamp(safe_end/1000)}")
    print(f"Tests: {num_tests}")
    print(f"{'='*80}")

    results = []

    for i in range(num_tests):
        # Random trigger time (not aligned to K-line boundary)
        test_ts = random.randint(safe_start, safe_end)
        test_ts += random.randint(15, period_minutes * 60 - 30) * 1000

        kline_start = floor_to_period(test_ts, period_minutes)
        kline_end = kline_start + period_ms
        elapsed_sec = (test_ts - kline_start) / 1000
        elapsed_pct = elapsed_sec / (period_minutes * 60) * 100

        print(f"\n--- Test {i+1}: {datetime.fromtimestamp(test_ts/1000).strftime('%Y-%m-%d %H:%M:%S')} ---")
        print(f"K-line: {datetime.fromtimestamp(kline_start/1000).strftime('%H:%M')} - "
              f"{datetime.fromtimestamp(kline_end/1000).strftime('%H:%M')} "
              f"(elapsed: {elapsed_pct:.1f}%)")

        # === Method A: Current system logic ===
        result_A = get_market_regime(db, symbol, period, timestamp_ms=test_ts)
        regime_A = result_A.get("regime", "unknown")

        # === Ground Truth: Backtest (K-line closed) ===
        result_truth = get_market_regime(db, symbol, period, timestamp_ms=kline_end + 1000)
        regime_truth = result_truth.get("regime", "unknown")

        # === Method B: Sliding window ===
        # ATR from closed K-lines only (new mode)
        kline_for_atr = fetch_kline_data(db, symbol, period, limit=50, current_time_ms=kline_start)
        if len(kline_for_atr) < 15:
            print(f"  Skip: Not enough K-line data")
            continue

        indicators = calculate_indicators(kline_for_atr, ["ATR14"])
        atr = indicators.get("ATR14", [])[-1] if indicators.get("ATR14") else 0
        if atr <= 0:
            print(f"  Skip: Invalid ATR")
            continue

        # Price from sliding window (past N minutes of flow data)
        flow_records = get_flow_price_data(db, symbol, test_ts - period_ms, test_ts)
        sw_price = calc_sliding_window_price(flow_records, atr)
        if not sw_price['valid']:
            print(f"  Skip: Invalid sliding window data")
            continue

        # Get flow indicators (CVD, OI, Taker) - same as current system
        flow_data = get_flow_indicators_for_prompt(db, symbol, period, ["CVD", "TAKER", "OI_DELTA"], test_ts)
        cvd_data = flow_data.get("CVD", {})
        taker_data = flow_data.get("TAKER", {})
        oi_data = flow_data.get("OI_DELTA", {})

        taker_buy = taker_data.get("buy", 0)
        taker_sell = taker_data.get("sell", 0)
        total_notional = taker_buy + taker_sell
        cvd_ratio = cvd_data.get("current", 0) / total_notional if total_notional > 0 else 0
        taker_log_ratio = math.log(taker_buy / taker_sell) if taker_buy > 0 and taker_sell > 0 else 0
        oi_delta = oi_data.get("current", 0) if oi_data else 0

        # RSI from closed K-lines
        rsi_indicators = calculate_indicators(kline_for_atr, ["RSI14"])
        rsi = rsi_indicators.get("RSI14", [50])[-1] if rsi_indicators.get("RSI14") else 50

        # Classify with sliding window price
        regime_B, _ = classify_regime(
            cvd_ratio, taker_log_ratio, oi_delta,
            sw_price['price_atr'], rsi, sw_price['price_range_atr'], config
        )

        # === Compare ===
        A_match = regime_A == regime_truth
        B_match = regime_B == regime_truth

        print(f"  Method A (Current):  {regime_A:12} {'OK' if A_match else 'MISS'}")
        print(f"  Method B (Sliding):  {regime_B:12} {'OK' if B_match else 'MISS'}")
        print(f"  Ground Truth:        {regime_truth:12}")

        results.append({
            'elapsed_pct': elapsed_pct,
            'regime_A': regime_A, 'regime_B': regime_B, 'regime_truth': regime_truth,
            'A_match': A_match, 'B_match': B_match
        })

    # === Summary ===
    print_summary(results)
    db.close()


def print_summary(results: List[Dict]):
    """Print test summary"""
    if not results:
        print("\nNo valid test results")
        return

    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")

    total = len(results)
    A_correct = sum(1 for r in results if r['A_match'])
    B_correct = sum(1 for r in results if r['B_match'])

    print(f"\nOverall Accuracy (vs Backtest Ground Truth):")
    print(f"  Method A (Current):        {A_correct}/{total} ({A_correct/total*100:.1f}%)")
    print(f"  Method B (Sliding Window): {B_correct}/{total} ({B_correct/total*100:.1f}%)")

    # By K-line progress
    early = [r for r in results if r['elapsed_pct'] < 33]
    mid = [r for r in results if 33 <= r['elapsed_pct'] < 66]
    late = [r for r in results if r['elapsed_pct'] >= 66]

    print(f"\nAccuracy by K-line Progress:")
    for name, group in [("Early (0-33%)", early), ("Mid (33-66%)", mid), ("Late (66-100%)", late)]:
        if group:
            a_acc = sum(1 for r in group if r['A_match']) / len(group) * 100
            b_acc = sum(1 for r in group if r['B_match']) / len(group) * 100
            better = "B better" if b_acc > a_acc else "A better" if a_acc > b_acc else "Same"
            print(f"  {name:16} n={len(group):2}  A={a_acc:5.1f}%  B={b_acc:5.1f}%  {better}")

    # Misclassification details
    misses = [r for r in results if not r['A_match'] or not r['B_match']]
    if misses:
        print(f"\nMisclassification Details:")
        for r in misses:
            if r['A_match'] and not r['B_match']:
                status = "B miss"
            elif not r['A_match'] and r['B_match']:
                status = "A miss"
            else:
                status = "Both miss"
            print(f"  [{r['elapsed_pct']:5.1f}%] {status:10} "
                  f"A={r['regime_A']:12} B={r['regime_B']:12} Truth={r['regime_truth']}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Test sliding window regime')
    parser.add_argument('--symbol', default='BTC', help='Symbol')
    parser.add_argument('--period', default='5m', help='Period (1m, 5m, 15m)')
    parser.add_argument('--num', type=int, default=20, help='Number of tests')
    args = parser.parse_args()

    run_test(symbol=args.symbol, period=args.period, num_tests=args.num)
