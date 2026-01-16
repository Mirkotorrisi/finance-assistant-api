"""Tests for financial data service."""

import pytest
from unittest.mock import MagicMock, Mock
from src.services.financial_data_service import FinancialDataService
from src.database.models import MonthlyAccountSnapshot, Account


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def financial_service(mock_session):
    """Create a FinancialDataService instance with mocked database."""
    return FinancialDataService(session=mock_session)


class TestFinancialDataService:
    """Tests for FinancialDataService."""
    
    def test_month_names_mapping(self):
        """Test that month names mapping is correct."""
        assert FinancialDataService.MONTH_NAMES[1] == "Jan"
        assert FinancialDataService.MONTH_NAMES[2] == "Feb"
        assert FinancialDataService.MONTH_NAMES[12] == "Dec"
    
    def test_account_type_categorization(self):
        """Test that account types are categorized correctly."""
        assert "checking" in FinancialDataService.LIQUIDITY_TYPES
        assert "savings" in FinancialDataService.LIQUIDITY_TYPES
        assert "investment" in FinancialDataService.INVESTMENT_TYPES
        assert "brokerage" in FinancialDataService.INVESTMENT_TYPES
    
    def test_empty_response_structure(self, financial_service):
        """Test that empty response has correct structure."""
        result = financial_service._empty_response(2024)
        
        assert result["year"] == 2024
        assert result["currentNetWorth"] == 0.0
        assert result["netSavings"] == 0.0
        assert len(result["monthlyData"]) == 12
        assert result["monthlyData"][0]["month"] == "Jan"
        assert result["monthlyData"][11]["month"] == "Dec"
        assert "accountBreakdown" in result
        assert result["accountBreakdown"]["liquidity"] == 0.0
        assert result["accountBreakdown"]["investments"] == 0.0
        assert result["accountBreakdown"]["otherAssets"] == 0.0
    
    def test_calculate_net_savings(self, financial_service):
        """Test net savings calculation from monthly data."""
        monthly_data = [
            {"month": "Jan", "netWorth": 1000, "expenses": 200, "income": 300, "net": 100},
            {"month": "Feb", "netWorth": 1100, "expenses": 150, "income": 250, "net": 100},
            {"month": "Mar", "netWorth": 1150, "expenses": 180, "income": 230, "net": 50}
        ]
        
        net_savings = financial_service._calculate_net_savings(monthly_data)
        assert net_savings == 250.0
    
    def test_get_financial_data_no_data(self, financial_service, mock_session):
        """Test that get_financial_data returns empty response when no data exists."""
        # Mock query to return empty list
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []
        mock_session.query.return_value = mock_query
        
        result = financial_service.get_financial_data(2024)
        
        assert result["year"] == 2024
        assert result["currentNetWorth"] == 0.0
        assert result["netSavings"] == 0.0
        assert len(result["monthlyData"]) == 12
    
    def test_service_has_required_methods(self, financial_service):
        """Test that service has all required methods."""
        assert hasattr(financial_service, 'get_financial_data')
        assert callable(financial_service.get_financial_data)
        assert hasattr(financial_service, '_calculate_monthly_data')
        assert hasattr(financial_service, '_calculate_account_breakdown')
        assert hasattr(financial_service, '_calculate_current_net_worth')
        assert hasattr(financial_service, '_calculate_net_savings')


class TestFinancialDataResponseModels:
    """Tests for response models."""
    
    def test_monthly_data_response_model(self):
        """Test MonthlyDataResponse model."""
        from src.api.app import MonthlyDataResponse
        
        data = MonthlyDataResponse(
            month="Jan",
            netWorth=1000.0,
            expenses=200.0,
            income=300.0,
            net=100.0
        )
        
        assert data.month == "Jan"
        assert data.netWorth == 1000.0
        assert data.expenses == 200.0
        assert data.income == 300.0
        assert data.net == 100.0
    
    def test_account_breakdown_response_model(self):
        """Test AccountBreakdownResponse model."""
        from src.api.app import AccountBreakdownResponse
        
        data = AccountBreakdownResponse(
            liquidity=1000.0,
            investments=2000.0,
            otherAssets=500.0
        )
        
        assert data.liquidity == 1000.0
        assert data.investments == 2000.0
        assert data.otherAssets == 500.0
    
    def test_financial_data_response_model(self):
        """Test FinancialDataResponse model."""
        from src.api.app import FinancialDataResponse, MonthlyDataResponse, AccountBreakdownResponse
        
        monthly = [
            MonthlyDataResponse(month="Jan", netWorth=1000.0, expenses=200.0, income=300.0, net=100.0)
        ]
        breakdown = AccountBreakdownResponse(liquidity=500.0, investments=500.0, otherAssets=0.0)
        
        data = FinancialDataResponse(
            year=2024,
            currentNetWorth=1000.0,
            netSavings=100.0,
            monthlyData=monthly,
            accountBreakdown=breakdown
        )
        
        assert data.year == 2024
        assert data.currentNetWorth == 1000.0
        assert data.netSavings == 100.0
        assert len(data.monthlyData) == 1
        assert data.accountBreakdown.liquidity == 500.0
