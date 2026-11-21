"""Service for aggregating financial data for dashboard frontend.

Balances come from ``NetWorthService`` (recorded balances plus the transactions since), the same figure the
dashboard total and the account list show; only income and expenses are summed from the transactions here.
"""

from datetime import date
from typing import Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract, case

from src.database.models import Account, Transaction
from src.services.investments import investment_texts, not_investment
from src.services.net_worth_service import VALUATION_TYPES, NetWorthService


class FinancialDataService:
    """Service for aggregating financial data across accounts."""

    # Month number to short name mapping
    MONTH_NAMES = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
    }

    # Account type categorization
    LIQUIDITY_TYPES = {"checking", "savings", "cash"}
    INVESTMENT_TYPES = VALUATION_TYPES  # the accounts net worth counts as "invested"

    def __init__(self, session: Session):
        self.session = session

    def get_financial_data(self, year: int) -> Dict[str, Any]:
        """Get aggregated financial data for a specific year.

        Returns:
            Dictionary containing year, currentNetWorth, netSavings, monthlyData, and accountBreakdown
        """
        last_month = self.session.query(func.max(extract("month", Transaction.date))).filter(
            extract("year", Transaction.date) == year
        ).scalar()
        if not last_month:
            return self._empty_response(year)
        last_month = int(last_month)

        flows = self._monthly_flows(year)
        net_worth = NetWorthService(self.session).net_worth(start_month=f"{year:04d}-01", end_month=f"{year:04d}-12")
        months = {m["month"]: m for m in net_worth["months"]}
        accounts = {a.id: a for a in self.session.query(Account).all()}

        monthly_data = []
        for month in range(1, 13):
            income, expenses = flows.get(month, (0.0, 0.0))
            cell = months.get(f"{year:04d}-{month:02d}")
            monthly_data.append({
                "month": self.MONTH_NAMES[month],
                "netWorth": round(cell["total"], 2) if cell else 0.0,
                "expenses": round(expenses, 2),
                "income": round(income, 2),
                "net": round(income - expenses, 2),
            })

        # the most recent month of the year with data: today's balances for the current year, month-end otherwise
        if (year, last_month) >= (date.today().year, date.today().month):
            cells = NetWorthService(self.session).current_balances(active_only=False)
            current_net_worth = NetWorthService(self.session).total_balance()["balance"]
        else:
            cell = months.get(f"{year:04d}-{last_month:02d}") or {"balances": {}, "total": 0.0}
            cells = {int(k): v for k, v in cell["balances"].items()}
            current_net_worth = cell["total"]

        return {
            "year": year,
            "currentNetWorth": round(current_net_worth, 2),
            "netSavings": self._calculate_net_savings(monthly_data),
            "monthlyData": monthly_data,
            "accountBreakdown": self._breakdown(cells, accounts),
        }

    def _monthly_flows(self, year: int) -> Dict[int, tuple]:
        """(income, expenses) per month of ``year`` in one query; transfers and investments are not flows."""
        counted = and_(Transaction.is_transfer.is_(False), not_investment(investment_texts(self.session)))
        month = extract("month", Transaction.date)
        rows = (
            self.session.query(
                month.label("month"),
                func.sum(case((and_(Transaction.amount > 0, counted), Transaction.amount), else_=0)).label("income"),
                func.sum(case((and_(Transaction.amount < 0, counted), func.abs(Transaction.amount)), else_=0)).label("expenses"),
            )
            .filter(extract("year", Transaction.date) == year)
            .group_by(month)
            .all()
        )
        return {int(r.month): (float(r.income or 0.0), float(r.expenses or 0.0)) for r in rows}

    def _breakdown(self, cells: Dict[int, Dict[str, Any]], accounts: Dict[int, Account]) -> Dict[str, float]:
        liquidity = investments = other_assets = 0.0
        for account_id, cell in cells.items():
            account = accounts.get(account_id)
            balance = cell.get("balance")
            if account is None or balance is None:
                continue
            account_type = (account.type or "").lower()
            if account_type in self.LIQUIDITY_TYPES:
                liquidity += balance
            elif account_type in self.INVESTMENT_TYPES:
                investments += balance
            else:
                other_assets += balance
        return {"liquidity": round(liquidity, 2), "investments": round(investments, 2), "otherAssets": round(other_assets, 2)}

    def _calculate_net_savings(self, monthly_data: List[Dict[str, Any]]) -> float:
        """Calculate net savings as sum of all monthly net values."""
        return round(sum(month["net"] for month in monthly_data), 2)

    def _empty_response(self, year: int) -> Dict[str, Any]:
        """Return empty response when no data exists for the year."""
        return {
            "year": year,
            "currentNetWorth": 0.0,
            "netSavings": 0.0,
            "monthlyData": [
                {"month": self.MONTH_NAMES[month], "netWorth": 0.0, "expenses": 0.0, "income": 0.0, "net": 0.0}
                for month in range(1, 13)
            ],
            "accountBreakdown": {"liquidity": 0.0, "investments": 0.0, "otherAssets": 0.0},
        }
