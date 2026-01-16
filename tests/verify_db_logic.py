import sys
import os
import datetime
# Add project root to path
sys.path.append(os.getcwd())

from src.business_logic.mcp_database import FinanceMCPDatabase
from src.database.init import init_database, get_db_session, close_database
from src.database.models import Base

def test_crud_operations():
    print("Initializing database...")
    # Force SQLite in-memory for testing by invalidating DB url or just relying on fallback if configured
    # Or just run against whatever is configured. Ideally we want a clean state.
    # The init_database tries to connect to PG, if fails falls back to SQLite.
    init_database()
    
    db_session = get_db_session()
    mcp = FinanceMCPDatabase(db_session)
    
    print("\n[TestCase] Create Transaction")
    t1 = mcp.add_transaction(
        amount=-50.0,
        category="Food",
        description="Lunch",
        date=datetime.date.today().isoformat()
    )
    print(f"Created: {t1}")
    assert t1['id'] is not None
    assert t1['amount'] == -50.0
    
    print("\n[TestCase] Read Transaction (List)")
    txs = mcp.list_transactions(category="Food")
    print(f"List Result: {txs}")
    assert len(txs) >= 1
    found = False
    for t in txs:
        if t['id'] == t1['id']:
            found = True
            break
    assert found
    
    print("\n[TestCase] Update Transaction")
    update_data = {"amount": -60.0, "description": "Big Lunch"}
    updated_t1 = mcp.update_transaction(t1['id'], update_data)
    print(f"Updated: {updated_t1}")
    assert updated_t1['amount'] == -60.0
    assert updated_t1['description'] == "Big Lunch"
    
    # Verify update persisted
    txs_after = mcp.list_transactions()
    reloaded = next(t for t in txs_after if t['id'] == t1['id'])
    assert reloaded['amount'] == -60.0
    
    print("\n[TestCase] Delete Transaction")
    success = mcp.delete_transaction(t1['id'])
    print(f"Delete Success: {success}")
    assert success is True
    
    # Verify deletion
    txs_final = mcp.list_transactions()
    deleted = next((t for t in txs_final if t['id'] == t1['id']), None)
    assert deleted is None
    
    print("\n[TestCase] Get Balance")
    # Add a fresh transaction to check balance
    mcp.add_transaction(-100, "Rent", "Rent Payment")
    balance = mcp.get_balance()
    print(f"Balance: {balance}")
    # Note: balance depends on existing data in DB if using persistent DB
    
    print("\nALL CRUD TESTS PASSED")
    mcp.close()

if __name__ == "__main__":
    test_crud_operations()
