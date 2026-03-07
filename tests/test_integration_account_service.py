"""Integration tests for AccountService using an in-memory SQLite database."""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, Account, Transaction, Category
from src.services.account_service import AccountService
from tests.mocks.mock_data import MOCK_ACCOUNTS, MOCK_TRANSACTIONS, MOCK_CATEGORIES


# ---------------------------------------------------------------------------
# Session fixtures
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
    """Return an AccountService backed by the seeded database."""
    return AccountService(session=seeded_session)


@pytest.fixture
def empty_service(db_session):
    """Return an AccountService backed by an empty in-memory database."""
    return AccountService(session=db_session)


# ---------------------------------------------------------------------------
# create_account
# ---------------------------------------------------------------------------

class TestCreateAccountIntegration:
    """Integration tests for AccountService.create_account."""

    def test_create_account_persists(self, empty_service, db_session):
        """A created account is stored in the database."""
        result = empty_service.create_account(
            name="Checking Account",
            account_type="checking",
            currency="USD",
        )

        assert result["id"] is not None
        assert result["name"] == "Checking Account"
        stored = db_session.query(Account).filter_by(id=result["id"]).first()
        assert stored is not None
        assert stored.name == "Checking Account"

    def test_create_account_defaults(self, empty_service):
        """Default values (EUR, active, 0 balance) are applied correctly."""
        result = empty_service.create_account(name="Test", account_type="savings")

        assert result["currency"] == "EUR"
        assert result["is_active"] is True
        assert result["current_balance"] == 0.0

    def test_create_multiple_accounts(self, empty_service, db_session):
        """Multiple accounts can be created independently."""
        empty_service.create_account(name="Account A", account_type="checking")
        empty_service.create_account(name="Account B", account_type="savings")

        count = db_session.query(Account).count()
        assert count == 2


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------

class TestGetAccountIntegration:
    """Integration tests for AccountService.get_account."""

    def test_get_existing_account(self, service):
        """Fetching an existing account returns its data."""
        result = service.get_account(MOCK_ACCOUNTS[0]["id"])

        assert result is not None
        assert result["id"] == MOCK_ACCOUNTS[0]["id"]
        assert result["name"] == MOCK_ACCOUNTS[0]["name"]

    def test_get_nonexistent_account(self, service):
        """Fetching a non-existent account returns None."""
        result = service.get_account(99999)
        assert result is None


# ---------------------------------------------------------------------------
# list_accounts
# ---------------------------------------------------------------------------

class TestListAccountsIntegration:
    """Integration tests for AccountService.list_accounts."""

    def test_list_active_accounts(self, service):
        """list_accounts(active_only=True) returns only active accounts."""
        results = service.list_accounts(active_only=True)
        assert all(r["is_active"] for r in results)
        # Mock data has 4 active + 1 inactive
        active_count = sum(1 for a in MOCK_ACCOUNTS if a["is_active"])
        assert len(results) == active_count

    def test_list_all_accounts(self, service):
        """list_accounts(active_only=False) returns all accounts including inactive."""
        results = service.list_accounts(active_only=False)
        assert len(results) == len(MOCK_ACCOUNTS)

    def test_list_accounts_returns_dicts(self, service):
        """Each account in the list is returned as a dict."""
        results = service.list_accounts()
        required_keys = {"id", "name", "type", "currency", "is_active", "current_balance"}
        for r in results:
            assert required_keys.issubset(r.keys())


# ---------------------------------------------------------------------------
# update_account
# ---------------------------------------------------------------------------

class TestUpdateAccountIntegration:
    """Integration tests for AccountService.update_account."""

    def test_update_account_name(self, service, seeded_session):
        """Updating the name field persists the change."""
        account_id = MOCK_ACCOUNTS[0]["id"]
        result = service.update_account(account_id, {"name": "Renamed Account"})

        assert result is not None
        assert result["name"] == "Renamed Account"
        stored = seeded_session.query(Account).filter_by(id=account_id).first()
        assert stored.name == "Renamed Account"

    def test_update_account_deactivate(self, service, seeded_session):
        """Setting is_active=False persists the deactivation."""
        account_id = MOCK_ACCOUNTS[0]["id"]
        result = service.update_account(account_id, {"is_active": False})

        assert result is not None
        assert result["is_active"] is False

    def test_update_nonexistent_account(self, service):
        """Updating a non-existent account returns None."""
        result = service.update_account(99999, {"name": "Ghost"})
        assert result is None


# ---------------------------------------------------------------------------
# delete_account
# ---------------------------------------------------------------------------

class TestDeleteAccountIntegration:
    """Integration tests for AccountService.delete_account."""

    def test_delete_account_soft_deletes(self, service, seeded_session):
        """Deleting an account sets is_active=False (soft delete)."""
        account_id = MOCK_ACCOUNTS[0]["id"]
        result = service.delete_account(account_id)

        assert result is True
        stored = seeded_session.query(Account).filter_by(id=account_id).first()
        assert stored is not None  # Record still exists
        assert stored.is_active is False

    def test_deleted_account_excluded_from_active_list(self, service):
        """A soft-deleted account is excluded from the active accounts list."""
        account_id = MOCK_ACCOUNTS[0]["id"]
        service.delete_account(account_id)

        active_accounts = service.list_accounts(active_only=True)
        assert not any(a["id"] == account_id for a in active_accounts)

    def test_delete_nonexistent_account(self, service):
        """Deleting a non-existent account returns False."""
        result = service.delete_account(99999)
        assert result is False


# ---------------------------------------------------------------------------
# get_account_balance
# ---------------------------------------------------------------------------

