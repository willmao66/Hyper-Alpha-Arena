#!/usr/bin/env python3
"""
获取真实的 Position, Trade, Order 示例数据
用于更新 Programs 功能的文档
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from database.connection import SessionLocal
from program_trader.data_provider import DataProvider
from sqlalchemy import text
import json

def find_ai_trader_accounts(db):
    """查找有交易记录的 AI Trader 账户"""
    print("=== 查找 AI Trader 账户 ===\n")

    # 先查询所有 testnet 账户
    query = text("""
        SELECT
            id as account_id,
            name,
            wallet_address,
            environment
        FROM accounts
        WHERE environment = 'testnet'
        ORDER BY id DESC
        LIMIT 10
    """)

    result = db.execute(query)
    accounts = result.fetchall()

    for acc in accounts:
        print(f"Account ID: {acc.account_id}")
        print(f"Name: {acc.name}")
        print(f"Wallet: {acc.wallet_address}")
        print(f"Environment: {acc.environment}")
        print("-" * 60)

    return accounts

def get_real_data(db, account_id, environment='testnet'):
    """获取真实的 Position, Trade, Order 数据"""
    print(f"\n=== 获取 Account {account_id} 的真实数据 ===\n")

    provider = DataProvider(db, account_id=account_id, environment=environment)

    # 获取持仓
    positions = provider.get_positions()
    print(f"Positions: {len(positions)} 个")

    # 获取交易历史
    trades = provider.get_recent_trades()
    print(f"Recent Trades: {len(trades)} 条")

    # 获取挂单
    orders = provider.get_open_orders()
    print(f"Open Orders: {len(orders)} 个")

    return positions, trades, orders

def format_position(pos):
    """格式化 Position 对象为文档示例"""
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
    """格式化 Trade 对象为文档示例"""
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
    """格式化 Order 对象为文档示例"""
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
        # 1. 查找账户
        accounts = find_ai_trader_accounts(db)

        if not accounts:
            print("\n❌ 没有找到任何账户")
            return

        # 2. 遍历账户，找到有数据的
        for acc in accounts:
            account_id = acc.account_id
            positions, trades, orders = get_real_data(db, account_id, acc.environment)

            # 如果这个账户有数据，输出示例
            if positions or trades or orders:
                print("\n" + "=" * 80)
                print(f"✅ 找到真实数据！Account ID: {account_id}, Name: {acc.name}")
                print("=" * 80)

                # 输出 Position 示例
                if positions:
                    print("\n### Position 示例（真实数据）###")
                    for symbol, pos in list(positions.items())[:2]:  # 最多输出2个
                        print(format_position(pos))
                        print()

                # 输出 Trade 示例
                if trades:
                    print("\n### Trade 示例（真实数据）###")
                    for trade in trades[:2]:  # 最多输出2个
                        print(format_trade(trade))
                        print()

                # 输出 Order 示例
                if orders:
                    print("\n### Order 示例（真实数据）###")
                    for order in orders[:2]:  # 最多输出2个
                        print(format_order(order))
                        print()

                # 找到数据后就停止
                break
        else:
            print("\n⚠️  所有账户都没有持仓、交易历史或挂单")
            print("\n建议：")
            print("1. 使用 AI Trader 在 Testnet 上执行一些交易")
            print("2. 或者手动在 Hyperliquid Testnet 上下单")
            print(f"3. 使用的钱包地址：{accounts[0].wallet_address if accounts else 'N/A'}")

    finally:
        db.close()

if __name__ == "__main__":
    main()
