#!/usr/bin/env python3
"""
Test script for Program Trader FULL FLOW.
Tests the complete execution path through program_execution_service.py.

This script:
1. Creates a test Program with a simple BUY strategy
2. Creates a binding to the test account
3. Triggers execution through program_execution_service
4. Verifies the order was placed correctly

Usage:
    docker exec -it hyper-arena-app python /app/backend/scripts/test_program_order.py
"""

import sys
import json
import time

sys.path.insert(0, "/app/backend")

from database.connection import SessionLocal
from database.models import Account, TradingProgram, AccountProgramBinding, ProgramExecutionLog

# ============== Configuration ==============
ACCOUNT_ID = 1  # Deepseek account
SYMBOL = "ETH"
TARGET_PORTION = 0.1  # 10% of balance (minimum allowed)
LEVERAGE = 5
# ===========================================

# Simple test strategy that always returns BUY
# Note: Decision is already available in sandbox, no import needed
TEST_STRATEGY_CODE = '''
class TestStrategy:
    def init(self, params):
        self.symbol = "{symbol}"
        self.portion = {portion}
        self.leverage = {leverage}

    def should_trade(self, data):
        """Test strategy: Always BUY with fixed parameters."""
        price = data.prices.get(self.symbol, 0)
        if price <= 0:
            return Decision(
                operation="hold",
                symbol=self.symbol,
                reason="No price data"
            )

        # Calculate max_price with 0.5% slippage
        max_price = price * 1.005

        return Decision(
            operation="buy",
            symbol=self.symbol,
            target_portion_of_balance=self.portion,
            leverage=self.leverage,
            max_price=max_price,
            time_in_force="Ioc",
            reason="Test order from test_program_order.py"
        )
'''.format(symbol=SYMBOL, portion=TARGET_PORTION, leverage=LEVERAGE)


def cleanup_test_data(db):
    """Remove test program and binding."""
    try:
        # Delete test bindings
        db.query(AccountProgramBinding).filter(
            AccountProgramBinding.program_id.in_(
                db.query(TradingProgram.id).filter(TradingProgram.name == "__TEST_PROGRAM__")
            )
        ).delete(synchronize_session=False)

        # Delete test program
        db.query(TradingProgram).filter(TradingProgram.name == "__TEST_PROGRAM__").delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Cleanup warning: {e}")


def main():
    print("=" * 60)
    print("Program Trader FULL FLOW Test")
    print("=" * 60)

    db = SessionLocal()

    try:
        # Step 1: Verify account exists
        print(f"\n[1] Verifying account {ACCOUNT_ID}...")
        account = db.query(Account).filter(Account.id == ACCOUNT_ID).first()
        if not account:
            print(f"ERROR: Account {ACCOUNT_ID} not found")
            return
        print(f"    Account: {account.name}")

        # Step 2: Cleanup any previous test data
        print(f"\n[2] Cleaning up previous test data...")
        cleanup_test_data(db)
        print("    Done")

        # Step 3: Create test program
        print(f"\n[3] Creating test program...")
        # TradingProgram uses user_id, get it from account
        user_id = account.user_id
        test_program = TradingProgram(
            user_id=user_id,
            name="__TEST_PROGRAM__",
            description="Test program for order execution",
            code=TEST_STRATEGY_CODE,
        )
        db.add(test_program)
        db.commit()
        db.refresh(test_program)
        print(f"    Program ID: {test_program.id}")

        # Step 4: Create binding
        print(f"\n[4] Creating program binding...")
        binding = AccountProgramBinding(
            account_id=ACCOUNT_ID,
            program_id=test_program.id,
            is_active=True,
            signal_pool_ids=json.dumps([]),  # No signal pool for test
        )
        db.add(binding)
        db.commit()
        db.refresh(binding)
        print(f"    Binding ID: {binding.id}")

        # Step 5: Execute through program_execution_service
        print(f"\n[5] Triggering execution through program_execution_service...")
        print(f"    This tests the FULL flow including:")
        print(f"    - get_hyperliquid_client() (correct client creation)")
        print(f"    - DataProvider with real trading_client")
        print(f"    - _handle_decision() with protection logic")
        print(f"    - _execute_buy() with price bounds and IOC->GTC retry")

        from services.program_execution_service import program_execution_service

        # Get count of logs before execution
        logs_before = db.query(ProgramExecutionLog).filter(
            ProgramExecutionLog.binding_id == binding.id
        ).count()

        # Trigger execution - pass db and binding object
        program_execution_service._execute_binding(
            db=db,
            binding=binding,
            symbol=SYMBOL,
            pool={"pool_id": None, "pool_name": "Test"},
            market_data_snapshot={},
            triggered_signals=[],
            trigger_type="signal"
        )

        # Wait for execution to complete
        time.sleep(2)

        # Step 6: Check execution log
        print(f"\n[6] Checking execution log...")
        db.expire_all()  # Refresh from DB

        logs_after = db.query(ProgramExecutionLog).filter(
            ProgramExecutionLog.binding_id == binding.id
        ).order_by(ProgramExecutionLog.id.desc()).all()

        if len(logs_after) > logs_before:
            log = logs_after[0]
            print(f"    Log ID: {log.id}")
            print(f"    Success: {log.success}")
            print(f"    Decision: {log.decision_action} {log.decision_symbol}")
            print(f"    Reason: {log.decision_reason}")

            if log.error_message:
                print(f"    Error: {log.error_message}")

            # Parse market_context to check account data
            if log.market_context:
                ctx = json.loads(log.market_context)
                input_data = ctx.get("input_data", {})
                balance = input_data.get("available_balance", 0)
                print(f"\n    Account Balance: ${balance:,.2f}")

                if balance == 10000.0:
                    print("    WARNING: Balance is $10000 (fallback value)")
                    print("    This means trading_client was None!")
                    print("    TEST FAILED - Client creation bug still exists")
                else:
                    print("    Balance looks correct (not fallback $10000)")
        else:
            print("    ERROR: No execution log created!")

        # Step 7: Cleanup
        print(f"\n[7] Cleaning up test data...")
        cleanup_test_data(db)
        print("    Done")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

    print("\n" + "=" * 60)
    print("Test completed")
    print("=" * 60)


if __name__ == "__main__":
    main()

