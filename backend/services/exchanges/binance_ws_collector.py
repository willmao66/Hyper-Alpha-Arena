"""
Binance WebSocket Data Collector Service

Collects real-time market data from Binance WebSocket streams:
- @aggTrade: Aggregated trades for Taker Buy/Sell volume (15-second aggregation)
- @markPrice@1s: Mark price and funding rate updates

Data is aggregated in 15-second windows to match Hyperliquid's granularity.
"""

import asyncio
import json
import logging
import threading
from decimal import Decimal
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

import websockets

from database.connection import SessionLocal
from services.exchanges.data_persistence import ExchangeDataPersistence
from database.models import MarketTradesAggregated

logger = logging.getLogger(__name__)

WS_URL = "wss://fstream.binance.com/ws"
AGGREGATION_WINDOW_SECONDS = 15


@dataclass
class SymbolAggregator:
    """Aggregates trade data for a single symbol"""
    symbol: str
    taker_buy_volume: Decimal = Decimal("0")
    taker_sell_volume: Decimal = Decimal("0")
    taker_buy_notional: Decimal = Decimal("0")
    taker_sell_notional: Decimal = Decimal("0")
    taker_buy_count: int = 0
    taker_sell_count: int = 0
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    window_start_ms: int = 0

    def add_trade(self, qty: Decimal, price: Decimal, is_buyer_maker: bool):
        """Add a trade to the aggregation"""
        notional = qty * price

        if is_buyer_maker:
            # Buyer is maker = Taker is seller
            self.taker_sell_volume += qty
            self.taker_sell_notional += notional
            self.taker_sell_count += 1
        else:
            # Seller is maker = Taker is buyer
            self.taker_buy_volume += qty
            self.taker_buy_notional += notional
            self.taker_buy_count += 1

        # Track high/low
        if self.high_price is None or price > self.high_price:
            self.high_price = price
        if self.low_price is None or price < self.low_price:
            self.low_price = price

    def reset(self, window_start_ms: int):
        """Reset for next aggregation window"""
        self.taker_buy_volume = Decimal("0")
        self.taker_sell_volume = Decimal("0")
        self.taker_buy_notional = Decimal("0")
        self.taker_sell_notional = Decimal("0")
        self.taker_buy_count = 0
        self.taker_sell_count = 0
        self.high_price = None
        self.low_price = None
        self.window_start_ms = window_start_ms


