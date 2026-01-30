"""
Binance historical data backfill service
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional

from database.connection import SessionLocal
from database.models import BinanceBackfillTask
from .binance_adapter import BinanceAdapter
from .data_persistence import ExchangeDataPersistence

logger = logging.getLogger(__name__)

# Backfill limits
KLINE_BACKFILL_LIMIT = 1500  # ~25 hours of 1m klines
OI_BACKFILL_DAYS = 30
FUNDING_BACKFILL_DAYS = 365
SENTIMENT_BACKFILL_DAYS = 30


class BinanceBackfillService:
    """Service for backfilling Binance historical data"""

    def __init__(self):
        self.adapter = BinanceAdapter()
        self.running = False
        self.current_task_id: Optional[int] = None

    async def start_backfill(self, task_id: int):
        """Start backfill task"""
        if self.running:
            logger.warning("Backfill already running")
            return False

        self.running = True
        self.current_task_id = task_id

        try:
            await self._process_task(task_id)
        finally:
            self.running = False
            self.current_task_id = None

        return True

    async def _process_task(self, task_id: int):
        """Process a backfill task"""
        db = SessionLocal()
        try:
            task = db.query(BinanceBackfillTask).filter(
                BinanceBackfillTask.id == task_id
            ).first()

            if not task:
                logger.error(f"Backfill task {task_id} not found")
                return

            task.status = "running"
            task.progress = 0
            db.commit()

            symbols = task.symbols.split(",") if task.symbols else ["BTC"]
            total_steps = len(symbols) * 4  # 4 data types per symbol
            current_step = 0

            persistence = ExchangeDataPersistence(db)

            for symbol in symbols:
                # 1. Backfill K-lines
                try:
                    await self._backfill_klines(symbol, persistence)
                except Exception as e:
                    logger.error(f"Kline backfill failed for {symbol}: {e}")
                current_step += 1
                task.progress = int(current_step / total_steps * 100)
                db.commit()
                await asyncio.sleep(1)

                # 2. Backfill OI (30 days)
                try:
                    await self._backfill_oi(symbol, persistence)
                except Exception as e:
                    logger.error(f"OI backfill failed for {symbol}: {e}")
                current_step += 1
                task.progress = int(current_step / total_steps * 100)
                db.commit()
                await asyncio.sleep(1)

                # 3. Backfill Funding Rate (365 days)
                try:
                    await self._backfill_funding(symbol, persistence)
                except Exception as e:
                    logger.error(f"Funding backfill failed for {symbol}: {e}")
                current_step += 1
                task.progress = int(current_step / total_steps * 100)
                db.commit()
                await asyncio.sleep(1)

                # 4. Backfill Sentiment (30 days)
                try:
                    await self._backfill_sentiment(symbol, persistence)
                except Exception as e:
                    logger.error(f"Sentiment backfill failed for {symbol}: {e}")
                current_step += 1
                task.progress = int(current_step / total_steps * 100)
                db.commit()

            task.status = "completed"
            task.progress = 100
            db.commit()
            logger.info(f"Backfill task {task_id} completed")

        except Exception as e:
            logger.error(f"Backfill task {task_id} failed: {e}")
            task = db.query(BinanceBackfillTask).filter(
                BinanceBackfillTask.id == task_id
            ).first()
            if task:
                task.status = "failed"
                task.error_message = str(e)
                db.commit()
        finally:
            db.close()

    async def _backfill_klines(self, symbol: str, persistence: ExchangeDataPersistence):
        """Backfill K-line data (1500 records)"""
        logger.info(f"Backfilling klines for {symbol}")
        klines = self.adapter.fetch_klines(symbol, "1m", limit=KLINE_BACKFILL_LIMIT)
        if klines:
            result = persistence.save_klines(klines)
            persistence.save_taker_volumes_from_klines(klines)
            logger.info(f"Klines backfill {symbol}: {result}")

    async def _backfill_oi(self, symbol: str, persistence: ExchangeDataPersistence):
        """Backfill Open Interest history (30 days)"""
        logger.info(f"Backfilling OI for {symbol} ({OI_BACKFILL_DAYS} days)")
        all_oi = []
        end_time = int(time.time() * 1000)
        start_time = end_time - (OI_BACKFILL_DAYS * 24 * 60 * 60 * 1000)

        current_end = end_time
        while current_end > start_time:
            oi_list = self.adapter.fetch_open_interest_history(
                symbol, "5m", limit=500, end_time=current_end
            )
            if not oi_list:
                break
            all_oi.extend(oi_list)
            current_end = min(oi.timestamp for oi in oi_list) - 1
            await asyncio.sleep(0.5)

        if all_oi:
            result = persistence.save_open_interest_batch(all_oi)
            logger.info(f"OI backfill {symbol}: {result}, total {len(all_oi)} records")

    async def _backfill_funding(self, symbol: str, persistence: ExchangeDataPersistence):
        """Backfill Funding Rate history (365 days)"""
        logger.info(f"Backfilling funding for {symbol} ({FUNDING_BACKFILL_DAYS} days)")
        all_funding = []
        end_time = int(time.time() * 1000)
        start_time = end_time - (FUNDING_BACKFILL_DAYS * 24 * 60 * 60 * 1000)

        current_end = end_time
        while current_end > start_time:
            funding_list = self.adapter.fetch_funding_history(
                symbol, limit=1000, end_time=current_end
            )
            if not funding_list:
                break
            all_funding.extend(funding_list)
            current_end = min(f.timestamp for f in funding_list) - 1
            await asyncio.sleep(0.5)

        if all_funding:
            result = persistence.save_funding_rates(all_funding)
            logger.info(f"Funding backfill {symbol}: {result}, total {len(all_funding)} records")

    async def _backfill_sentiment(self, symbol: str, persistence: ExchangeDataPersistence):
        """Backfill Long/Short ratio history (30 days)"""
        logger.info(f"Backfilling sentiment for {symbol} ({SENTIMENT_BACKFILL_DAYS} days)")
        all_sentiment = []
        end_time = int(time.time() * 1000)
        start_time = end_time - (SENTIMENT_BACKFILL_DAYS * 24 * 60 * 60 * 1000)

        current_end = end_time
        while current_end > start_time:
            sentiment_list = self.adapter.fetch_sentiment_history(
                symbol, "5m", limit=500, end_time=current_end
            )
            if not sentiment_list:
                break
            all_sentiment.extend(sentiment_list)
            current_end = min(s.timestamp for s in sentiment_list) - 1
            await asyncio.sleep(0.5)

        if all_sentiment:
            result = persistence.save_sentiment_metrics(all_sentiment)
            logger.info(f"Sentiment backfill {symbol}: {result}, total {len(all_sentiment)} records")


# Singleton instance
binance_backfill_service = BinanceBackfillService()