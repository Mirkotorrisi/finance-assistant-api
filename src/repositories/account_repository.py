from typing import List, Optional
from sqlalchemy.orm import Session
from src.database.models import Account

class AccountRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, account: Account) -> Account:
        self.session.add(account)
        self.session.commit()
        self.session.refresh(account)
        return account

    def get_by_id(self, account_id: int) -> Optional[Account]:
        return self.session.query(Account).filter(Account.id == account_id).first()

    def list_all(self, active_only: bool = True) -> List[Account]:
        query = self.session.query(Account)
        if active_only:
            query = query.filter(Account.is_active == True)
        return query.order_by(Account.name).all()

    def update(self, account_id: int, updates: dict) -> Optional[Account]:
        """Update an account with partial updates."""
        account = self.get_by_id(account_id)
        if not account:
            return None
        
        for key, value in updates.items():
            if hasattr(account, key):
                setattr(account, key, value)
        
        self.session.commit()
        self.session.refresh(account)
        return account

    def delete(self, account_id: int) -> bool:
        """Soft delete an account by setting is_active to False."""
        account = self.get_by_id(account_id)
        if not account:
            return False
        
        account.is_active = False
        self.session.commit()
        return True
