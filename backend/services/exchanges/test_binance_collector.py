"""
Test script for Binance data collector.
Run inside container: python -m services.exchanges.test_binance_collector
"""

import sys
import time
sys.path.insert(0, "/app/backend")

from services.exchanges.binance_collector import binance_collector


def test_collector():
    """Test the Binance collector start/stop cycle"""
    print("=== Testing Binance Collector ===")

    try:
        # Start collector with test symbols
        print("1. Starting collector with BTC, ETH...")
        binance_collector.start(symbols=["BTC", "ETH"])

        # Wait for initial collection
        print("2. Waiting 10 seconds for data collection...")
        time.sleep(10)

        # Check scheduler jobs
        print("3. Checking scheduled jobs...")
        if binance_collector.scheduler:
            jobs = binance_collector.scheduler.get_jobs()
            print(f"   Active jobs: {len(jobs)}")
            for job in jobs:
                print(f"   - {job.id}: next run at {job.next_run_time}")

        # Stop collector
        print("4. Stopping collector...")
        binance_collector.stop()

        print("\nCollector test PASSED!")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        binance_collector.stop()
        return False


if __name__ == "__main__":
    success = test_collector()
    sys.exit(0 if success else 1)
