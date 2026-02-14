# Program Backtest Engine Design Specification

> Created: 2026-01-21
> Status: Design Complete, Ready for Development

## 1. Overview

Programs backtest engine for event-driven backtesting with signal/scheduled triggers.

### Core Principle
- Event-driven execution (not K-line iteration)
- State dependency: each decision depends on previous execution results
- Shared backtest engine for future Prompts backtest integration

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ProgramBacktestEngine                        │
│  - Event scheduling and coordination                            │
│  - Trigger event merging (signal + scheduled)                   │
└─────────────────────────────────────────────────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Historical   │    │ Execution    │    │ Virtual      │
│ DataProvider │    │ Simulator    │    │ Account      │
│ (new)        │    │ (new)        │    │ (new)        │
└──────────────┘    └──────────────┘    └──────────────┘
        │                    │
        ▼                    ▼
┌──────────────┐    ┌──────────────┐
│ Sandbox      │    │ Signal       │
│ Executor     │    │ Backtest     │
│ (reuse)      │    │ Service      │
└──────────────┘    │ (reuse)      │
                    └──────────────┘
```

## 3. Component Analysis

### 3.1 Reused Components (No Modification)

| Component | File | Purpose |
|-----------|------|---------|
| SandboxExecutor | program_trader/executor.py | Execute strategy code safely |
| SignalBacktestService | services/signal_backtest_service.py | Detect signal triggers |
| calculate_indicators() | services/technical_indicators.py | Calculate technical indicators |
| Data Models | program_trader/models.py | Decision, Position, Trade, Order, RegimeInfo |

### 3.2 Existing Components (Keep Unchanged)

| Component | File | Reason |
|-----------|------|--------|
| DataProvider | program_trader/data_provider.py | Real-time data, different from historical |
| BacktestEngine | program_trader/backtest.py | K-line iteration, different from event-driven |

### 3.3 New Components

| Component | Purpose |
|-----------|---------|
| HistoricalDataProvider | Historical data retrieval, interface compatible with DataProvider |
| ProgramBacktestEngine | Event-driven backtest orchestration |
| VirtualAccount | Virtual account state management |
| ExecutionSimulator | Order execution simulation (slippage, fees, TP/SL) |
| TriggerEvent | Unified trigger event format |
| BacktestConfig | Backtest configuration |

## 4. Data Structures

### 4.1 BacktestConfig
```python
@dataclass
class BacktestConfig:
    code: str                      # Strategy code
    signal_pool_ids: List[int]     # Signal pool IDs
    symbols: List[str]             # Trading symbols ["BTC", "ETH"]
    start_time: datetime           # Backtest start
    end_time: datetime             # Backtest end
    scheduled_interval: Optional[str] = None  # "1h", "4h", "1d"
    initial_balance: float = 10000.0
    slippage_percent: float = 0.05
    fee_rate: float = 0.035        # Hyperliquid taker fee
    execution_price: str = "close" # "close", "open", "vwap"
```

### 4.2 TriggerEvent
```python
@dataclass
class TriggerEvent:
    timestamp: int                 # Millisecond timestamp
    trigger_type: str              # "signal" or "scheduled"
    symbol: str
    pool_id: Optional[int] = None
    pool_name: Optional[str] = None
    pool_logic: Optional[str] = None
    triggered_signals: List[Dict] = None
    market_regime: Optional[Dict] = None
```

### 4.3 VirtualAccount
```python
@dataclass
class VirtualAccount:
    balance: float
    equity: float
    positions: Dict[str, Position]
    open_orders: List[Order]       # TP/SL orders

    def update_equity(self, prices: Dict[str, float]): ...
```

### 4.4 BacktestResult
```python
@dataclass
class BacktestResult:
    success: bool
    error: Optional[str] = None

    # Core metrics
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    sharpe_ratio: float = 0.0

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0

    # Trigger statistics
    signal_triggers: int = 0
    scheduled_triggers: int = 0

    # Detailed data
    equity_curve: List[Dict] = None
    trades: List[BacktestTradeRecord] = None
    trigger_log: List[TriggerEvent] = None
```

## 5. Core Flow

```
1. Generate Trigger Events
   ├── SignalBacktestService.backtest_pool() for each pool
   ├── Generate scheduled triggers based on interval
   └── Merge and sort by timestamp

