"""Tests for FinancialSummaryService."""

import pytest
from datetime import date
from unittest.mock import Mock, MagicMock, patch
from src.services.financial_summary_service import FinancialSummaryService
from src.database.models import Transaction, Account


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def mock_account_service():
    """Create a mock AccountService."""
    return MagicMock()


@pytest.fixture
def financial_summary_service(mock_session, mock_account_service):
    """Create a FinancialSummaryService instance with mocked dependencies."""
    with patch('src.services.financial_summary_service.AccountService', return_value=mock_account_service):
        service = FinancialSummaryService(mock_session)
        service.account_service = mock_account_service
        return service


class TestGetMonthlySummary:
    """Tests for get_monthly_summary method."""
    
    def test_get_monthly_summary_success(self, financial_summary_service, mock_session, mock_account_service):
        """Test successful monthly summary generation."""
        # Mock transactions
        mock_transactions = [
            Mock(amount=1000.0, category="Salary", date=date(2026, 2, 1)),
            Mock(amount=-200.0, category="Food", date=date(2026, 2, 5)),
            Mock(amount=-150.0, category="Transport", date=date(2026, 2, 10)),
            Mock(amount=-100.0, category="Food", date=date(2026, 2, 15)),
        ]
        
        # Mock query chain properly
        mock_filter1 = Mock()
        mock_filter2 = Mock()
        mock_filter2.all.return_value = mock_transactions
        mock_filter1.filter.return_value = mock_filter2
        
        mock_query = Mock()
        mock_query.filter.return_value = mock_filter1
        mock_session.query.return_value = mock_query
        
        # Mock accounts
        mock_account_service.list_accounts.return_value = [
            {"id": 1, "name": "Bank Account", "currency": "EUR"}
        ]
        mock_account_service.get_account_balance.return_value = 5000.0
        
        # Call method
        result = financial_summary_service.get_monthly_summary("2026-02")
        
        # Assertions
        assert result["month"] == "2026-02"
        assert result["income"] == 1000.0
        assert result["expenses"] == 450.0  # 200 + 150 + 100
        assert result["net"] == 550.0  # 1000 - 450
        assert len(result["top_categories"]) == 2
        assert result["top_categories"][0]["name"] == "Food"
        assert result["top_categories"][0]["amount"] == 300.0
        assert result["top_categories"][0]["count"] == 2
        assert len(result["accounts"]) == 1
        assert result["accounts"][0]["balance"] == 5000.0
    
    def test_get_monthly_summary_invalid_format(self, financial_summary_service):
        """Test monthly summary with invalid month format."""
        with pytest.raises(ValueError, match="Invalid month number"):
            financial_summary_service.get_monthly_summary("2026-13")
    
    def test_get_monthly_summary_invalid_month_number(self, financial_summary_service):
        """Test monthly summary with invalid month number."""
        with pytest.raises(ValueError, match="Invalid month number"):
            financial_summary_service.get_monthly_summary("2026-13")
    
    def test_get_monthly_summary_no_transactions(self, financial_summary_service, mock_session, mock_account_service):
        """Test monthly summary with no transactions."""
        # Mock empty transactions properly
        mock_filter1 = Mock()
        mock_filter2 = Mock()
        mock_filter2.all.return_value = []
        mock_filter1.filter.return_value = mock_filter2
        
        mock_query = Mock()
        mock_query.filter.return_value = mock_filter1
        mock_session.query.return_value = mock_query
        
        # Mock accounts
        mock_account_service.list_accounts.return_value = []
        
        # Call method
        result = financial_summary_service.get_monthly_summary("2026-02")
        
        # Assertions
        assert result["income"] == 0.0
        assert result["expenses"] == 0.0
        assert result["net"] == 0.0
        assert len(result["top_categories"]) == 0
        assert len(result["accounts"]) == 0


