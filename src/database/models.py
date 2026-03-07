"""Database models using SQLAlchemy ORM."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Account(Base):
    """Account model representing a financial account.
    
    Represents a stable financial account over time (checking, credit, cash, investment, etc.)
    """
    
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False)  # checking, credit, cash, investment, etc.
    currency = Column(String(3), nullable=False, default="EUR")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    current_balance = Column(Float, nullable=False, default=0.0)
    
    # Relationships
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Account(id={self.id}, name='{self.name}', type='{self.type}')>"
    
    def to_dict(self):
        """Convert account to dictionary format.
        
        Returns:
            Dictionary representation of the account
        """
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "currency": self.currency,
            "is_active": self.is_active,
            "current_balance": self.current_balance
        }


class Category(Base):
    """Category model for transaction categories."""
    
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    type = Column(String(10), nullable=False)  # 'income' or 'expense'
    color = Column(String(7), nullable=True)  # Hex color code, e.g., '#FF5733'
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship
    transactions = relationship("Transaction", back_populates="category_rel")
    
    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}', type='{self.type}')>"
    
    def to_dict(self):
        """Convert category to dictionary format.
        
        Returns:
            Dictionary representation of the category
        """
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "color": self.color
        }


class Transaction(Base):
    """Transaction model for financial transactions.
    
    Transactions are the single source of truth for all financial data.
    Monthly account snapshots are computed by aggregating transactions
    filtered by account_id and date (year/month).
    """
    
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)  # Nullable for backward compatibility
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)  # positive = income, negative = expense
    category = Column(String(100), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    currency = Column(String(3), default="EUR")  # Kept for backward compatibility with existing code
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Foreign key (optional - category can be free text or reference to categories table)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    
    # Relationships
    category_rel = relationship("Category", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
    
    def __repr__(self):
        return f"<Transaction(id={self.id}, date='{self.date}', amount={self.amount}, category='{self.category}')>"
    
    def to_dict(self):
        """Convert transaction to dictionary format.
        
        Returns:
            Dictionary representation of the transaction
        """
        return {
            "id": self.id,
            "account_id": self.account_id,
            "date": self.date.isoformat() if self.date else None,
            "amount": self.amount,
            "category": self.category,
            "description": self.description,
            "currency": self.currency
        }
