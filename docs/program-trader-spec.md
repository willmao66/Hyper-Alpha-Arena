# Program Trader Development Specification

> Last Updated: 2026-01-12
> Status: Planning Phase

## Table of Contents
1. [Product Overview](#1-product-overview)
2. [System Architecture](#2-system-architecture)
3. [Core Modules](#3-core-modules)
4. [Data Layer Design](#4-data-layer-design)
5. [Frontend Design](#5-frontend-design)
6. [Technical Decisions](#6-technical-decisions)
7. [Implementation Path](#7-implementation-path)
8. [Open Questions](#8-open-questions)

---

## 1. Product Overview

### 1.1 Positioning
**Program Trader** runs parallel to **AI Trader**, offering two trading modes:
- **AI Trader** = Intelligent decisions (LLM real-time inference, handles ambiguous situations)
- **Program Trader** = Rule execution (strategy scripts run automatically, deterministic & backtestable)

### 1.2 Unified Narrative
"AI helps you design strategies, validate strategies, and execute strategies" - a complete pipeline from R&D to live trading.

### 1.3 Value Proposition
| Aspect | AI Trader | Program Trader |
|--------|-----------|----------------|
| Decision | LLM real-time inference | Script rule execution |
| Transparency | Black box | White box (auditable code) |
| Backtestable | Difficult (LLM output varies) | Fully backtestable |
| Latency | Higher (wait for LLM) | Lower (local execution) |
| Cost | Token consumption per decision | One-time script generation |

---

## 2. System Architecture

### 2.1 Integration with Existing System
```
                    ┌─────────────────┐
                    │   Signal Pool   │  ← Unified Trigger
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                              ▼
     ┌─────────────────┐           ┌─────────────────┐
     │   AI Trader     │           │ Program Trader  │
     │  (LLM Decision) │           │ (Script Exec)   │
     └────────┬────────┘           └────────┬────────┘
              │                              │
              └──────────────┬───────────────┘
                             ▼
                    ┌─────────────────┐
                    │   Dashboard     │  ← Unified Display
                    │  [AI] / [Prog]  │     with source tags
                    └─────────────────┘
```

### 2.2 Component Reuse
**Reused Components:**
- Signal Pool (trigger mechanism)
- Data Pipeline (klines, indicators, flow metrics)
- Order Execution (Hyperliquid API)
- Dashboard (asset curves, trade records)

**New Components:**
- Strategy Generator (AI generates code)
- Backtest Engine (historical validation)
- Programs Management (save, edit, version)
- Sandbox Executor (safe code execution)
- Code Validator (syntax & security check)

---

## 3. Core Modules

### 3.1 Strategy Generator
- User describes requirements in natural language
- AI generates Python strategy code
- Must conform to Strategy template format
- Includes syntax validation before saving

### 3.2 Backtest Engine
- Self-built lightweight engine (not Freqtrade)
- Uses Hyperliquid historical data
- Output: equity curve, win rate, max drawdown, Sharpe ratio

### 3.3 Programs Management
- Save and organize strategy scripts
- Code editor for viewing/editing
- Version history (optional)

### 3.4 Deployment Binding
- Bind Program to Signal Pool
- When signal triggers, execute script instead of AI

### 3.5 Sandbox Executor
- Restricted Python environment
- Only predefined APIs allowed
- Time limit (e.g., 5s timeout)
- Memory limit

### 3.6 Code Validator
| Check Level | Description | Implementation |
|-------------|-------------|----------------|
| Syntax | Python syntax correct | `ast.parse()` |
| Template | Has Strategy class, should_trade method | AST structure check |
| Security | No dangerous operations | AST scan for forbidden imports |
| Test Run | Execute with mock data | Sandbox call should_trade |

### 3.7 Execution Monitor
- Program status (running/paused/error)
- Trigger history
- Decision logs (structured data, not natural language)
- Performance statistics

---

## 4. Data Layer Design

### 4.1 MarketData Structure (Complete)

```python
class MarketData:
    """
    Input data structure passed to strategy scripts.
    All fields mirror existing AI Trader data sources.
    """

    # === Account Info ===
    available_balance: float      # Available balance (USD)
    total_equity: float           # Total equity (USD)
    used_margin: float            # Used margin (USD)
    margin_usage_percent: float   # Margin usage (%)
    maintenance_margin: float     # Maintenance margin (USD)

    # === Positions ===
    positions: dict[str, Position]  # symbol -> Position
    # Position: {side, size, entry_price, unrealized_pnl, leverage, liquidation_price}

    # === Recent Trades ===
    recent_trades: list[Trade]    # Recent trade history
    # Trade: {symbol, side, size, price, timestamp, pnl}

    # === Trigger Info ===
    trigger_symbol: str           # Symbol that triggered
    trigger_type: str             # "signal" | "scheduled"

    # === Methods (Multi-symbol, Multi-timeframe) ===

    def get_market_data(self, symbol: str) -> dict:
        """
        Get complete market data (price, volume, OI, funding rate).
        Returns: {symbol, price, oracle_price, change24h, volume24h,
                  percentage24h, open_interest, funding_rate}
        """

    def get_price_change(self, symbol: str, period: str) -> dict:
        """
        Get price change for symbol over period.
        Returns: {change_percent: float, change_usd: float}
        Period: "5m", "1h", "4h", "1d"
        """

    def get_klines(self, symbol: str, period: str, count: int = 50) -> list[Kline]:
        """
        Get K-line data.
        Kline: {open, high, low, close, volume, timestamp}
        Default count: 50 for 5m, 24 for 1h
        """

    def get_indicator(self, symbol: str, indicator: str, period: str) -> dict:
        """
        Get technical indicator values.
        Supported indicators:
        - RSI14, RSI7: {value: float}
        - MACD: {dif: float, dea: float, histogram: float}
        - EMA: {ema7: float, ema25: float, ema99: float}
        - ATR14: {value: float}
        - BOLL: {upper: float, middle: float, lower: float}
        - STOCH: {k: float, d: float}
        - VWAP: {value: float}
        - OBV: {value: float}
        """

    def get_flow(self, symbol: str, metric: str, period: str) -> dict:
        """
        Get market flow metrics.
        Supported metrics:
        - CVD: {value: float, delta: float}
        - TAKER: {buy_volume: float, sell_volume: float, ratio: float}
        - OI: {value: float, delta: float}
        - OI_DELTA: {value: float}
        - FUNDING: {rate: float, predicted: float}
        - DEPTH: {bid_depth: float, ask_depth: float, imbalance: float}
        """

    def get_regime(self, symbol: str, period: str) -> RegimeInfo:
        """
        Get market regime classification.
        Returns: {
            regime: str,  # breakout/absorption/stop_hunt/exhaustion/trap/continuation/noise
            conf: float   # confidence 0.0-1.0
        }
        """
```

### 4.2 Decision Output Structure

```python
class Decision:
    """
    Output structure returned by strategy scripts.
    """
    action: str          # "buy" | "sell" | "close" | "hold"
    symbol: str          # Trading pair (e.g., "BTC")
    size_usd: float      # Position size in USD
    leverage: int        # Leverage (1-20, recommend 10-16)
    tp_price: float      # Take profit price (required for buy/sell)
    sl_price: float      # Stop loss price (required for buy/sell)
    reason: str          # Decision reasoning (for logging)
```

### 4.3 Strategy Template Format

```python
class Strategy:
    """
    Base template for all trading programs.
    AI generates code that fills in these methods.
    """

    def init(self, params: dict) -> None:
        """
        Initialize strategy parameters.
        Called once when strategy is loaded.

        Example params:
        - rsi_threshold: 30
        - atr_multiplier: 1.5
        - max_position_pct: 0.5
        """
        self.params = params

    def should_trade(self, data: MarketData) -> Decision:
        """
        Main decision logic.
        Called each time signal triggers.

        Args:
            data: MarketData object with all market info

        Returns:
            Decision object with action and parameters
        """
        # Strategy logic here
        pass
```

### 4.4 Data Source Mapping

| MarketData Field | Existing Data Source | Notes |
|------------------|---------------------|-------|
| available_balance | Hyperliquid API | Already used by AI Trader |
| total_equity | Hyperliquid API | Already used by AI Trader |
| used_margin | Hyperliquid API | Already used by AI Trader |
| positions | Hyperliquid API | Already used by AI Trader |
| prices | Hyperliquid API | Already used by AI Trader |
| get_klines() | Kline cache service | Already implemented |
| get_indicator() | Factors module | Already implemented |
| get_flow() | Flow metrics service | Already implemented |
| get_regime() | Regime classifier | Already implemented |
| get_price_change() | **NEW** | Need to implement |
| recent_trades | **NEW** | Need to implement |

### 4.5 Available API Functions (Sandbox Whitelist)

```python
# Data Access (read-only)
data.available_balance
data.total_equity
data.positions
data.get_market_data(symbol)
data.get_klines(symbol, period, count)
data.get_indicator(symbol, indicator, period)
data.get_flow(symbol, metric, period)
data.get_regime(symbol, period)
data.get_price_change(symbol, period)

# Math & Utilities (safe built-ins)
abs(), min(), max(), sum(), len(), round()
math.sqrt(), math.log(), math.exp()

# Logging
log(message)  # For debugging, recorded in execution logs

# FORBIDDEN (will fail security check)
import os, sys, subprocess, eval, exec, open, __import__
```

---

## 5. Frontend Design

### 5.1 Entry Point
- Location: Under "Prompts" in navigation
- Icon: Python logo (SVG provided by user)
- Menu item: "Program Trader"

### 5.2 Dashboard Integration
All trade records unified in Dashboard with source tags:
- `[AI Trader]` Buy BTC @ 42000
- `[Program: RSI_Reversal]` Sell ETH @ 2200

Asset curve remains unified (same account), with filter option to view:
- All trades
- AI Trader only
- Program Trader only

### 5.3 UI Components (Planned)
1. **Program List** - View all saved programs
2. **Code Editor** - View/edit strategy code (Monaco editor)
3. **Backtest Panel** - Run backtest, view results
4. **Deploy Panel** - Bind to signal pool
5. **Monitor Panel** - View execution status and logs

---

## 6. Technical Decisions

### 6.1 Framework Choice
**Decision: Self-built, NOT Freqtrade**

Reasons:
- Freqtrade is too heavy (full trading bot system)
- No native Hyperliquid support
- Architecture conflicts with existing system
- We only need: strategy template + backtest + sandbox

### 6.2 Backtest Engine
- Self-built lightweight engine
- Core logic: iterate klines → call strategy → simulate trades → calculate metrics
- Data source: Hyperliquid historical data via existing pipeline

### 6.3 Sandbox Execution
- Restricted Python environment
- AST-based security scanning
- Whitelist of allowed functions
- Execution timeout (5 seconds)
- Memory limit

### 6.4 Code Validation Pipeline
```
Code Input → Syntax Check → Template Check → Security Check → Test Run → Save
                ↓               ↓                ↓              ↓
            ast.parse()    Check class      Scan forbidden   Mock data
                           structure        imports/calls    execution
```

---

## 7. Implementation Path

### 7.1 Recommended Order
1. **Strategy Template Design** - Foundation for all modules
2. **MarketData Implementation** - Data layer wrapper
3. **Backtest Engine** - Validate strategies work
4. **Code Validator** - Syntax + security checks
5. **Strategy Generator** - AI generates code
6. **Programs Management** - Save/edit/list
7. **Sandbox Executor** - Safe runtime
8. **Deployment Binding** - Connect to Signal Pool
9. **Execution Monitor** - Status and logs
10. **Dashboard Integration** - Unified display

### 7.2 Module Dependencies
```
Strategy Template ──┬──→ Backtest Engine
                    ├──→ Code Validator
                    └──→ Strategy Generator

MarketData ─────────┬──→ Backtest Engine
                    └──→ Sandbox Executor

Code Validator ─────────→ Strategy Generator
                         Programs Management

Sandbox Executor ───────→ Deployment Binding
                         Execution Monitor
```

---

## 8. Open Questions

### 8.1 To Be Decided
- [ ] Backtest date range: how far back? (30 days? 90 days?)
- [ ] Max programs per user?
- [ ] Program sharing between users?
- [ ] Versioning strategy for programs?

### 8.2 To Be Implemented
- [ ] `get_price_change()` method - new data source
- [ ] `recent_trades` field - new data source
- [ ] Monaco editor integration for code editing
- [ ] Backtest result visualization (equity curve chart)

---

## Appendix A: Example Strategy

```python
class RSIReversalStrategy(Strategy):
    """
    Simple RSI reversal strategy.
    Buy when RSI < 30, Sell when RSI > 70.
    """

    def init(self, params):
        self.rsi_buy = params.get('rsi_buy', 30)
        self.rsi_sell = params.get('rsi_sell', 70)
        self.position_pct = params.get('position_pct', 0.5)

    def should_trade(self, data: MarketData) -> Decision:
        symbol = data.trigger_symbol
        rsi = data.get_indicator(symbol, 'RSI14', '5m')['value']
        market_data = data.get_market_data(symbol)
        price = market_data['price']
        atr = data.get_indicator(symbol, 'ATR14', '1h')['value']

        # Check existing position
        position = data.positions.get(symbol)

        if position is None:
            # No position - look for entry
            if rsi < self.rsi_buy:
                return Decision(
                    action='buy',
                    symbol=symbol,
                    size_usd=data.available_balance * self.position_pct,
                    leverage=10,
                    tp_price=price + atr,
                    sl_price=price - atr * 1.2,
                    reason=f'RSI oversold at {rsi:.1f}'
                )
            elif rsi > self.rsi_sell:
                return Decision(
                    action='sell',
                    symbol=symbol,
                    size_usd=data.available_balance * self.position_pct,
                    leverage=10,
                    tp_price=price - atr,
                    sl_price=price + atr * 1.2,
                    reason=f'RSI overbought at {rsi:.1f}'
                )

        return Decision(action='hold', symbol=symbol, reason='No signal')
```

---

*Document created: 2026-01-12*
*This document is for internal development reference only, not included in Git.*
