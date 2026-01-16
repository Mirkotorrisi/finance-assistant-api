"""Unit tests for FinancialDataService."""

import pytest
from unittest.mock import MagicMock, patch
from src.services.financial_data_service import FinancialDataService, MONTH_NAMES


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def financial_service(mock_db):
    """Create a FinancialDataService instance with mocked database."""
    return FinancialDataService(session=mock_db)


class TestFinancialDataService:
    """Tests for FinancialDataService."""
    
    def test_service_initialization(self, financial_service):
        """Test that service initializes correctly."""
        assert financial_service is not None
        assert hasattr(financial_service, 'session')
        assert hasattr(financial_service, 'account_repo')
        assert hasattr(financial_service, 'snapshot_repo')
    
    def test_get_financial_data_for_year_method_exists(self, financial_service):
        """Test that get_financial_data_for_year method exists."""
        assert hasattr(financial_service, 'get_financial_data_for_year')
        assert callable(financial_service.get_financial_data_for_year)
    
    def test_month_names_constant(self):
        """Test that month names are correctly defined."""
        assert len(MONTH_NAMES) == 12
        assert MONTH_NAMES[0] == "Jan"
        assert MONTH_NAMES[1] == "Feb"
        assert MONTH_NAMES[11] == "Dec"
    
    def test_get_monthly_data_returns_12_months(self, financial_service, mock_db):
        """Test that _get_monthly_data returns data for all 12 months."""
        # Mock the query results
        mock_result = MagicMock()
        mock_result.net_worth = 1000.0
        mock_result.expenses = 500.0
        mock_result.income = 800.0
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_result
        
        monthly_data = financial_service._get_monthly_data(2026, [])
        
        assert len(monthly_data) == 12
        assert all('month' in data for data in monthly_data)
        assert all('netWorth' in data for data in monthly_data)
        assert all('expenses' in data for data in monthly_data)
        assert all('income' in data for data in monthly_data)
        assert all('net' in data for data in monthly_data)
    
    def test_get_monthly_data_handles_no_data(self, financial_service, mock_db):
        """Test that _get_monthly_data handles months with no data."""
        # Mock the query to return None (no data)
        mock_result = MagicMock()
        mock_result.net_worth = None
        mock_result.expenses = None
        mock_result.income = None
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_result
        
        monthly_data = financial_service._get_monthly_data(2026, [])
        
        assert len(monthly_data) == 12
        # All values should be 0 for months with no data
        assert all(data['netWorth'] == 0.0 for data in monthly_data)
        assert all(data['expenses'] == 0.0 for data in monthly_data)
        assert all(data['income'] == 0.0 for data in monthly_data)
        assert all(data['net'] == 0.0 for data in monthly_data)
    
    def test_get_account_breakdown_categorizes_correctly(self, financial_service):
        """Test that _get_account_breakdown categorizes accounts correctly."""
        from src.database.models import Account
        
        # Create mock accounts of different types
        checking = Account(id=1, name="Checking", type="checking", currency="EUR", is_active=True)
        savings = Account(id=2, name="Savings", type="savings", currency="EUR", is_active=True)
        investment = Account(id=3, name="Investment", type="investment", currency="EUR", is_active=True)
        other = Account(id=4, name="Other", type="other", currency="EUR", is_active=True)
        
        accounts = [checking, savings, investment, other]
        
        # Mock snapshot queries
        mock_snapshot = MagicMock()
        mock_snapshot.ending_balance = 1000.0
        financial_service.session.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_snapshot
        
        breakdown = financial_service._get_account_breakdown(accounts)
        
        assert 'liquidity' in breakdown
        assert 'investments' in breakdown
        assert 'otherAssets' in breakdown
        assert breakdown['liquidity'] == 2000.0  # checking + savings
        assert breakdown['investments'] == 1000.0  # investment
        assert breakdown['otherAssets'] == 1000.0  # other
    
    def test_get_account_breakdown_ignores_negative_balances(self, financial_service):
        """Test that _get_account_breakdown ignores accounts with negative balances."""
        from src.database.models import Account
        
        checking = Account(id=1, name="Checking", type="checking", currency="EUR", is_active=True)
        
        # Mock snapshot with negative balance
        mock_snapshot = MagicMock()
        mock_snapshot.ending_balance = -500.0
        financial_service.session.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_snapshot
        
        breakdown = financial_service._get_account_breakdown([checking])
        
        # Negative balance should not be included
        assert breakdown['liquidity'] == 0.0
        assert breakdown['investments'] == 0.0
        assert breakdown['otherAssets'] == 0.0
    
    def test_get_account_breakdown_handles_no_snapshots(self, financial_service):
        """Test that _get_account_breakdown handles accounts with no snapshots."""
        from src.database.models import Account
        
        checking = Account(id=1, name="Checking", type="checking", currency="EUR", is_active=True)
        
        # Mock query to return None (no snapshots)
        financial_service.session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        
        breakdown = financial_service._get_account_breakdown([checking])
        
        assert breakdown['liquidity'] == 0.0
        assert breakdown['investments'] == 0.0
        assert breakdown['otherAssets'] == 0.0
    
    def test_financial_data_response_structure(self, financial_service, mock_db):
        """Test that get_financial_data_for_year returns correct structure."""
        from src.database.models import Account
        
        # Mock repositories
        financial_service.account_repo.list_all = MagicMock(return_value=[])
        financial_service.snapshot_repo.get_current_total_balance = MagicMock(return_value=5000.0)
        
        # Mock query results for monthly data
        mock_result = MagicMock()
        mock_result.net_worth = 1000.0
        mock_result.expenses = 500.0
        mock_result.income = 800.0
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_result
        
        result = financial_service.get_financial_data_for_year(2026)
        
        assert 'year' in result
        assert 'currentNetWorth' in result
        assert 'netSavings' in result
        assert 'monthlyData' in result
        assert 'accountBreakdown' in result
        assert result['year'] == 2026
        assert isinstance(result['monthlyData'], list)
        assert len(result['monthlyData']) == 12
        assert isinstance(result['accountBreakdown'], dict)


class TestAccountCategorization:
    """Tests for account type categorization."""
    
    def test_liquidity_types(self):
        """Test that liquidity types are correctly defined."""
        from src.services.financial_data_service import LIQUIDITY_TYPES
        
        assert "checking" in LIQUIDITY_TYPES
        assert "savings" in LIQUIDITY_TYPES
        assert "cash" in LIQUIDITY_TYPES
    
    def test_investment_types(self):
        """Test that investment types are correctly defined."""
        from src.services.financial_data_service import INVESTMENT_TYPES
        
        assert "investment" in INVESTMENT_TYPES
        assert "brokerage" in INVESTMENT_TYPES
        assert "retirement" in INVESTMENT_TYPES
    
    def test_other_asset_types(self):
        """Test that other asset types are correctly defined."""
        from src.services.financial_data_service import OTHER_ASSET_TYPES
        
        assert "other" in OTHER_ASSET_TYPES
        assert "asset" in OTHER_ASSET_TYPES
        assert "loan" in OTHER_ASSET_TYPES
