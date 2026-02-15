"""Financial Summary Service for aggregated financial data."""

from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from src.database.models import Transaction, Account
from src.services.account_service import AccountService


class FinancialSummaryService:
    """Service for generating financial summaries and breakdowns."""
    
    def __init__(self, session: Session):
        """Initialize the FinancialSummaryService.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.account_service = AccountService(session)
    
    def get_monthly_summary(self, month: str) -> Dict[str, Any]:
        """Get aggregated monthly financial summary.
        
        Returns aggregated monthly financial data for SummaryTable component.
        
        Args:
            month: String in YYYY-MM format (e.g., "2026-02")
            
        Returns:
            Dictionary containing monthly summary with schema:
            {
                "month": "2026-02",
                "income": 5000.00,
                "expenses": 3200.00,
                "net": 1800.00,
                "top_categories": [
                    {"name": "Food", "amount": 800.00, "count": 45},
                    {"name": "Transport", "amount": 500.00, "count": 20}
                ],
                "accounts": [
                    {"id": 1, "name": "Bank Account", "balance": 15000.00}
                ]
            }
        """
        # Parse month string
        try:
            year, month_num = month.split("-")
            year = int(year)
            month_num = int(month_num)
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid month format: {month}. Expected YYYY-MM format.")
        
        if month_num < 1 or month_num > 12:
            raise ValueError(f"Invalid month number: {month_num}. Must be between 1 and 12.")
        
        # Query transactions for the given month
        transactions = self.session.query(Transaction).filter(
            extract('year', Transaction.date) == year,
            extract('month', Transaction.date) == month_num
        ).all()
        
        # Calculate totals
        income = sum(t.amount for t in transactions if t.amount > 0)
        expenses = sum(abs(t.amount) for t in transactions if t.amount < 0)
        net = income - expenses
        
        # Group by category and calculate
        category_data = {}
        for t in transactions:
            if t.amount < 0:  # Only count expenses for categories
                category = t.category
                if category not in category_data:
                    category_data[category] = {"amount": 0.0, "count": 0}
                category_data[category]["amount"] += abs(t.amount)
                category_data[category]["count"] += 1
        
        # Sort categories by amount and take top 5
        top_categories = [
            {"name": cat, "amount": data["amount"], "count": data["count"]}
            for cat, data in sorted(
                category_data.items(),
                key=lambda x: x[1]["amount"],
                reverse=True
            )[:5]
        ]
        
        # Get current account balances
        accounts = self.account_service.list_accounts(active_only=True)
        account_balances = []
        for account in accounts:
            balance = self.account_service.get_account_balance(account["id"])
            account_balances.append({
                "id": account["id"],
                "name": account["name"],
                "balance": balance
            })
        
        return {
            "month": month,
            "income": income,
            "expenses": expenses,
            "net": net,
            "top_categories": top_categories,
            "accounts": account_balances
        }
    
    def get_spending_distribution(
        self,
        start_date: str,
        end_date: str,
        group_by: str = "category"
    ) -> List[Dict[str, Any]]:
        """Get spending breakdown for bubble/pie charts.
        
        Args:
            start_date: String in YYYY-MM-DD format
            end_date: String in YYYY-MM-DD format
            group_by: "category" or "account" (default: "category")
            
        Returns:
            List of dictionaries with schema:
            [
                {"name": "Food", "amount": 1200.00, "percentage": 37.5, "count": 120},
                {"name": "Transport", "amount": 800.00, "percentage": 25.0, "count": 45}
            ]
        """
        # Validate group_by parameter
        if group_by not in ["category", "account"]:
            raise ValueError(f"Invalid group_by parameter: {group_by}. Must be 'category' or 'account'.")
        
        # Parse date strings
        try:
            start_date_obj = datetime.fromisoformat(start_date).date()
            end_date_obj = datetime.fromisoformat(end_date).date()
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid date format. Expected YYYY-MM-DD format. Error: {e}")
        
        # Query transactions in date range (only expenses)
        transactions = self.session.query(Transaction).filter(
            Transaction.date >= start_date_obj,
            Transaction.date <= end_date_obj,
            Transaction.amount < 0  # Only expenses
        ).all()
        
        if not transactions:
            return []
        
        # Group by category or account
        grouped_data = {}
        
        if group_by == "category":
            for t in transactions:
                category = t.category
                if category not in grouped_data:
                    grouped_data[category] = {"amount": 0.0, "count": 0}
                grouped_data[category]["amount"] += abs(t.amount)
                grouped_data[category]["count"] += 1
        else:  # group_by == "account"
            # Get account names
            accounts = {acc["id"]: acc["name"] for acc in self.account_service.list_accounts(active_only=False)}
            
            for t in transactions:
                if t.account_id is not None:
                    account_name = accounts.get(t.account_id, f"Account {t.account_id}")
                else:
                    account_name = "Unassigned"
                
                if account_name not in grouped_data:
                    grouped_data[account_name] = {"amount": 0.0, "count": 0}
                grouped_data[account_name]["amount"] += abs(t.amount)
                grouped_data[account_name]["count"] += 1
        
        # Calculate total for percentages
        total_amount = sum(data["amount"] for data in grouped_data.values())
        
        # Build result list with percentages
        result = []
        for name, data in sorted(grouped_data.items(), key=lambda x: x[1]["amount"], reverse=True):
            percentage = (data["amount"] / total_amount * 100) if total_amount > 0 else 0.0
            result.append({
                "name": name,
                "amount": data["amount"],
                "percentage": round(percentage, 2),
                "count": data["count"]
            })
        
        return result
    
    def get_account_breakdown(self) -> List[Dict[str, Any]]:
        """Get current balance breakdown by account.
        
        Returns current balance breakdown by account for stacked/donut charts.
        
        Returns:
            List of dictionaries with schema:
            [
                {
                    "account_id": 1,
                    "account_name": "Bank Account",
                    "balance": 15000.00,
                    "percentage": 75.0,
                    "currency": "EUR"
                }
            ]
        """
        # Get all active accounts
        accounts = self.account_service.list_accounts(active_only=True)
        
        if not accounts:
            return []
        
        # Get balances for each account
        account_data = []
        total_balance = 0.0
        
        for account in accounts:
            balance = self.account_service.get_account_balance(account["id"])
            if balance > 0:  # Only include accounts with positive balance
                account_data.append({
                    "account_id": account["id"],
                    "account_name": account["name"],
                    "balance": balance,
                    "currency": account.get("currency", "EUR")
                })
                total_balance += balance
        
        # Calculate percentages
        for account in account_data:
            percentage = (account["balance"] / total_balance * 100) if total_balance > 0 else 0.0
            account["percentage"] = round(percentage, 2)
        
        # Sort by balance descending
        account_data.sort(key=lambda x: x["balance"], reverse=True)
        
        return account_data
