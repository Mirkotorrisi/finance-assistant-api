"""Tests for AggregationService."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.services.aggregation_service import AggregationService


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def aggregation_service(mock_db_session):
    """Create an AggregationService with mocked DB."""
    with patch('src.services.aggregation_service.get_db_session', return_value=mock_db_session):
        service = AggregationService(db_session=mock_db_session)
        yield service
        service.close()


def test_aggregation_service_initialization(mock_db_session):
    """Test AggregationService initialization."""
    service = AggregationService(db_session=mock_db_session)
    assert service.db == mock_db_session
    assert service.owns_session is False
    service.close()


def test_get_monthly_totals_with_data(aggregation_service, mock_db_session):
    """Test get_monthly_totals with mock data."""
    # Mock snapshot data
    mock_snapshot1 = MagicMock()
    mock_snapshot1.total_income = 5000.0
    mock_snapshot1.total_expense = 3000.0
    
    mock_snapshot2 = MagicMock()
    mock_snapshot2.total_income = 1000.0
    mock_snapshot2.total_expense = 500.0
    
    # Mock query chain
    mock_query = MagicMock()
    mock_query.filter.return_value.all.return_value = [mock_snapshot1, mock_snapshot2]
    mock_db_session.query.return_value = mock_query
    
    # Call method
    result = aggregation_service.get_monthly_totals(2026, 1)
    
    # Verify results
    assert result["total_income"] == 6000.0
    assert result["total_expense"] == 3500.0
    assert result["net_savings"] == 2500.0


def test_get_monthly_totals_empty(aggregation_service, mock_db_session):
    """Test get_monthly_totals with no data."""
    # Mock empty query
    mock_query = MagicMock()
    mock_query.filter.return_value.all.return_value = []
    mock_db_session.query.return_value = mock_query
    
    result = aggregation_service.get_monthly_totals(2026, 1)
    
    assert result["total_income"] == 0.0
    assert result["total_expense"] == 0.0
    assert result["net_savings"] == 0.0


def test_get_net_worth(aggregation_service, mock_db_session):
    """Test get_net_worth calculation."""
    # Mock query result
    mock_query = MagicMock()
    mock_query.filter.return_value.scalar.return_value = 50000.0
    mock_db_session.query.return_value = mock_query
    
    result = aggregation_service.get_net_worth(2026, 1)
    
    assert result == 50000.0


def test_get_net_worth_no_data(aggregation_service, mock_db_session):
    """Test get_net_worth with no data."""
    # Mock query returning None
    mock_query = MagicMock()
    mock_query.filter.return_value.scalar.return_value = None
    mock_db_session.query.return_value = mock_query
    
    result = aggregation_service.get_net_worth(2026, 1)
    
    assert result == 0.0


def test_get_category_aggregates(aggregation_service, mock_db_session):
    """Test get_category_aggregates."""
    # Mock category results
    mock_result1 = MagicMock()
    mock_result1.category = "food"
    mock_result1.total = -1500.0
    mock_result1.count = 10
    
    mock_result2 = MagicMock()
    mock_result2.category = "transport"
    mock_result2.total = -500.0
    mock_result2.count = 5
    
    # Mock query chain
    mock_query = MagicMock()
    mock_query.filter.return_value.filter.return_value.group_by.return_value.order_by.return_value.all.return_value = [
        mock_result1, mock_result2
    ]
    mock_db_session.query.return_value = mock_query
    
    result = aggregation_service.get_category_aggregates(2026, 1)
    
    assert len(result) == 2
    assert result[0]["category"] == "food"
    assert result[0]["total"] == -1500.0
    assert result[0]["count"] == 10


def test_get_month_over_month_delta(aggregation_service, mock_db_session):
    """Test get_month_over_month_delta calculation."""
    # We need to mock get_monthly_totals and get_net_worth
    with patch.object(aggregation_service, 'get_monthly_totals') as mock_totals, \
         patch.object(aggregation_service, 'get_net_worth') as mock_net_worth:
        
        # Mock current month
        mock_totals.side_effect = [
            {"total_income": 6000.0, "total_expense": 4000.0, "net_savings": 2000.0},  # Current
            {"total_income": 5000.0, "total_expense": 3000.0, "net_savings": 2000.0}   # Previous
        ]
        mock_net_worth.side_effect = [50000.0, 48000.0]  # Current, Previous
        
        result = aggregation_service.get_month_over_month_delta(2026, 2)
        
        assert result["income_delta"] == 1000.0
        assert result["expense_delta"] == 1000.0
        assert result["net_worth_delta"] == 2000.0
        assert result["previous_month"] == 1
        assert result["previous_year"] == 2026


def test_detect_anomalies(aggregation_service, mock_db_session):
    """Test detect_anomalies."""
    # Mock get_category_aggregates
    with patch.object(aggregation_service, 'get_category_aggregates') as mock_cat_agg:
        mock_cat_agg.return_value = [
            {"category": "food", "total": -3000.0, "count": 10}  # High spending
        ]
        
        # Mock historical query
        mock_query = MagicMock()
        mock_query.filter.return_value.filter.return_value.filter.return_value.filter.return_value.group_by.return_value.scalar.return_value = -1000.0
        mock_db_session.query.return_value = mock_query
        
        result = aggregation_service.detect_anomalies(2026, 6, threshold_multiplier=1.5)
        
        # Should detect food as anomaly (3000 > 1000 * 1.5)
        assert len(result) > 0
        assert result[0]["category"] == "food"
        assert result[0]["is_high"] is True


def test_get_yearly_summary(aggregation_service, mock_db_session):
    """Test get_yearly_summary."""
    with patch.object(aggregation_service, 'get_monthly_totals') as mock_totals, \
         patch.object(aggregation_service, 'get_net_worth') as mock_net_worth, \
         patch.object(aggregation_service, 'get_category_aggregates') as mock_cat_agg:
        
        # Mock 12 months of data
        mock_totals.return_value = {
            "total_income": 5000.0,
            "total_expense": 3000.0,
            "net_savings": 2000.0
        }
        mock_net_worth.return_value = 50000.0
        mock_cat_agg.return_value = [
            {"category": "food", "total": -12000.0, "count": 120}
        ]
        
        result = aggregation_service.get_yearly_summary(2026)
        
        assert result["year"] == 2026
        assert result["total_income"] == 60000.0  # 5000 * 12
        assert result["total_expense"] == 36000.0  # 3000 * 12
        assert len(result["monthly_data"]) == 12
        assert len(result["top_expense_categories"]) == 1