2. Initialize
   ├── VirtualAccount with initial_balance
   └── HistoricalDataProvider with time range

3. Event Loop (for each trigger)
   ├── Set data_provider.current_time = trigger.timestamp
   ├── ExecutionSimulator.check_tp_sl() - check pending orders
   ├── Build MarketData with virtual account state
   ├── SandboxExecutor.execute(code, market_data)
   ├── ExecutionSimulator.execute_decision() - simulate order
   ├── Update VirtualAccount state
   └── Record equity curve point

4. Calculate Statistics
   ├── PnL, max drawdown, Sharpe ratio
   ├── Win rate, profit factor
   └── Generate BacktestResult
```

## 6. ExecutionSimulator Details

### 6.1 Responsibilities
- Calculate actual execution price (with slippage)
- Calculate fees (open + close)
- Check TP/SL triggers at each time point
- Check liquidation price (optional, for leverage)
- Update VirtualAccount state

### 6.2 Slippage Model
```python
def calculate_execution_price(self, price: float, side: str, slippage_pct: float):
    if side == "buy":
        return price * (1 + slippage_pct / 100)
    else:
        return price * (1 - slippage_pct / 100)
```

### 6.3 Fee Calculation
```python
def calculate_fee(self, notional: float, fee_rate: float):
    return notional * fee_rate / 100
```

### 6.4 TP/SL Check
```python
def check_tp_sl(self, account: VirtualAccount, prices: Dict[str, float]):
    for symbol, pos in account.positions.items():
        price = prices.get(symbol)
        # Check take profit
        if pos.take_profit and self._tp_triggered(pos, price):
            self._close_position(account, symbol, price, "TP")
        # Check stop loss
        elif pos.stop_loss and self._sl_triggered(pos, price):
            self._close_position(account, symbol, price, "SL")
```

## 7. HistoricalDataProvider Details

### 7.1 Interface (Compatible with DataProvider)
```python
class HistoricalDataProvider:
    def set_current_time(self, timestamp_ms: int): ...
    def get_klines(self, symbol: str, period: str, count: int = 50): ...
    def get_indicator(self, symbol: str, indicator: str, period: str): ...
    def get_flow(self, symbol: str, metric: str, period: str): ...
    def get_regime(self, symbol: str, period: str): ...
    def get_current_prices(self, symbols: List[str]): ...
    def get_market_data(self, symbol: str): ...
```

### 7.2 Data Sources
- K-lines: `crypto_klines` table
- Flow data: `market_trades_aggregated`, `market_asset_metrics`, `market_orderbook_snapshots`
- Regime: Calculate from historical flow data using `market_regime_service`

### 7.3 Time Filtering
All queries filter by `timestamp <= current_time_ms` to simulate real-time data availability.

## 8. Development Plan

### Phase 1: Core Infrastructure
1. BacktestConfig, TriggerEvent, BacktestResult data classes
2. VirtualAccount class with position/order management
3. ExecutionSimulator with slippage, fees, TP/SL

### Phase 2: Data Layer
4. HistoricalDataProvider with all data methods
5. Integration with existing calculate_indicators()

### Phase 3: Engine
6. ProgramBacktestEngine main class
7. Trigger event generation and merging
8. Event loop implementation

### Phase 4: API & Frontend
9. Backend API endpoint for backtest
10. Frontend UI for configuration and results display

## 9. File Structure

```
backend/program_trader/
├── __init__.py
├── models.py              # Existing - add new dataclasses
├── executor.py            # Existing - no change
├── data_provider.py       # Existing - no change
├── backtest.py            # Existing - no change
├── validator.py           # Existing - no change
├── historical_data_provider.py  # NEW
├── virtual_account.py           # NEW
├── execution_simulator.py       # NEW
├── program_backtest_engine.py   # NEW
└── backtest_models.py           # NEW - BacktestConfig, TriggerEvent, etc.
```

## 10. Notes

- Keep existing components unchanged to avoid regression
- HistoricalDataProvider interface must match DataProvider for code compatibility
- ExecutionSimulator is REQUIRED, not optional (TP/SL, fees are essential)
- Future Prompts backtest can reuse: ExecutionSimulator, VirtualAccount, BacktestResult
