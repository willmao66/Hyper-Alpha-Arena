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

    testnet_configured = any(w.environment == "testnet" and w.is_active == "true" for w in wallets)
    mainnet_configured = any(w.environment == "mainnet" and w.is_active == "true" for w in wallets)

    # Get leverage settings from active wallet
    global_env = get_global_trading_mode(db)
    active_wallet = next((w for w in wallets if w.environment == global_env and w.is_active == "true"), None)

    return {
        "testnet_configured": testnet_configured,
        "mainnet_configured": mainnet_configured,
        "current_environment": global_env,
        "max_leverage": active_wallet.max_leverage if active_wallet else None,
        "default_leverage": active_wallet.default_leverage if active_wallet else None,
        "is_active": active_wallet.is_active == "true" if active_wallet else False
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
        result = client.place_order(
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            price=request.price,
            leverage=request.leverage,
            reduce_only=request.reduce_only
        )
        return result
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
