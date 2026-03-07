"""Unit tests for TransactionService."""

import datetime
import pytest
from unittest.mock import MagicMock, Mock, patch
from sqlalchemy.exc import IntegrityError

from src.services.transaction_service import TransactionService
from src.database.models import Transaction, Account, Category
from tests.mocks.mock_data import MOCK_TRANSACTIONS, MOCK_ACCOUNTS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    """Return a mock SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def mock_transaction_repo():
    return MagicMock()


@pytest.fixture
def mock_category_repo():
    return MagicMock()


@pytest.fixture
def transaction_service(mock_session, mock_transaction_repo, mock_category_repo):
    """Return a TransactionService with all repos mocked."""
    service = TransactionService(session=mock_session)
    service.transaction_repo = mock_transaction_repo
    service.category_repo = mock_category_repo
    return service


def _make_transaction_mock(**kwargs):
    """Build a Mock that mimics a Transaction ORM object."""
    defaults = dict(
        id=1,
        account_id=1,
        date=datetime.date(2024, 1, 1),
        amount=100.0,
        category="salary",
        description="Test transaction",
        currency="EUR",
    )
    defaults.update(kwargs)
    mock_txn = Mock(spec=Transaction)
    for k, v in defaults.items():
        setattr(mock_txn, k, v)
    mock_txn.to_dict.return_value = {
        "id": defaults["id"],
        "account_id": defaults["account_id"],
        "date": defaults["date"].isoformat(),
        "amount": defaults["amount"],
        "category": defaults["category"],
        "description": defaults["description"],
        "currency": defaults["currency"],
    }
    return mock_txn


# ---------------------------------------------------------------------------
# list_transactions
# ---------------------------------------------------------------------------

class TestListTransactions:
    """Tests for TransactionService.list_transactions."""

    def test_list_all_transactions(self, transaction_service, mock_transaction_repo):
        """list_transactions with no filters returns all transactions."""
        mock_txn = _make_transaction_mock()
        mock_transaction_repo.list.return_value = [mock_txn]

        results = transaction_service.list_transactions()

        mock_transaction_repo.list.assert_called_once_with(None, None, None, None)
        assert len(results) == 1
        assert results[0]["id"] == 1

    def test_list_with_category_filter(self, transaction_service, mock_transaction_repo):
        """Passing a category string is forwarded to the repo."""
        mock_transaction_repo.list.return_value = []

        transaction_service.list_transactions(category="groceries")

        call_args = mock_transaction_repo.list.call_args[0]
        assert call_args[0] == "groceries"

    def test_list_with_date_filters(self, transaction_service, mock_transaction_repo):
        """Date strings are converted to date objects before being passed to repo."""
        mock_transaction_repo.list.return_value = []

        transaction_service.list_transactions(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        call_args = mock_transaction_repo.list.call_args[0]
        assert call_args[1] == datetime.date(2024, 1, 1)
        assert call_args[2] == datetime.date(2024, 1, 31)

    def test_list_with_account_id_filter(self, transaction_service, mock_transaction_repo):
        """account_id filter is forwarded to the repo."""
        mock_transaction_repo.list.return_value = []

        transaction_service.list_transactions(account_id=42)

        call_args = mock_transaction_repo.list.call_args[0]
        assert call_args[3] == 42

    def test_list_returns_dicts(self, transaction_service, mock_transaction_repo):
        """Each returned Transaction is converted to a dict."""
        mock_txn = _make_transaction_mock(id=5, amount=-99.0)
        mock_transaction_repo.list.return_value = [mock_txn]

        results = transaction_service.list_transactions()

        assert isinstance(results[0], dict)
        assert results[0]["amount"] == -99.0


# ---------------------------------------------------------------------------
# add_transaction
# ---------------------------------------------------------------------------

class TestAddTransaction:
    """Tests for TransactionService.add_transaction."""

    def test_add_basic_transaction(self, transaction_service, mock_transaction_repo, mock_category_repo):
        """Adding a valid transaction returns the created transaction dict."""
        mock_category_repo.get_by_name.return_value = Mock()  # category exists
        mock_txn = _make_transaction_mock(id=10, amount=500.0, category="salary")
        mock_transaction_repo.add.return_value = mock_txn

        result = transaction_service.add_transaction(
            amount=500.0,
            category="salary",
            description="Salary payment",
            date="2024-01-01",
            currency="EUR",
        )

        mock_transaction_repo.add.assert_called_once()
        assert result["amount"] == 500.0

    def test_add_transaction_uses_today_when_no_date(self, transaction_service, mock_transaction_repo, mock_category_repo):
        """When no date is supplied, today's date is used."""
        mock_category_repo.get_by_name.return_value = Mock()
        today = datetime.date.today()
        mock_txn = _make_transaction_mock(date=today)
        mock_transaction_repo.add.return_value = mock_txn

        transaction_service.add_transaction(
            amount=100.0,
            category="groceries",
            description="Shopping",
        )

        added_txn = mock_transaction_repo.add.call_args[0][0]
        assert added_txn.date == today

    def test_add_transaction_with_account_id(self, transaction_service, mock_transaction_repo, mock_category_repo, mock_session):
        """When account_id is provided and account exists, no error is raised."""
        mock_account = Mock(spec=Account)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_account
        mock_category_repo.get_by_name.return_value = Mock()
        mock_txn = _make_transaction_mock(account_id=1)
        mock_transaction_repo.add.return_value = mock_txn

        result = transaction_service.add_transaction(
            amount=200.0,
            category="rent",
            description="Monthly rent",
            account_id=1,
        )

        assert result["account_id"] == 1

    def test_add_transaction_invalid_account_raises(self, transaction_service, mock_session):
        """Providing an account_id that doesn't exist raises ValueError."""
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="does not exist"):
            transaction_service.add_transaction(
                amount=100.0,
                category="groceries",
                description="Shopping",
                account_id=999,
            )

    def test_add_transaction_creates_new_category(self, transaction_service, mock_transaction_repo, mock_category_repo):
        """When the category doesn't exist it is created automatically."""
        mock_category_repo.get_by_name.return_value = None  # not found
        mock_txn = _make_transaction_mock(category="new_category")
        mock_transaction_repo.add.return_value = mock_txn

        transaction_service.add_transaction(
            amount=50.0,
            category="new_category",
            description="Test",
        )

        mock_category_repo.create.assert_called_once()

    def test_add_transaction_default_currency_eur(self, transaction_service, mock_transaction_repo, mock_category_repo):
        """When currency is not provided, EUR is used as default."""
        mock_category_repo.get_by_name.return_value = Mock()
        mock_txn = _make_transaction_mock(currency="EUR")
        mock_transaction_repo.add.return_value = mock_txn

        transaction_service.add_transaction(
            amount=100.0,
            category="groceries",
            description="Shopping",
        )

        added_txn = mock_transaction_repo.add.call_args[0][0]
        assert added_txn.currency == "EUR"


