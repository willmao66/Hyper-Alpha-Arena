"""System configuration and data management API routes"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.connection import get_db
from database.models import SystemConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])

# Config keys
HYPERLIQUID_RETENTION_KEY = "hyperliquid_retention_days"
BINANCE_RETENTION_KEY = "binance_retention_days"
DEFAULT_RETENTION_DAYS = 365


class RetentionDaysRequest(BaseModel):
    days: int
    exchange: str = "hyperliquid"


class RetentionDaysResponse(BaseModel):
    days: int
    exchange: str = "hyperliquid"


def get_retention_key(exchange: str) -> str:
    """Get the config key for a specific exchange"""
    if exchange == "binance":
        return BINANCE_RETENTION_KEY
    return HYPERLIQUID_RETENTION_KEY


def get_retention_days(db: Session, exchange: str = "hyperliquid") -> int:
    """Get configured retention days from SystemConfig for specific exchange"""
    key = get_retention_key(exchange)
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if config and config.value:
        try:
            return int(config.value)
        except ValueError:
            pass
    return DEFAULT_RETENTION_DAYS


def set_retention_days(db: Session, days: int, exchange: str = "hyperliquid") -> int:
    """Set retention days in SystemConfig for specific exchange"""
    key = get_retention_key(exchange)
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if config:
        config.value = str(days)
    else:
        config = SystemConfig(
            key=key,
            value=str(days),
            description=f"{exchange.capitalize()} market data retention period in days"
        )
        db.add(config)
    db.commit()
    return days


@router.get("/storage-stats")
def get_storage_stats(exchange: str = "hyperliquid", db: Session = Depends(get_db)):
    """Get storage statistics for market flow data tables by exchange"""
    try:
        # Query table sizes filtered by exchange
        if exchange == "binance":
            # Binance also uses market_sentiment_metrics
            size_query = text("""
                SELECT
                    relname as table_name,
                    pg_total_relation_size(relid) as total_bytes
                FROM pg_catalog.pg_statio_user_tables
                WHERE relname IN (
                    'market_trades_aggregated',
                    'market_asset_metrics',
                    'market_orderbook_snapshots',
                    'market_sentiment_metrics',
                    'crypto_klines'
                )
            """)
        else:
            size_query = text("""
                SELECT
                    relname as table_name,
                    pg_total_relation_size(relid) as total_bytes
                FROM pg_catalog.pg_statio_user_tables
                WHERE relname IN (
                    'market_trades_aggregated',
                    'market_asset_metrics',
                    'market_orderbook_snapshots'
                )
            """)
        result = db.execute(size_query)
        rows = result.fetchall()

        tables = {}
        total_bytes = 0
        for row in rows:
            table_name = row[0]
            size_bytes = row[1] or 0
            tables[table_name] = round(size_bytes / (1024 * 1024), 1)
            total_bytes += size_bytes

        total_mb = round(total_bytes / (1024 * 1024), 1)
        retention_days = get_retention_days(db, exchange)

        # Get symbol count and date range for estimation
        count_query = text("""
            SELECT
                COUNT(DISTINCT symbol) as symbol_count,
                MIN(timestamp) as min_ts,
                MAX(timestamp) as max_ts
            FROM market_trades_aggregated
            WHERE exchange = :exchange
        """)
        count_result = db.execute(count_query, {"exchange": exchange}).fetchone()
        symbol_count = count_result[0] or 1
        min_ts = count_result[1]
        max_ts = count_result[2]

        # Calculate per-symbol-per-day estimate
        if min_ts and max_ts and total_mb > 0:
            days_of_data = max((max_ts - min_ts) / (1000 * 86400), 1)
            per_symbol_per_day = total_mb / (symbol_count * days_of_data)
        else:
            per_symbol_per_day = 6.7  # fallback estimate

        return {
            "exchange": exchange,
            "total_size_mb": total_mb,
            "tables": tables,
            "retention_days": retention_days,
            "symbol_count": symbol_count,
            "estimated_per_symbol_per_day_mb": round(per_symbol_per_day, 2)
        }
    except Exception as e:
        logger.error(f"Failed to get storage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-coverage")
def get_data_coverage(
    days: int = 30,
    symbol: str = None,
    tz_offset: int = 0,
    exchange: str = "hyperliquid",
    db: Session = Depends(get_db)
):
    """Get data coverage heatmap for market flow data.
    If symbol is provided, returns coverage for that symbol only.
    If symbol is not provided, returns list of available symbols.
    tz_offset: timezone offset in minutes (e.g., -480 for UTC+8)
    exchange: hyperliquid or binance
    """
    try:
        import time
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - (days * 24 * 60 * 60 * 1000)

        # If no symbol specified, return available symbols list
        if not symbol:
            symbols_query = text("""
                SELECT DISTINCT symbol FROM market_trades_aggregated
                WHERE timestamp >= :start_ms AND exchange = :exchange
                ORDER BY symbol
            """)
            result = db.execute(symbols_query, {"start_ms": start_ms, "exchange": exchange})
            symbols = [row[0] for row in result.fetchall()]
            return {"symbols": symbols, "exchange": exchange}

        # Convert tz_offset from minutes to interval string
        offset_minutes = -tz_offset
        offset_interval = f"{offset_minutes} minutes"

        # Query hourly coverage
        coverage_query = text("""
            SELECT
                to_char(to_timestamp(timestamp / 1000) + interval :tz_interval, 'YYYY-MM-DD') as date,
                COUNT(DISTINCT to_char(to_timestamp(timestamp / 1000) + interval :tz_interval, 'HH24')) as hours_with_data
            FROM market_trades_aggregated
            WHERE timestamp >= :start_ms AND symbol = :symbol AND exchange = :exchange
            GROUP BY to_char(to_timestamp(timestamp / 1000) + interval :tz_interval, 'YYYY-MM-DD')
            ORDER BY date
        """)
        result = db.execute(coverage_query, {
            "start_ms": start_ms,
            "symbol": symbol.upper(),
            "tz_interval": offset_interval,
            "exchange": exchange
        })
        rows = result.fetchall()

        # Build coverage list
        coverage_map = {}
        for row in rows:
            date_str = row[0]
            hours = row[1]
            coverage_pct = min(100, round(hours / 24 * 100))
            coverage_map[date_str] = coverage_pct

        # Generate date list
        from datetime import timezone as tz
        local_offset = timedelta(minutes=offset_minutes)
        local_tz = tz(local_offset)
        end_date = datetime.now(local_tz).date()
        start_date = end_date - timedelta(days=days - 1)
        coverage = []
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            coverage.append({
                "date": date_str,
                "pct": coverage_map.get(date_str, 0)
            })
            current += timedelta(days=1)

        return {
            "symbol": symbol.upper(),
            "days": days,
            "coverage": coverage,
            "exchange": exchange
        }
    except Exception as e:
        logger.error(f"Failed to get data coverage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/retention-days")
def get_retention_days_api(exchange: str = "hyperliquid", db: Session = Depends(get_db)):
    """Get current retention days setting for specific exchange"""
    days = get_retention_days(db, exchange)
    return RetentionDaysResponse(days=days, exchange=exchange)


@router.put("/retention-days")
def update_retention_days(request: RetentionDaysRequest, db: Session = Depends(get_db)):
    """Update retention days setting for specific exchange"""
    if request.days < 7 or request.days > 730:
        raise HTTPException(status_code=400, detail="Retention days must be between 7 and 730")

    days = set_retention_days(db, request.days, request.exchange)
    logger.info(f"Updated {request.exchange} retention to {days} days")

    return RetentionDaysResponse(days=days, exchange=request.exchange)


@router.get("/collection-days")
def get_collection_days(db: Session = Depends(get_db)):
    """Get total days of market flow data collection.
    Calculated from earliest record timestamp to now.
    """
    try:
        import time
        query = text("SELECT MIN(timestamp) FROM market_trades_aggregated")
        result = db.execute(query).scalar()

        if not result:
            return {"days": 0}

        now_ms = int(time.time() * 1000)
        days = (now_ms - result) / (24 * 60 * 60 * 1000)
        return {"days": round(days, 1)}
    except Exception as e:
        logger.error(f"Failed to get collection days: {e}")
        return {"days": 0}
