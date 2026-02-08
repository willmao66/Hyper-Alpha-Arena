"""
Binance Futures Management API Routes

Provides endpoints for:
- Wallet setup and configuration (API key binding)
- Balance and position queries
- Manual order placement
- Connection testing
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from database.connection import get_db
from database.models import Account, BinanceWallet
from utils.encryption import encrypt_private_key, decrypt_private_key
from services.binance_trading_client import BinanceTradingClient
from services.hyperliquid_environment import get_global_trading_mode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/binance", tags=["binance"])

# Client cache for reuse
_client_cache: dict = {}


def _get_client(wallet: BinanceWallet) -> BinanceTradingClient:
    """Get or create trading client for a wallet"""
    cache_key = f"{wallet.account_id}_{wallet.environment}"
    if cache_key not in _client_cache:
        api_key = decrypt_private_key(wallet.api_key_encrypted)
        secret_key = decrypt_private_key(wallet.secret_key_encrypted)
        _client_cache[cache_key] = BinanceTradingClient(
            api_key=api_key,
            secret_key=secret_key,
            environment=wallet.environment
        )
    return _client_cache[cache_key]


def _clear_client_cache(account_id: int = None, environment: str = None):
    """Clear client cache"""
    if account_id and environment:
        cache_key = f"{account_id}_{environment}"
        _client_cache.pop(cache_key, None)
    else:
        _client_cache.clear()


# Request/Response Models
class BinanceSetupRequest(BaseModel):
    """Request model for Binance wallet setup"""
    environment: str = Field(..., pattern="^(testnet|mainnet)$")
    api_key: str = Field(..., min_length=10, alias="apiKey")
    secret_key: str = Field(..., min_length=10, alias="secretKey")
    max_leverage: int = Field(20, ge=1, le=125, alias="maxLeverage")
    default_leverage: int = Field(1, ge=1, le=125, alias="defaultLeverage")

    class Config:
        populate_by_name = True


class ManualOrderRequest(BaseModel):
    """Request model for manual order placement"""
    symbol: str = Field(..., description="Asset symbol (e.g., 'BTC')")
    side: str = Field(..., pattern="^(BUY|SELL)$")
    quantity: float = Field(..., gt=0)
    order_type: str = Field("MARKET", pattern="^(MARKET|LIMIT)$", alias="orderType")
    price: Optional[float] = Field(None, gt=0)
    leverage: int = Field(1, ge=1, le=125)
    reduce_only: bool = Field(False, alias="reduceOnly")
    take_profit_price: Optional[float] = Field(None, gt=0, alias="takeProfitPrice")
    stop_loss_price: Optional[float] = Field(None, gt=0, alias="stopLossPrice")

    class Config:
        populate_by_name = True


# API Endpoints

@router.post("/accounts/{account_id}/setup")
async def setup_wallet(
    account_id: int,
    request: BinanceSetupRequest,
    db: Session = Depends(get_db)
):
    """
    Setup Binance Futures wallet for an account.
    Encrypts and stores API credentials.
    """
    # Verify account exists
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Validate credentials by testing connection
    try:
        test_client = BinanceTradingClient(
            api_key=request.api_key,
            secret_key=request.secret_key,
            environment=request.environment
        )
        balance = test_client.get_balance()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid credentials: {e}")

    # Encrypt credentials
    api_key_encrypted = encrypt_private_key(request.api_key)
    secret_key_encrypted = encrypt_private_key(request.secret_key)

    # Check if wallet exists for this account+environment
    existing = db.query(BinanceWallet).filter(
        BinanceWallet.account_id == account_id,
        BinanceWallet.environment == request.environment
    ).first()

    if existing:
        # Update existing wallet
        existing.api_key_encrypted = api_key_encrypted
        existing.secret_key_encrypted = secret_key_encrypted
        existing.max_leverage = request.max_leverage
        existing.default_leverage = request.default_leverage
        existing.is_active = "true"
        _clear_client_cache(account_id, request.environment)
    else:
        # Create new wallet
        wallet = BinanceWallet(
            account_id=account_id,
            environment=request.environment,
            api_key_encrypted=api_key_encrypted,
            secret_key_encrypted=secret_key_encrypted,
            max_leverage=request.max_leverage,
            default_leverage=request.default_leverage,
            is_active="true"
        )
        db.add(wallet)

    db.commit()

    return {
        "success": True,
        "message": f"Binance {request.environment} wallet configured",
        "environment": request.environment,
        "balance": balance
    }


@router.get("/accounts/{account_id}/config")
async def get_config(account_id: int, db: Session = Depends(get_db)):
    """Get Binance wallet configuration for an account"""
    wallets = db.query(BinanceWallet).filter(
        BinanceWallet.account_id == account_id
    ).all()

    # Helper to mask API key
    def mask_api_key(wallet: BinanceWallet) -> str:
        try:
            api_key = decrypt_private_key(wallet.api_key_encrypted)
            if len(api_key) > 8:
                return f"{api_key[:4]}****{api_key[-4:]}"
            return "****"
        except:
            return "****"

    # Get wallet info for each environment
    testnet_wallet = next((w for w in wallets if w.environment == "testnet" and w.is_active == "true"), None)
    mainnet_wallet = next((w for w in wallets if w.environment == "mainnet" and w.is_active == "true"), None)

    testnet_info = None
    if testnet_wallet:
        testnet_info = {
            "configured": True,
            "api_key_masked": mask_api_key(testnet_wallet),
            "max_leverage": testnet_wallet.max_leverage,
            "default_leverage": testnet_wallet.default_leverage
        }

    mainnet_info = None
    if mainnet_wallet:
        mainnet_info = {
            "configured": True,
            "api_key_masked": mask_api_key(mainnet_wallet),
            "max_leverage": mainnet_wallet.max_leverage,
            "default_leverage": mainnet_wallet.default_leverage
        }

    global_env = get_global_trading_mode(db)

    return {
        "testnet_configured": testnet_wallet is not None,
        "mainnet_configured": mainnet_wallet is not None,
        "testnet": testnet_info,
        "mainnet": mainnet_info,
        "current_environment": global_env
    }


@router.get("/accounts/{account_id}/balance")
async def get_balance(
    account_id: int,
    environment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get Binance Futures account balance"""
    if not environment:
        environment = get_global_trading_mode(db)

    wallet = db.query(BinanceWallet).filter(
        BinanceWallet.account_id == account_id,
        BinanceWallet.environment == environment,
        BinanceWallet.is_active == "true"
    ).first()

    if not wallet:
        raise HTTPException(status_code=404, detail=f"No {environment} wallet configured")

    try:
        client = _get_client(wallet)
        return client.get_balance()
    except Exception as e:
        logger.error(f"Failed to get balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts/{account_id}/positions")
