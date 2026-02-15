"""Tests for FinancialSummaryService."""

import pytest
from datetime import date
from unittest.mock import MagicMock, Mock
from src.services.financial_summary_service import FinancialSummaryService
from src.database.models import MonthlyAccountSnapshot, Account, Transaction


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def financial_summary_service(mock_session):
    """Create a FinancialSummaryService instance with mocked database."""
    return FinancialSummaryService(session=mock_session)


class TestGetMonthlySummary:
    """Tests for get_monthly_summary method."""
    
    def test_valid_month_format(self, financial_summary_service, mock_session):
        """Test with valid month format."""
        # Mock query results
        mock_result = Mock()
        mock_result.income = 5000.0
        mock_result.expenses = 3000.0
        
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_result
        mock_session.query.return_value = mock_query
        
        # Mock top categories query
        financial_summary_service._get_top_categories = MagicMock(return_value=[
            {"category": "Groceries", "amount": 500.0, "count": 10},
            {"category": "Rent", "amount": 1200.0, "count": 1}
        ])
        
        result = financial_summary_service.get_monthly_summary("2024-01")
        
        assert result["month"] == "2024-01"
        assert result["income"] == 5000.0
        assert result["expenses"] == 3000.0
        assert result["net"] == 2000.0
        assert len(result["top_categories"]) == 2
    
    def test_invalid_month_format(self, financial_summary_service):
        """Test with invalid month format."""
        with pytest.raises(ValueError, match="Invalid month format"):
            financial_summary_service.get_monthly_summary("2024/01")
        
        with pytest.raises(ValueError, match="Invalid month format"):
            financial_summary_service.get_monthly_summary("202401")
        
        with pytest.raises(ValueError, match="Invalid month format"):
            financial_summary_service.get_monthly_summary("invalid")
    
    def test_no_data_for_month(self, financial_summary_service, mock_session):
        """Test when no data exists for the month."""
        mock_result = Mock()
        mock_result.income = None
        mock_result.expenses = None
        
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_result
        mock_session.query.return_value = mock_query
        
        financial_summary_service._get_top_categories = MagicMock(return_value=[])
        
        result = financial_summary_service.get_monthly_summary("2024-01")
        
        assert result["income"] == 0.0
        assert result["expenses"] == 0.0
        assert result["net"] == 0.0
        assert result["top_categories"] == []


class TestGetSpendingDistribution:
    """Tests for get_spending_distribution method."""
    
    def test_valid_date_range_category_grouping(self, financial_summary_service, mock_session):
        """Test with valid date range and category grouping."""
        # Mock transactions
        txn1 = Mock()
        txn1.amount = -100.0
        txn1.category = "Groceries"
        txn1.account_id = 1
        
        txn2 = Mock()
        txn2.amount = -200.0
        txn2.category = "Groceries"
        txn2.account_id = 1
        
        txn3 = Mock()
        txn3.amount = -150.0
        txn3.category = "Transportation"
        txn3.account_id = 2
        
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [txn1, txn2, txn3]
        mock_session.query.return_value = mock_query
        
        result = financial_summary_service.get_spending_distribution(
            "2024-01-01", "2024-01-31", "category"
        )
        
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-01-31"
        assert result["group_by"] == "category"
        assert result["total_amount"] == 450.0
        assert len(result["distribution"]) == 2
        
        # Verify Groceries is first (highest amount)
        assert result["distribution"][0]["name"] == "Groceries"
        assert result["distribution"][0]["amount"] == 300.0
        assert result["distribution"][0]["count"] == 2
        assert round(result["distribution"][0]["percent"], 2) == 66.67
        
        # Verify Transportation is second
        assert result["distribution"][1]["name"] == "Transportation"
        assert result["distribution"][1]["amount"] == 150.0
        assert result["distribution"][1]["count"] == 1
        assert round(result["distribution"][1]["percent"], 2) == 33.33
    
    def test_valid_date_range_account_grouping(self, financial_summary_service, mock_session):
        """Test with account grouping."""
        txn1 = Mock()
        txn1.amount = -100.0
        txn1.category = "Groceries"
        txn1.account_id = 1
        
        txn2 = Mock()
        txn2.amount = -200.0
        txn2.category = "Transportation"
        txn2.account_id = 2
        
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [txn1, txn2]
        mock_session.query.return_value = mock_query
        
        result = financial_summary_service.get_spending_distribution(
            "2024-01-01", "2024-01-31", "account"
        )
        
        assert result["group_by"] == "account"
        assert len(result["distribution"]) == 2
        assert "Account 1" in [d["name"] for d in result["distribution"]]
        assert "Account 2" in [d["name"] for d in result["distribution"]]
    
    def test_invalid_date_format(self, financial_summary_service):
        """Test with invalid date format."""
        with pytest.raises(ValueError, match="Invalid date format"):
            financial_summary_service.get_spending_distribution(
                "2024/01/01", "2024-01-31", "category"
            )
        
        with pytest.raises(ValueError, match="Invalid date format"):
            financial_summary_service.get_spending_distribution(
                "2024-01-01", "invalid", "category"
            )
    
    def test_invalid_group_by(self, financial_summary_service):
        """Test with invalid group_by parameter."""
        with pytest.raises(ValueError, match="group_by must be"):
            financial_summary_service.get_spending_distribution(
                "2024-01-01", "2024-01-31", "invalid"
            )
    
    def test_no_transactions(self, financial_summary_service, mock_session):
        """Test when no transactions exist in the date range."""
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []
        mock_session.query.return_value = mock_query
        
        result = financial_summary_service.get_spending_distribution(
            "2024-01-01", "2024-01-31", "category"
        )
        
        assert result["total_amount"] == 0.0
        assert result["distribution"] == []


