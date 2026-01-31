#!/usr/bin/env python3
"""
Test script for closing position via place_order_with_tpsl().
"""

import sys
import requests

sys.path.insert(0, "/app/backend")

from database.connection import SessionLocal
from database.models import HyperliquidWallet
from services.hyperliquid_trading_client import HyperliquidTradingClient
from utils.encryption import decrypt_private_key

# ============== Configuration ==============
ACCOUNT_ID = 1
ENVIRONMENT = "testnet"
SYMBOL = "ETH"
SLIPPAGE_PERCENT = 0.5  # Allow 0.5% slippage below current price
# ===========================================


def get_testnet_price(symbol: str) -> float:
    """Get real-time price from Testnet API."""
    url = "https://api.hyperliquid-testnet.xyz/info"
    resp = requests.post(url, json={"type": "allMids"}, timeout=10)
    resp.raise_for_status()
    return float(resp.json().get(symbol, 0))


def main():
    print("=" * 60)
    print("Close Position Test - Testnet")
    print("=" * 60)

    db = SessionLocal()

    try:
        # Step 1: Get wallet and initialize client
        print(f"\n[1] Initializing client...")
        wallet = db.query(HyperliquidWallet).filter(
            HyperliquidWallet.account_id == ACCOUNT_ID,
            HyperliquidWallet.environment == ENVIRONMENT,
            HyperliquidWallet.is_active == "true"
        ).first()

        private_key = decrypt_private_key(wallet.private_key_encrypted)
        client = HyperliquidTradingClient(
            account_id=ACCOUNT_ID,
            private_key=private_key,
            environment=ENVIRONMENT,
            wallet_address=wallet.wallet_address
        )
        print(f"    Wallet: {wallet.wallet_address}")

        # Step 2: Get current position
        print(f"\n[2] Getting {SYMBOL} position...")
        positions = client.get_positions(db)

        eth_position = None
        for pos in positions:
            if pos.get("coin") == SYMBOL:
                eth_position = pos
                break

        if not eth_position:
            print(f"    No {SYMBOL} position found!")
            return

        position_size = eth_position.get("szi", 0)
        position_side = eth_position.get("side", "").lower()
        entry_price = eth_position.get("entry_px", 0)
        unrealized_pnl = eth_position.get("unrealized_pnl", 0)

        print(f"    Side: {position_side.upper()}")
        print(f"    Size: {position_size} {SYMBOL}")
        print(f"    Entry price: ${entry_price:,.2f}")
        print(f"    Unrealized PnL: ${unrealized_pnl:,.2f}")

        # Step 3: Get current price
        print(f"\n[3] Getting current price...")
        current_price = get_testnet_price(SYMBOL)
        print(f"    Current price: ${current_price:,.2f}")

        # Step 4: Calculate close parameters
        print(f"\n[4] Calculating close parameters...")

        # For closing LONG: sell at min_price (current - slippage)
        # For closing SHORT: buy at max_price (current + slippage)
        is_long = position_side == "long"
        is_buy = not is_long  # Close long = sell, Close short = buy

        if is_long:
            close_price = round(current_price * (1 - SLIPPAGE_PERCENT / 100), 1)
            print(f"    Closing LONG -> SELL")
        else:
            close_price = round(current_price * (1 + SLIPPAGE_PERCENT / 100), 1)
            print(f"    Closing SHORT -> BUY")

        print(f"    Close price: ${close_price:,.1f}")
        print(f"    Size to close: {position_size}")
        print(f"    reduce_only: True")

        # Step 5: Execute close
        print(f"\n[5] Executing close order...")
        result = client.place_order_with_tpsl(
            db=db,
            symbol=SYMBOL,
            is_buy=is_buy,
            size=abs(position_size),
            price=close_price,
            leverage=10,
            time_in_force="Ioc",
            reduce_only=True,
            take_profit_price=None,
            stop_loss_price=None,
        )

        # Step 6: Print result
        print(f"\n[6] Close Result:")
        print("-" * 40)

        status = result.get("status", "")
        if status in ("filled", "partial", "resting"):
            print(f"    Status: SUCCESS ({status})")
            print(f"    Order ID: {result.get('order_id')}")
            print(f"    Filled: {result.get('filled_amount')} {SYMBOL}")
            print(f"    Avg price: ${result.get('average_price', 0):,.2f}")

            # Calculate realized PnL
            if result.get('average_price'):
                if is_long:
                    pnl = (result['average_price'] - entry_price) * position_size
                else:
                    pnl = (entry_price - result['average_price']) * position_size
                print(f"    Realized PnL: ${pnl:,.2f}")
        else:
            print(f"    Status: FAILED ({status})")
            print(f"    Error: {result.get('error')}")

        print("-" * 40)
        print(f"\nFull result: {result}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
