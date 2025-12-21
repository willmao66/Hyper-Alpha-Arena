"""
Market Regime Classification Service

Classifies market conditions into 7 regime types:
1. Stop Hunt - Price spike through key level then reversal
2. Absorption - Strong flow but price doesn't move
3. Breakout - Trend initiation with aligned signals
4. Continuation - Trend continuation
5. Exhaustion - Trend exhaustion at extremes
6. Trap - Bull/bear trap (strong flow but OI decreasing)
7. Noise - No clear signal

Indicator definitions (per planning document):
- cvd_ratio: CVD / Total Notional (not z-score)
- taker_ratio: ln(buy_notional / sell_notional) - log transformation for symmetry
- oi_delta: OI change percentage
- price_atr: Price Change / ATR
- rsi: RSI14
"""

import math
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from database.models import MarketRegimeConfig, CryptoKline
from services.technical_indicators import calculate_indicators
from services.market_flow_indicators import get_flow_indicators_for_prompt, TIMEFRAME_MS

logger = logging.getLogger(__name__)


# Regime type constants
REGIME_STOP_HUNT = "stop_hunt"
REGIME_ABSORPTION = "absorption"
REGIME_BREAKOUT = "breakout"
REGIME_CONTINUATION = "continuation"
REGIME_EXHAUSTION = "exhaustion"
REGIME_TRAP = "trap"
REGIME_NOISE = "noise"

# Direction constants
DIRECTION_BULLISH = "bullish"
DIRECTION_BEARISH = "bearish"
DIRECTION_NEUTRAL = "neutral"


def get_default_config(db: Session) -> Optional[MarketRegimeConfig]:
    """Get default regime config from database"""
    return db.query(MarketRegimeConfig).filter(
        MarketRegimeConfig.is_default == True
    ).first()


def calculate_direction(cvd_ratio: float, taker_log_ratio: float, price_atr: float) -> str:
    """
    Calculate direction by voting: cvd + taker + price.
    Note: taker_log_ratio is already log-transformed, so >0 means bullish, <0 means bearish.
    """
    votes = 0
    if cvd_ratio > 0:
        votes += 1
    elif cvd_ratio < 0:
        votes -= 1
    if taker_log_ratio > 0:  # log(buy/sell) > 0 means buy > sell
        votes += 1
    elif taker_log_ratio < 0:
        votes -= 1
    if price_atr > 0:
        votes += 1
    elif price_atr < 0:
        votes -= 1

    if votes >= 2:
        return DIRECTION_BULLISH
    elif votes <= -2:
        return DIRECTION_BEARISH
    return DIRECTION_NEUTRAL


def calculate_confidence(
    cvd_ratio: float, taker_log_ratio: float, oi_delta: float, price_atr: float
) -> float:
    """Calculate confidence score (0-1) based on signal strength"""
    # Normalize each indicator to 0-1 range
    # cvd_ratio: typical range -0.5 to 0.5, cap at 0.3
    # taker_log_ratio: typical range -1 to 1 (log scale)
    # oi_delta: typical range -5% to 5%
    # price_atr: typical range -2 to 2
    score = (
        0.3 * min(abs(cvd_ratio), 0.3) / 0.3 +
        0.2 * min(abs(taker_log_ratio), 1.0) / 1.0 +
        0.2 * min(abs(oi_delta), 5.0) / 5.0 +
        0.3 * min(abs(price_atr), 2.0) / 2.0
    )
    return max(0.0, min(1.0, score))


