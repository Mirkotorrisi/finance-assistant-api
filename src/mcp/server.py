from typing import List, Optional
import json
from mcp.server.fastmcp import FastMCP
from src.services.transaction_service import TransactionService
from src.services.account_service import AccountService
from src.services.financial_summary_service import FinancialSummaryService
from src.database.init import get_db_session, init_database

# Initialize FastMCP Server
mcp = FastMCP("Finance Assistant MCP")

def get_transaction_service():
    session = get_db_session()
    return TransactionService(session), session

def get_account_service():
    session = get_db_session()
    return AccountService(session), session

def get_financial_summary_service():
    session = get_db_session()
    return FinancialSummaryService(session), session

@mcp.tool()
def list_transactions(category: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, account_id: Optional[int] = None) -> str:
    """List financial transactions with optional filters.
    
    Args:
        category: Filter by category name
        start_date: Filter by start date (YYYY-MM-DD)
        end_date: Filter by end date (YYYY-MM-DD)
        account_id: Filter by account ID
    """
    service, session = get_transaction_service()
    try:
        results = service.list_transactions(category, start_date, end_date, account_id)
        return json.dumps(results, default=str)
    finally:
        session.close()

@mcp.tool()
def add_transaction(amount: float, category: str, description: str, date: str = None, currency: str = "EUR", account_id: Optional[int] = None) -> str:
    """Add a new financial transaction. If positive is an income, if negative is an expense.
    
    Args:
        amount: Transaction amount (negative for expense, positive for income)
        category: Category of the transaction
        description: Description of the transaction
        date: Date of transaction (YYYY-MM-DD), defaults to today
        currency: Currency code (default: EUR)
        account_id: Optional account ID to associate with the transaction
    """
    service, session = get_transaction_service()
    try:
        result = service.add_transaction(amount, category, description, date, currency, account_id)
        return json.dumps(result, default=str)
    except ValueError as e:
        return json.dumps({"error": str(e)}, default=str)
    finally:
        session.close()

@mcp.tool()
def update_transaction(transaction_id: int, amount: Optional[float] = None, category: Optional[str] = None, description: Optional[str] = None, date: Optional[str] = None, account_id: Optional[int] = None) -> str:
    """Update an existing transaction.
    
    Args:
        transaction_id: ID of the transaction to update
        amount: New amount
        category: New category
        description: New description
        date: New date
        account_id: New account ID
    """
    service, session = get_transaction_service()
    updates = {}
    if amount is not None: updates['amount'] = amount
    if category is not None: updates['category'] = category
    if description is not None: updates['description'] = description
    if date is not None: updates['date'] = date
    if account_id is not None: updates['account_id'] = account_id
    
    try:
        result = service.update_transaction(transaction_id, updates)
        if result:
            return json.dumps(result, default=str)
        return "Transaction not found"
    except ValueError as e:
        return json.dumps({"error": str(e)}, default=str)
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
    """Get the current total balance by summing all transactions."""
    service, session = get_account_service()
    try:
        balance = service.get_current_total_balance()
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

@mcp.tool()
def get_monthly_summary(month: str) -> str:
    """Get monthly financial summary including income, expenses, net, and top categories.
    
    This tool provides chart-ready data for SummaryTable components in the generative UI.
    Returns structured JSON with income, expenses, net income, and top spending categories.
    
    Args:
        month: Month in format "YYYY-MM" (e.g., "2024-01")
        
    Returns:
        JSON string containing monthly summary data
    """
    service, session = get_financial_summary_service()
    try:
        result = service.get_monthly_summary(month)
        return json.dumps(result, default=str)
    except ValueError as e:
        return json.dumps({"error": str(e)}, default=str)
    finally:
        session.close()

@mcp.tool()
def get_spending_distribution(start_date: str, end_date: str, group_by: str = "category") -> str:
    """Get spending distribution breakdown for a date range.
    
    This tool provides chart-ready data for bubble/pie chart components in the generative UI.
    Returns category or account breakdown with amounts, percentages, and transaction counts.
    
    Args:
        start_date: Start date in format "YYYY-MM-DD"
        end_date: End date in format "YYYY-MM-DD"
        group_by: Grouping method - "category" or "account" (default: "category")
        
    Returns:
        JSON string containing spending distribution data
    """
    service, session = get_financial_summary_service()
    try:
        result = service.get_spending_distribution(start_date, end_date, group_by)
        return json.dumps(result, default=str)
    except ValueError as e:
        return json.dumps({"error": str(e)}, default=str)
    finally:
        session.close()

@mcp.tool()
def get_account_breakdown() -> str:
    """Get current account breakdown by type with balances and percentages.
    
    This tool provides chart-ready data for account breakdown visualization in the generative UI.
    Returns total balance, breakdown by type (liquidity/investments/other), and individual
    account details with percentages.
    
    Returns:
        JSON string containing account breakdown data
    """
    service, session = get_financial_summary_service()
    try:
        result = service.get_account_breakdown()
        return json.dumps(result, default=str)
    finally:
        session.close()

if __name__ == "__main__":
    # Ensure database is initialized
    init_database()
    mcp.run(transport="sse")
