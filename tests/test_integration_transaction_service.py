"""Integration tests for TransactionService using an in-memory SQLite database."""

import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, Account, Transaction, Category
from src.services.transaction_service import TransactionService
from tests.mocks.mock_data import MOCK_ACCOUNTS, MOCK_TRANSACTIONS, MOCK_CATEGORIES


# ---------------------------------------------------------------------------
# Session fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def seeded_session(db_session):
    """In-memory database pre-seeded with mock accounts, categories, and transactions."""
    for acc_data in MOCK_ACCOUNTS:
        db_session.add(Account(**acc_data))
    db_session.commit()

    for cat_data in MOCK_CATEGORIES:
        db_session.add(Category(**cat_data))
    db_session.commit()

    for txn_data in MOCK_TRANSACTIONS:
        db_session.add(Transaction(**txn_data))
    db_session.commit()

    return db_session


@pytest.fixture
def service(seeded_session):
    """Return a TransactionService backed by the seeded database."""
    return TransactionService(session=seeded_session)


@pytest.fixture
def empty_service(db_session):
    """Return a TransactionService backed by an empty in-memory database."""
    return TransactionService(session=db_session)


# ---------------------------------------------------------------------------
# list_transactions
# ---------------------------------------------------------------------------

class TestListTransactionsIntegration:
    """Integration tests for TransactionService.list_transactions."""

    def test_list_all_returns_all_transactions(self, service):
        """Listing without filters returns every transaction in the DB."""
        results = service.list_transactions()
        assert len(results) == len(MOCK_TRANSACTIONS)

    def test_list_by_category(self, service):
        """Filtering by category returns only matching transactions."""
        results = service.list_transactions(category="salary")
        assert all(r["category"] == "salary" for r in results)
        assert len(results) > 0

    def test_list_by_date_range(self, service):
        """Filtering by date range returns only matching transactions."""
        results = service.list_transactions(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        for r in results:
            txn_date = datetime.date.fromisoformat(r["date"])
            assert txn_date >= datetime.date(2024, 1, 1)
            assert txn_date <= datetime.date(2024, 1, 31)

    def test_list_by_account_id(self, service):
        """Filtering by account_id returns only that account's transactions."""
        results = service.list_transactions(account_id=1)
        assert all(r["account_id"] == 1 for r in results)

    def test_list_empty_when_no_match(self, service):
        """Filtering with criteria that match nothing returns an empty list."""
        results = service.list_transactions(category="nonexistent_category_xyz")
        assert results == []

    def test_list_returns_dicts(self, service):
        """Every result is a dictionary with the expected keys."""
        results = service.list_transactions()
        required_keys = {"id", "account_id", "date", "amount", "category", "description", "currency"}
        for r in results:
            assert required_keys.issubset(r.keys())


# ---------------------------------------------------------------------------
# add_transaction
# ---------------------------------------------------------------------------

class TestAddTransactionIntegration:
    """Integration tests for TransactionService.add_transaction."""

    def test_add_transaction_persists(self, empty_service, db_session):
        """Adding a transaction stores it in the database."""
        # Need an account first
        db_session.add(Account(id=1, name="Checking", type="checking", currency="EUR"))
        db_session.commit()

        result = empty_service.add_transaction(
            amount=500.0,
            category="salary",
            description="Test salary",
            date="2024-01-01",
            account_id=1,
        )

        assert result["id"] is not None
        assert result["amount"] == 500.0
        stored = db_session.query(Transaction).filter_by(id=result["id"]).first()
        assert stored is not None
        assert stored.amount == 500.0

    def test_add_transaction_creates_missing_category(self, empty_service, db_session):
        """A new category is automatically created when it doesn't exist."""
        db_session.add(Account(id=1, name="Checking", type="checking", currency="EUR"))
        db_session.commit()

        empty_service.add_transaction(
            amount=-50.0,
            category="brand_new_category",
            description="Test",
        )

        category = db_session.query(Category).filter_by(name="brand_new_category").first()
        assert category is not None

    def test_add_transaction_without_date_uses_today(self, empty_service):
        """Omitting the date defaults to today."""
        result = empty_service.add_transaction(
            amount=100.0,
            category="groceries",
            description="Shopping",
        )
        assert result["date"] == datetime.date.today().isoformat()

    def test_add_transaction_invalid_account_raises(self, empty_service):
        """Providing a non-existent account_id raises ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            empty_service.add_transaction(
                amount=100.0,
                category="groceries",
                description="Shopping",
                account_id=9999,
            )


# ---------------------------------------------------------------------------
# add_transactions_bulk
# ---------------------------------------------------------------------------

class TestAddTransactionsBulkIntegration:
    """Integration tests for TransactionService.add_transactions_bulk."""

    def test_bulk_add_persists_all(self, empty_service, db_session):
        """Bulk adding transactions stores all of them in the database."""
        txn_data = [
            {"amount": 100.0, "category": "groceries", "description": "Shop 1", "date": "2024-01-05"},
            {"amount": -200.0, "category": "rent", "description": "Rent", "date": "2024-01-10"},
        ]
        results = empty_service.add_transactions_bulk(txn_data)

        assert len(results) == 2
        assert db_session.query(Transaction).count() == 2

    def test_bulk_add_empty_list(self, empty_service):
        """Bulk add with empty list returns empty list and changes nothing."""
        result = empty_service.add_transactions_bulk([])
        assert result == []


# ---------------------------------------------------------------------------
# delete_transaction
# ---------------------------------------------------------------------------

class TestDeleteTransactionIntegration:
    """Integration tests for TransactionService.delete_transaction."""

    def test_delete_removes_from_db(self, service, seeded_session):
        """Deleting a transaction removes it from the database."""
        target_id = MOCK_TRANSACTIONS[0]["id"]
        result = service.delete_transaction(target_id)

        assert result is True
        assert seeded_session.query(Transaction).filter_by(id=target_id).first() is None

    def test_delete_nonexistent_returns_false(self, service):
        """Deleting a non-existent transaction returns False."""
        result = service.delete_transaction(99999)
        assert result is False


# ---------------------------------------------------------------------------
# update_transaction
# ---------------------------------------------------------------------------

class TestUpdateTransactionIntegration:
    """Integration tests for TransactionService.update_transaction."""

    def test_update_amount(self, service, seeded_session):
        """Updating the amount field is reflected in the database."""
        target_id = MOCK_TRANSACTIONS[0]["id"]
        result = service.update_transaction(target_id, {"amount": 9999.0})

        assert result is not None
        assert result["amount"] == 9999.0
        updated = seeded_session.query(Transaction).filter_by(id=target_id).first()
        assert updated.amount == 9999.0

    def test_update_date_string(self, service):
        """Updating with a date string converts it to a date object."""
        target_id = MOCK_TRANSACTIONS[0]["id"]
        result = service.update_transaction(target_id, {"date": "2025-06-15"})

        assert result is not None
        assert result["date"] == "2025-06-15"

    def test_update_nonexistent_returns_none(self, service):
        """Updating a non-existent transaction returns None."""
        result = service.update_transaction(99999, {"amount": 100.0})
        assert result is None


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------

class TestGetBalanceIntegration:
    """Integration tests for TransactionService.get_balance."""

    def test_balance_equals_sum_of_amounts(self, service):
        """get_balance equals the sum of all transaction amounts."""
        expected = sum(t["amount"] for t in MOCK_TRANSACTIONS)
        balance = service.get_balance()
        assert abs(balance - expected) < 0.01

    def test_balance_zero_when_empty(self, empty_service):
        """get_balance is 0.0 when no transactions exist."""
        assert empty_service.get_balance() == 0.0