class BinanceWSCollector:
    """
    WebSocket-based data collector for Binance.
    Aggregates trade data in 15-second windows.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.symbols: List[str] = []
        self.aggregators: Dict[str, SymbolAggregator] = {}
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        logger.info("BinanceWSCollector initialized")

    def start(self, symbols: Optional[List[str]] = None):
        """Start the WebSocket collector"""
        if self.running:
            logger.warning("BinanceWSCollector already running")
            return

        if symbols is None:
            from services.hyperliquid_symbol_service import get_selected_symbols
            symbols = get_selected_symbols() or ["BTC"]

        self.symbols = symbols
        self.aggregators = {s: SymbolAggregator(symbol=s) for s in symbols}

        # Initialize window start time (aligned to 15-second boundary)
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        window_start = (now_ms // (AGGREGATION_WINDOW_SECONDS * 1000)) * (AGGREGATION_WINDOW_SECONDS * 1000)
        for agg in self.aggregators.values():
            agg.window_start_ms = window_start

        self.running = True

        # Start in background thread with its own event loop
        thread = threading.Thread(target=self._run_async_loop, daemon=True)
        thread.start()

        logger.info(f"BinanceWSCollector started with symbols: {symbols}")

    def _run_async_loop(self):
        """Run the async event loop in a separate thread"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_loop())
        except Exception as e:
            logger.error(f"WebSocket loop error: {e}")
        finally:
            self._loop.close()

    async def _main_loop(self):
        """Main WebSocket connection and message handling loop"""
        while self.running:
            try:
                await self._connect_and_process()
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                if self.running:
                    await asyncio.sleep(5)  # Reconnect delay

    async def _connect_and_process(self):
        """Connect to WebSocket and process messages"""
        # Build stream list
        streams = []
        for symbol in self.symbols:
            exchange_symbol = f"{symbol}usdt".lower()
            streams.append(f"{exchange_symbol}@aggTrade")

        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1
        }

        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to streams: {streams}")

            # Start flush timer
            flush_task = asyncio.create_task(self._periodic_flush())

            try:
                while self.running:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                        data = json.loads(msg)
                        self._process_message(data)
                    except asyncio.TimeoutError:
                        # Send ping to keep connection alive
                        await ws.ping()
            finally:
                flush_task.cancel()

    def _process_message(self, data: dict):
        """Process incoming WebSocket message"""
        event_type = data.get("e")

        if event_type == "aggTrade":
            symbol = data.get("s", "").replace("USDT", "")
            if symbol in self.aggregators:
                qty = Decimal(str(data["q"]))
                price = Decimal(str(data["p"]))
                is_buyer_maker = data["m"]
                self.aggregators[symbol].add_trade(qty, price, is_buyer_maker)

    async def _periodic_flush(self):
        """Periodically flush aggregated data to database"""
        while self.running:
            try:
                # Wait until next 15-second boundary
                now_ms = int(datetime.utcnow().timestamp() * 1000)
                current_window = (now_ms // (AGGREGATION_WINDOW_SECONDS * 1000)) * (AGGREGATION_WINDOW_SECONDS * 1000)
                next_window = current_window + (AGGREGATION_WINDOW_SECONDS * 1000)
                wait_ms = next_window - now_ms + 100  # Add 100ms buffer
                await asyncio.sleep(wait_ms / 1000)

                # Flush all aggregators
                self._flush_to_database()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Flush error: {e}")

    def _flush_to_database(self):
        """Flush aggregated data to database"""
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        current_window = (now_ms // (AGGREGATION_WINDOW_SECONDS * 1000)) * (AGGREGATION_WINDOW_SECONDS * 1000)

        db = SessionLocal()
        try:
            for symbol, agg in self.aggregators.items():
                if agg.window_start_ms == 0:
                    agg.reset(current_window)
                    continue

                # Only save if we have data
                if agg.taker_buy_count > 0 or agg.taker_sell_count > 0:
                    self._save_aggregated_trades(db, agg)

                # Reset for next window
                agg.reset(current_window)

        except Exception as e:
            logger.error(f"Database flush error: {e}")
            db.rollback()
        finally:
            db.close()

        # Run signal detection for Binance pools after data flush
        self._run_signal_detection()

    def _run_signal_detection(self):
        """Run signal detection for Binance pools only"""
        try:
            from services.signal_detection_service import signal_detection_service

            for symbol in self.symbols:
                # Binance detection doesn't need market_data context, queries DB directly
                market_data = {}
                triggered = signal_detection_service.detect_signals(
                    symbol, market_data, exchange="binance"
                )
                if triggered:
                    logger.info(f"Binance pools triggered for {symbol}: {[p['pool_name'] for p in triggered]}")

        except Exception as e:
            logger.error(f"Error in Binance signal detection: {e}", exc_info=True)

    def _save_aggregated_trades(self, db, agg: SymbolAggregator):
        """Save aggregated trade data to database"""
        try:
            existing = db.query(MarketTradesAggregated).filter(
                MarketTradesAggregated.exchange == "binance",
                MarketTradesAggregated.symbol == agg.symbol,
                MarketTradesAggregated.timestamp == agg.window_start_ms,
            ).first()

            if existing:
                existing.taker_buy_volume = agg.taker_buy_volume
                existing.taker_sell_volume = agg.taker_sell_volume
                existing.taker_buy_count = agg.taker_buy_count
                existing.taker_sell_count = agg.taker_sell_count
                existing.taker_buy_notional = agg.taker_buy_notional
                existing.taker_sell_notional = agg.taker_sell_notional
                existing.high_price = agg.high_price
                existing.low_price = agg.low_price
            else:
                record = MarketTradesAggregated(
                    exchange="binance",
                    symbol=agg.symbol,
                    timestamp=agg.window_start_ms,
                    taker_buy_volume=agg.taker_buy_volume,
                    taker_sell_volume=agg.taker_sell_volume,
                    taker_buy_count=agg.taker_buy_count,
                    taker_sell_count=agg.taker_sell_count,
                    taker_buy_notional=agg.taker_buy_notional,
                    taker_sell_notional=agg.taker_sell_notional,
                    high_price=agg.high_price,
                    low_price=agg.low_price,
                )
                db.add(record)

            db.commit()
            logger.debug(f"Saved trades for {agg.symbol}: buy={agg.taker_buy_volume}, sell={agg.taker_sell_volume}")

        except Exception as e:
            logger.error(f"Failed to save trades for {agg.symbol}: {e}")
            db.rollback()

    def stop(self):
        """Stop the WebSocket collector"""
        if not self.running:
            return

        self.running = False
        logger.info("BinanceWSCollector stopped")

    def refresh_symbols(self, new_symbols: List[str]):
        """Update symbols - requires restart"""
        logger.info(f"Symbol refresh requested: {new_symbols}")
        self.stop()
        self.start(new_symbols)


# Singleton instance
binance_ws_collector = BinanceWSCollector()
