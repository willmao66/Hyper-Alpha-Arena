#!/usr/bin/env python3
"""
真实下单并获取 Position, Trade, Order 数据
使用 Deepseek AI Trader (account_id=1) 在 Testnet 上下单
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from database.connection import SessionLocal
from database.models import Account
from services.hyperliquid_trading_client import HyperliquidTradingClient
from utils.encryption import decrypt_private_key
import time

ACCOUNT_ID = 1
ENVIRONMENT = 'testnet'

def main():
    db = SessionLocal()

    try:
        print("=" * 80)
        print("真实下单测试 - Hyperliquid Testnet")
        print("=" * 80)
        print()

        # 1. 从数据库读取账户配置
        print("### 步骤 0: 读取账户配置 ###")
        account = db.query(Account).filter(Account.id == ACCOUNT_ID).first()
        if not account:
            print(f"❌ Account ID {ACCOUNT_ID} not found")
            return

        print(f"Account: {account.name}")
        print(f"Hyperliquid Environment: {account.hyperliquid_environment}")

        # 2. 解密私钥
        if ENVIRONMENT == 'testnet':
            encrypted_key = account.hyperliquid_testnet_private_key
        else:
            encrypted_key = account.hyperliquid_mainnet_private_key

        if not encrypted_key:
            print(f"❌ No private key found for {ENVIRONMENT}")
            return

        try:
            private_key = decrypt_private_key(encrypted_key)
            print(f"✅ Private key decrypted (length: {len(private_key)})")
        except Exception as e:
            print(f"❌ Failed to decrypt private key: {e}")
            return

        # 3. 创建 Trading Client
        client = HyperliquidTradingClient(
            account_id=ACCOUNT_ID,
            private_key=private_key,
            environment=ENVIRONMENT
        )
        print(f"✅ Trading client created")
        print()

        # 1. 下一个小额市价单（Long BTC）
        print("### 步骤 1: 下市价单 ###")
        symbol = "BTC"
        size = 0.001  # 小额测试
        is_buy = True  # Long

        print(f"下单参数: {symbol} {'Buy' if is_buy else 'Sell'} {size}")

        try:
            # 下市价单
            order_result = client.place_order(
                db=db,
                symbol=symbol,
                is_buy=is_buy,
                size=size,
                order_type="market",
                reduce_only=False,
                leverage=1
            )
            print(f"✅ 市价单已下: {order_result}")
        except Exception as e:
            print(f"❌ 下单失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 等待订单成交
        print("\n等待 5 秒让订单成交...")
        time.sleep(5)

        # 2. 查询持仓
        print("\n### 步骤 2: 查询持仓 (Position) ###")
        try:
            positions = client.get_positions(db)
            print(f"找到 {len(positions)} 个持仓")

            if positions:
                print("\n真实 Position 数据：")
                for pos in positions[:3]:
                    print(f"""
Position(
    symbol="{pos.get('coin') or pos.get('symbol', '')}",
    side="{pos.get('side', 'long').lower()}",
    size={abs(float(pos.get('szi', 0) or pos.get('size', 0)))},
    entry_price={float(pos.get('entry_px', 0) or pos.get('entry_price', 0))},
    unrealized_pnl={float(pos.get('unrealized_pnl', 0))},
    leverage={int(float(pos.get('leverage', 1) or 1))},
    liquidation_price={float(pos.get('liquidation_px', 0) or pos.get('liquidation_price', 0))}
)""")
            else:
                print("  当前没有持仓")
        except Exception as e:
            print(f"  错误: {e}")

        # 3. 查询交易历史
        print("\n### 步骤 3: 查询交易历史 (Trade) ###")
        try:
            trades = client.get_recent_trades(db, limit=5)
            print(f"找到 {len(trades)} 条交易记录")

            if trades:
                print("\n真实 Trade 数据：")
                for trade in trades[:3]:
                    print(f"""
Trade(
    symbol="{trade.get('symbol', '')}",
    side="{trade.get('side', '')}",
    size={trade.get('size', 0)},
    price={trade.get('price', 0)},
    timestamp={trade.get('timestamp', 0)},
    pnl={trade.get('pnl', 0)},
    close_time="{trade.get('close_time', '')}"
)""")
            else:
                print("  没有交易历史")
        except Exception as e:
            print(f"  错误: {e}")

        # 4. 下一个限价单（不会立即成交）
        print("\n### 步骤 4: 下限价单（用于获取 Order 数据）###")
        try:
            # 获取当前价格
            current_price = float(positions[0].get('entry_px', 100000)) if positions else 100000
            # 设置一个远离市场价的限价单
            limit_price = current_price * 0.8  # 低于市价 20%

            print(f"下限价单: {symbol} Sell {size} @ {limit_price}")

            limit_order_result = client.place_order(
                db=db,
                symbol=symbol,
                is_buy=False,  # Sell
                size=size,
                order_type="limit",
                price=limit_price,
                reduce_only=True,
                leverage=1
            )
            print(f"✅ 限价单已下: {limit_order_result}")
        except Exception as e:
            print(f"❌ 下限价单失败: {e}")

        # 等待订单同步
        print("\n等待 3 秒让订单同步...")
        time.sleep(3)

        # 5. 查询挂单
        print("\n### 步骤 5: 查询挂单 (Order) ###")
        try:
            orders = client.get_open_orders(db)
            print(f"找到 {len(orders)} 个挂单")

            if orders:
                print("\n真实 Order 数据：")
                for order in orders[:3]:
                    print(f"""
Order(
    order_id={order.get('order_id', 0)},
    symbol="{order.get('symbol', '')}",
    side="{order.get('side', '')}",
    direction="{order.get('direction', '')}",
    order_type="{order.get('order_type', '')}",
    size={order.get('size', 0)},
    price={order.get('price', 0)},
    trigger_price={order.get('trigger_price')},
    reduce_only={order.get('reduce_only', False)},
    timestamp={order.get('timestamp', 0)}
)""")
            else:
                print("  没有挂单")
        except Exception as e:
            print(f"  错误: {e}")

        print("\n" + "=" * 80)
        print("✅ 完成！已获取真实的 Position, Trade, Order 数据")
        print("=" * 80)

    except Exception as e:
        print(f"\n致命错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

if __name__ == "__main__":
    main()