class TestGetSpendingDistribution:
    """Tests for get_spending_distribution method."""
    
    def test_get_spending_distribution_by_category(self, financial_summary_service, mock_session):
        """Test spending distribution grouped by category."""
        # Mock transactions
        mock_transactions = [
            Mock(amount=-200.0, category="Food", account_id=1),
            Mock(amount=-150.0, category="Transport", account_id=1),
            Mock(amount=-100.0, category="Food", account_id=2),
        ]
        
        # Mock query chain properly
        mock_filter1 = Mock()
        mock_filter2 = Mock()
        mock_filter3 = Mock()
        mock_filter3.all.return_value = mock_transactions
        mock_filter2.filter.return_value = mock_filter3
        mock_filter1.filter.return_value = mock_filter2
        
        mock_query = Mock()
        mock_query.filter.return_value = mock_filter1
        mock_session.query.return_value = mock_query
        
        # Call method
        result = financial_summary_service.get_spending_distribution("2026-01-01", "2026-01-31", "category")
        
        # Assertions
        assert len(result) == 2
        assert result[0]["name"] == "Food"
        assert result[0]["amount"] == 300.0
        assert result[0]["percentage"] == 66.67
        assert result[0]["count"] == 2
        assert result[1]["name"] == "Transport"
        assert result[1]["amount"] == 150.0
        assert result[1]["percentage"] == 33.33
        assert result[1]["count"] == 1
    
    def test_get_spending_distribution_by_account(self, financial_summary_service, mock_session, mock_account_service):
        """Test spending distribution grouped by account."""
        # Mock transactions
        mock_transactions = [
            Mock(amount=-200.0, category="Food", account_id=1),
            Mock(amount=-150.0, category="Transport", account_id=1),
            Mock(amount=-100.0, category="Food", account_id=2),
        ]
        
        # Mock query chain properly
        mock_filter1 = Mock()
        mock_filter2 = Mock()
        mock_filter3 = Mock()
        mock_filter3.all.return_value = mock_transactions
        mock_filter2.filter.return_value = mock_filter3
        mock_filter1.filter.return_value = mock_filter2
        
        mock_query = Mock()
        mock_query.filter.return_value = mock_filter1
        mock_session.query.return_value = mock_query
        
        # Mock accounts
        mock_account_service.list_accounts.return_value = [
            {"id": 1, "name": "Checking"},
            {"id": 2, "name": "Savings"}
        ]
        
        # Call method
        result = financial_summary_service.get_spending_distribution("2026-01-01", "2026-01-31", "account")
        
        # Assertions
        assert len(result) == 2
        assert result[0]["name"] == "Checking"
        assert result[0]["amount"] == 350.0
        assert result[0]["percentage"] == 77.78
        assert result[0]["count"] == 2
    
    def test_get_spending_distribution_invalid_group_by(self, financial_summary_service):
        """Test spending distribution with invalid group_by parameter."""
        with pytest.raises(ValueError, match="Invalid group_by parameter"):
            financial_summary_service.get_spending_distribution("2026-01-01", "2026-01-31", "invalid")
    
    def test_get_spending_distribution_invalid_date_format(self, financial_summary_service):
        """Test spending distribution with invalid date format."""
        with pytest.raises(ValueError, match="Invalid date format"):
            financial_summary_service.get_spending_distribution("2026-01", "2026-01-31", "category")
    
    def test_get_spending_distribution_no_transactions(self, financial_summary_service, mock_session):
        """Test spending distribution with no transactions."""
        # Mock empty transactions properly
        mock_filter1 = Mock()
        mock_filter2 = Mock()
        mock_filter3 = Mock()
        mock_filter3.all.return_value = []
        mock_filter2.filter.return_value = mock_filter3
        mock_filter1.filter.return_value = mock_filter2
        
        mock_query = Mock()
        mock_query.filter.return_value = mock_filter1
        mock_session.query.return_value = mock_query
        
        # Call method
        result = financial_summary_service.get_spending_distribution("2026-01-01", "2026-01-31", "category")
        
        # Assertions
        assert len(result) == 0


class TestGetAccountBreakdown:
    """Tests for get_account_breakdown method."""
    
    def test_get_account_breakdown_success(self, financial_summary_service, mock_account_service):
        """Test successful account breakdown generation."""
        # Mock accounts
        mock_account_service.list_accounts.return_value = [
            {"id": 1, "name": "Checking", "currency": "EUR"},
            {"id": 2, "name": "Savings", "currency": "EUR"},
            {"id": 3, "name": "Investment", "currency": "USD"}
        ]
        
        # Mock balances
        def mock_get_balance(account_id):
            balances = {1: 5000.0, 2: 3000.0, 3: 2000.0}
            return balances.get(account_id, 0.0)
        
        mock_account_service.get_account_balance.side_effect = mock_get_balance
        
        # Call method
        result = financial_summary_service.get_account_breakdown()
        
        # Assertions
        assert len(result) == 3
        assert result[0]["account_name"] == "Checking"
        assert result[0]["balance"] == 5000.0
        assert result[0]["percentage"] == 50.0
        assert result[1]["account_name"] == "Savings"
        assert result[1]["balance"] == 3000.0
        assert result[1]["percentage"] == 30.0
        assert result[2]["account_name"] == "Investment"
        assert result[2]["balance"] == 2000.0
        assert result[2]["percentage"] == 20.0
    
    def test_get_account_breakdown_no_accounts(self, financial_summary_service, mock_account_service):
        """Test account breakdown with no accounts."""
        # Mock empty accounts
        mock_account_service.list_accounts.return_value = []
        
        # Call method
        result = financial_summary_service.get_account_breakdown()
        
        # Assertions
        assert len(result) == 0
    
    def test_get_account_breakdown_zero_balances(self, financial_summary_service, mock_account_service):
        """Test account breakdown with zero balances."""
        # Mock accounts
        mock_account_service.list_accounts.return_value = [
            {"id": 1, "name": "Checking", "currency": "EUR"}
        ]
        
        # Mock zero balance
        mock_account_service.get_account_balance.return_value = 0.0
        
        # Call method
        result = financial_summary_service.get_account_breakdown()
        
        # Assertions
        assert len(result) == 0  # Accounts with zero balance are excluded