# ---------------------------------------------------------------------------
# add_transactions_bulk
# ---------------------------------------------------------------------------

class TestAddTransactionsBulk:
    """Tests for TransactionService.add_transactions_bulk."""

    def test_bulk_empty_list(self, transaction_service):
        """Passing an empty list returns an empty list without touching the repo."""
        result = transaction_service.add_transactions_bulk([])
        assert result == []

    def test_bulk_adds_multiple_transactions(self, transaction_service, mock_transaction_repo, mock_category_repo):
        """Bulk add creates all supplied transactions."""
        mock_category_repo.get_by_name.return_value = Mock()
        txn_data = [
            {"amount": 100.0, "category": "groceries", "description": "Shop 1", "date": "2024-01-05", "currency": "EUR"},
            {"amount": 200.0, "category": "groceries", "description": "Shop 2", "date": "2024-01-06", "currency": "EUR"},
        ]
        mock_txn1 = _make_transaction_mock(id=1, amount=100.0)
        mock_txn2 = _make_transaction_mock(id=2, amount=200.0)
        mock_transaction_repo.add_all.return_value = [mock_txn1, mock_txn2]

        results = transaction_service.add_transactions_bulk(txn_data)

        mock_transaction_repo.add_all.assert_called_once()
        assert len(results) == 2

    def test_bulk_uses_today_for_missing_date(self, transaction_service, mock_transaction_repo, mock_category_repo):
        """Transactions without a date field default to today."""
        mock_category_repo.get_by_name.return_value = Mock()
        today = datetime.date.today()
        txn_data = [{"amount": 50.0, "category": "dining", "description": "Lunch"}]
        mock_txn = _make_transaction_mock(date=today)
        mock_transaction_repo.add_all.return_value = [mock_txn]

        transaction_service.add_transactions_bulk(txn_data)

        added_txns = mock_transaction_repo.add_all.call_args[0][0]
        assert added_txns[0].date == today


# ---------------------------------------------------------------------------
# delete_transaction
# ---------------------------------------------------------------------------

