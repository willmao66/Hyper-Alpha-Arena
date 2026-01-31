#!/usr/bin/env python3
"""
获取真实的 Position, Trade, Order 示例数据
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from database.connection import SessionLocal
from database.models import Account
from program_trader.data_provider import DataProvider

def format_position(pos):
    return f"""Position(
    symbol="{pos.symbol}",
    side="{pos.side}",
    size={pos.size},
    entry_price={pos.entry_price},
    unrealized_pnl={pos.unrealized_pnl},
    leverage={pos.leverage},
    liquidation_price={pos.liquidation_price}
)"""

def format_trade(trade):
    return f"""Trade(
    symbol="{trade.symbol}",
    side="{trade.side}",
    size={trade.size},
    price={trade.price},
    timestamp={trade.timestamp},
    pnl={trade.pnl},
    close_time="{trade.close_time}"
)"""

def format_order(order):
    return f"""Order(
    order_id={order.order_id},
    symbol="{order.symbol}",
    side="{order.side}",
    direction="{order.direction}",
    order_type="{order.order_type}",
    size={order.size},
    price={order.price},
    trigger_price={order.trigger_price},
    reduce_only={order.reduce_only},
    timestamp={order.timestamp}
)"""

def main():
    db = SessionLocal()

    try:
        # 查找所有 testnet 账户
        accounts = db.query(Account).filter(Account.environment == 'testnet').all()
        print(f"=== 找到 {len(accounts)} 个 Testnet 账户 ===\n")

        for acc in accounts:
            print(f"检查 Account ID: {acc.id}, Name: {acc.name}")

            # 创建 DataProvider
            provider = DataProvider(db, account_id=acc.id, environment='testnet')

            # 获取数据
            positions = provider.get_positions()
            trades = provider.get_recent_trades()
            orders = provider.get_open_orders()

            print(f"  Positions: {len(positions)}, Trades: {len(trades)}, Orders: {len(orders)}")

            # 如果有数据，输出
            if positions or trades or orders:
                print("\n" + "=" * 80)
                print(f"✅ 找到真实数据！Account: {acc.name} (ID: {acc.id})")
                print("=" * 80)

                if positions:
                    print("\n### Position 示例（真实数据）###")
                    for symbol, pos in list(positions.items())[:2]:
                        print(format_position(pos))
                        print()

                if trades:
                    print("\n### Trade 示例（真实数据）###")
                    for trade in trades[:2]:
                        print(format_trade(trade))
                        print()

                if orders:
                    print("\n### Order 示例（真实数据）###")
                    for order in orders[:2]:
                        print(format_order(order))
                        print()

                break
            print()
        else:
            print("\n⚠️  所有账户都没有持仓、交易历史或挂单")
            print("建议：使用 AI Trader 在 Testnet 上执行交易")

    finally:
        db.close()

if __name__ == "__main__":
    main()
