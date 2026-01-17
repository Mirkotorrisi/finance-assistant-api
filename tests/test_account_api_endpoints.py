
import sys
import os
from fastapi.testclient import TestClient

# Add project root to path
sys.path.append(os.getcwd())

from src.api.app import app

client = TestClient(app)


def test_account_api_endpoints():
    """Test Account CRUD API endpoints."""
    print("Initializing Account API tests...")
    
    with TestClient(app) as client:
        # Test POST /api/accounts - Create account
        print("\n[TestCase] POST /api/accounts")
        response = client.post("/api/accounts", json={
            "name": "Test Checking Account",
            "account_type": "checking",
            "currency": "USD",
            "is_active": True
        })
        print(f"Create Response: {response.status_code} - {response.json()}")
        assert response.status_code == 200
        account_data = response.json()
        assert account_data["name"] == "Test Checking Account"
        assert account_data["type"] == "checking"
        assert account_data["currency"] == "USD"
        assert account_data["is_active"] == True
        account_id = account_data["id"]
        
        # Test GET /api/accounts - List accounts
        print("\n[TestCase] GET /api/accounts")
        response = client.get("/api/accounts")
        print(f"List Response: {response.status_code}")
        assert response.status_code == 200
        accounts = response.json()
        assert len(accounts) > 0
        assert any(acc['id'] == account_id for acc in accounts)
        
        # Test GET /api/accounts/{account_id} - Get single account
        print(f"\n[TestCase] GET /api/accounts/{account_id}")
        response = client.get(f"/api/accounts/{account_id}")
        print(f"Get Response: {response.status_code} - {response.json()}")
        assert response.status_code == 200
        account_data = response.json()
        assert account_data["id"] == account_id
        assert account_data["name"] == "Test Checking Account"
        
        # Test PUT /api/accounts/{account_id} - Update account
        print(f"\n[TestCase] PUT /api/accounts/{account_id}")
        response = client.put(f"/api/accounts/{account_id}", json={
            "name": "Updated Checking Account"
        })
        print(f"Update Response: {response.status_code} - {response.json()}")
        assert response.status_code == 200
        updated_data = response.json()
        assert updated_data["name"] == "Updated Checking Account"
        assert updated_data["type"] == "checking"  # Should remain unchanged
        
        # Test GET /api/accounts/{account_id}/balance - Get account balance
        print(f"\n[TestCase] GET /api/accounts/{account_id}/balance")
        response = client.get(f"/api/accounts/{account_id}/balance")
        print(f"Balance Response: {response.status_code} - {response.json()}")
        assert response.status_code == 200
        balance_data = response.json()
        assert "account_id" in balance_data
        assert "balance" in balance_data
        assert balance_data["account_id"] == account_id
        # Balance should be 0.0 as no snapshots exist yet
        assert balance_data["balance"] == 0.0
        
        # Test DELETE /api/accounts/{account_id} - Delete account (soft delete)
        print(f"\n[TestCase] DELETE /api/accounts/{account_id}")
        response = client.delete(f"/api/accounts/{account_id}")
        print(f"Delete Response: {response.status_code} - {response.json()}")
        assert response.status_code == 200
        assert "message" in response.json()
        
        # Confirm soft deletion - account should not appear in active list
        response = client.get("/api/accounts?active_only=true")
        active_accounts = response.json()
        assert not any(acc['id'] == account_id for acc in active_accounts)
        
        # But should appear when including inactive accounts
        response = client.get("/api/accounts?active_only=false")
        all_accounts = response.json()
        deleted_account = next((acc for acc in all_accounts if acc['id'] == account_id), None)
        assert deleted_account is not None
        assert deleted_account["is_active"] == False
        
        # Test 404 errors
        print("\n[TestCase] GET /api/accounts/99999 (non-existent)")
        response = client.get("/api/accounts/99999")
        print(f"Not Found Response: {response.status_code}")
        assert response.status_code == 404
        
        print("\n[TestCase] PUT /api/accounts/99999 (non-existent)")
        response = client.put("/api/accounts/99999", json={"name": "Test"})
        assert response.status_code == 404
        
        print("\n[TestCase] DELETE /api/accounts/99999 (non-existent)")
        response = client.delete("/api/accounts/99999")
        assert response.status_code == 404
        
        print("\nALL ACCOUNT API TESTS PASSED")


if __name__ == "__main__":
    test_account_api_endpoints()