async def get_positions(
    account_id: int,
    environment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get Binance Futures open positions"""
    if not environment:
        environment = get_global_trading_mode(db)

    wallet = db.query(BinanceWallet).filter(
        BinanceWallet.account_id == account_id,
        BinanceWallet.environment == environment,
        BinanceWallet.is_active == "true"
    ).first()

    if not wallet:
        raise HTTPException(status_code=404, detail=f"No {environment} wallet configured")

    try:
        client = _get_client(wallet)
        return {"positions": client.get_positions()}
    except Exception as e:
        logger.error(f"Failed to get positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/{account_id}/order")
async def place_order(
    account_id: int,
    request: ManualOrderRequest,
    environment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Place a manual order on Binance Futures"""
    if not environment:
        environment = get_global_trading_mode(db)

    wallet = db.query(BinanceWallet).filter(
        BinanceWallet.account_id == account_id,
        BinanceWallet.environment == environment,
        BinanceWallet.is_active == "true"
    ).first()

    if not wallet:
        raise HTTPException(status_code=404, detail=f"No {environment} wallet configured")

    # Validate leverage
    if request.leverage > wallet.max_leverage:
        raise HTTPException(
            status_code=400,
            detail=f"Leverage {request.leverage} exceeds max {wallet.max_leverage}"
        )

    try:
        client = _get_client(wallet)

        # Use unified place_order_with_tpsl method (same as AI Trader and Program Trader)
        is_buy = request.side.upper() == "BUY"
        result = client.place_order_with_tpsl(
            db=db,
            symbol=request.symbol,
            is_buy=is_buy,
            size=request.quantity,
            price=request.price or 0,
            leverage=request.leverage,
            time_in_force="GTC",
            reduce_only=request.reduce_only,
            take_profit_price=request.take_profit_price,
            stop_loss_price=request.stop_loss_price,
            order_type=request.order_type,
            tp_execution="market",  # Manual orders default to market execution
            sl_execution="market",
        )

        # Map result to API response format
        return {
            "order_id": result.get("order_id"),
            "status": result.get("status"),
            "filled_qty": result.get("filled_qty"),
            "avg_price": result.get("avg_price"),
            "environment": result.get("environment"),
            "tp_order": {"algo_id": result.get("tp_order_id")} if result.get("tp_order_id") else None,
            "sl_order": {"algo_id": result.get("sl_order_id")} if result.get("sl_order_id") else None,
            "errors": result.get("errors", []),
        }
    except Exception as e:
        logger.error(f"Order failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/{account_id}/close-position")
async def close_position(
    account_id: int,
    symbol: str,
    environment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Close entire position for a symbol"""
    if not environment:
        environment = get_global_trading_mode(db)

    wallet = db.query(BinanceWallet).filter(
        BinanceWallet.account_id == account_id,
        BinanceWallet.environment == environment,
        BinanceWallet.is_active == "true"
    ).first()

    if not wallet:
        raise HTTPException(status_code=404, detail=f"No {environment} wallet configured")

    try:
        client = _get_client(wallet)
        result = client.close_position(symbol)
        if result is None:
            return {"message": f"No position to close for {symbol}"}
        return result
    except Exception as e:
        logger.error(f"Close position failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/accounts/{account_id}/wallet")
async def delete_wallet(
    account_id: int,
    environment: str,
    db: Session = Depends(get_db)
):
    """Disable Binance wallet for an account"""
    wallet = db.query(BinanceWallet).filter(
        BinanceWallet.account_id == account_id,
        BinanceWallet.environment == environment
    ).first()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    wallet.is_active = "false"
    _clear_client_cache(account_id, environment)
    db.commit()

    return {"success": True, "message": f"Binance {environment} wallet disabled"}


@router.get("/accounts/{account_id}/summary")
async def get_account_summary(
    account_id: int,
    environment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get Binance account summary for dashboard display."""
    if not environment:
        environment = get_global_trading_mode(db)

    wallet = db.query(BinanceWallet).filter(
        BinanceWallet.account_id == account_id,
        BinanceWallet.environment == environment,
        BinanceWallet.is_active == "true"
    ).first()

    if not wallet:
        raise HTTPException(status_code=404, detail=f"No {environment} wallet configured")

    try:
        client = _get_client(wallet)
        balance = client.get_balance()
        rate_limit = client.get_rate_limit()

        total_equity = balance.get("total_equity", 0.0)
        used_margin = balance.get("used_margin", 0.0)
        margin_usage = (used_margin / total_equity * 100) if total_equity > 0 else 0.0

        return {
            "account_id": account_id,
            "environment": environment,
            "exchange": "binance",
            "equity": total_equity,
            "available_balance": balance.get("available_balance", 0.0),
            "used_margin": used_margin,
            "margin_usage": round(margin_usage, 1),
            "unrealized_pnl": balance.get("unrealized_pnl", 0.0),
            "rate_limit": rate_limit,
            "last_updated": balance.get("timestamp"),
        }
    except Exception as e:
        logger.error(f"Failed to get account summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts/{account_id}/rate-limit")
async def get_rate_limit(
    account_id: int,
    environment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get Binance API rate limit (weight per minute) for an account."""
    if not environment:
        environment = get_global_trading_mode(db)

    wallet = db.query(BinanceWallet).filter(
        BinanceWallet.account_id == account_id,
        BinanceWallet.environment == environment,
        BinanceWallet.is_active == "true"
    ).first()

    if not wallet:
        raise HTTPException(status_code=404, detail=f"No {environment} wallet configured")

    try:
        client = _get_client(wallet)
        # Make a lightweight call to get fresh weight from response header
        client.get_balance()
        return {"success": True, "rate_limit": client.get_rate_limit()}
    except Exception as e:
        logger.error(f"Failed to get rate limit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price/{symbol}")
async def get_price(symbol: str):
    """
    Get current price for a symbol from Binance Futures.
    This is a public endpoint that doesn't require authentication.
    """
    import requests
    try:
        binance_symbol = symbol.upper()
        if not binance_symbol.endswith("USDT"):
            binance_symbol = f"{binance_symbol}USDT"

        # Use public API endpoint (no auth required)
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={binance_symbol}"
        response = requests.get(url, timeout=5)

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to get price")

        data = response.json()
        return {
            "symbol": symbol.upper(),
            "price": float(data.get("price", 0)),
            "binance_symbol": binance_symbol
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get Binance price: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wallets/all")
async def get_all_binance_wallets(db: Session = Depends(get_db)):
    """
    Get all Binance wallets across all accounts for manual trading page.
    Returns wallet info with masked API keys.
    """
    wallets = db.query(BinanceWallet).filter(
        BinanceWallet.is_active == "true"
    ).all()

    result = []
    for wallet in wallets:
        account = db.query(Account).filter(Account.id == wallet.account_id).first()
        if not account:
            continue

        # Mask API key for display
        try:
            api_key = decrypt_private_key(wallet.api_key_encrypted)
            if len(api_key) > 8:
                masked_key = f"{api_key[:4]}****{api_key[-4:]}"
            else:
                masked_key = "****"
        except:
            masked_key = "****"

        result.append({
            "wallet_id": wallet.id,
            "account_id": wallet.account_id,
            "account_name": account.name,
            "model": account.model,
            "api_key_masked": masked_key,
            "environment": wallet.environment,
            "is_active": wallet.is_active == "true",
            "max_leverage": wallet.max_leverage,
            "default_leverage": wallet.default_leverage,
        })

    return result


@router.get("/accounts/{account_id}/trading-stats")
async def get_binance_trading_stats(
    account_id: int,
    environment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get trading statistics for Binance account.

    Returns win rate, profit factor, and other trading metrics based on
    historical trades.

    Args:
        account_id: Account ID
        environment: Optional environment override ("testnet" or "mainnet")
                    If not specified, uses global trading mode
        db: Database session

    Returns:
        Trading statistics including win rate, total trades, PnL metrics
    """
    try:
        # Determine environment
        if environment is None:
            environment = get_global_trading_mode(db)

        # Get wallet
        wallet = db.query(BinanceWallet).filter(
            BinanceWallet.account_id == account_id,
            BinanceWallet.environment == environment,
            BinanceWallet.is_active == "true"
        ).first()

        if not wallet:
            raise HTTPException(
                status_code=400,
                detail=f"No active Binance wallet for account {account_id} in {environment}"
            )

        client = _get_client(wallet)
        stats = client.get_trading_stats()

        return {
            "success": True,
            "accountId": account_id,
            "environment": environment,
            "stats": stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Binance trading stats for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
