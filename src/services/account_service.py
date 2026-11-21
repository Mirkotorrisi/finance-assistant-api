from typing import Any

from sqlalchemy import and_, case, desc, extract, func
from sqlalchemy.orm import Session

from src.database.models import Account, Transaction
from src.repositories.account_repository import AccountRepository
from src.services.investments import investment_texts, not_investment


class AccountService:
    def __init__(self, session: Session):
        self.session = session
        self.account_repo = AccountRepository(session)

    # --- Account Operations ---

    def create_account(self, name: str, account_type: str, currency: str = "EUR", is_active: bool = True, current_balance: float = 0.0) -> dict[str, Any]:
        account = Account(name=name, type=account_type, currency=currency, is_active=is_active, current_balance=current_balance)
        created = self.account_repo.create(account)
        return created.to_dict()

    def _with_balances(self, accounts: list[Account]) -> list[dict[str, Any]]:
        """Account dicts whose ``current_balance`` is what the account holds today (recorded balance plus the
        transactions since, or transactions alone), with ``balance_basis`` saying which."""
        from src.services.net_worth_service import NetWorthService

        cells = NetWorthService(self.session).current_balances(active_only=False)
        out = []
        for acc in accounts:
            data = acc.to_dict()
            cell = cells.get(acc.id) or {"balance": None, "basis": "none"}
            data["current_balance"] = cell["balance"] if cell["balance"] is not None else 0.0
            data["balance_basis"] = cell["basis"]
            out.append(data)
        return out

    def get_account(self, account_id: int) -> dict[str, Any] | None:
        account = self.account_repo.get_by_id(account_id)
        return self._with_balances([account])[0] if account else None

    def list_accounts(self, active_only: bool = True) -> list[dict[str, Any]]:
        return self._with_balances(self.account_repo.list_all(active_only))

    def update_account(self, account_id: int, updates: dict) -> dict[str, Any] | None:
        """Update an account."""
        updated = self.account_repo.update(account_id, updates)
        return updated.to_dict() if updated else None

    def delete_account(self, account_id: int) -> bool:
        """Delete (deactivate) an account."""
        return self.account_repo.delete(account_id)

    def get_account_balance(self, account_id: int) -> float:
        """What the account holds today: its latest recorded balance plus the transactions since, or the sum of
        its transactions when no balance was ever recorded."""
        account = self.account_repo.get_by_id(account_id)
        if account is None:
            return 0.0
        return float(self._with_balances([account])[0]["current_balance"])

    # --- Aggregates from Transactions ---

    def get_total_balance_for_month(self, year: int, month: int) -> float:
        """Get total balance (cumulative) across all accounts up to end of given month."""
        from sqlalchemy import and_, or_
        result = self.session.query(func.sum(Transaction.amount)).filter(
            or_(
                extract('year', Transaction.date) < year,
                and_(
                    extract('year', Transaction.date) == year,
                    extract('month', Transaction.date) <= month
                )
            )
        ).scalar()
        return round(result or 0.0, 2)

    def get_current_total_balance(self) -> float:
        """Get total balance across all accounts by summing all transactions."""
        result = self.session.query(func.sum(Transaction.amount)).scalar()
        return round(result or 0.0, 2)

    def get_total_expenses_for_month(self, year: int, month: int) -> float:
        """Get total expenses for a specific month from transactions (investments are not spending)."""
        result = self.session.query(
            func.sum(func.abs(Transaction.amount))
        ).filter(
            Transaction.amount < 0,
            Transaction.is_transfer.is_(False),
            not_investment(investment_texts(self.session)),
            extract('year', Transaction.date) == year,
            extract('month', Transaction.date) == month
        ).scalar()
        return round(result or 0.0, 2)

    def get_total_income_for_month(self, year: int, month: int) -> float:
        """Get total income for a specific month from transactions."""
        result = self.session.query(func.sum(Transaction.amount)).filter(
            Transaction.amount > 0,
            Transaction.is_transfer.is_(False),
            not_investment(investment_texts(self.session)),
            extract('year', Transaction.date) == year,
            extract('month', Transaction.date) == month
        ).scalar()
        return round(result or 0.0, 2)

    def get_balance_trend(self, account_id: int | None = None, num_months: int = 12) -> list[dict[str, Any]]:
        """Get monthly aggregated balance trend from transactions."""
        counted = and_(Transaction.is_transfer.is_(False), not_investment(investment_texts(self.session)))
        query = self.session.query(
            extract('year', Transaction.date).label('year'),
            extract('month', Transaction.date).label('month'),
            func.sum(case((and_(Transaction.amount > 0, counted), Transaction.amount), else_=0)).label('total_income'),
            func.sum(case((and_(Transaction.amount < 0, counted), func.abs(Transaction.amount)), else_=0)).label('total_expense'),
            func.sum(Transaction.amount).label('net')
        )
        if account_id is not None:
            query = query.filter(Transaction.account_id == account_id)

        rows = query.group_by(
            extract('year', Transaction.date),
            extract('month', Transaction.date)
        ).order_by(
            desc(extract('year', Transaction.date)),
            desc(extract('month', Transaction.date))
        ).limit(num_months).all()

        return [
            {
                "year": int(row.year),
                "month": int(row.month),
                "total_income": round(row.total_income or 0.0, 2),
                "total_expense": round(row.total_expense or 0.0, 2),
                "net": round(row.net or 0.0, 2)
            }
            for row in rows
        ]
