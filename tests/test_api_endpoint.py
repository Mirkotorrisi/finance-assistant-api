"""Test API endpoint with TestClient."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock the database initialization before importing app
os.environ['USE_DATABASE'] = 'false'
os.environ['ENVIRONMENT'] = 'test'

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


def test_financial_data_api():
    """Test the /api/financial-data/{year} endpoint."""
    
    # Mock the database dependencies
    with patch('src.database.init.init_database'), \
         patch('src.database.init.close_database'), \
         patch('src.database.init.get_db_session') as mock_get_session:
        
        # Setup mock session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock query results for empty data
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []
        mock_session.query.return_value = mock_query
        
        # Import app after mocking
        from src.api.app import app
        
        # Create test client
        client = TestClient(app)
        
        # Test health endpoint first
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
        print("✅ Health check passed")
        
        # Test financial data endpoint
        response = client.get("/api/financial-data/2024")
        assert response.status_code == 200
        
        data = response.json()
        print("\n" + "=" * 80)
        print("API ENDPOINT TEST - /api/financial-data/2024")
        print("=" * 80)
        print(f"Response Status: {response.status_code}")
        print(f"Response Data: {data}")
        print("=" * 80)
        
        # Verify response structure
        assert "year" in data
        assert "currentNetWorth" in data
        assert "netSavings" in data
        assert "monthlyData" in data
        assert "accountBreakdown" in data
        
        assert data["year"] == 2024
        assert isinstance(data["currentNetWorth"], (int, float))
        assert isinstance(data["netSavings"], (int, float))
        assert isinstance(data["monthlyData"], list)
        assert len(data["monthlyData"]) == 12
        
        # Check monthly data structure
        first_month = data["monthlyData"][0]
        assert "month" in first_month
        assert "netWorth" in first_month
        assert "expenses" in first_month
        assert "income" in first_month
        assert "net" in first_month
        assert first_month["month"] == "Jan"
        
        # Check account breakdown structure
        breakdown = data["accountBreakdown"]
        assert "liquidity" in breakdown
        assert "investments" in breakdown
        assert "otherAssets" in breakdown
        
        print("\n✅ All API endpoint tests passed!")
        print("✅ Response matches TypeScript interface requirements")


if __name__ == "__main__":
    test_financial_data_api()
