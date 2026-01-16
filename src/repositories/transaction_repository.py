from typing import List, Optional, Dict, Any
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import desc
from src.database.models import Transaction

class TransactionRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self, 
             category: Optional[str] = None, 
             start_date: Optional[date] = None, 
             end_date: Optional[date] = None,
             account_id: Optional[int] = None) -> List[Transaction]:
        query = self.session.query(Transaction)
        
        if category:
            query = query.filter(Transaction.category.ilike(category))
        if start_date:
            query = query.filter(Transaction.date >= start_date)
        if end_date:
            query = query.filter(Transaction.date <= end_date)
        if account_id is not None:
            query = query.filter(Transaction.account_id == account_id)
            
        return query.order_by(Transaction.date.desc()).all()

    def add(self, transaction: Transaction) -> Transaction:
        self.session.add(transaction)
        self.session.commit()
        self.session.refresh(transaction)
        return transaction

    def add_all(self, transactions: List[Transaction]) -> List[Transaction]:
        self.session.add_all(transactions)
        self.session.commit()
        for t in transactions:
            self.session.refresh(t)
        return transactions

    def get_by_id(self, transaction_id: int) -> Optional[Transaction]:
        return self.session.query(Transaction).filter(Transaction.id == transaction_id).first()

    def delete(self, transaction: Transaction) -> None:
        self.session.delete(transaction)
        self.session.commit()

    def update(self, transaction: Transaction, updates: Dict[str, Any]) -> Transaction:
        for key, value in updates.items():
            if value is not None and hasattr(transaction, key):
                if key != 'id':
                    setattr(transaction, key, value)
        
        self.session.commit()
        self.session.refresh(transaction)
        return transaction

    def get_total_balance(self) -> float:
        """Naive sum of all transactions. 
        Note: Real balance should come from Snapshots.
        """
        transactions = self.session.query(Transaction).all()
        return sum(t.amount for t in transactions)
