"""Unit tests for AccountService."""

import pytest
from unittest.mock import MagicMock, Mock, patch

from src.services.account_service import AccountService
from src.database.models import Account, Transaction
from tests.mocks.mock_data import MOCK_ACCOUNTS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    """Return a mock SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def mock_account_repo():
    return MagicMock()


@pytest.fixture
def account_service(mock_session, mock_account_repo):
    """Return an AccountService with the repository mocked."""
    service = AccountService(session=mock_session)
    service.account_repo = mock_account_repo
    return service


def _make_account_mock(**kwargs):
    """Build a Mock that mimics an Account ORM object."""
    defaults = dict(
        id=1,
        name="Test Account",
        type="checking",
        currency="EUR",
        is_active=True,
        current_balance=0.0,
    )
    defaults.update(kwargs)
    mock_acc = Mock(spec=Account)
    for k, v in defaults.items():
        setattr(mock_acc, k, v)
    mock_acc.to_dict.return_value = {
        "id": defaults["id"],
        "name": defaults["name"],
        "type": defaults["type"],
        "currency": defaults["currency"],
        "is_active": defaults["is_active"],
        "current_balance": defaults["current_balance"],
    }
    return mock_acc


# ---------------------------------------------------------------------------
# create_account
# ---------------------------------------------------------------------------

class TestCreateAccount:
    """Tests for AccountService.create_account."""

    def test_create_basic_account(self, account_service, mock_account_repo):
        """Creating an account returns the created account dict."""
        mock_acc = _make_account_mock(id=10, name="Checking", type="checking")
        mock_account_repo.create.return_value = mock_acc

        result = account_service.create_account(
            name="Checking",
            account_type="checking",
            currency="EUR",
        )

        mock_account_repo.create.assert_called_once()
        assert result["name"] == "Checking"
        assert result["type"] == "checking"
        assert result["currency"] == "EUR"

    def test_create_account_default_currency(self, account_service, mock_account_repo):
        """Default currency is EUR when not specified."""
        mock_acc = _make_account_mock(currency="EUR")
        mock_account_repo.create.return_value = mock_acc

        account_service.create_account(name="Test", account_type="savings")

        created_acc = mock_account_repo.create.call_args[0][0]
        assert created_acc.currency == "EUR"

    def test_create_account_inactive(self, account_service, mock_account_repo):
        """Accounts can be created as inactive."""
        mock_acc = _make_account_mock(is_active=False)
        mock_account_repo.create.return_value = mock_acc

        result = account_service.create_account(
            name="Closed",
            account_type="checking",
            is_active=False,
        )

        assert result["is_active"] is False

    def test_create_account_with_initial_balance(self, account_service, mock_account_repo):
        """Initial balance is forwarded to the repo model."""
        mock_acc = _make_account_mock(current_balance=500.0)
        mock_account_repo.create.return_value = mock_acc

        account_service.create_account(
            name="Funded",
            account_type="savings",
            current_balance=500.0,
        )

        created_acc = mock_account_repo.create.call_args[0][0]
        assert created_acc.current_balance == 500.0


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------

class TestGetAccount:
    """Tests for AccountService.get_account."""

    def test_get_existing_account(self, account_service, mock_account_repo):
        """Fetching an existing account returns its dict."""
        mock_acc = _make_account_mock(id=1, name="Main Checking")
        mock_account_repo.get_by_id.return_value = mock_acc

        result = account_service.get_account(1)

        assert result is not None
        assert result["id"] == 1
        assert result["name"] == "Main Checking"

    def test_get_nonexistent_account(self, account_service, mock_account_repo):
        """Fetching a non-existent account returns None."""
        mock_account_repo.get_by_id.return_value = None

        result = account_service.get_account(999)

        assert result is None


# ---------------------------------------------------------------------------
# list_accounts
# ---------------------------------------------------------------------------

class TestListAccounts:
    """Tests for AccountService.list_accounts."""

    def test_list_active_only(self, account_service, mock_account_repo):
        """list_accounts(active_only=True) calls repo with active_only=True."""
        mock_accs = [_make_account_mock(id=i) for i in range(1, 4)]
        mock_account_repo.list_all.return_value = mock_accs

        results = account_service.list_accounts(active_only=True)

        mock_account_repo.list_all.assert_called_with(True)
        assert len(results) == 3

    def test_list_all_accounts(self, account_service, mock_account_repo):
        """list_accounts(active_only=False) includes inactive accounts."""
        mock_accs = [_make_account_mock(id=i) for i in range(1, 6)]
        mock_account_repo.list_all.return_value = mock_accs

        results = account_service.list_accounts(active_only=False)

        mock_account_repo.list_all.assert_called_with(False)
        assert len(results) == 5

    def test_list_returns_dicts(self, account_service, mock_account_repo):
        """Each account is returned as a dict."""
        mock_account_repo.list_all.return_value = [_make_account_mock()]

        results = account_service.list_accounts()

        assert isinstance(results[0], dict)


# ---------------------------------------------------------------------------
# update_account
# ---------------------------------------------------------------------------

class TestUpdateAccount:
    """Tests for AccountService.update_account."""

    def test_update_existing_account(self, account_service, mock_account_repo):
        """Updating an existing account returns the updated dict."""
        mock_acc = _make_account_mock(id=1, name="Updated Name")
        mock_account_repo.update.return_value = mock_acc

        result = account_service.update_account(1, {"name": "Updated Name"})

        mock_account_repo.update.assert_called_once_with(1, {"name": "Updated Name"})
        assert result["name"] == "Updated Name"

    def test_update_nonexistent_account(self, account_service, mock_account_repo):
        """Updating a non-existent account returns None."""
        mock_account_repo.update.return_value = None

        result = account_service.update_account(999, {"name": "Ghost"})

        assert result is None


# ---------------------------------------------------------------------------
# delete_account
# ---------------------------------------------------------------------------

class TestDeleteAccount:
    """Tests for AccountService.delete_account."""

    def test_delete_existing_account(self, account_service, mock_account_repo):
        """Soft-deleting an existing account returns True."""
        mock_account_repo.delete.return_value = True

        result = account_service.delete_account(1)

        mock_account_repo.delete.assert_called_once_with(1)
        assert result is True

    def test_delete_nonexistent_account(self, account_service, mock_account_repo):
        """Attempting to delete a non-existent account returns False."""
        mock_account_repo.delete.return_value = False

        result = account_service.delete_account(999)

        assert result is False


# ---------------------------------------------------------------------------
# get_account_balance
# ---------------------------------------------------------------------------

class TestGetAccountBalance:
    """Tests for AccountService.get_account_balance."""

    def test_returns_rounded_balance(self, account_service, mock_session):
        """get_account_balance sums transaction amounts and rounds to 2 dp."""
        mock_session.query.return_value.filter.return_value.scalar.return_value = 1234.5678

        balance = account_service.get_account_balance(1)

        assert balance == 1234.57

    def test_returns_zero_when_no_transactions(self, account_service, mock_session):
        """get_account_balance returns 0.0 when there are no transactions."""
        mock_session.query.return_value.filter.return_value.scalar.return_value = None

        balance = account_service.get_account_balance(1)

        assert balance == 0.0


# ---------------------------------------------------------------------------
# get_total_balance_for_month
# ---------------------------------------------------------------------------

class TestGetTotalBalanceForMonth:
    """Tests for AccountService.get_total_balance_for_month."""

    def test_returns_cumulative_balance(self, account_service, mock_session):
        """Returns cumulative balance up to end of the given month."""
        mock_session.query.return_value.filter.return_value.scalar.return_value = 5000.0

        balance = account_service.get_total_balance_for_month(2024, 1)

        assert balance == 5000.0

    def test_returns_zero_when_no_data(self, account_service, mock_session):
        """Returns 0.0 when there are no transactions."""
        mock_session.query.return_value.filter.return_value.scalar.return_value = None

        balance = account_service.get_total_balance_for_month(2024, 1)

        assert balance == 0.0


# ---------------------------------------------------------------------------
# get_current_total_balance
# ---------------------------------------------------------------------------

class TestGetCurrentTotalBalance:
    """Tests for AccountService.get_current_total_balance."""

    def test_returns_total_balance(self, account_service, mock_session):
        """Returns the sum of all transactions across all accounts."""
        mock_session.query.return_value.scalar.return_value = 10000.0

        balance = account_service.get_current_total_balance()

        assert balance == 10000.0

    def test_returns_zero_when_no_transactions(self, account_service, mock_session):
        """Returns 0.0 when the database is empty."""
        mock_session.query.return_value.scalar.return_value = None

        balance = account_service.get_current_total_balance()

        assert balance == 0.0


# ---------------------------------------------------------------------------
# get_total_expenses_for_month
# ---------------------------------------------------------------------------

class TestGetTotalExpensesForMonth:
    """Tests for AccountService.get_total_expenses_for_month."""

    def test_returns_absolute_expense_sum(self, account_service, mock_session):
        """Returns the absolute sum of negative transactions for the month."""
        mock_session.query.return_value.filter.return_value.scalar.return_value = 350.0

        expenses = account_service.get_total_expenses_for_month(2024, 1)

        assert expenses == 350.0

    def test_returns_zero_when_no_expenses(self, account_service, mock_session):
        """Returns 0.0 when there are no expense transactions."""
        mock_session.query.return_value.filter.return_value.scalar.return_value = None

        expenses = account_service.get_total_expenses_for_month(2024, 1)

        assert expenses == 0.0


# ---------------------------------------------------------------------------
# get_total_income_for_month
# ---------------------------------------------------------------------------

class TestGetTotalIncomeForMonth:
    """Tests for AccountService.get_total_income_for_month."""

    def test_returns_income_sum(self, account_service, mock_session):
        """Returns the sum of positive transactions for the month."""
        mock_session.query.return_value.filter.return_value.scalar.return_value = 3000.0

        income = account_service.get_total_income_for_month(2024, 1)

        assert income == 3000.0

    def test_returns_zero_when_no_income(self, account_service, mock_session):
        """Returns 0.0 when there are no income transactions."""
        mock_session.query.return_value.filter.return_value.scalar.return_value = None

        income = account_service.get_total_income_for_month(2024, 1)

        assert income == 0.0


# ---------------------------------------------------------------------------
# get_balance_trend
# ---------------------------------------------------------------------------

class TestGetBalanceTrend:
    """Tests for AccountService.get_balance_trend."""

    def test_returns_trend_list(self, account_service, mock_session):
        """get_balance_trend returns a list of monthly aggregates."""
        mock_row = Mock()
        mock_row.year = 2024
        mock_row.month = 1
        mock_row.total_income = 3000.0
        mock_row.total_expense = 1000.0
        mock_row.net = 2000.0

        mock_query = MagicMock()
        mock_query.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_row]
        mock_query.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_row]
        mock_session.query.return_value = mock_query

        results = account_service.get_balance_trend()

        assert isinstance(results, list)

    def test_empty_trend_when_no_transactions(self, account_service, mock_session):
        """Returns empty list when there are no transactions."""
        mock_query = MagicMock()
        mock_query.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
        mock_session.query.return_value = mock_query

        results = account_service.get_balance_trend()

        assert results == []

    def test_trend_with_account_filter(self, account_service, mock_session):
        """Passing account_id adds a filter to the query."""
        mock_query = MagicMock()
        mock_query.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
        mock_session.query.return_value = mock_query

        account_service.get_balance_trend(account_id=1)

        # filter should have been called with the account_id condition
        mock_query.filter.assert_called_once()
