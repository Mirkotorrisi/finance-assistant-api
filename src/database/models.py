"""Database models using SQLAlchemy ORM."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Boolean, JSON, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Workspace(Base):
    """A project: its own accounts, transactions, rules and blueprint.

    ``blueprint`` is a validated document (see ``src.blueprint``) that says how this project's spending
    is organised. ``owner_user_id`` is the lightweight client identity; NULL means unowned (legacy data).
    """

    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    owner_user_id = Column(String(64), nullable=True, index=True)
    blueprint = Column(JSON, nullable=False)
    blueprint_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self, include_blueprint: bool = False):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "owner_user_id": self.owner_user_id,
            "blueprint_version": self.blueprint_version,
        }
        if include_blueprint:
            data["blueprint"] = self.blueprint
        return data


class ImportBatch(Base):
    """One uploaded statement. Lets an import be listed and undone as a whole."""

    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    filename = Column(String(300), nullable=True)
    file_hash = Column(String(64), nullable=True, index=True)
    row_count = Column(Integer, nullable=False, default=0)
    added_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "filename": self.filename,
            "file_hash": self.file_hash,
            "row_count": self.row_count,
            "added_count": self.added_count,
            "skipped_count": self.skipped_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Account(Base):
    """Account model representing a financial account.
    
    Represents a stable financial account over time (checking, credit, cash, investment, etc.)
    """
    
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
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


class UserPreferences(Base):
    """Per-user onboarding context: focus areas, known categories, budget target.

    ``user_id`` is a lightweight client-generated identifier (no auth system yet),
    not a foreign key to a users table.
    """

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)
    onboarding_completed = Column(Boolean, nullable=False, default=False)
    focus_categories = Column(JSON, nullable=False, default=list)
    custom_categories = Column(JSON, nullable=False, default=list)
    budget_amount = Column(Float, nullable=True)
    budget_period = Column(String(20), nullable=False, default="monthly")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<UserPreferences(user_id='{self.user_id}', onboarding_completed={self.onboarding_completed})>"

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "onboarding_completed": self.onboarding_completed,
            "focus_categories": self.focus_categories or [],
            "custom_categories": self.custom_categories or [],
            "budget_amount": self.budget_amount,
            "budget_period": self.budget_period,
            "notes": self.notes,
        }


class MerchantRule(Base):
    """Merchant alias rules: map description patterns to a fixed category."""

    __tablename__ = "merchant_rules"
    __table_args__ = (UniqueConstraint("workspace_id", "pattern", name="uix_merchant_rules_workspace_pattern"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    pattern = Column(String(200), nullable=False, index=True)
    category = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "pattern": self.pattern,
            "category": self.category,
        }


class Transaction(Base):
    """Transaction model for financial transactions.
    
    Transactions are the single source of truth for all financial data.
    Monthly account snapshots are computed by aggregating transactions
    filtered by account_id and date (year/month).
    """
    
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)  # Nullable for backward compatibility
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)  # positive = income, negative = expense
    category = Column(String(100), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    currency = Column(String(3), default="EUR")  # Kept for backward compatibility with existing code
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Import bookkeeping: identical rows share a fingerprint (account, date, amount, normalised description)
    fingerprint = Column(String(64), nullable=True, index=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=True, index=True)
    # Money moved between the user's own accounts (incl. credit-card payments): not spending, not income
    is_transfer = Column(Boolean, nullable=False, default=False)
    transfer_pair_id = Column(Integer, nullable=True)

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
            "currency": self.currency,
            "is_transfer": bool(self.is_transfer),
            "transfer_pair_id": self.transfer_pair_id,
            "import_batch_id": self.import_batch_id,
        }
