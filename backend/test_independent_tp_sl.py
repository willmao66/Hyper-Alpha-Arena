#!/usr/bin/env python3
"""
Test script for independent TP/SL orders.
Verifies that each order is independent and partial close works correctly.
"""
import sys
sys.path.insert(0, '/home/wwwroot/hyper-alpha-arena-prod/backend')

from backtest.virtual_account import VirtualAccount, VirtualOrder
from backtest.execution_simulator import ExecutionSimulator
from dataclasses import dataclass

@dataclass
class MockDecision:
    """Mock decision for testing."""
    operation: str
    symbol: str
    reason: str = ""
    target_portion_of_balance: float = 0.3
    leverage: int = 10
    take_profit_price: float = None
    stop_loss_price: float = None


def test_independent_tp_sl():
    """Test that TP/SL orders are independent for each position entry."""
    print("=" * 60)
    print("TEST: Independent TP/SL Orders")
    print("=" * 60)

    account = VirtualAccount(initial_balance=10000.0)
    simulator = ExecutionSimulator(slippage_percent=0.05, fee_rate=0.035)

    # Simulate 3 SELL (short) entries at different prices with different SL
    entries = [
        {"price": 91000, "sl": 92000},  # SL at 92000 (1.1% above entry)
        {"price": 90000, "sl": 91000},  # SL at 91000 (1.1% above entry)
        {"price": 89000, "sl": 90000},  # SL at 90000 (1.1% above entry)
    ]

    print("\n--- Opening 3 short positions with independent SL ---")
    for i, entry in enumerate(entries):
        decision = MockDecision(
            operation="sell",
            symbol="BTC",
            reason=f"Entry {i+1}",
            target_portion_of_balance=0.3,
            leverage=10,
            stop_loss_price=entry["sl"],
        )

        trade = simulator.execute_decision(
            decision=decision,
            account=account,
            current_price=entry["price"],
            timestamp=1000000 + i * 1000,
            trigger_type="signal",
        )

        if trade:
            print(f"  Entry {i+1}: price={entry['price']}, size={trade.size:.4f}, SL={entry['sl']}")

    # Check pending orders
    print(f"\n--- Pending Orders: {len(account.pending_orders)} ---")
    for order in account.pending_orders:
        print(f"  Order {order.order_id}: type={order.order_type}, "
              f"size={order.size:.4f}, trigger={order.trigger_price}, entry={order.entry_price}")

    # Check position
    pos = account.get_position("BTC")
    print(f"\n--- Position ---")
    print(f"  Total size: {pos.size:.4f}")
    print(f"  Avg entry: {pos.entry_price:.2f}")
    print(f"  Balance: {account.balance:.2f}")

    # Now simulate price rising to 91500 - should trigger SL for entry 2 and 3
    print("\n--- Price rises to 91500 (triggers SL for entries 2 & 3) ---")
    triggered = simulator.check_tp_sl_triggers(account, {"BTC": 91500}, 2000000)

    print(f"  Triggered trades: {len(triggered)}")
    for t in triggered:
        print(f"    - Entry price: {t.entry_price:.2f}, Exit: {t.exit_price:.2f}, "
              f"Size: {t.size:.4f}, PnL: {t.pnl:.2f}, Reason: {t.exit_reason}")

    # Check remaining position and orders
    pos = account.get_position("BTC")
    print(f"\n--- After partial close ---")
    if pos:
        print(f"  Remaining size: {pos.size:.4f}")
    else:
        print(f"  Position fully closed")
    print(f"  Remaining orders: {len(account.pending_orders)}")
    for order in account.pending_orders:
        print(f"    Order {order.order_id}: trigger={order.trigger_price}, size={order.size:.4f}")
    print(f"  Balance: {account.balance:.2f}")
    print(f"  Equity: {account.equity:.2f}")

    # Verify PnL is negative (short position, price went up = loss)
    print("\n--- Verification ---")
    all_pnl_negative = all(t.pnl < 0 for t in triggered)
    print(f"  All triggered SL have negative PnL (correct for short): {all_pnl_negative}")

    # Entry 1 should still have its SL order
    entry1_sl_exists = any(o.trigger_price == 92000 for o in account.pending_orders)
    print(f"  Entry 1 SL (92000) still exists: {entry1_sl_exists}")

    return all_pnl_negative and entry1_sl_exists


