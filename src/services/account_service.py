from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case, desc
from src.database.models import Account, Transaction
from src.repositories.account_repository import AccountRepository

class AccountService:
    def __init__(self, session: Session):
        self.session = session
        self.account_repo = AccountRepository(session)

    # --- Account Operations ---

    def create_account(self, name: str, account_type: str, currency: str = "EUR", is_active: bool = True, current_balance: float = 0.0) -> Dict[str, Any]:
        account = Account(name=name, type=account_type, currency=currency, is_active=is_active, current_balance=current_balance)
        created = self.account_repo.create(account)
        return created.to_dict()

    def get_account(self, account_id: int) -> Optional[Dict[str, Any]]:
        account = self.account_repo.get_by_id(account_id)
        return account.to_dict() if account else None

    def list_accounts(self, active_only: bool = True) -> List[Dict[str, Any]]:
        accounts = self.account_repo.list_all(active_only)
        return [acc.to_dict() for acc in accounts]

    def update_account(self, account_id: int, updates: dict) -> Optional[Dict[str, Any]]:
        """Update an account."""
        updated = self.account_repo.update(account_id, updates)
        return updated.to_dict() if updated else None

    def delete_account(self, account_id: int) -> bool:
        """Delete (deactivate) an account."""
        return self.account_repo.delete(account_id)

    def get_account_balance(self, account_id: int) -> float:
        """Get current balance for an account by summing all its transactions."""
        result = self.session.query(func.sum(Transaction.amount)).filter(
            Transaction.account_id == account_id
        ).scalar()
        return round(result or 0.0, 2)

    # --- Aggregates from Transactions ---

    def get_total_balance_for_month(self, year: int, month: int) -> float:
        """Get total balance (cumulative) across all accounts up to end of given month."""
        from sqlalchemy import or_, and_
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
        """Get total expenses for a specific month from transactions."""
        result = self.session.query(
            func.sum(func.abs(Transaction.amount))
        ).filter(
            Transaction.amount < 0,
            extract('year', Transaction.date) == year,
            extract('month', Transaction.date) == month
        ).scalar()
        return round(result or 0.0, 2)

    def get_total_income_for_month(self, year: int, month: int) -> float:
        """Get total income for a specific month from transactions."""
        result = self.session.query(func.sum(Transaction.amount)).filter(
            Transaction.amount > 0,
            extract('year', Transaction.date) == year,
            extract('month', Transaction.date) == month
        ).scalar()
        return round(result or 0.0, 2)

    def get_balance_trend(self, account_id: Optional[int] = None, num_months: int = 12) -> List[Dict[str, Any]]:
        """Get monthly aggregated balance trend from transactions."""
        query = self.session.query(
            extract('year', Transaction.date).label('year'),
            extract('month', Transaction.date).label('month'),
            func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)).label('total_income'),
            func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)).label('total_expense'),
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
