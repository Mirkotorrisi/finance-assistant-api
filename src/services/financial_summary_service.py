"""Service for UI-driven financial aggregation and summary data."""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract, case
from datetime import datetime
from src.database.models import Account, Transaction, Category


class FinancialSummaryService:
    """Service for aggregating financial data for UI components."""
    
    # Account type categorization
    LIQUIDITY_TYPES = {"checking", "savings", "cash"}
    INVESTMENT_TYPES = {"investment", "brokerage", "retirement"}
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_monthly_summary(self, month: str) -> Dict[str, Any]:
        """Get monthly financial summary for a specific month.
        
        Args:
            month: Month in format "YYYY-MM" (e.g., "2024-01")
            
        Returns:
            Dictionary containing:
            - month: Month string
            - income: Total income for the month
            - expenses: Total expenses for the month
            - net: Net income (income - expenses)
            - top_categories: List of top spending categories with amounts
        """
        try:
            # Parse the month string
            year, month_num = month.split("-")
            year = int(year)
            month_num = int(month_num)
        except (ValueError, AttributeError):
            raise ValueError("Invalid month format. Use 'YYYY-MM' (e.g., '2024-01')")
        
        # Get aggregated income and expenses from transactions
        result = self.session.query(
            func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)).label('income'),
            func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)).label('expenses')
        ).filter(
            and_(
                extract('year', Transaction.date) == year,
                extract('month', Transaction.date) == month_num
            )
        ).first()
        
        income = result.income or 0.0
        expenses = result.expenses or 0.0
        net = income - expenses
        
        # Get top spending categories from transactions
        top_categories = self._get_top_categories(year, month_num, limit=5)
        
        return {
            "month": month,
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "net": round(net, 2),
            "top_categories": top_categories
        }
    
    def get_spending_distribution(
        self,
        start_date: str,
        end_date: str,
        group_by: str = "category"
    ) -> Dict[str, Any]:
        """Get spending distribution for a date range.
        
        Args:
            start_date: Start date in format "YYYY-MM-DD"
            end_date: End date in format "YYYY-MM-DD"
            group_by: Grouping method - "category" or "account" (default: "category")
            
        Returns:
            Dictionary containing:
            - start_date: Start date
            - end_date: End date
            - group_by: Grouping method used
            - total_amount: Total spending amount
            - distribution: List of items with amount, percent, count
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            raise ValueError("Invalid date format. Use 'YYYY-MM-DD'")
        
        if group_by not in ["category", "account"]:
            raise ValueError("group_by must be 'category' or 'account'")
        
        if group_by == "category":
            # Query transactions for the date range (only expenses - negative amounts)
            query = self.session.query(Transaction).filter(
                and_(
                    Transaction.date >= start,
                    Transaction.date <= end,
                    Transaction.amount < 0  # Only expenses
                )
            )
            
            transactions = query.all()
            
            if not transactions:
                return {
                    "start_date": start_date,
                    "end_date": end_date,
                    "group_by": group_by,
                    "total_amount": 0.0,
                    "distribution": []
                }
            
            # Calculate distribution by category
            distribution_dict = {}
            total_amount = 0.0
            
            for txn in transactions:
                amount = abs(txn.amount)
                total_amount += amount
                key = txn.category
                
                if key not in distribution_dict:
                    distribution_dict[key] = {"amount": 0.0, "count": 0}
                
                distribution_dict[key]["amount"] += amount
                distribution_dict[key]["count"] += 1
        else:  # group_by == "account"
            # Query transactions with account names for better UX
            query = self.session.query(
                Transaction,
                Account.name
            ).outerjoin(
                Account, Transaction.account_id == Account.id
            ).filter(
                and_(
                    Transaction.date >= start,
                    Transaction.date <= end,
                    Transaction.amount < 0  # Only expenses
                )
            )
            
            results = query.all()
            
            if not results:
                return {
                    "start_date": start_date,
                    "end_date": end_date,
                    "group_by": group_by,
                    "total_amount": 0.0,
                    "distribution": []
                }
            
            # Calculate distribution by account
            distribution_dict = {}
            total_amount = 0.0
            
            for txn, account_name in results:
                amount = abs(txn.amount)
                total_amount += amount
                key = account_name if account_name else "No Account"
                
                if key not in distribution_dict:
                    distribution_dict[key] = {"amount": 0.0, "count": 0}
                
                distribution_dict[key]["amount"] += amount
                distribution_dict[key]["count"] += 1
        
        # Convert to list and calculate percentages
        distribution = []
        for key, data in distribution_dict.items():
            percent = (data["amount"] / total_amount * 100) if total_amount > 0 else 0
            distribution.append({
                "name": key,
                "amount": round(data["amount"], 2),
                "percent": round(percent, 2),
                "count": data["count"]
            })
        
        # Sort by amount descending
        distribution.sort(key=lambda x: x["amount"], reverse=True)
        
        return {
            "start_date": start_date,
            "end_date": end_date,
            "group_by": group_by,
            "total_amount": round(total_amount, 2),
            "distribution": distribution
        }
    
    def get_account_breakdown(self) -> Dict[str, Any]:
        """Get current account breakdown by type.
        
        Returns:
            Dictionary containing:
            - total_balance: Total balance across all accounts
            - by_type: Breakdown by account type (liquidity, investments, other)
            - accounts: List of individual account balances with percentages
        """
        # For each active account, sum all transactions to get current balance
        account_balances = self.session.query(
            Account.id,
            Account.name,
            Account.type,
            Account.currency,
            func.coalesce(func.sum(Transaction.amount), 0.0).label('balance')
        ).outerjoin(
            Transaction, Account.id == Transaction.account_id
        ).filter(
            Account.is_active
        ).group_by(Account.id, Account.name, Account.type, Account.currency).all()

        if not account_balances:
            return {
                "total_balance": 0.0,
                "by_type": {
                    "liquidity": {"amount": 0.0, "percent": 0.0},
                    "investments": {"amount": 0.0, "percent": 0.0},
                    "other": {"amount": 0.0, "percent": 0.0}
                },
                "accounts": []
            }
        
        # Calculate totals
        total_balance = sum(row.balance for row in account_balances)
        
        # Categorize by type
        type_breakdown = {
            "liquidity": 0.0,
            "investments": 0.0,
            "other": 0.0
        }
        
        accounts_list = []
        
        for row in account_balances:
            account_type_lower = row.type.lower()
            balance = row.balance
            
            # Categorize
            if account_type_lower in self.LIQUIDITY_TYPES:
                type_breakdown["liquidity"] += balance
                category = "liquidity"
            elif account_type_lower in self.INVESTMENT_TYPES:
                type_breakdown["investments"] += balance
                category = "investments"
            else:
                type_breakdown["other"] += balance
                category = "other"
            
            # Calculate percentage
            percent = (balance / total_balance * 100) if total_balance > 0 else 0
            
            accounts_list.append({
                "account_id": row.id,
                "name": row.name,
                "type": row.type,
                "category": category,
                "balance": round(balance, 2),
                "percent": round(percent, 2),
                "currency": row.currency
            })
        
        # Sort accounts by balance descending
        accounts_list.sort(key=lambda x: x["balance"], reverse=True)
        
        # Prepare by_type breakdown with percentages
        by_type = {}
        for type_name, amount in type_breakdown.items():
            percent = (amount / total_balance * 100) if total_balance > 0 else 0
            by_type[type_name] = {
                "amount": round(amount, 2),
                "percent": round(percent, 2)
            }
        
        return {
            "total_balance": round(total_balance, 2),
            "by_type": by_type,
            "accounts": accounts_list
        }
    
    def _get_top_categories(self, year: int, month: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top spending categories for a specific month.
        
        Args:
            year: Year
            month: Month (1-12)
            limit: Number of top categories to return
            
        Returns:
            List of categories with amounts, sorted by amount descending
        """
        # Query transactions for the month (only expenses)
        result = self.session.query(
            Transaction.category,
            func.sum(func.abs(Transaction.amount)).label('total_amount'),
            func.count(Transaction.id).label('count')
        ).filter(
            and_(
                extract('year', Transaction.date) == year,
                extract('month', Transaction.date) == month,
                Transaction.amount < 0  # Only expenses
            )
        ).group_by(
            Transaction.category
        ).order_by(
            func.sum(func.abs(Transaction.amount)).desc()
        ).limit(limit).all()
        
        return [
            {
                "category": row.category,
                "amount": round(row.total_amount, 2),
                "count": row.count
            }
            for row in result
        ]