class TestDeleteTransaction:
    """Tests for TransactionService.delete_transaction."""

    def test_delete_existing_transaction(self, transaction_service, mock_transaction_repo):
        """Deleting an existing transaction returns True."""
        mock_transaction_repo.get_by_id.return_value = _make_transaction_mock()

        result = transaction_service.delete_transaction(1)

        mock_transaction_repo.delete.assert_called_once()
        assert result is True

    def test_delete_nonexistent_transaction(self, transaction_service, mock_transaction_repo):
        """Attempting to delete a non-existent transaction returns False."""
        mock_transaction_repo.get_by_id.return_value = None

        result = transaction_service.delete_transaction(999)

        mock_transaction_repo.delete.assert_not_called()
        assert result is False


# ---------------------------------------------------------------------------
# update_transaction
# ---------------------------------------------------------------------------

class TestUpdateTransaction:
    """Tests for TransactionService.update_transaction."""

    def test_update_existing_transaction(self, transaction_service, mock_transaction_repo):
        """Updating an existing transaction returns the updated dict."""
        original = _make_transaction_mock(id=1, amount=100.0)
        updated = _make_transaction_mock(id=1, amount=200.0)
        mock_transaction_repo.get_by_id.return_value = original
        mock_transaction_repo.update.return_value = updated

        result = transaction_service.update_transaction(1, {"amount": 200.0})

        mock_transaction_repo.update.assert_called_once()
        assert result["amount"] == 200.0

    def test_update_nonexistent_transaction(self, transaction_service, mock_transaction_repo):
        """Updating a non-existent transaction returns None."""
        mock_transaction_repo.get_by_id.return_value = None

        result = transaction_service.update_transaction(999, {"amount": 200.0})

        assert result is None

    def test_update_converts_date_string(self, transaction_service, mock_transaction_repo):
        """String dates in the updates dict are converted to date objects."""
        original = _make_transaction_mock()
        updated = _make_transaction_mock(date=datetime.date(2024, 3, 15))
        mock_transaction_repo.get_by_id.return_value = original
        mock_transaction_repo.update.return_value = updated

        transaction_service.update_transaction(1, {"date": "2024-03-15"})

        call_kwargs = mock_transaction_repo.update.call_args[0][1]
        assert call_kwargs["date"] == datetime.date(2024, 3, 15)


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------

class TestGetBalance:
    """Tests for TransactionService.get_balance."""

    def test_get_balance_delegates_to_repo(self, transaction_service, mock_transaction_repo):
        """get_balance returns the value from the transaction repository."""
        mock_transaction_repo.get_total_balance.return_value = 1500.0

        balance = transaction_service.get_balance()

        mock_transaction_repo.get_total_balance.assert_called_once()
        assert balance == 1500.0

    def test_get_balance_zero(self, transaction_service, mock_transaction_repo):
        """get_balance returns 0.0 when there are no transactions."""
        mock_transaction_repo.get_total_balance.return_value = 0.0

        balance = transaction_service.get_balance()

        assert balance == 0.0


# ---------------------------------------------------------------------------
# _ensure_category_exists
# ---------------------------------------------------------------------------

class TestEnsureCategoryExists:
    """Tests for TransactionService._ensure_category_exists."""

    def test_does_nothing_for_empty_category(self, transaction_service, mock_category_repo):
        """An empty category name is ignored."""
        transaction_service._ensure_category_exists("")
        mock_category_repo.get_by_name.assert_not_called()

    def test_skips_creation_when_category_exists(self, transaction_service, mock_category_repo):
        """If category already exists, create is not called."""
        mock_category_repo.get_by_name.return_value = Mock()

        transaction_service._ensure_category_exists("groceries")

        mock_category_repo.create.assert_not_called()

    def test_creates_category_when_missing(self, transaction_service, mock_category_repo):
        """If category is missing, it is created as an expense category."""
        mock_category_repo.get_by_name.return_value = None

        transaction_service._ensure_category_exists("NewCategory")

        mock_category_repo.create.assert_called_once()
        created_category = mock_category_repo.create.call_args[0][0]
        assert created_category.name == "newcategory"
        assert created_category.type == "expense"

    def test_handles_integrity_error_on_create(self, transaction_service, mock_category_repo, mock_session):
        """IntegrityError during category creation is swallowed (race condition)."""
        mock_category_repo.get_by_name.return_value = None
        mock_category_repo.create.side_effect = IntegrityError("", {}, Exception())

        # Should not raise
        transaction_service._ensure_category_exists("duplicate")
        mock_session.rollback.assert_called_once()
