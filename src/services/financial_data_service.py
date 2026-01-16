"""Service for aggregating financial data for dashboard frontend."""

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from src.database.models import MonthlyAccountSnapshot, Account


class FinancialDataService:
    """Service for aggregating financial data across accounts."""
    
    # Month number to short name mapping
    MONTH_NAMES = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
    }
    
    # Account type categorization
    LIQUIDITY_TYPES = {"checking", "savings", "cash"}
    INVESTMENT_TYPES = {"investment", "brokerage", "retirement"}
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_financial_data(self, year: int) -> Dict[str, Any]:
        """Get aggregated financial data for a specific year.
        
        Args:
            year: The year to retrieve data for
            
        Returns:
            Dictionary containing year, currentNetWorth, netSavings, monthlyData, and accountBreakdown
        """
        # Get all snapshots for the year
        snapshots = self.session.query(MonthlyAccountSnapshot).filter(
            MonthlyAccountSnapshot.year == year
        ).all()
        
        if not snapshots:
            return self._empty_response(year)
        
        # Calculate monthly aggregates
        monthly_data = self._calculate_monthly_data(year)
        
        # Calculate account breakdown (use most recent month data)
        account_breakdown = self._calculate_account_breakdown(year)
        
        # Calculate current net worth (most recent month)
        current_net_worth = self._calculate_current_net_worth(year)
        
        # Calculate net savings (sum of all monthly nets or Dec - Jan starting)
        net_savings = self._calculate_net_savings(monthly_data)
        
        return {
            "year": year,
            "currentNetWorth": current_net_worth,
            "netSavings": net_savings,
            "monthlyData": monthly_data,
            "accountBreakdown": account_breakdown
        }
    
    def _calculate_monthly_data(self, year: int) -> List[Dict[str, Any]]:
        """Calculate monthly aggregated data for all 12 months."""
        monthly_data = []
        
        for month in range(1, 13):
            # Aggregate data for this month across all accounts
            result = self.session.query(
                func.sum(MonthlyAccountSnapshot.ending_balance).label('net_worth'),
                func.sum(MonthlyAccountSnapshot.total_expense).label('expenses'),
                func.sum(MonthlyAccountSnapshot.total_income).label('income')
            ).filter(
                and_(
                    MonthlyAccountSnapshot.year == year,
                    MonthlyAccountSnapshot.month == month
                )
            ).first()
            
            net_worth = result.net_worth or 0.0
            expenses = result.expenses or 0.0
            income = result.income or 0.0
            net = income - expenses
            
            monthly_data.append({
                "month": self.MONTH_NAMES[month],
                "netWorth": round(net_worth, 2),
                "expenses": round(expenses, 2),
                "income": round(income, 2),
                "net": round(net, 2)
            })
        
        return monthly_data
    
    def _calculate_account_breakdown(self, year: int) -> Dict[str, float]:
        """Calculate account breakdown by type for the most recent month with data."""
        # Find the most recent month with data in the year
        max_month_result = self.session.query(
            func.max(MonthlyAccountSnapshot.month)
        ).filter(
            MonthlyAccountSnapshot.year == year
        ).scalar()
        
        if not max_month_result:
            return {"liquidity": 0.0, "investments": 0.0, "otherAssets": 0.0}
        
        # Get all snapshots for the most recent month, joined with Account info
        snapshots = self.session.query(
            MonthlyAccountSnapshot.ending_balance,
            Account.type
        ).join(
            Account, MonthlyAccountSnapshot.account_id == Account.id
        ).filter(
            and_(
                MonthlyAccountSnapshot.year == year,
                MonthlyAccountSnapshot.month == max_month_result
            )
        ).all()
        
        # Categorize by account type
        liquidity = 0.0
        investments = 0.0
        other_assets = 0.0
        
        for balance, account_type in snapshots:
            account_type_lower = account_type.lower()
            if account_type_lower in self.LIQUIDITY_TYPES:
                liquidity += balance
            elif account_type_lower in self.INVESTMENT_TYPES:
                investments += balance
            else:
                other_assets += balance
        
        return {
            "liquidity": round(liquidity, 2),
            "investments": round(investments, 2),
            "otherAssets": round(other_assets, 2)
        }
    
    def _calculate_current_net_worth(self, year: int) -> float:
        """Calculate current net worth (sum of ending balances for most recent month)."""
        # Find the most recent month with data in the year
        max_month_result = self.session.query(
            func.max(MonthlyAccountSnapshot.month)
        ).filter(
            MonthlyAccountSnapshot.year == year
        ).scalar()
        
        if not max_month_result:
            return 0.0
        
        # Sum ending balances for that month
        result = self.session.query(
            func.sum(MonthlyAccountSnapshot.ending_balance)
        ).filter(
            and_(
                MonthlyAccountSnapshot.year == year,
                MonthlyAccountSnapshot.month == max_month_result
            )
        ).scalar()
        
        return round(result or 0.0, 2)
    
    def _calculate_net_savings(self, monthly_data: List[Dict[str, Any]]) -> float:
        """Calculate net savings as sum of all monthly net values."""
        total = sum(month["net"] for month in monthly_data)
        return round(total, 2)
    
    def _empty_response(self, year: int) -> Dict[str, Any]:
        """Return empty response when no data exists for the year."""
        return {
            "year": year,
            "currentNetWorth": 0.0,
            "netSavings": 0.0,
            "monthlyData": [
                {
                    "month": self.MONTH_NAMES[month],
                    "netWorth": 0.0,
                    "expenses": 0.0,
                    "income": 0.0,
                    "net": 0.0
                }
                for month in range(1, 13)
            ],
            "accountBreakdown": {
                "liquidity": 0.0,
                "investments": 0.0,
                "otherAssets": 0.0
            }
        }
