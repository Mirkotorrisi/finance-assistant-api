from typing import List, Optional, Dict, Any
import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from src.database.models import Transaction, Category, Account
from src.repositories.transaction_repository import TransactionRepository
from src.repositories.category_repository import CategoryRepository

class TransactionService:
    def __init__(self, session: Session):
        self.session = session
        self.transaction_repo = TransactionRepository(session)
        self.category_repo = CategoryRepository(session)

    def list_transactions(
        self, 
        category: Optional[str] = None, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None,
        account_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """List transactions with optional filters."""
        # Convert string dates to date objects if present
        start_date_obj = datetime.datetime.fromisoformat(start_date).date() if start_date else None
        end_date_obj = datetime.datetime.fromisoformat(end_date).date() if end_date else None
        
        transactions = self.transaction_repo.list(category, start_date_obj, end_date_obj, account_id)
        return [t.to_dict() for t in transactions]

    def add_transaction(
        self, 
        amount: float, 
        category: str, 
        description: str, 
        date: str = None,
        currency: str = None,
        account_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Add a new transaction."""
        if not date:
            date_str = datetime.date.today().isoformat()
            transaction_date = datetime.date.today()
        else:
            date_str = date
            transaction_date = datetime.datetime.fromisoformat(date).date()

        # Validate account if provided
        if account_id is not None:
            self._validate_account_exists(account_id)

        self._ensure_category_exists(category)

        new_transaction = Transaction(
            date=transaction_date,
            amount=amount,
            category=category,
            description=description,
            currency=currency or "EUR",
            account_id=account_id
        )
        
        added = self.transaction_repo.add(new_transaction)
        return added.to_dict()

    def add_transactions_bulk(self, transactions_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add multiple transactions at once."""
        if not transactions_data:
            return []

        # 1. Collect all unique categories and ensure they exist
        categories = {t.get("category") for t in transactions_data if t.get("category")}
        for category_name in categories:
            self._ensure_category_exists(category_name)
            
        # 2. Add transactions
        transactions_to_add = []
        for t_data in transactions_data:
            date_str = t_data.get("date")
            if date_str:
                transaction_date = datetime.datetime.fromisoformat(date_str).date()
            else:
                transaction_date = datetime.date.today()
            
            new_transaction = Transaction(
                date=transaction_date,
                amount=t_data["amount"],
                category=t_data["category"],
                description=t_data["description"],
                currency=t_data.get("currency", "EUR"),
                account_id=t_data.get("account_id")
            )
            transactions_to_add.append(new_transaction)
            
        added = self.transaction_repo.add_all(transactions_to_add)
        return [t.to_dict() for t in added]

    def delete_transaction(self, transaction_id: int) -> bool:
        """Delete a transaction by ID."""
        transaction = self.transaction_repo.get_by_id(transaction_id)
        if transaction:
            self.transaction_repo.delete(transaction)
            return True
        return False

    def update_transaction(self, transaction_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a transaction by ID."""
        transaction = self.transaction_repo.get_by_id(transaction_id)
        if not transaction:
            return None
        
        # Handle special fields
        if 'date' in updates and isinstance(updates['date'], str):
             updates['date'] = datetime.datetime.fromisoformat(updates['date']).date()

        updated = self.transaction_repo.update(transaction, updates)
        return updated.to_dict()

    def get_balance(self) -> float:
        """Get the current balance (sum of all transactions).
        Note: This is the naive implementation compatible with FinanceMCPDatabase.
        """
        # TODO: If we switch to Account-based source of truth, this should call SnapshotService/AccountService
        return self.transaction_repo.get_total_balance()

    def _validate_account_exists(self, account_id: int) -> None:
        """Validate that an account exists.
        
        Args:
            account_id: The account ID to validate
            
        Raises:
            ValueError: If account does not exist
        """
        account = self.session.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError(f"Account with id {account_id} does not exist")

    def _ensure_category_exists(self, category_name: str) -> None:
        """Ensure a category exists."""
        if not category_name:
            return
            
        existing = self.category_repo.get_by_name(category_name)
        if not existing:
            new_category = Category(name=category_name.lower(), type="expense")
            try:
                self.category_repo.create(new_category)
            except IntegrityError:
                self.session.rollback()
            except Exception as e:
                 print(f"Warning: Failed to create category '{category_name}': {e}")
