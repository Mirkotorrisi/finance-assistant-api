#!/usr/bin/env python3
"""Manual test script to verify account_id integration in transactions."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.init import init_database, get_db_session
from src.services.transaction_service import TransactionService
from src.services.account_service import AccountService

def test_account_id_integration():
    """Test account_id integration across all transaction operations."""
    
    print("=" * 60)
    print("Testing Account ID Integration in Transactions")
    print("=" * 60)
    
    # Initialize database
    print("\n1. Initializing database...")
    init_database()
    session = get_db_session()
    
    try:
        # Create services
        account_service = AccountService(session)
        transaction_service = TransactionService(session)
        
        # Test 1: Create a test account
        print("\n2. Creating test account...")
        account = account_service.create_account(
            name="Test Account",
            account_type="checking",
            currency="EUR",
            is_active=True
        )
        print(f"   ✓ Created account: {account['name']} (ID: {account['id']})")
        
        # Test 2: Create transaction with account_id
        print("\n3. Creating transaction WITH account_id...")
        transaction_with_account = transaction_service.add_transaction(
            amount=-50.0,
            category="Food",
            description="Groceries",
            account_id=account['id']
        )
        print(f"   ✓ Created transaction ID {transaction_with_account['id']} with account_id={transaction_with_account.get('account_id')}")
        
        # Test 3: Create transaction without account_id
        print("\n4. Creating transaction WITHOUT account_id...")
        transaction_without_account = transaction_service.add_transaction(
            amount=-25.0,
            category="Transport",
            description="Bus ticket"
        )
        print(f"   ✓ Created transaction ID {transaction_without_account['id']} with account_id={transaction_without_account.get('account_id')}")
        
        # Test 4: List transactions filtered by account_id
        print(f"\n5. Listing transactions for account_id={account['id']}...")
        filtered_transactions = transaction_service.list_transactions(account_id=account['id'])
        print(f"   ✓ Found {len(filtered_transactions)} transaction(s) for this account")
        
        # Test 5: List all transactions
        print("\n6. Listing ALL transactions...")
        all_transactions = transaction_service.list_transactions()
        print(f"   ✓ Found {len(all_transactions)} total transaction(s)")
        
        # Test 6: Try to create transaction with invalid account_id
        print("\n7. Testing invalid account_id (should fail)...")
        try:
            invalid_transaction = transaction_service.add_transaction(
                amount=-10.0,
                category="Test",
                description="Should fail",
                account_id=99999
            )
            print("   ✗ FAILED: Should have raised ValueError")
        except ValueError as e:
            print(f"   ✓ Correctly rejected invalid account_id: {e}")
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    test_account_id_integration()
