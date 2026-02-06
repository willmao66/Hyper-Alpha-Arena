"""
Binance Futures Trading Client

Handles trading operations on Binance USDS-M Futures via REST API.
Supports both testnet and mainnet environments.
"""

import hashlib
import hmac
import logging
import time
import requests
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode

from config.settings import BINANCE_BROKER_CONFIG

logger = logging.getLogger(__name__)


class BinanceTradingClient:
    """
    Binance Futures trading client with HMAC authentication.

    Supports:
    - Account balance and position queries
    - Leverage configuration
    - Market/Limit order placement
    - Stop-loss and take-profit orders
    """

    # API Endpoints
    MAINNET_BASE_URL = "https://fapi.binance.com"
    TESTNET_BASE_URL = "https://demo-fapi.binance.com"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        environment: str = "testnet"
    ):
        """
        Initialize Binance trading client.

        Args:
            api_key: Binance API key
            secret_key: Binance secret key
            environment: 'testnet' or 'mainnet'
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.environment = environment
        self.base_url = self.TESTNET_BASE_URL if environment == "testnet" else self.MAINNET_BASE_URL
        self.broker_id = BINANCE_BROKER_CONFIG.broker_id

        # Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        })

        # Cache for exchange info (precision data)
        self._exchange_info_cache: Optional[Dict] = None
        self._exchange_info_timestamp: float = 0
        self._cache_ttl = 3600  # 1 hour

        # Rate limit tracking (from response headers)
        self._last_used_weight: int = 0
        self._weight_cap: int = 2400  # Binance Futures default

        logger.info(f"[BINANCE] Client initialized for {environment}")

    def _get_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)

    def _sign(self, params: Dict[str, Any]) -> str:
        """
        Generate HMAC SHA256 signature for request parameters.

        Args:
            params: Request parameters dict

        Returns:
            Hex-encoded signature string
        """
        query_string = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Binance API.

        Args:
            method: HTTP method ('GET' or 'POST')
            endpoint: API endpoint path
            params: Request parameters
            signed: Whether to sign the request

        Returns:
            JSON response as dict

        Raises:
            Exception: On API error
        """
        url = f"{self.base_url}{endpoint}"
        params = params or {}

        if signed:
            params["timestamp"] = self._get_timestamp()
            params["recvWindow"] = 5000
            params["signature"] = self._sign(params)

        try:
            if method == "GET":
                response = self.session.get(url, params=params, timeout=10)
            else:
                response = self.session.post(url, data=params, timeout=10)

            # Log rate limit info and save to instance
            used_weight = response.headers.get("X-MBX-USED-WEIGHT-1M", "0")
            try:
                self._last_used_weight = int(used_weight)
            except (ValueError, TypeError):
                pass
            logger.debug(f"[BINANCE] {method} {endpoint} - Weight: {used_weight}/{self._weight_cap}")

            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                error_code = error_data.get("code", response.status_code)
                error_msg = error_data.get("msg", response.text)
                logger.error(f"[BINANCE] API Error: {error_code} - {error_msg}")
                raise Exception(f"Binance API Error {error_code}: {error_msg}")

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"[BINANCE] Request failed: {endpoint} - {e}")
            raise

    def _get_exchange_info(self) -> Dict[str, Any]:
        """
        Get exchange info with caching.

        Returns:
            Exchange info dict with symbols and filters
        """
        now = time.time()
        if self._exchange_info_cache and (now - self._exchange_info_timestamp) < self._cache_ttl:
            return self._exchange_info_cache

        self._exchange_info_cache = self._request("GET", "/fapi/v1/exchangeInfo")
        self._exchange_info_timestamp = now
        return self._exchange_info_cache

    def _get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get symbol-specific info including precision filters.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')

        Returns:
            Symbol info dict or None if not found
        """
        exchange_info = self._get_exchange_info()
        for sym_info in exchange_info.get("symbols", []):
            if sym_info["symbol"] == symbol:
                return sym_info
        return None

    def _get_precision(self, symbol: str) -> Dict[str, Any]:
        """
        Get price and quantity precision for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')

        Returns:
            Dict with tick_size, step_size, min_qty, min_notional
        """
        sym_info = self._get_symbol_info(symbol)
        if not sym_info:
            # Default conservative values
            return {
                "tick_size": Decimal("0.01"),
                "step_size": Decimal("0.001"),
                "min_qty": Decimal("0.001"),
                "min_notional": Decimal("5")
            }

        result = {
            "tick_size": Decimal("0.01"),
            "step_size": Decimal("0.001"),
            "min_qty": Decimal("0.001"),
            "min_notional": Decimal("5")
        }

        for f in sym_info.get("filters", []):
            if f["filterType"] == "PRICE_FILTER":
                result["tick_size"] = Decimal(f["tickSize"])
            elif f["filterType"] == "LOT_SIZE":
                result["step_size"] = Decimal(f["stepSize"])
                result["min_qty"] = Decimal(f["minQty"])
            elif f["filterType"] == "MIN_NOTIONAL":
                result["min_notional"] = Decimal(f["notional"])

        return result

    def _round_price(self, price: float, tick_size: Decimal) -> Decimal:
        """Round price to tick size."""
        price_dec = Decimal(str(price))
        return (price_dec / tick_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * tick_size

    def _round_quantity(self, quantity: float, step_size: Decimal) -> Decimal:
        """Round quantity to step size."""
        qty_dec = Decimal(str(quantity))
        return (qty_dec / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size

    def _to_binance_symbol(self, symbol: str) -> str:
        """
        Convert internal symbol to Binance format.

        Args:
            symbol: Internal symbol (e.g., 'BTC' or 'BTCUSDT')

        Returns:
            Binance symbol (e.g., 'BTCUSDT')
        """
        symbol = symbol.upper()
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
        return symbol

    # ==================== Account Methods ====================

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get current price ticker for a symbol.

        Args:
            symbol: Trading pair (e.g., 'BTC')

        Returns:
            Dict with price info:
            - symbol: Trading pair
            - price: Current price
        """
        binance_symbol = self._to_binance_symbol(symbol)
        result = self._request("GET", "/fapi/v1/ticker/price", {"symbol": binance_symbol})
        return {
            "symbol": symbol,
            "price": float(result.get("price", 0)),
            "binance_symbol": binance_symbol
        }

    def get_account(self) -> Dict[str, Any]:
        """
        Get full account information including balances and positions.

        Returns:
            Account info dict with assets and positions arrays
        """
        return self._request("GET", "/fapi/v3/account", signed=True)

    def get_balance(self) -> Dict[str, Any]:
        """
        Get account balance summary.

        Returns:
            Dict with balance fields mapped to unified format:
            - total_equity: Total wallet balance + unrealized PnL
            - available_balance: Available for trading
            - used_margin: Total initial margin
            - maintenance_margin: Total maintenance margin
            - unrealized_pnl: Total unrealized profit
        """
        account = self.get_account()

        return {
            "environment": self.environment,
            "total_equity": float(account.get("totalMarginBalance", 0)),
            "available_balance": float(account.get("availableBalance", 0)),
            "used_margin": float(account.get("totalInitialMargin", 0)),
            "maintenance_margin": float(account.get("totalMaintMargin", 0)),
            "unrealized_pnl": float(account.get("totalUnrealizedProfit", 0)),
            "total_wallet_balance": float(account.get("totalWalletBalance", 0)),
            "timestamp": self._get_timestamp(),
            "source": "live"
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get all open positions with unified field format (compatible with Hyperliquid).

        Returns:
            List of position dicts with unified format matching Hyperliquid:
            - coin: Symbol without suffix (e.g., "BTC")
            - szi: Signed size (positive=long, negative=short)
            - entry_px: Average entry price
            - position_value: Notional value
            - unrealized_pnl: Position PnL
            - leverage: Position leverage
            - liquidation_px: Estimated liquidation price
            - margin_used: Initial margin
            - leverage_type: "cross" or "isolated"
        """
        account = self.get_account()
        positions = []

        for pos in account.get("positions", []):
            position_amt = float(pos.get("positionAmt", 0))
            if position_amt == 0:
                continue  # Skip empty positions

            symbol = pos.get("symbol", "")
            # Remove USDT suffix for internal format
            if symbol.endswith("USDT"):
                symbol = symbol[:-4]

            entry_price = float(pos.get("entryPrice", 0))
            notional = float(pos.get("notional", 0))
            leverage = int(pos.get("leverage", 1))

            # Calculate position value if notional is 0
            if notional == 0 and entry_price > 0:
                notional = abs(position_amt) * entry_price

            positions.append({
                # Unified fields (Hyperliquid-compatible)
                "coin": symbol,
                "szi": position_amt,
                "entry_px": entry_price,
                "position_value": abs(notional),
                "unrealized_pnl": float(pos.get("unrealizedProfit", 0)),
                "leverage": leverage,
                "liquidation_px": float(pos.get("liquidationPrice", 0)),
                "margin_used": float(pos.get("initialMargin", 0)),
                "leverage_type": pos.get("marginType", "cross"),
                # Additional Binance-specific fields (for reference)
                "symbol": symbol,  # Alias for coin
                "mark_price": float(pos.get("markPrice", 0)),
                "maint_margin": float(pos.get("maintMargin", 0)),
                "position_side": pos.get("positionSide", "BOTH"),
            })

        return positions

    # ==================== Leverage Methods ====================

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        Set leverage for a symbol.

        Args:
            symbol: Trading pair (e.g., 'BTC' or 'BTCUSDT')
            leverage: Target leverage (1-125, depends on symbol)

        Returns:
            Dict with leverage and maxNotionalValue
        """
        binance_symbol = self._to_binance_symbol(symbol)
        params = {
            "symbol": binance_symbol,
            "leverage": leverage
        }

        result = self._request("POST", "/fapi/v1/leverage", params, signed=True)
        logger.info(f"[BINANCE] Set leverage for {binance_symbol}: {leverage}x")
        return result

    # ==================== Order Methods ====================

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        leverage: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Place an order on Binance Futures.

        Args:
            symbol: Trading pair (e.g., 'BTC')
            side: 'BUY' or 'SELL'
            quantity: Order quantity
            order_type: 'MARKET' or 'LIMIT'
            price: Limit price (required for LIMIT orders)
            time_in_force: 'GTC', 'IOC', 'FOK', 'GTX'
            reduce_only: Only reduce position
            leverage: Set leverage before order (optional)

        Returns:
            Order result dict with orderId, status, etc.
        """
        binance_symbol = self._to_binance_symbol(symbol)

        # Set leverage if specified
        if leverage:
            self.set_leverage(symbol, leverage)

        # Get precision for rounding
        precision = self._get_precision(binance_symbol)
        rounded_qty = self._round_quantity(quantity, precision["step_size"])

        # Validate minimum quantity
        if rounded_qty < precision["min_qty"]:
            raise ValueError(
                f"Quantity {rounded_qty} below minimum {precision['min_qty']} for {binance_symbol}"
            )

        # Build order params
        params = {
            "symbol": binance_symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(rounded_qty),
            # Add broker ID prefix for commission tracking
            "newClientOrderId": f"x-{self.broker_id}-{self._get_timestamp()}"
        }

        if reduce_only:
            params["reduceOnly"] = "true"

        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("Price required for LIMIT orders")
            rounded_price = self._round_price(price, precision["tick_size"])
            params["price"] = str(rounded_price)
            params["timeInForce"] = time_in_force

        result = self._request("POST", "/fapi/v1/order", params, signed=True)

        logger.info(
            f"[BINANCE] Order placed: {side} {rounded_qty} {binance_symbol} "
            f"@ {order_type} - Status: {result.get('status')}"
        )

        return {
            "order_id": result.get("orderId"),
            "client_order_id": result.get("clientOrderId"),
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": float(rounded_qty),
            "price": float(result.get("price", 0)),
            "avg_price": float(result.get("avgPrice", 0)),
            "executed_qty": float(result.get("executedQty", 0)),
            "status": result.get("status"),
            "time_in_force": result.get("timeInForce"),
            "reduce_only": result.get("reduceOnly", False),
            "environment": self.environment,
            "raw_response": result
        }

    def place_stop_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        order_type: str = "STOP_MARKET",
        reduce_only: bool = True,
        working_type: str = "MARK_PRICE"
    ) -> Dict[str, Any]:
        """
        Place a stop-loss or take-profit order.

        Args:
            symbol: Trading pair (e.g., 'BTC')
            side: 'BUY' or 'SELL'
            quantity: Order quantity
            stop_price: Trigger price
            order_type: 'STOP_MARKET' or 'TAKE_PROFIT_MARKET'
            reduce_only: Only reduce position (default True for SL/TP)
            working_type: 'MARK_PRICE' or 'CONTRACT_PRICE'

        Returns:
            Order result dict
        """
        binance_symbol = self._to_binance_symbol(symbol)
        precision = self._get_precision(binance_symbol)

        rounded_qty = self._round_quantity(quantity, precision["step_size"])
        rounded_stop = self._round_price(stop_price, precision["tick_size"])

        params = {
            "symbol": binance_symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(rounded_qty),
            "stopPrice": str(rounded_stop),
            "workingType": working_type,
            "newClientOrderId": f"x-{self.broker_id}-{self._get_timestamp()}"
        }

        if reduce_only:
            params["reduceOnly"] = "true"

        result = self._request("POST", "/fapi/v1/order", params, signed=True)

        logger.info(
            f"[BINANCE] Stop order placed: {order_type} {side} {rounded_qty} "
            f"{binance_symbol} @ {rounded_stop}"
        )

        return {
            "order_id": result.get("orderId"),
            "client_order_id": result.get("clientOrderId"),
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": float(rounded_qty),
            "stop_price": float(rounded_stop),
            "status": result.get("status"),
            "working_type": working_type,
            "reduce_only": reduce_only,
            "environment": self.environment,
            "raw_response": result
        }

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel an open order.

        Args:
            symbol: Trading pair
            order_id: Binance order ID
            client_order_id: Client order ID (alternative to order_id)

        Returns:
            Cancelled order info
        """
        binance_symbol = self._to_binance_symbol(symbol)
        params = {"symbol": binance_symbol}

        if order_id:
            params["orderId"] = order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("Either order_id or client_order_id required")

        result = self._request("DELETE", "/fapi/v1/order", params, signed=True)
        logger.info(f"[BINANCE] Order cancelled: {order_id or client_order_id}")
        return result

    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """Cancel all open orders for a symbol."""
        binance_symbol = self._to_binance_symbol(symbol)
        result = self._request(
            "DELETE", "/fapi/v1/allOpenOrders",
            {"symbol": binance_symbol}, signed=True
        )
        logger.info(f"[BINANCE] All orders cancelled for {binance_symbol}")
        return result

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all open orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            params["symbol"] = self._to_binance_symbol(symbol)

        return self._request("GET", "/fapi/v1/openOrders", params, signed=True)

    def get_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Query a specific order by ID."""
        binance_symbol = self._to_binance_symbol(symbol)
        params = {"symbol": binance_symbol}

        if order_id:
            params["orderId"] = order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("Either order_id or client_order_id required")

        return self._request("GET", "/fapi/v1/order", params, signed=True)

    def get_mark_price(self, symbol: str) -> float:
        """Get current mark price for a symbol."""
        binance_symbol = self._to_binance_symbol(symbol)
        result = self._request("GET", "/fapi/v1/premiumIndex", {"symbol": binance_symbol})
        return float(result.get("markPrice", 0))

    def close_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Close entire position for a symbol using market order.

        Returns:
            Order result if position exists, None if no position
        """
        positions = self.get_positions()
        position = next((p for p in positions if p["symbol"] == symbol.upper()), None)

        if not position or position["position_size"] == 0:
            logger.info(f"[BINANCE] No position to close for {symbol}")
            return None

        # Determine side to close
        size = abs(position["position_size"])
        side = "SELL" if position["position_size"] > 0 else "BUY"

        return self.place_order(
            symbol=symbol,
            side=side,
            quantity=size,
            order_type="MARKET",
            reduce_only=True
        )

    def get_account_state(self, db=None) -> Dict[str, Any]:
        """
        Get account state in unified format (compatible with HyperliquidTradingClient).

        Returns:
            Dict with: available_balance, total_equity, used_margin,
                      margin_usage_percent, maintenance_margin
        """
        balance = self.get_balance()
        return {
            "available_balance": balance.get("available_balance", 0.0),
            "total_equity": balance.get("total_equity", 0.0),
            "used_margin": balance.get("used_margin", 0.0),
            "margin_usage_percent": balance.get("margin_usage_percent", 0.0),
            "maintenance_margin": balance.get("maintenance_margin", 0.0),
        }

    def get_rate_limit(self) -> Dict[str, Any]:
        """
        Get current API rate limit info from last request's response header.

        Returns:
            Dict with: used_weight, weight_cap, remaining, usage_percent
        """
        remaining = self._weight_cap - self._last_used_weight
        usage_percent = (self._last_used_weight / self._weight_cap * 100) if self._weight_cap > 0 else 0
        return {
            "used_weight": self._last_used_weight,
            "weight_cap": self._weight_cap,
            "remaining": remaining,
            "usage_percent": round(usage_percent, 1),
        }

    def get_open_orders_formatted(self, db=None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get open orders in unified format (compatible with HyperliquidTradingClient).

        Returns list of dicts with fields:
            order_id, symbol, side, direction, order_type, size, price,
            order_value, reduce_only, trigger_condition, trigger_price, order_time
        """
        raw_orders = self.get_open_orders(symbol)
        orders = []

        for o in raw_orders:
            sym = self._to_internal_symbol(o.get("symbol", ""))
            side = o.get("side", "")  # BUY or SELL
            position_side = o.get("positionSide", "BOTH")
            reduce_only = o.get("reduceOnly", False)

            # Determine direction based on side and positionSide
            if position_side == "LONG":
                direction = "Close Long" if side == "SELL" else "Open Long"
            elif position_side == "SHORT":
                direction = "Close Short" if side == "BUY" else "Open Short"
            else:
                direction = "Close" if reduce_only else ("Long" if side == "BUY" else "Short")

            order_type = o.get("type", "LIMIT")
            price = float(o.get("price", 0))
            size = float(o.get("origQty", 0))
            stop_price = float(o.get("stopPrice", 0)) if o.get("stopPrice") else None

            # Build trigger condition string
            trigger_condition = None
            if stop_price:
                trigger_condition = f"Price {'above' if side == 'BUY' else 'below'} {stop_price}"

            # Parse order time
            order_time_ms = o.get("time", 0)
            order_time = datetime.fromtimestamp(order_time_ms / 1000).strftime("%Y-%m-%d %H:%M:%S") if order_time_ms else "N/A"

            orders.append({
                "order_id": o.get("orderId"),
                "symbol": sym,
                "side": side,
                "direction": direction,
                "order_type": order_type,
                "size": size,
                "original_size": size,
                "price": price,
                "order_value": price * size,
                "reduce_only": reduce_only,
                "is_trigger": stop_price is not None,
                "trigger_condition": trigger_condition,
                "trigger_price": stop_price,
                "order_time": order_time,
                "timestamp": order_time_ms,
            })

        return orders

    def get_recent_closed_trades(self, db=None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent closed trades in unified format (compatible with HyperliquidTradingClient).

        Uses Binance's /fapi/v1/userTrades endpoint to get trade history,
        then filters for trades that closed positions (have realizedPnl != 0).

        Returns list of dicts with fields:
            symbol, side, close_time, close_price, realized_pnl, direction
        """
        # Get all trades from last 7 days (Binance default)
        params = {"limit": 1000}  # Get more to filter
        raw_trades = self._request("GET", "/fapi/v1/userTrades", params, signed=True)

        # Filter for trades with realized PnL (position closures)
        closed_trades = []
        for t in raw_trades:
            realized_pnl = float(t.get("realizedPnl", 0))
            if realized_pnl != 0:
                sym = self._to_internal_symbol(t.get("symbol", ""))
                side = t.get("side", "")
                trade_time_ms = t.get("time", 0)
                close_time = datetime.fromtimestamp(trade_time_ms / 1000).strftime("%Y-%m-%d %H:%M:%S") if trade_time_ms else "N/A"

                # Direction: if SELL with positive PnL = closed long, etc.
                if realized_pnl > 0:
                    direction = "WIN"
                else:
                    direction = "LOSS"

                closed_trades.append({
                    "symbol": sym,
                    "side": side,
                    "close_time": close_time,
                    "close_timestamp": trade_time_ms,
                    "close_price": float(t.get("price", 0)),
                    "realized_pnl": realized_pnl,
                    "direction": direction,
                    "size": float(t.get("qty", 0)),
                })

        # Sort by time (newest first) and limit
        closed_trades.sort(key=lambda x: x.get("close_timestamp", 0), reverse=True)
        return closed_trades[:limit]