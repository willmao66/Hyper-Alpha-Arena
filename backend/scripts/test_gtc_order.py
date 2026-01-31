#!/usr/bin/env python3
"""
Test GTC (Good Till Cancel) limit order.
Places a buy order below market price to test resting order.
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
TARGET_PORTION = 0.05  # 5% of balance (small test)
LEVERAGE = 10
PRICE_OFFSET_PERCENT = -1.0  # 1% BELOW market price (won't fill immediately)
TIME_IN_FORCE = "Gtc"  # Good Till Cancel
# ===========================================


def get_testnet_price(symbol: str) -> float:
    url = "https://api.hyperliquid-testnet.xyz/info"
    resp = requests.post(url, json={"type": "allMids"}, timeout=10)
    resp.raise_for_status()
    return float(resp.json().get(symbol, 0))


def main():
    print("=" * 60)
    print("GTC Limit Order Test - Testnet")
    print("=" * 60)

    db = SessionLocal()

    try:
        # Step 1: Initialize client
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

        # Step 2: Get account balance
        print(f"\n[2] Getting account info...")
        account_info = client.get_account_state(db)
        available_balance = account_info.get("available_balance", 0)
        print(f"    Available balance: ${available_balance:,.2f}")

        # Step 3: Get current price
        print(f"\n[3] Getting {SYMBOL} price...")
        current_price = get_testnet_price(SYMBOL)
        print(f"    Current price: ${current_price:,.2f}")

        # Step 4: Calculate order parameters
        print(f"\n[4] Calculating GTC order parameters...")

        size_usd = available_balance * TARGET_PORTION
        size = size_usd / current_price

        # Set limit price BELOW market (won't fill immediately)
        limit_price = round(current_price * (1 + PRICE_OFFSET_PERCENT / 100), 1)

        print(f"    Order type: GTC (Good Till Cancel)")
        print(f"    Side: BUY (Long)")
        print(f"    Size: {size:.4f} {SYMBOL} (~${size_usd:,.2f})")
        print(f"    Limit price: ${limit_price:,.1f} ({PRICE_OFFSET_PERCENT}% from market)")
        print(f"    Expected: Order should REST (not fill immediately)")

        # Step 5: Place GTC order
        print(f"\n[5] Placing GTC order...")
        result = client.place_order_with_tpsl(
            db=db,
            symbol=SYMBOL,
            is_buy=True,
            size=size,
            price=limit_price,
            leverage=LEVERAGE,
            time_in_force=TIME_IN_FORCE,
            reduce_only=False,
            take_profit_price=None,
            stop_loss_price=None,
        )

        # Step 6: Print result
        print(f"\n[6] Order Result:")
        print("-" * 40)

        status = result.get("status", "")
        order_id = result.get("order_id")

        if status == "resting":
            print(f"    Status: RESTING (as expected)")
            print(f"    Order ID: {order_id}")
            print(f"    Order is waiting in orderbook at ${limit_price:,.1f}")
        elif status == "filled":
            print(f"    Status: FILLED (unexpected - price moved)")
            print(f"    Order ID: {order_id}")
            print(f"    Filled: {result.get('filled_amount')} @ ${result.get('average_price'):,.2f}")
        else:
            print(f"    Status: {status}")
            print(f"    Error: {result.get('error')}")

        print("-" * 40)
        print(f"\nFull result: {result}")

        # Step 7: Cancel the resting order
        if status == "resting" and order_id:
            print(f"\n[7] Cancelling resting order...")
            cancel_result = client.cancel_order(db, SYMBOL, order_id)
            print(f"    Cancel result: {cancel_result}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
