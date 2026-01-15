"""Tests for NarrativeGenerator."""

import pytest
from unittest.mock import MagicMock, patch

from src.services.narrative_generator import NarrativeGenerator


@pytest.fixture
def mock_aggregation_service():
    """Create a mock AggregationService."""
    return MagicMock()


@pytest.fixture
def narrative_generator(mock_aggregation_service):
    """Create a NarrativeGenerator with mocked AggregationService."""
    with patch('src.services.narrative_generator.AggregationService', return_value=mock_aggregation_service):
        generator = NarrativeGenerator()
        generator.aggregation_service = mock_aggregation_service
        yield generator
        generator.close()


def test_narrative_generator_initialization():
    """Test NarrativeGenerator initialization."""
    with patch('src.services.narrative_generator.AggregationService'):
        generator = NarrativeGenerator()
        assert generator.aggregation_service is not None
        generator.close()


def test_generate_monthly_summary(narrative_generator, mock_aggregation_service):
    """Test generate_monthly_summary with data."""
    # Mock aggregation data
    mock_aggregation_service.get_monthly_totals.return_value = {
        "total_income": 5000.0,
        "total_expense": 3000.0,
        "net_savings": 2000.0
    }
    mock_aggregation_service.get_net_worth.return_value = 50000.0
    mock_aggregation_service.get_month_over_month_delta.return_value = {
        "income_delta": 500.0,
        "expense_delta": 300.0,
        "net_worth_delta": 2000.0,
        "income_pct_change": 10.0,
        "expense_pct_change": 11.0,
        "net_worth_pct_change": 4.2,
        "previous_month": 2,
        "previous_year": 2026
    }
    
    result = narrative_generator.generate_monthly_summary(2026, 3)
    
    assert result is not None
    assert result["type"] == "monthly_summary"
    assert "March 2026" in result["text"]
    assert "€5000.00" in result["text"] or "5000" in result["text"]
    assert "€3000.00" in result["text"] or "3000" in result["text"]
    assert result["metadata"]["year"] == 2026
    assert result["metadata"]["month"] == 3


def test_generate_monthly_summary_no_data(narrative_generator, mock_aggregation_service):
    """Test generate_monthly_summary with no data."""
    # Mock no data
    mock_aggregation_service.get_monthly_totals.return_value = {
        "total_income": 0.0,
        "total_expense": 0.0,
        "net_savings": 0.0
    }
    
    result = narrative_generator.generate_monthly_summary(2026, 3)
    
    assert result is None


def test_generate_category_summary(narrative_generator, mock_aggregation_service):
    """Test generate_category_summary."""
    # Mock category aggregates
    mock_aggregation_service.get_category_aggregates.side_effect = [
        # Yearly data
        [
            {"category": "food", "total": -12000.0, "count": 100},
            {"category": "transport", "total": -5000.0, "count": 50}
        ],
        # Monthly data (called 12 times)
        *[
            [{"category": "food", "total": -1000.0, "count": 10}]
            for _ in range(12)
        ]
    ]
    
    result = narrative_generator.generate_category_summary(2026, "food")
    
    assert result is not None
    assert result["type"] == "category_summary"
    assert "food" in result["text"].lower()
    assert "2026" in result["text"]
    assert result["metadata"]["category"] == "food"


def test_generate_category_summary_no_data(narrative_generator, mock_aggregation_service):
    """Test generate_category_summary with no data."""
    mock_aggregation_service.get_category_aggregates.return_value = []
    
    result = narrative_generator.generate_category_summary(2026, "food")
    
    assert result is None


def test_generate_anomaly_summary(narrative_generator, mock_aggregation_service):
    """Test generate_anomaly_summary."""
    # Mock anomaly detection
    mock_aggregation_service.detect_anomalies.return_value = [
        {
            "category": "home",
            "current_amount": -5000.0,
            "average_amount": -2000.0,
            "deviation_pct": 150.0,
            "is_high": True
        }
    ]
    mock_aggregation_service.get_monthly_totals.return_value = {
        "total_income": 5000.0,
        "total_expense": 7000.0,
        "net_savings": -2000.0
    }
    
    result = narrative_generator.generate_anomaly_summary(2026, 6)
    
    assert result is not None
    assert result["type"] == "anomaly"
    assert "June 2026" in result["text"]
    assert result["metadata"]["year"] == 2026
    assert result["metadata"]["month"] == 6


def test_generate_anomaly_summary_no_anomalies(narrative_generator, mock_aggregation_service):
    """Test generate_anomaly_summary with no anomalies."""
    mock_aggregation_service.detect_anomalies.return_value = []
    
    result = narrative_generator.generate_anomaly_summary(2026, 6)
    
    assert result is None


def test_generate_all_documents(narrative_generator, mock_aggregation_service):
    """Test generate_all_documents."""
    # Mock monthly totals for 12 months
    mock_aggregation_service.get_monthly_totals.return_value = {
        "total_income": 5000.0,
        "total_expense": 3000.0,
        "net_savings": 2000.0
    }
    mock_aggregation_service.get_net_worth.return_value = 50000.0
    mock_aggregation_service.get_month_over_month_delta.return_value = {
        "income_delta": 0.0,
        "expense_delta": 0.0,
        "net_worth_delta": 0.0,
        "income_pct_change": 0.0,
        "expense_pct_change": 0.0,
        "net_worth_pct_change": 0.0,
        "previous_month": None,
        "previous_year": None
    }
    
    # Mock category aggregates
    mock_aggregation_service.get_category_aggregates.return_value = [
        {"category": "food", "total": -12000.0, "count": 100}
    ]
    
    # Mock no anomalies
    mock_aggregation_service.detect_anomalies.return_value = []
    
    result = narrative_generator.generate_all_documents(2026)
    
    # Should generate at least monthly summaries (12) and category summaries
    assert len(result) >= 12
    
    # Check document types
    types = [doc["type"] for doc in result]
    assert "monthly_summary" in types
    assert "category_summary" in types


def test_generate_yearly_overview(narrative_generator, mock_aggregation_service):
    """Test generate_yearly_overview."""
    # Mock yearly summary
    mock_aggregation_service.get_yearly_summary.return_value = {
        "year": 2026,
        "total_income": 60000.0,
        "total_expense": 36000.0,
        "net_savings": 24000.0,
        "monthly_data": [
            {"month": i, "income": 5000.0, "expense": 3000.0, "net_savings": 2000.0, "net_worth": 50000.0}
            for i in range(1, 13)
        ],
        "top_expense_categories": [
            {"category": "food", "total": -12000.0, "count": 100}
        ]
    }
    
    result = narrative_generator.generate_yearly_overview(2026)
    
    assert result is not None
    assert result["type"] == "yearly_overview"
    assert "2026" in result["text"]
    assert "€60000.00" in result["text"] or "60000" in result["text"]
    assert result["metadata"]["year"] == 2026


def test_generate_yearly_overview_no_data(narrative_generator, mock_aggregation_service):
    """Test generate_yearly_overview with no data."""
    mock_aggregation_service.get_yearly_summary.return_value = {
        "year": 2026,
        "total_income": 0.0,
        "total_expense": 0.0,
        "net_savings": 0.0,
        "monthly_data": [],
        "top_expense_categories": []
    }
    
    result = narrative_generator.generate_yearly_overview(2026)
    
    assert result is None