def classify_regime(
    cvd_ratio: float,
    taker_log_ratio: float,
    oi_delta: float,
    price_atr: float,
    rsi: float,
    price_range_atr: float,
    config: MarketRegimeConfig
) -> Tuple[str, str]:
    """
    Classify market regime based on indicators.
    Returns (regime_type, reason)
    Priority order: Stop Hunt > Absorption > Breakout > Continuation >
                    Exhaustion > Trap > Noise

    Indicator definitions:
    - cvd_ratio: CVD / Total Notional (range roughly -0.5 to 0.5)
    - taker_log_ratio: ln(buy/sell), symmetric around 0
    - oi_delta: OI change percentage
    - price_atr: (close - open) / ATR
    - rsi: RSI14
    - price_range_atr: (high - low) / ATR
    """
    # Convert config thresholds (designed for z-score) to ratio-based thresholds
    # Config uses z-score thresholds, we need to adapt for ratio-based values
    # cvd_z=1.5 roughly corresponds to cvd_ratio=0.15 (strong flow)
    cvd_threshold = config.breakout_cvd_z * 0.1  # Scale down for ratio
    oi_threshold = config.breakout_oi_z  # OI delta is already percentage

    # taker_log_ratio thresholds: log(1.8) ≈ 0.59, log(0.55) ≈ -0.60
    taker_high_log = math.log(config.breakout_taker_high) if config.breakout_taker_high > 0 else 0.59
    taker_low_log = math.log(config.breakout_taker_low) if config.breakout_taker_low > 0 else -0.60

    # 1. Stop Hunt: large range but close near open (spike and reversal)
    if (price_range_atr > config.stop_hunt_range_atr and
        abs(price_atr) < config.stop_hunt_close_atr):
        return REGIME_STOP_HUNT, "Price spiked but closed near open"

    # 2. Absorption: strong flow but price doesn't move
    taker_extreme = taker_log_ratio > taker_high_log or taker_log_ratio < taker_low_log
    if (abs(cvd_ratio) > cvd_threshold and taker_extreme and
        abs(price_atr) < config.absorption_price_atr):
        return REGIME_ABSORPTION, "Strong flow absorbed without price movement"

    # 3. Breakout: aligned signals with price movement
    cvd_bullish = cvd_ratio > cvd_threshold
    cvd_bearish = cvd_ratio < -cvd_threshold
    oi_increasing = oi_delta > oi_threshold

    if cvd_bullish and taker_log_ratio > taker_high_log and \
       oi_increasing and price_atr > config.breakout_price_atr:
        return REGIME_BREAKOUT, "Bullish breakout with aligned signals"
    if cvd_bearish and taker_log_ratio < taker_low_log and \
       oi_increasing and price_atr < -config.breakout_price_atr:
        return REGIME_BREAKOUT, "Bearish breakout with aligned signals"

    # 4. Continuation: moderate flow in trend direction
    cont_cvd_min = cvd_threshold * 0.5
    cont_cvd_max = cvd_threshold
    if (cont_cvd_min < abs(cvd_ratio) < cont_cvd_max and oi_delta >= 0 and
        abs(price_atr) > config.absorption_price_atr):
        return REGIME_CONTINUATION, "Trend continuation with moderate flow"

    # 5. Exhaustion: strong flow but OI decreasing at RSI extremes
    rsi_extreme = rsi > config.exhaustion_rsi_high or rsi < config.exhaustion_rsi_low
    if (abs(cvd_ratio) > cvd_threshold * 0.7 and taker_extreme and
        oi_delta < 0 and rsi_extreme):
        return REGIME_EXHAUSTION, "Trend exhaustion at RSI extreme"

    # 6. Trap: strong flow but OI decreasing (closing positions)
    trap_oi_threshold = config.trap_oi_z  # Already percentage
    if abs(cvd_ratio) > cvd_threshold * 0.7 and oi_delta < trap_oi_threshold:
        return REGIME_TRAP, "Strong flow but positions closing (trap)"

    # 7. Noise: no clear pattern
    return REGIME_NOISE, "No clear market regime detected"