class TestGetAccountBreakdown:
    """Tests for get_account_breakdown method."""
    
    def test_with_multiple_accounts(self, financial_summary_service, mock_session):
        """Test with multiple accounts of different types."""
        # Mock snapshots
        snap1 = Mock()
        snap1.account_id = 1
        snap1.ending_balance = 5000.0
        snap1.name = "Checking Account"
        snap1.type = "checking"
        snap1.currency = "EUR"
        
        snap2 = Mock()
        snap2.account_id = 2
        snap2.ending_balance = 10000.0
        snap2.name = "Investment Account"
        snap2.type = "investment"
        snap2.currency = "EUR"
        
        snap3 = Mock()
        snap3.account_id = 3
        snap3.ending_balance = 2000.0
        snap3.name = "Savings Account"
        snap3.type = "savings"
        snap3.currency = "EUR"
        
        mock_query = MagicMock()
        mock_query.join.return_value.join.return_value.filter.return_value.all.return_value = [
            snap1, snap2, snap3
        ]
        mock_session.query.return_value = mock_query
        
        result = financial_summary_service.get_account_breakdown()
        
        assert result["total_balance"] == 17000.0
        assert result["by_type"]["liquidity"]["amount"] == 7000.0
        assert result["by_type"]["investments"]["amount"] == 10000.0
        assert result["by_type"]["other"]["amount"] == 0.0
        
        # Verify percentages
        assert round(result["by_type"]["liquidity"]["percent"], 2) == 41.18
        assert round(result["by_type"]["investments"]["percent"], 2) == 58.82
        
        # Verify accounts list
        assert len(result["accounts"]) == 3
        
        # First account should be Investment (highest balance)
        assert result["accounts"][0]["name"] == "Investment Account"
        assert result["accounts"][0]["balance"] == 10000.0
        assert result["accounts"][0]["category"] == "investments"
    
    def test_no_accounts(self, financial_summary_service, mock_session):
        """Test when no accounts exist."""
        mock_query = MagicMock()
        mock_query.join.return_value.join.return_value.filter.return_value.all.return_value = []
        mock_session.query.return_value = mock_query
        
        result = financial_summary_service.get_account_breakdown()
        
        assert result["total_balance"] == 0.0
        assert result["by_type"]["liquidity"]["amount"] == 0.0
        assert result["by_type"]["investments"]["amount"] == 0.0
        assert result["by_type"]["other"]["amount"] == 0.0
        assert result["accounts"] == []


class TestGetTopCategories:
    """Tests for _get_top_categories helper method."""
    
    def test_get_top_categories(self, financial_summary_service, mock_session):
        """Test getting top categories."""
        mock_row1 = Mock()
        mock_row1.category = "Groceries"
        mock_row1.total_amount = 500.0
        mock_row1.count = 10
        
        mock_row2 = Mock()
        mock_row2.category = "Rent"
        mock_row2.total_amount = 1200.0
        mock_row2.count = 1
        
        mock_query = MagicMock()
        mock_query.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_row1, mock_row2
        ]
        mock_session.query.return_value = mock_query
        
        result = financial_summary_service._get_top_categories(2024, 1, limit=5)
        
        assert len(result) == 2
        assert result[0]["category"] == "Groceries"
        assert result[0]["amount"] == 500.0
        assert result[0]["count"] == 10


class TestAccountTypeConstants:
    """Test service constants."""
    
    def test_liquidity_types(self):
        """Test liquidity account types."""
        assert "checking" in FinancialSummaryService.LIQUIDITY_TYPES
        assert "savings" in FinancialSummaryService.LIQUIDITY_TYPES
        assert "cash" in FinancialSummaryService.LIQUIDITY_TYPES
    
    def test_investment_types(self):
        """Test investment account types."""
        assert "investment" in FinancialSummaryService.INVESTMENT_TYPES
        assert "brokerage" in FinancialSummaryService.INVESTMENT_TYPES
        assert "retirement" in FinancialSummaryService.INVESTMENT_TYPES
