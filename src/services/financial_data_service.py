"""Service for aggregating and providing financial data for dashboard."""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from src.database.models import Account, MonthlyAccountSnapshot
from src.repositories.account_repository import AccountRepository
from src.repositories.snapshot_repository import SnapshotRepository

logger = logging.getLogger(__name__)

# Month names mapping
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Account type categorization
LIQUIDITY_TYPES = {"checking", "savings", "cash"}
INVESTMENT_TYPES = {"investment", "brokerage", "retirement"}
OTHER_ASSET_TYPES = {"other", "asset", "loan"}


class FinancialDataService:
    """Service for aggregating financial data for the dashboard."""
    
    def __init__(self, session: Session):
        self.session = session
        self.account_repo = AccountRepository(session)
        self.snapshot_repo = SnapshotRepository(session)
    
    def get_financial_data_for_year(self, year: int) -> Dict[str, Any]:
        """Get aggregated financial data for a specific year.
        
        Args:
            year: The year to get data for
            
        Returns:
            Dictionary containing:
            - year: The requested year
            - currentNetWorth: Total net worth from most recent account balances
            - netSavings: Total income - total expenses for the year
            - monthlyData: List of monthly aggregated data (all 12 months)
            - accountBreakdown: Categorized account totals
        """
        logger.info(f"Getting financial data for year {year}")
        
        # Get all active accounts
        accounts = self.account_repo.list_all(active_only=True)
        
        # Get monthly data for all 12 months
        monthly_data = self._get_monthly_data(year, accounts)
        
        # Calculate net savings for the year (sum of all monthly net)
        net_savings = sum(month["net"] for month in monthly_data)
        
        # Get current net worth (most recent balances)
        current_net_worth = self.snapshot_repo.get_current_total_balance()
        
        # Get account breakdown by category
        account_breakdown = self._get_account_breakdown(accounts)
        
        return {
            "year": year,
            "currentNetWorth": current_net_worth,
            "netSavings": net_savings,
            "monthlyData": monthly_data,
            "accountBreakdown": account_breakdown
        }
    
    def _get_monthly_data(self, year: int, accounts: List[Account]) -> List[Dict[str, Any]]:
        """Get aggregated data for all 12 months.
        
        Args:
            year: The year to get data for
            accounts: List of all active accounts
            
        Returns:
            List of 12 monthly data dictionaries
        """
        monthly_data = []
        
        for month in range(1, 13):
            # Query aggregated data for this month
            monthly_totals = self.session.query(
                func.sum(MonthlyAccountSnapshot.ending_balance).label('net_worth'),
                func.sum(MonthlyAccountSnapshot.total_expense).label('expenses'),
                func.sum(MonthlyAccountSnapshot.total_income).label('income')
            ).filter(
                and_(
                    MonthlyAccountSnapshot.year == year,
                    MonthlyAccountSnapshot.month == month
                )
            ).first()
            
            # Extract values, defaulting to 0 if no data
            net_worth = monthly_totals.net_worth if monthly_totals.net_worth is not None else 0.0
            expenses = monthly_totals.expenses if monthly_totals.expenses is not None else 0.0
            income = monthly_totals.income if monthly_totals.income is not None else 0.0
            net = income - expenses
            
            monthly_data.append({
                "month": MONTH_NAMES[month - 1],
                "netWorth": net_worth,
                "expenses": expenses,
                "income": income,
                "net": net
            })
        
        return monthly_data
    
    def _get_account_breakdown(self, accounts: List[Account]) -> Dict[str, float]:
        """Get account balances categorized by type.
        
        Args:
            accounts: List of all active accounts
            
        Returns:
            Dictionary with liquidity, investments, and otherAssets totals
        """
        breakdown = {
            "liquidity": 0.0,
            "investments": 0.0,
            "otherAssets": 0.0
        }
        
        # Get the most recent balance for each account
        for account in accounts:
            # Get the most recent snapshot for this account
            recent_snapshot = self.session.query(MonthlyAccountSnapshot).filter(
                MonthlyAccountSnapshot.account_id == account.id
            ).order_by(
                MonthlyAccountSnapshot.year.desc(),
                MonthlyAccountSnapshot.month.desc()
            ).first()
            
            if recent_snapshot and recent_snapshot.ending_balance > 0:
                balance = recent_snapshot.ending_balance
                account_type = account.type.lower()
                
                if account_type in LIQUIDITY_TYPES:
                    breakdown["liquidity"] += balance
                elif account_type in INVESTMENT_TYPES:
                    breakdown["investments"] += balance
                elif account_type in OTHER_ASSET_TYPES:
                    breakdown["otherAssets"] += balance
                else:
                    # Default unknown types to otherAssets
                    logger.warning(f"Unknown account type '{account_type}' for account {account.id}, categorizing as otherAssets")
                    breakdown["otherAssets"] += balance
        
        return breakdown