class TestGetAccountBalanceIntegration:
    """Integration tests for AccountService.get_account_balance."""

    def test_balance_equals_sum_of_transactions(self, service):
        """Account balance equals the sum of all its transactions."""
        account_id = 1
        expected = sum(
            t["amount"] for t in MOCK_TRANSACTIONS if t["account_id"] == account_id
        )
        balance = service.get_account_balance(account_id)
        assert abs(balance - round(expected, 2)) < 0.01

    def test_balance_zero_for_empty_account(self, empty_service, db_session):
        """Account balance is 0.0 when no transactions exist."""
        db_session.add(Account(id=1, name="Empty", type="checking", currency="EUR"))
        db_session.commit()

        balance = empty_service.get_account_balance(1)
        assert balance == 0.0


# ---------------------------------------------------------------------------
# get_total_balance_for_month
# ---------------------------------------------------------------------------

class TestGetTotalBalanceForMonthIntegration:
    """Integration tests for AccountService.get_total_balance_for_month."""

    def test_cumulative_balance_up_to_month(self, service):
        """Returns cumulative balance for all transactions up to end of month."""
        # Sum all mock transactions that are <= 2024-01
        expected = sum(
            t["amount"] for t in MOCK_TRANSACTIONS
            if t["date"] <= date(2024, 1, 31)
        )
        balance = service.get_total_balance_for_month(2024, 1)
        assert abs(balance - round(expected, 2)) < 0.01

    def test_balance_for_month_with_no_data(self, service):
        """Returns 0.0 for a month that has no transactions."""
        balance = service.get_total_balance_for_month(2020, 6)
        assert balance == 0.0


# ---------------------------------------------------------------------------
# get_current_total_balance
# ---------------------------------------------------------------------------

class TestGetCurrentTotalBalanceIntegration:
    """Integration tests for AccountService.get_current_total_balance."""

    def test_total_balance_equals_all_transactions(self, service):
        """get_current_total_balance equals the sum of all transaction amounts."""
        expected = sum(t["amount"] for t in MOCK_TRANSACTIONS)
        balance = service.get_current_total_balance()
        assert abs(balance - round(expected, 2)) < 0.01

    def test_total_balance_zero_when_empty(self, empty_service):
        """Returns 0.0 when there are no transactions."""
        balance = empty_service.get_current_total_balance()
        assert balance == 0.0


# ---------------------------------------------------------------------------
# get_total_expenses_for_month
# ---------------------------------------------------------------------------

class TestGetTotalExpensesForMonthIntegration:
    """Integration tests for AccountService.get_total_expenses_for_month."""

    def test_expenses_are_positive_absolute_values(self, service):
        """Total expenses for a month is the absolute sum of negative transactions."""
        expected = sum(
            abs(t["amount"]) for t in MOCK_TRANSACTIONS
            if t["amount"] < 0
            and t["date"].year == 2024
            and t["date"].month == 1
        )
        expenses = service.get_total_expenses_for_month(2024, 1)
        assert abs(expenses - round(expected, 2)) < 0.01

    def test_expenses_zero_for_empty_month(self, service):
        """Returns 0.0 for a month with no expense transactions."""
        expenses = service.get_total_expenses_for_month(2020, 6)
        assert expenses == 0.0


# ---------------------------------------------------------------------------
# get_total_income_for_month
# ---------------------------------------------------------------------------

class TestGetTotalIncomeForMonthIntegration:
    """Integration tests for AccountService.get_total_income_for_month."""

    def test_income_for_month(self, service):
        """Returns the sum of positive transactions for the given month."""
        expected = sum(
            t["amount"] for t in MOCK_TRANSACTIONS
            if t["amount"] > 0
            and t["date"].year == 2024
            and t["date"].month == 1
        )
        income = service.get_total_income_for_month(2024, 1)
        assert abs(income - round(expected, 2)) < 0.01

    def test_income_zero_for_empty_month(self, service):
        """Returns 0.0 for a month with no income transactions."""
        income = service.get_total_income_for_month(2020, 6)
        assert income == 0.0


# ---------------------------------------------------------------------------
# get_balance_trend
# ---------------------------------------------------------------------------

class TestGetBalanceTrendIntegration:
    """Integration tests for AccountService.get_balance_trend."""

    def test_trend_returns_list_of_dicts(self, service):
        """get_balance_trend returns a list of monthly aggregate dicts."""
        results = service.get_balance_trend()
        assert isinstance(results, list)
        if results:
            required_keys = {"year", "month", "total_income", "total_expense", "net"}
            assert required_keys.issubset(results[0].keys())

    def test_trend_ordered_most_recent_first(self, service):
        """Results are ordered with the most recent month first."""
        results = service.get_balance_trend()
        if len(results) >= 2:
            assert (results[0]["year"], results[0]["month"]) >= (results[1]["year"], results[1]["month"])

    def test_trend_filtered_by_account(self, service):
        """Passing account_id only returns trend data for that account."""
        results_all = service.get_balance_trend()
        results_acc1 = service.get_balance_trend(account_id=1)
        # Account 1 has transactions so its filtered list should be non-empty
        assert len(results_acc1) > 0
        # The totals for a single account should be <= the totals for all accounts
        if results_all and results_acc1:
            total_income_all = sum(r["total_income"] for r in results_all)
            total_income_acc1 = sum(r["total_income"] for r in results_acc1)
            assert total_income_acc1 <= total_income_all

    def test_trend_empty_when_no_transactions(self, empty_service):
        """Returns empty list when no transactions exist."""
        results = empty_service.get_balance_trend()
        assert results == []

    def test_trend_respects_num_months(self, service):
        """num_months parameter limits the number of results returned."""
        results = service.get_balance_trend(num_months=1)
        assert len(results) <= 1
