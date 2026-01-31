"""
Test partial close and TP/SL functionality in backtest execution simulator.
"""
import sys
sys.path.insert(0, '/home/wwwroot/hyper-alpha-arena-prod/backend')

from backtest.virtual_account import VirtualAccount
from backtest.execution_simulator import ExecutionSimulator


class MockDecision:
    """Mock decision object for testing."""
    def __init__(self, operation, symbol, target_portion=1.0, leverage=1, reason="",
                 take_profit_price=None, stop_loss_price=None):
        self.operation = operation
        self.symbol = symbol
        self.target_portion_of_balance = target_portion
        self.leverage = leverage
        self.reason = reason
        self.take_profit_price = take_profit_price
        self.stop_loss_price = stop_loss_price


def test_partial_close():
    """Test that partial close works correctly."""
    print("=" * 60)
    print("Test 1: Basic Partial Close")
    print("=" * 60)

    account = VirtualAccount(initial_balance=10000.0)
    simulator = ExecutionSimulator(slippage_percent=0.0, fee_rate=0.0)

    # Open position
    account.open_position(symbol="BTC", side="long", size=1.0, entry_price=100000.0,
                          leverage=10, timestamp=1000)
    account.update_equity({"BTC": 100000.0})
    print(f"\n[Initial] Position: 1.0 BTC @ $100,000")

    # Partial close 30%
    decision = MockDecision("close", "BTC", target_portion=0.3)
    trade = simulator.execute_decision(decision, account, 101000.0, 2000)
    account.update_equity({"BTC": 101000.0})

    pos = account.get_position("BTC")
    assert pos is not None, "Position should still exist"
    assert abs(pos.size - 0.7) < 0.0001, f"Expected 0.7, got {pos.size}"
    assert abs(trade.size - 0.3) < 0.0001, f"Expected trade size 0.3, got {trade.size}"
    print(f"[After 30% close] Remaining: {pos.size:.4f} BTC ✅")

    # Full close
    decision = MockDecision("close", "BTC", target_portion=1.0)
    trade = simulator.execute_decision(decision, account, 102000.0, 3000)

    pos = account.get_position("BTC")
    assert pos is None, "Position should be fully closed"
    assert abs(trade.size - 0.7) < 0.0001, f"Expected trade size 0.7, got {trade.size}"
    print(f"[After full close] Position closed ✅")
    print("Test 1 PASSED ✅\n")
    return True


def test_tp_sl_after_partial_close():
    """Test TP/SL triggers correctly after partial close."""
    print("=" * 60)
    print("Test 2: TP/SL After Partial Close")
    print("=" * 60)

    account = VirtualAccount(initial_balance=10000.0)
    simulator = ExecutionSimulator(slippage_percent=0.0, fee_rate=0.0)

    # Open position with TP/SL
    decision = MockDecision("buy", "BTC", target_portion=0.6, leverage=10,
                           take_profit_price=105000.0, stop_loss_price=95000.0)
    trade = simulator.execute_decision(decision, account, 100000.0, 1000)
    account.update_equity({"BTC": 100000.0})

    pos = account.get_position("BTC")
    original_size = pos.size
    print(f"\n[Initial] Position: {original_size:.4f} BTC @ $100,000")
    print(f"          TP: $105,000, SL: $95,000")
    print(f"          Pending orders: {len(account.pending_orders)}")

    # Partial close 50% (simulating profit protection)
    decision = MockDecision("close", "BTC", target_portion=0.5, reason="Profit protection")
    trade = simulator.execute_decision(decision, account, 101000.0, 2000)
    account.update_equity({"BTC": 101000.0})

    pos = account.get_position("BTC")
    remaining_size = pos.size
    print(f"\n[After 50% close] Remaining: {remaining_size:.4f} BTC")
    print(f"                  Expected: {original_size * 0.5:.4f} BTC")
    assert abs(remaining_size - original_size * 0.5) < 0.0001

    # Now trigger TP - should only close remaining position
    print(f"\n[Triggering TP at $105,000]")
    tp_trades = simulator.check_tp_sl_triggers(account, {"BTC": 105000.0}, 3000)

    if tp_trades:
        tp_trade = tp_trades[0]
        print(f"  TP trade size: {tp_trade.size:.4f} BTC")
        print(f"  Expected size: {remaining_size:.4f} BTC (remaining position)")

        # The TP should close only the remaining position, not the original size
        if abs(tp_trade.size - remaining_size) < 0.0001:
            print("  ✅ TP correctly closed only remaining position")
        else:
            print(f"  ❌ ERROR: TP closed {tp_trade.size:.4f} instead of {remaining_size:.4f}")
            return False
    else:
        print("  ❌ ERROR: No TP trade triggered")
        return False

    # Verify position is fully closed
    pos = account.get_position("BTC")
    if pos is None:
        print("\n[Final] Position fully closed ✅")
    else:
        print(f"\n[Final] ❌ Position still exists: {pos.size}")
        return False

    print("Test 2 PASSED ✅\n")
    return True


def test_sl_after_partial_close():
    """Test SL triggers correctly after partial close."""
    print("=" * 60)
    print("Test 3: SL After Partial Close")
    print("=" * 60)

    account = VirtualAccount(initial_balance=10000.0)
    simulator = ExecutionSimulator(slippage_percent=0.0, fee_rate=0.0)

    # Open short position with TP/SL
    decision = MockDecision("sell", "BTC", target_portion=0.6, leverage=10,
                           take_profit_price=95000.0, stop_loss_price=105000.0)
    trade = simulator.execute_decision(decision, account, 100000.0, 1000)
    account.update_equity({"BTC": 100000.0})

    pos = account.get_position("BTC")
    original_size = pos.size
    print(f"\n[Initial] Short position: {original_size:.4f} BTC @ $100,000")

    # Partial close 30%
    decision = MockDecision("close", "BTC", target_portion=0.3)
    trade = simulator.execute_decision(decision, account, 99000.0, 2000)
    account.update_equity({"BTC": 99000.0})

    pos = account.get_position("BTC")
    remaining_size = pos.size
    expected_remaining = original_size * 0.7
    print(f"\n[After 30% close] Remaining: {remaining_size:.4f} BTC")
    assert abs(remaining_size - expected_remaining) < 0.0001

    # Trigger SL
    print(f"\n[Triggering SL at $105,000]")
    sl_trades = simulator.check_tp_sl_triggers(account, {"BTC": 105000.0}, 3000)

    if sl_trades:
        sl_trade = sl_trades[0]
        print(f"  SL trade size: {sl_trade.size:.4f} BTC")
        print(f"  Expected size: {remaining_size:.4f} BTC")

        if abs(sl_trade.size - remaining_size) < 0.0001:
            print("  ✅ SL correctly closed only remaining position")
        else:
            print(f"  ❌ ERROR: SL closed {sl_trade.size:.4f} instead of {remaining_size:.4f}")
            return False
    else:
        print("  ❌ ERROR: No SL trade triggered")
        return False

    print("Test 3 PASSED ✅\n")
    return True


if __name__ == "__main__":
    all_passed = True

    all_passed = test_partial_close() and all_passed
    all_passed = test_tp_sl_after_partial_close() and all_passed
    all_passed = test_sl_after_partial_close() and all_passed

    print("=" * 60)
    if all_passed:
        print("ALL TESTS PASSED ✅")
    else:
        print("SOME TESTS FAILED ❌")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)
