#!/usr/bin/env python3
"""
使用钱包地址直接获取真实的 Position, Trade, Order 数据
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from database.connection import SessionLocal
from sqlalchemy import text

# Deepseek AI Trader 的钱包地址
WALLET_ADDRESS = '0x012E82f81e506b8f0EF69FF719a6AC65822b5924'
ENVIRONMENT = 'testnet'

def get_trades_from_db(db, wallet_address, environment):
    """从数据库获取交易历史"""
    query = text("""
        SELECT
            symbol, side, size, price, timestamp, pnl, close_time
        FROM hyperliquid_trades
        WHERE wallet_address = :wallet
        AND environment = :env
        ORDER BY timestamp DESC
        LIMIT 10
    """)

    result = db.execute(query, {"wallet": wallet_address, "env": environment})
    return result.fetchall()

def get_positions_from_db(db, wallet_address, environment):
    """从数据库获取持仓"""
    query = text("""
        SELECT
            symbol, side, size, entry_price, unrealized_pnl, leverage, liquidation_price
        FROM hyperliquid_positions
        WHERE wallet_address = :wallet
        AND environment = :env
    """)

    result = db.execute(query, {"wallet": wallet_address, "env": environment})
    return result.fetchall()

def get_orders_from_db(db, wallet_address, environment):
    """从数据库获取订单"""
    query = text("""
        SELECT
            order_id, symbol, side, direction, order_type, size, price,
            trigger_price, reduce_only, timestamp
        FROM hyperliquid_orders
        WHERE wallet_address = :wallet
        AND environment = :env
        LIMIT 10
    """)

    result = db.execute(query, {"wallet": wallet_address, "env": environment})
    return result.fetchall()

def format_trade(trade):
    """格式化 Trade"""
    return f"""Trade(
    symbol="{trade.symbol}",
    side="{trade.side}",
    size={trade.size},
    price={trade.price},
    timestamp={trade.timestamp},
    pnl={trade.pnl},
    close_time="{trade.close_time}"
)"""

def format_position(pos):
    """格式化 Position"""
    return f"""Position(
    symbol="{pos.symbol}",
    side="{pos.side}",
    size={pos.size},
    entry_price={pos.entry_price},
    unrealized_pnl={pos.unrealized_pnl},
    leverage={pos.leverage},
    liquidation_price={pos.liquidation_price}
)"""

def format_order(order):
    """格式化 Order"""
    return f"""Order(
    order_id={order.order_id},
    symbol="{order.symbol}",
    side="{order.side}",
    direction="{order.direction}",
    order_type="{order.order_type}",
    size={order.size},
    price={order.price},
    trigger_price={order.trigger_price if order.trigger_price else 'None'},
    reduce_only={order.reduce_only},
    timestamp={order.timestamp}
)"""

def main():
    db = SessionLocal()

    try:
        print(f"=== 查询钱包地址: {WALLET_ADDRESS} ===")
        print(f"=== 环境: {ENVIRONMENT} ===\n")

        # 获取交易历史
        print("查询交易历史...")
        trades = get_trades_from_db(db, WALLET_ADDRESS, ENVIRONMENT)
        print(f"找到 {len(trades)} 条交易记录\n")

        # 获取持仓
        print("查询持仓...")
        positions = get_positions_from_db(db, WALLET_ADDRESS, ENVIRONMENT)
        print(f"找到 {len(positions)} 个持仓\n")

        # 获取订单
        print("查询订单...")
        orders = get_orders_from_db(db, WALLET_ADDRESS, ENVIRONMENT)
        print(f"找到 {len(orders)} 个订单\n")

        # 输出结果
        if trades or positions or orders:
            print("=" * 80)
            print("✅ 找到真实数据！")
            print("=" * 80)

            if trades:
                print("\n### Trade 示例（真实数据）###")
                for trade in trades[:2]:
                    print(format_trade(trade))
                    print()

            if positions:
                print("\n### Position 示例（真实数据）###")
                for pos in positions[:2]:
                    print(format_position(pos))
                    print()

            if orders:
                print("\n### Order 示例（真实数据）###")
                for order in orders[:2]:
                    print(format_order(order))
                    print()
        else:
            print("⚠️  数据库中没有找到数据")
            print("\n尝试直接调用 Hyperliquid API...")

            # 如果数据库没有，尝试直接调用 API
            from services.hyperliquid_market_data import get_user_state
            try:
                user_state = get_user_state(WALLET_ADDRESS, ENVIRONMENT)
                print(f"\nAPI 返回: {user_state}")
            except Exception as e:
                print(f"API 调用失败: {e}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

if __name__ == "__main__":
    main()
