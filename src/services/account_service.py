from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.database.models import Account, MonthlyAccountSnapshot, Transaction
from src.repositories.account_repository import AccountRepository
from src.repositories.snapshot_repository import SnapshotRepository

class AccountService:
    def __init__(self, session: Session):
        self.session = session
        self.account_repo = AccountRepository(session)
        self.snapshot_repo = SnapshotRepository(session)

    # --- Account Operations ---

    def create_account(self, name: str, account_type: str, currency: str = "EUR", is_active: bool = True) -> Dict[str, Any]:
        account = Account(name=name, type=account_type, currency=currency, is_active=is_active)
        created = self.account_repo.create(account)
        return created.to_dict()

    def get_account(self, account_id: int) -> Optional[Dict[str, Any]]:
        account = self.account_repo.get_by_id(account_id)
        return account.to_dict() if account else None

    def list_accounts(self, active_only: bool = True) -> List[Dict[str, Any]]:
        accounts = self.account_repo.list_all(active_only)
        return [acc.to_dict() for acc in accounts]

    # --- Snapshot Operations ---

    def create_snapshot(
        self,
        account_id: int,
        year: int,
        month: int,
        starting_balance: float,
        ending_balance: float,
        total_income: float = 0.0,
        total_expense: float = 0.0
    ) -> Dict[str, Any]:
        existing = self.snapshot_repo.get_by_account_year_month(account_id, year, month)
        if existing:
            raise ValueError(f"Snapshot already exists for account {account_id}, year {year}, month {month}")

        snapshot = MonthlyAccountSnapshot(
            account_id=account_id,
            year=year,
            month=month,
            starting_balance=starting_balance,
            ending_balance=ending_balance,
            total_income=total_income,
            total_expense=total_expense
        )
        created = self.snapshot_repo.create(snapshot)
        return created.to_dict()

    def update_snapshot(
        self,
        account_id: int,
        year: int,
        month: int,
        starting_balance: Optional[float] = None,
        ending_balance: Optional[float] = None,
        total_income: Optional[float] = None,
        total_expense: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        snapshot = self.snapshot_repo.get_by_account_year_month(account_id, year, month)
        if not snapshot:
            return None

        if starting_balance is not None: snapshot.starting_balance = starting_balance
        if ending_balance is not None: snapshot.ending_balance = ending_balance
        if total_income is not None: snapshot.total_income = total_income
        if total_expense is not None: snapshot.total_expense = total_expense

        updated = self.snapshot_repo.update(snapshot)
        return updated.to_dict()

    def get_snapshot(self, account_id: int, year: int, month: int) -> Optional[Dict[str, Any]]:
        snapshot = self.snapshot_repo.get_by_account_year_month(account_id, year, month)
        return snapshot.to_dict() if snapshot else None

    def list_snapshots_for_account(
        self,
        account_id: int,
        start_year: Optional[int] = None,
        start_month: Optional[int] = None,
        end_year: Optional[int] = None,
        end_month: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        snapshots = self.snapshot_repo.list_by_account(
            account_id, start_year, start_month, end_year, end_month
        )
        return [s.to_dict() for s in snapshots]

    # --- Aggregates & Trends ---

    def get_total_balance_for_month(self, year: int, month: int) -> float:
        return self.snapshot_repo.get_total_balance_for_month(year, month)

    def get_current_total_balance(self) -> float:
        return self.snapshot_repo.get_current_total_balance()

    def get_total_expenses_for_month(self, year: int, month: int) -> float:
        return self.snapshot_repo.get_total_expenses_for_month(year, month)
        
    def get_total_income_for_month(self, year: int, month: int) -> float:
        return self.snapshot_repo.get_total_income_for_month(year, month)

    def get_balance_trend(self, account_id: Optional[int] = None, num_months: int = 12) -> List[Dict[str, Any]]:
        snapshots = self.snapshot_repo.get_trend(account_id, num_months)
        return [s.to_dict() for s in snapshots]

    # --- Snapshot Population from Transactions ---

    def populate_snapshot_from_transactions(
        self, 
        account_id: int, 
        year: int, 
        month: int, 
        starting_balance: float = 0.0,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """Calculate and create/update a snapshot from transaction data.
        
        Args:
            account_id: Account ID
            year: Year
            month: Month (1-12)
            starting_balance: Starting balance for the month (default 0.0)
            overwrite: If True, update existing snapshot; if False, raise error if exists
            
        Returns:
            Created or updated snapshot as dictionary
        """
        # Get all transactions for this account/month
        transactions = self.session.query(Transaction).filter(
            Transaction.account_id == account_id,
            func.extract('year', Transaction.date) == year,
            func.extract('month', Transaction.date) == month
        ).all()
        
        # Calculate aggregates
        total_income = sum(t.amount for t in transactions if t.amount > 0)
        total_expense = abs(sum(t.amount for t in transactions if t.amount < 0))
        net_change = sum(t.amount for t in transactions)
        ending_balance = starting_balance + net_change
        
        # Check if snapshot already exists
        existing = self.snapshot_repo.get_by_account_year_month(account_id, year, month)
        
        if existing:
            if not overwrite:
                raise ValueError(f"Snapshot already exists for account {account_id}, year {year}, month {month}. Use overwrite=True to update.")
            
            # Update existing
            existing.starting_balance = starting_balance
            existing.ending_balance = ending_balance
            existing.total_income = total_income
            existing.total_expense = total_expense
            updated = self.snapshot_repo.update(existing)
            return updated.to_dict()
        else:
            # Create new
            snapshot = MonthlyAccountSnapshot(
                account_id=account_id,
                year=year,
                month=month,
                starting_balance=starting_balance,
                ending_balance=ending_balance,
                total_income=total_income,
                total_expense=total_expense
            )
            created = self.snapshot_repo.create(snapshot)
            return created.to_dict()
