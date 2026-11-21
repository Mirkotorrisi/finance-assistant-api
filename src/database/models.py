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
    # trades booked on this (cash) account build positions valued on that (investment) account: Trade Republic's
    # cash account feeds "Trade Republic titoli". NULL = the trades value this same account.
    securities_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    
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
            "current_balance": self.current_balance,
            "securities_account_id": self.securities_account_id,
        }


class BalanceSnapshot(Base):
    """What an account held on a day, as observed by the user (statement, app, a monthly sheet).

    Not a transaction: transactions stay the source of truth for flows. A snapshot is a checkpoint to reconcile
    them against, and the only record of accounts with no imported transactions (cash) or whose value is not a
    cash balance (brokerage: market value).
    """

    __tablename__ = "balance_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "date", name="uix_balance_snapshots_account_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    balance = Column(Float, nullable=False)
    source = Column(String(16), nullable=False, default="user")  # user | import
    note = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "date": self.date.isoformat() if self.date else None,
            "balance": self.balance,
            "source": self.source,
            "note": self.note,
        }


class ClientProfile(Base):
    """The advisor's memory of the person behind a workspace: situation, goals, risk and the agreed investment policy.

    One row per workspace; ``document`` is validated by ``src.profile.ClientProfile``. Every save bumps ``version``
    and keeps the previous document in ``client_profile_versions``. The IPS approval is bound to a hash of the
    policy's content: a rewritten policy is pending until the user approves it again from the app.
    """

    __tablename__ = "client_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, unique=True, index=True)
    document = Column(JSON, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    updated_by = Column(String(16), nullable=False, default="user")  # user | agent
    ips_approved_at = Column(DateTime, nullable=True)
    ips_approved_hash = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ClientProfileVersion(Base):
    """A past state of a client profile (what the advisor knew when a decision was taken)."""

    __tablename__ = "client_profile_versions"
    __table_args__ = (UniqueConstraint("workspace_id", "version", name="uix_client_profile_versions_ws_version"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    document = Column(JSON, nullable=False)
    source = Column(String(16), nullable=False, default="user")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AdvisorDecision(Base):
    """A recommendation and what became of it: the advisor's decision log.

    ``data_refs`` names the figures the advice rests on (tool, period, amount), ``ips_refs`` the policy points it
    follows; both are required, so an advice without evidence cannot be logged.
    """

    __tablename__ = "advisor_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    rationale = Column(Text, nullable=False)
    data_refs = Column(JSON, nullable=False, default=list)
    ips_refs = Column(JSON, nullable=False, default=list)
    status = Column(String(16), nullable=False, default="proposed")  # proposed | accepted | rejected | done
    profile_version = Column(Integer, nullable=True)
    outcome = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            "title": self.title,
            "rationale": self.rationale,
            "data_refs": self.data_refs or [],
            "ips_refs": self.ips_refs or [],
            "status": self.status,
            "profile_version": self.profile_version,
            "outcome": self.outcome,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BankConnection(Base):
    """A PSD2 consent given to one bank (ASPSP) through the aggregator, and what we know about syncing it.

    The aggregator's session id (what actually grants access) is NOT here: the gateway keeps it encrypted under
    ``session_ref``. This row holds the metadata the app shows (bank, validity, last sync) and the sync settings.
    """

    __tablename__ = "bank_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="enablebanking")
    aspsp_name = Column(String(120), nullable=False)
    aspsp_country = Column(String(2), nullable=False)
    psu_type = Column(String(16), nullable=False, default="personal")
    session_ref = Column(String(64), nullable=False, unique=True)
    status = Column(String(16), nullable=False, default="active")  # active | expired | revoked | error
    valid_until = Column(DateTime, nullable=True)
    sync_balances = Column(Boolean, nullable=False, default=True)
    sync_transactions = Column(Boolean, nullable=False, default=True)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(16), nullable=True)  # ok | partial | error | rate_limited | expired
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    links = relationship("BankAccountLink", back_populates="connection", cascade="all, delete-orphan")

    def to_dict(self, include_links: bool = True):
        data = {
            "id": self.id,
            "provider": self.provider,
            "aspsp_name": self.aspsp_name,
            "aspsp_country": self.aspsp_country,
            "psu_type": self.psu_type,
            "session_ref": self.session_ref,
            "status": self.status,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "sync_balances": bool(self.sync_balances),
            "sync_transactions": bool(self.sync_transactions),
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_status": self.last_sync_status,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_links:
            data["accounts"] = [link.to_dict() for link in sorted(self.links, key=lambda l: l.id)]
        return data


class BankAccountLink(Base):
    """One account the bank exposes under a connection, and the app account it feeds (if any).

    ``identification_hash`` is the bank's stable identity of the account across consents; ``bank_uid`` is the
    per-session handle the API calls use and is refreshed on every renewal.
    """

    __tablename__ = "bank_account_links"
    __table_args__ = (UniqueConstraint("connection_id", "identification_hash", name="uix_bank_account_links_conn_hash"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    connection_id = Column(Integer, ForeignKey("bank_connections.id"), nullable=False, index=True)
    identification_hash = Column(String(512), nullable=False)  # banks send long opaque tokens (UniCredit: 133 chars)
    bank_uid = Column(String(64), nullable=True)
    iban_masked = Column(String(40), nullable=True)
    label = Column(String(200), nullable=True)  # product / holder name as the bank gives it
    currency = Column(String(3), nullable=True)
    cash_account_type = Column(String(8), nullable=True)  # CACC | CARD | CASH | LOAN | OTHR | SVGS
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    last_transaction_date = Column(Date, nullable=True)
    last_balance = Column(Float, nullable=True)
    last_balance_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    connection = relationship("BankConnection", back_populates="links")

    def to_dict(self):
        return {
            "id": self.id,
            "connection_id": self.connection_id,
            "identification_hash": self.identification_hash,
            "bank_uid": self.bank_uid,
            "iban_masked": self.iban_masked,
            "label": self.label,
            "currency": self.currency,
            "cash_account_type": self.cash_account_type,
            "account_id": self.account_id,
            "enabled": bool(self.enabled),
            "last_transaction_date": self.last_transaction_date.isoformat() if self.last_transaction_date else None,
            "last_balance": self.last_balance,
            "last_balance_date": self.last_balance_date.isoformat() if self.last_balance_date else None,
        }


class Instrument(Base):
    """A security the user holds or held: identified by ISIN, priced through a symbol on a price source.

    Global (an ISIN is the same in every project). ``valuation`` says how its value is found: ``market`` (quantity
    held × last close), ``cost`` (money-market funds and anything without units: value = net cash in), ``manual``
    (the user types a price). ``asset_class`` feeds the IPS allocation.
    """

    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    isin = Column(String(12), nullable=True, unique=True, index=True)
    key = Column(String(120), nullable=False, unique=True)  # ISIN, else the normalised name (as investments.py keys trades)
    name = Column(String(200), nullable=False)
    type = Column(String(16), nullable=False, default="other")  # etf | stock | bond | fund | certificate | other
    currency = Column(String(3), nullable=False, default="EUR")
    asset_class = Column(String(16), nullable=False, default="other")  # equity | bonds | cash | real_estate | commodities | crypto | other
    valuation = Column(String(8), nullable=False, default="market")  # market | cost | manual
    price_symbol = Column(String(40), nullable=True)  # e.g. LYY0.DEX, AAPL
    symbol_candidates = Column(JSON, nullable=True)  # other listings to try when the symbol gives no data
    price_source = Column(String(24), nullable=True)  # alphavantage | manual
    manual_price = Column(Float, nullable=True)
    manual_price_date = Column(Date, nullable=True)
    last_error = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "isin": self.isin,
            "key": self.key,
            "name": self.name,
            "type": self.type,
            "currency": self.currency,
            "asset_class": self.asset_class,
            "valuation": self.valuation,
            "price_symbol": self.price_symbol,
            "symbol_candidates": self.symbol_candidates or [],
            "price_source": self.price_source,
            "manual_price": self.manual_price,
            "manual_price_date": self.manual_price_date.isoformat() if self.manual_price_date else None,
            "last_error": self.last_error,
        }


class Price(Base):
    """A daily close of an instrument, in the instrument's currency. Global cache, one row per instrument and day."""

    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("instrument_id", "date", name="uix_prices_instrument_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    close = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="EUR")
    source = Column(String(24), nullable=False, default="alphavantage")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FxRate(Base):
    """Daily exchange rate: 1 unit of ``base`` = ``rate`` units of ``quote`` (e.g. EUR→USD 1.08). Global cache."""

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("base", "quote", "date", name="uix_fx_rates_pair_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    base = Column(String(3), nullable=False)
    quote = Column(String(3), nullable=False)
    date = Column(Date, nullable=False, index=True)
    rate = Column(Float, nullable=False)
    source = Column(String(24), nullable=False, default="alphavantage")


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
    
    # Who decided the category and how sure it is: 'user' | 'rule' | 'file' | 'ai' | 'fallback' | 'legacy'.
    # Only decisions by the user (or a rule the user made) count as certain (reviewed).
    category_source = Column(String(16), nullable=False, default="user")
    confidence = Column(Float, nullable=True)
    reviewed = Column(Boolean, nullable=False, default=False)
    merchant_key = Column(String(120), nullable=True, index=True)
    # Import bookkeeping: identical rows share a fingerprint (account, date, amount, normalised description)
    fingerprint = Column(String(64), nullable=True, index=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=True, index=True)
    # Money moved between the user's own accounts (incl. credit-card payments): not spending, not income
    is_transfer = Column(Boolean, nullable=False, default=False)
    transfer_pair_id = Column(Integer, nullable=True)
    # Where the row came from ('statement' upload, 'bank' API sync, 'manual', 'adjustment') and the bank's own
    # reference for it when the bank gave one: rows with the same (account, external_id) are the same movement.
    source = Column(String(16), nullable=False, default="statement")
    external_id = Column(String(128), nullable=True, index=True)
    # A bank-synced row that looks like a statement row already stored (same account, amount, date within a few
    # days) but could not be matched exactly: kept, and pointed at the suspect twin for the user to settle.
    duplicate_of = Column(Integer, nullable=True)

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
            "category_source": self.category_source,
            "confidence": self.confidence,
            "reviewed": bool(self.reviewed),
            "merchant_key": self.merchant_key,
            "is_transfer": bool(self.is_transfer),
            "transfer_pair_id": self.transfer_pair_id,
            "import_batch_id": self.import_batch_id,
            "source": self.source or "statement",
            "external_id": self.external_id,
            "duplicate_of": self.duplicate_of,
        }
