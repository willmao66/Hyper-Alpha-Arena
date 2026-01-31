#!/usr/bin/env python3
"""
Test Zero Builder Fee Order on Mainnet

This script tests whether Hyperliquid accepts orders with builder fee = 0.
It will place a REAL order on mainnet using Deepseek Hammer account.

IMPORTANT: This uses REAL funds. Review carefully before running!
"""

import sys
import requests

sys.path.insert(0, "/app/backend")

from database.connection import SessionLocal
from database.models import HyperliquidWallet
from utils.encryption import decrypt_private_key

# Hyperliquid SDK
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

# ============== Configuration ==============
ACCOUNT_ID = 3  # Deepseek Hammer
ENVIRONMENT = "mainnet"
SYMBOL = "BTC"
LEVERAGE = 3
BUILDER_ADDRESS = "0x012E82f81e506b8f0EF69FF719a6AC65822b5924"
BUILDER_FEE = 0  # <-- KEY TEST: Zero fee
# ===========================================


def get_mainnet_price(symbol: str) -> float:
    """Get current price from Hyperliquid mainnet"""
    url = "https://api.hyperliquid.xyz/info"
    resp = requests.post(url, json={"type": "allMids"}, timeout=10)
    resp.raise_for_status()
    return float(resp.json().get(symbol, 0))


def main():
    print("=" * 70)
    print("ZERO BUILDER FEE TEST - MAINNET (REAL FUNDS)")
    print("=" * 70)
    print(f"\nBuilder Address: {BUILDER_ADDRESS}")
    print(f"Builder Fee: {BUILDER_FEE} (0 = 0%)")
    print("\n*** WARNING: This will place a REAL order on mainnet! ***\n")

    db = SessionLocal()

    try:
        # Step 1: Get wallet info
        print(f"[1] Loading wallet for account {ACCOUNT_ID} ({ENVIRONMENT})...")
        wallet = db.query(HyperliquidWallet).filter(
            HyperliquidWallet.account_id == ACCOUNT_ID,
            HyperliquidWallet.environment == ENVIRONMENT,
            HyperliquidWallet.is_active == "true"
        ).first()

        if not wallet:
            print("ERROR: Wallet not found!")
            return

        print(f"    Wallet: {wallet.wallet_address[:10]}...{wallet.wallet_address[-8:]}")

        # Step 2: Decrypt private key and init SDK
        print(f"\n[2] Initializing Hyperliquid SDK...")
        private_key = decrypt_private_key(wallet.private_key_encrypted)

        # Create wallet object from private key
        from eth_account import Account as EthAccount
        eth_wallet = EthAccount.from_key(private_key)

        info = Info(base_url="https://api.hyperliquid.xyz", skip_ws=True)
        exchange = Exchange(
            wallet=eth_wallet,  # 需要 wallet 对象，不是字符串
            base_url="https://api.hyperliquid.xyz",
            account_address=wallet.wallet_address
        )

        # Step 3: Get account state
        print(f"\n[3] Getting account state...")
        user_state = info.user_state(wallet.wallet_address)

        margin_summary = user_state.get("marginSummary", {})
        account_value = float(margin_summary.get("accountValue", 0))
        available = float(margin_summary.get("totalMarginUsed", 0))

        print(f"    Account Value: ${account_value:,.2f}")

        # Step 4: Get current positions
        print(f"\n[4] Getting current positions...")
        positions = user_state.get("assetPositions", [])
        btc_position = None

        for pos in positions:
            pos_info = pos.get("position", {})
            coin = pos_info.get("coin", "")
            if coin == SYMBOL:
                btc_position = pos_info
                break

        if btc_position:
            szi = float(btc_position.get("szi", 0))
            entry_px = float(btc_position.get("entryPx", 0))
            print(f"    BTC Position: {szi} @ ${entry_px:,.2f}")
        else:
            print(f"    No BTC position found")
            szi = 0

        # Step 5: Get current BTC price
        print(f"\n[5] Getting BTC price...")
        btc_price = get_mainnet_price(SYMBOL)
        print(f"    Current BTC: ${btc_price:,.2f}")

        # Step 6: Calculate order size (50% of current position or minimum)
        print(f"\n[6] Calculating order size...")

        if abs(szi) > 0:
            # 50% of current position
            order_size = abs(szi) * 0.5
        else:
            # Minimum order: ~$100 worth
            order_size = 100 / btc_price

        # Round to 5 decimal places (Hyperliquid precision)
        order_size = round(order_size, 5)
        order_value = order_size * btc_price

        print(f"    Order Size: {order_size} BTC (~${order_value:,.2f})")
        print(f"    Side: SELL (Short)")
        print(f"    Leverage: {LEVERAGE}x")

        # Step 7: Show order preview
        print(f"\n" + "=" * 70)
        print("ORDER PREVIEW (with builder fee = 0)")
        print("=" * 70)
        print(f"  Symbol:        {SYMBOL}")
        print(f"  Side:          SELL (Short)")
        print(f"  Size:          {order_size} BTC")
        print(f"  Value:         ~${order_value:,.2f}")
        print(f"  Leverage:      {LEVERAGE}x")
        print(f"  Builder:       {BUILDER_ADDRESS}")
        print(f"  Builder Fee:   {BUILDER_FEE} (0%)")
        print("=" * 70)

        # Step 8: Confirm before placing (skip if --confirm flag)
        if "--confirm" not in sys.argv:
            print("\nTo execute, run with --confirm flag")
            return

        # Step 9: Set leverage
        print(f"\n[7] Setting leverage to {LEVERAGE}x...")
        try:
            lev_result = exchange.update_leverage(LEVERAGE, SYMBOL, is_cross=True)
            print(f"    Leverage result: {lev_result}")
        except Exception as e:
            print(f"    Leverage warning: {e}")

        # Step 10: Place order with builder fee = 0
        print(f"\n[8] Placing order with builder fee = 0...")

        order_result = exchange.market_open(
            name=SYMBOL,  # 参数名是 name 不是 coin
            is_buy=False,  # SELL (Short)
            sz=order_size,
            px=None,  # Market order
            slippage=0.05,  # 5% slippage
            builder={
                "b": BUILDER_ADDRESS,
                "f": BUILDER_FEE  # <-- KEY: Testing fee = 0
            }
        )

        # Step 11: Print result
        print(f"\n" + "=" * 70)
        print("ORDER RESULT")
        print("=" * 70)
        print(f"Raw response: {order_result}")

        response = order_result.get("response", {})
        data = response.get("data", {})
        statuses = data.get("statuses", [])

        if statuses:
            status = statuses[0]
            if "error" in status:
                print(f"\n*** ERROR: {status['error']} ***")
                print("\nBuilder fee = 0 may NOT be supported!")
            elif "filled" in status:
                filled = status["filled"]
                print(f"\n*** SUCCESS: Order filled! ***")
                print(f"  Total Size: {filled.get('totalSz')}")
                print(f"  Avg Price:  ${float(filled.get('avgPx', 0)):,.2f}")
                print(f"  Order ID:   {filled.get('oid')}")
                print("\nBuilder fee = 0 IS SUPPORTED!")
            elif "resting" in status:
                print(f"\n*** Order resting (limit order) ***")
                print(f"  Order ID: {status['resting'].get('oid')}")
        else:
            print(f"\nUnexpected response format")

        print("=" * 70)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    main()