def fetch_kline_data(
    db: Session, symbol: str, period: str = "5m", limit: int = 50,
    current_time_ms: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Fetch K-line data for technical indicator calculation.
    Returns list of dicts with timestamp, open, high, low, close, volume.

    Args:
        db: Database session
        symbol: Trading symbol
        period: Timeframe (1m, 5m, 15m, etc.)
        limit: Number of candles to fetch
        current_time_ms: Optional timestamp for historical queries (backtesting)
    """
    query = db.query(CryptoKline).filter(
        CryptoKline.symbol == symbol,
        CryptoKline.period == period
    )

    if current_time_ms:
        query = query.filter(CryptoKline.timestamp <= current_time_ms)

    klines = query.order_by(CryptoKline.timestamp.desc()).limit(limit).all()

    if not klines:
        return []

    # Reverse to chronological order and convert to dict format
    result = []
    for k in reversed(klines):
        result.append({
            "timestamp": k.timestamp,
            "open": float(k.open_price) if k.open_price else 0,
            "high": float(k.high_price) if k.high_price else 0,
            "low": float(k.low_price) if k.low_price else 0,
            "close": float(k.close_price) if k.close_price else 0,
            "volume": float(k.volume) if k.volume else 0
        })
    return result


def calculate_price_metrics(kline_data: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculate price-based metrics using technical indicators.
    Returns: price_atr, price_range_atr, rsi
    """
    if len(kline_data) < 15:  # Need at least 15 bars for ATR14 and RSI14
        return {"price_atr": 0.0, "price_range_atr": 0.0, "rsi": 50.0}

    # Calculate ATR and RSI using technical_indicators service
    indicators = calculate_indicators(kline_data, ["ATR14", "RSI14"])

    atr_values = indicators.get("ATR14", [])
    rsi_values = indicators.get("RSI14", [])

    # Get latest values
    atr = atr_values[-1] if atr_values else 0.0
    rsi = rsi_values[-1] if rsi_values else 50.0

    # Calculate price_atr: (close - open) / ATR (normalized price change)
    if atr > 0 and len(kline_data) >= 1:
        latest = kline_data[-1]
        price_change = latest["close"] - latest["open"]
        price_atr = price_change / atr
        # Calculate price_range_atr: (high - low) / ATR
        price_range = latest["high"] - latest["low"]
        price_range_atr = price_range / atr
    else:
        price_atr = 0.0
        price_range_atr = 0.0

    return {
        "price_atr": price_atr,
        "price_range_atr": price_range_atr,
        "rsi": rsi
    }


def get_market_regime(
    db: Session,
    symbol: str,
    timeframe: str = "5m",
    config_id: Optional[int] = None,
    timestamp_ms: Optional[int] = None
) -> Dict[str, Any]:
    """
    Main entry point: Get market regime classification for a symbol.

    IMPORTANT: This function reuses market_flow_indicators service for CVD, Taker, OI
    to ensure consistency with signal detection system.

    Args:
        db: Database session
        symbol: Trading pair symbol (e.g., "BTC")
        timeframe: Time frame (1m, 5m, 15m, 1h, etc.)
        config_id: Optional config ID, uses default if not specified
        timestamp_ms: Optional timestamp for historical queries (backtesting)

    Returns:
        Dict with regime, direction, confidence, reason, indicators, and debug info
    """
    # Get config
    if config_id:
        config = db.query(MarketRegimeConfig).filter(
            MarketRegimeConfig.id == config_id
        ).first()
    else:
        config = get_default_config(db)

    if not config:
        return {
            "regime": REGIME_NOISE,
            "direction": DIRECTION_NEUTRAL,
            "confidence": 0.0,
            "reason": "No regime config found",
            "indicators": {},
            "debug": {}
        }

    # Validate timeframe
    if timeframe not in TIMEFRAME_MS:
        return {
            "regime": REGIME_NOISE,
            "direction": DIRECTION_NEUTRAL,
            "confidence": 0.0,
            "reason": f"Unsupported timeframe: {timeframe}",
            "indicators": {},
            "debug": {}
        }

    # Get current time if not specified
    if timestamp_ms is None:
        timestamp_ms = int(datetime.utcnow().timestamp() * 1000)

    # Fetch flow indicators using market_flow_indicators service (REUSE!)
    flow_data = get_flow_indicators_for_prompt(
        db, symbol, timeframe, ["CVD", "TAKER", "OI_DELTA"], timestamp_ms
    )

    cvd_data = flow_data.get("CVD")
    taker_data = flow_data.get("TAKER")
    oi_delta_data = flow_data.get("OI_DELTA")

    # Check if we have enough data
    if not cvd_data or not taker_data:
        return {
            "regime": REGIME_NOISE,
            "direction": DIRECTION_NEUTRAL,
            "confidence": 0.0,
            "reason": "Insufficient market flow data",
            "indicators": {},
            "debug": {"cvd_data": cvd_data, "taker_data": taker_data}
        }

    # Extract indicator values
    # CVD ratio: current CVD / total notional (buy + sell)
    cvd_current = cvd_data.get("current", 0)
    taker_buy = taker_data.get("buy", 0)
    taker_sell = taker_data.get("sell", 0)
    total_notional = taker_buy + taker_sell

    cvd_ratio = cvd_current / total_notional if total_notional > 0 else 0.0

    # Taker log ratio: ln(buy/sell) for symmetry around 0
    if taker_buy > 0 and taker_sell > 0:
        taker_log_ratio = math.log(taker_buy / taker_sell)
    else:
        taker_log_ratio = 0.0

    # OI delta: percentage change
    oi_delta = oi_delta_data.get("current", 0) if oi_delta_data else 0.0

    # Fetch K-line data and calculate price metrics (ATR, RSI)
    kline_data = fetch_kline_data(db, symbol, timeframe, limit=50, current_time_ms=timestamp_ms)
    price_metrics = calculate_price_metrics(kline_data)
    price_atr = price_metrics["price_atr"]
    price_range_atr = price_metrics["price_range_atr"]
    rsi = price_metrics["rsi"]

    # Classify regime
    regime, reason = classify_regime(
        cvd_ratio, taker_log_ratio, oi_delta, price_atr, rsi, price_range_atr, config
    )

    # Calculate direction and confidence
    direction = calculate_direction(cvd_ratio, taker_log_ratio, price_atr)
    confidence = calculate_confidence(cvd_ratio, taker_log_ratio, oi_delta, price_atr)

    return {
        "regime": regime,
        "direction": direction,
        "confidence": round(confidence, 3),
        "reason": reason,
        "indicators": {
            "cvd_z": round(cvd_ratio, 4),  # Keep field name for API compatibility
            "oi_z": round(oi_delta, 3),    # Keep field name for API compatibility
            "taker_ratio": round(math.exp(taker_log_ratio), 3),  # Convert back for display
            "price_atr": round(price_atr, 3),
            "rsi": round(rsi, 1)
        },
        "debug": {
            "cvd_ratio": round(cvd_ratio, 4),
            "taker_log_ratio": round(taker_log_ratio, 4),
            "oi_delta_pct": round(oi_delta, 3),
            "taker_buy": round(taker_buy, 2),
            "taker_sell": round(taker_sell, 2),
            "total_notional": round(total_notional, 2),
            "timestamp_ms": timestamp_ms,
            "timeframe": timeframe
        }
    }
