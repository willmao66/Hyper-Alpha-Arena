#!/usr/bin/env python3
"""
Get actual API return values for documentation.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from database.connection import SessionLocal
from program_trader.data_provider import DataProvider
import json

db = SessionLocal()

try:
    provider = DataProvider(db, account_id=0, environment='testnet')

    print('=== get_market_data("BTC") ===')
    result = provider.get_market_data('BTC')
    print(json.dumps(result, indent=2))

    print('\n=== get_price_change("BTC", "1h") ===')
    result = provider.get_price_change('BTC', '1h')
    print(json.dumps(result, indent=2))

    print('\n=== get_klines("BTC", "1h", 3) ===')
    klines = provider.get_klines('BTC', '1h', 3)
    if klines:
        result = [{'timestamp': k.timestamp, 'open': k.open, 'high': k.high, 'low': k.low, 'close': k.close, 'volume': k.volume} for k in klines[:3]]
        print(json.dumps(result, indent=2))
    else:
        print('[]')

    print('\n=== get_indicator("BTC", "RSI", "1h") ===')
    result = provider.get_indicator('BTC', 'RSI', '1h')
    print(json.dumps(result, indent=2))

    print('\n=== get_indicator("BTC", "MACD", "1h") ===')
    result = provider.get_indicator('BTC', 'MACD', '1h')
    print(json.dumps(result, indent=2))

    print('\n=== get_flow("BTC", "CVD", "1h") ===')
    result = provider.get_flow('BTC', 'CVD', '1h')
    print(json.dumps(result, indent=2))

    print('\n=== get_regime("BTC", "1h") ===')
    regime = provider.get_regime('BTC', '1h')
    result = {
        'regime': regime.regime,
        'conf': regime.conf,
        'direction': regime.direction,
        'reason': regime.reason,
        'indicators': regime.indicators
    }
    print(json.dumps(result, indent=2))

finally:
    db.close()
