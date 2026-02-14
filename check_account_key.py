#!/usr/bin/env python3
"""
查询 account_id=1 的配置信息
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from database.connection import SessionLocal
from database.models import Account

def main():
    db = SessionLocal()

    try:
        account = db.query(Account).filter(Account.id == 1).first()

        if not account:
            print("❌ Account ID 1 not found")
            return

        print(f"Account ID: {account.id}")
        print(f"Name: {account.name}")
        print(f"Environment: {account.environment}")
        print(f"Wallet Address: {account.wallet_address}")
        print(f"Has Private Key: {'Yes' if account.private_key else 'No'}")

        if account.private_key:
            print(f"Private Key Preview: {account.private_key[:20]}...")
        else:
            print("⚠️  No private key found - cannot place orders")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
