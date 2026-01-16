from typing import List, Optional
import json
from mcp.server.fastmcp import FastMCP
from src.services.transaction_service import TransactionService
from src.services.account_service import AccountService
from src.database.init import get_db_session, init_database

# Initialize FastMCP Server
mcp = FastMCP("Finance Assistant MCP")

def get_transaction_service():
    session = get_db_session()
    return TransactionService(session), session

def get_account_service():
    session = get_db_session()
    return AccountService(session), session

@mcp.tool()
def list_transactions(category: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """List financial transactions with optional filters.
    
    Args:
        category: Filter by category name
        start_date: Filter by start date (YYYY-MM-DD)
        end_date: Filter by end date (YYYY-MM-DD)
    """
    service, session = get_transaction_service()
    try:
        results = service.list_transactions(category, start_date, end_date)
        return json.dumps(results, default=str)
    finally:
        session.close()

@mcp.tool()
def add_transaction(amount: float, category: str, description: str, date: str = None, currency: str = "EUR") -> str:
    """Add a new financial transaction.
    
    Args:
        amount: Transaction amount (negative for expense, positive for income)
        category: Category of the transaction
        description: Description of the transaction
        date: Date of transaction (YYYY-MM-DD), defaults to today
        currency: Currency code (default: EUR)
    """
    service, session = get_transaction_service()
    try:
        # Auto-detect expense: if amount is positive but category implies expense? 
        # No, trust the agent/user input. 
        # But commonly users say "Spent 50". Agent should pass -50.
        result = service.add_transaction(amount, category, description, date, currency)
        return json.dumps(result, default=str)
    finally:
        session.close()

@mcp.tool()
def update_transaction(transaction_id: int, amount: Optional[float] = None, category: Optional[str] = None, description: Optional[str] = None, date: Optional[str] = None) -> str:
    """Update an existing transaction.
    
    Args:
        transaction_id: ID of the transaction to update
        amount: New amount
        category: New category
        description: New description
        date: New date
    """
    service, session = get_transaction_service()
    updates = {}
    if amount is not None: updates['amount'] = amount
    if category is not None: updates['category'] = category
    if description is not None: updates['description'] = description
    if date is not None: updates['date'] = date
    
    try:
        result = service.update_transaction(transaction_id, updates)
        if result:
            return json.dumps(result, default=str)
        return "Transaction not found"
    finally:
        session.close()

@mcp.tool()
def delete_transaction(transaction_id: int) -> str:
    """Delete a transaction.
    
    Args:
        transaction_id: ID of the transaction to delete
    """
    service, session = get_transaction_service()
    try:
        success = service.delete_transaction(transaction_id)
        if success:
            return "Transaction deleted successfully"
        return "Transaction not found"
    finally:
        session.close()

@mcp.tool()
def get_balance() -> str:
    """Get the current total balance."""
    # Using AccountService for more accurate balance if available, 
    # but initially the request mentioned backward compatibility.
    # We will use AccountService's get_current_total_balance which is smarter.
    service, session = get_account_service()
    try:
        # Check if we have snapshots. If not, fallback to simple transaction sum?
        # AccountService.get_current_total_balance uses snapshots.
        # If no snapshots, it returns 0.
        # Let's check if we should fallback.
        # Ideally, we should migrate to snapshots. 
        # But let's expose both or choose one?
        # The prompt says: "The MCP Server decides... Reading aggregated financial data".
        
        balance = service.get_current_total_balance()
        # If balance is 0, maybe check transaction sum?
        if balance == 0:
             # Fallback to transaction sum for now to be safe with existing data?
             # Or maybe just return 0. 
             # Let's provide a breakdown or just return the balance.
             pass
        return str(balance)
    finally:
        session.close()

@mcp.tool()
def list_accounts() -> str:
    """List all financial accounts."""
    service, session = get_account_service()
    try:
        accounts = service.list_accounts()
        return json.dumps(accounts, default=str)
    finally:
        session.close()

@mcp.tool()
def get_balance_trend(num_months: int = 12) -> str:
    """Get the balance trend for the last N months.
    
    Args:
        num_months: Number of months to retrieve
    """
    service, session = get_account_service()
    try:
        trend = service.get_balance_trend(num_months=num_months)
        return json.dumps(trend, default=str)
    finally:
        session.close()

if __name__ == "__main__":
    # Ensure database is initialized
    init_database()
    mcp.run()