def test_partial_close_pnl():
    """Test that PnL is calculated correctly for each partial close."""
    print("\n" + "=" * 60)
    print("TEST: Partial Close PnL Calculation")
    print("=" * 60)

    account = VirtualAccount(initial_balance=10000.0)
    simulator = ExecutionSimulator(slippage_percent=0, fee_rate=0)  # No slippage/fee for easy calc

    # Open short at 100
    decision = MockDecision(
        operation="sell",
        symbol="BTC",
        target_portion_of_balance=0.5,
        leverage=1,
        stop_loss_price=110,  # 10% SL
    )

    trade = simulator.execute_decision(
        decision=decision,
        account=account,
        current_price=100,
        timestamp=1000,
        trigger_type="signal",
    )
    size1 = trade.size
    print(f"\n  Entry 1: price=100, size={size1:.2f}")

    # Add to position at 90 (better price for short)
    decision2 = MockDecision(
        operation="sell",
        symbol="BTC",
        target_portion_of_balance=0.5,
        leverage=1,
        stop_loss_price=100,  # 10% SL from 90
    )

    trade2 = simulator.execute_decision(
        decision=decision2,
        account=account,
        current_price=90,
        timestamp=2000,
        trigger_type="signal",
    )
    size2 = trade2.size
    print(f"  Entry 2: price=90, size={size2:.2f}")

    print(f"\n  Pending orders: {len(account.pending_orders)}")
    for o in account.pending_orders:
        print(f"    SL at {o.trigger_price}, size={o.size:.2f}, entry={o.entry_price}")

    # Price goes to 105 - triggers SL for entry 2 (SL at 100)
    print("\n  Price rises to 105 (triggers SL at 100 for entry 2)")
    triggered = simulator.check_tp_sl_triggers(account, {"BTC": 105}, 3000)

    for t in triggered:
        # Entry 2 was at 90, SL at 100, short position
        # PnL = (entry - exit) * size = (90 - 100) * size = -10 * size
        expected_pnl = (90 - 100) * t.size
        print(f"    Triggered: entry={t.entry_price}, exit={t.exit_price}, "
              f"size={t.size:.2f}, PnL={t.pnl:.2f}")
        print(f"    Expected PnL: {expected_pnl:.2f}, Match: {abs(t.pnl - expected_pnl) < 0.01}")

    # Entry 1 SL at 110 should still exist
    remaining_orders = account.pending_orders
    print(f"\n  Remaining orders: {len(remaining_orders)}")
    entry1_sl = next((o for o in remaining_orders if o.trigger_price == 110), None)
    if entry1_sl:
        print(f"    Entry 1 SL still active: trigger={entry1_sl.trigger_price}, size={entry1_sl.size:.2f}")

    return len(triggered) == 1 and entry1_sl is not None


def test_no_profit_on_sl():
    """Test that stop loss never results in profit."""
    print("\n" + "=" * 60)
    print("TEST: Stop Loss Should Not Result in Profit")
    print("=" * 60)

    account = VirtualAccount(initial_balance=10000.0)
    simulator = ExecutionSimulator(slippage_percent=0, fee_rate=0)

    # Short at 100, SL at 101 (1% loss if triggered)
    decision = MockDecision(
        operation="sell",
        symbol="BTC",
        target_portion_of_balance=0.5,
        leverage=1,
        stop_loss_price=101,
    )

    trade = simulator.execute_decision(
        decision=decision,
        account=account,
        current_price=100,
        timestamp=1000,
        trigger_type="signal",
    )
    print(f"\n  Short entry: price=100, SL=101, size={trade.size:.2f}")

    # Price goes to 101 - triggers SL
    print("  Price rises to 101 (triggers SL)")
    triggered = simulator.check_tp_sl_triggers(account, {"BTC": 101}, 2000)

    for t in triggered:
        print(f"    SL triggered: entry={t.entry_price}, exit={t.exit_price}, PnL={t.pnl:.2f}")
        # Short at 100, exit at 101 = loss
        is_loss = t.pnl < 0
        print(f"    Is loss (correct): {is_loss}")

    return len(triggered) == 1 and triggered[0].pnl < 0


if __name__ == "__main__":
    results = []

    results.append(("Independent TP/SL", test_independent_tp_sl()))
    results.append(("Partial Close PnL", test_partial_close_pnl()))
    results.append(("No Profit on SL", test_no_profit_on_sl()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + ("ALL TESTS PASSED!" if all_passed else "SOME TESTS FAILED!"))
    sys.exit(0 if all_passed else 1)
