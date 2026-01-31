#!/usr/bin/env python3
"""
最终脚本：使用 Deepseek AI Trader 的钱包地址获取真实数据
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from database.connection import SessionLocal
from services.hyperliquid_trading_client import HyperliquidTradingClient

# Deepseek AI Trader 的钱包地址
WALLET_ADDRESS = '0x012E82f81e506b8f0EF69FF719a6AC65822b5924'
ENVIRONMENT = 'testnet'

def main():
    db = SessionLocal()

    try:
        print("=" * 80)
        print(f"查询 Deepseek AI Trader")
        print(f"钱包地址: {WALLET_ADDRESS}")
        print(f"环境: {ENVIRONMENT}")
        print("=" * 80)
        print()

        # 创建 Hyperliquid Trading Client
        client = HyperliquidTradingClient(
            wallet_address=WALLET_ADDRESS,
            environment=ENVIRONMENT
        )

        # 1. 获取持仓
        print("### 1. 获取持仓 (Positions) ###")
        try:
            positions = client.get_positions(db)
            print(f"找到 {len(positions)} 个持仓")

            if positions:
                print("\n真实 Position 示例：")
                for pos in positions[:2]:
                    symbol = pos.get("coin") or pos.get("symbol", "")
                    size = abs(float(pos.get("szi", 0) or pos.get("size", 0)))
                    entry_price = float(pos.get("entry_px", 0) or pos.get("entry_price", 0))
                    unrealized_pnl = float(pos.get("unrealized_pnl", 0))
                    leverage = int(float(pos.get("leverage", 1) or 1))
                    liquidation_price = float(pos.get("liquidation_px", 0) or pos.get("liquidation_price", 0))
                    side = pos.get("side", "long").lower()

                    print(f"""
Position(
    symbol="{symbol}",
    side="{side}",
    size={size},
    entry_price={entry_price},
    unrealized_pnl={unrealized_pnl},
    leverage={leverage},
    liquidation_price={liquidation_price}
)""")
            else:
                print("  当前没有持仓")
        except Exception as e:
            print(f"  错误: {e}")

        print()

        # 2. 获取交易历史
        print("### 2. 获取交易历史 (Trades) ###")
        try:
            trades = client.get_recent_trades(db, limit=10)
            print(f"找到 {len(trades)} 条交易记录")

            if trades:
                print("\n真实 Trade 示例：")
                for trade in trades[:2]:
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

        print()

        # 3. 获取订单
        print("### 3. 获取订单 (Orders) ###")
        try:
            orders = client.get_open_orders(db)
            print(f"找到 {len(orders)} 个订单")

            if orders:
                print("\n真实 Order 示例：")
                for order in orders[:2]:
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

        print()
        print("=" * 80)
        print("完成！")
        print("=" * 80)

    except Exception as e:
        print(f"\n致命错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

if __name__ == "__main__":
    main()
