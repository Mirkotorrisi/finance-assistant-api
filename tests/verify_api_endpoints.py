
import sys
import os
import datetime
from fastapi.testclient import TestClient

# Add project root to path
sys.path.append(os.getcwd())

from src.api.app import app
from src.database.init import init_database

client = TestClient(app)

def test_api_endpoints():
    print("Initializing API tests...")
    # Initialize DB (lifespan of app usually does this, but for TestClient on module level we might need to ensure it's ready)
    # The TestClient calls lifespan startup events automatically
    
    print("\n[TestCase] POST /api/transactions")
    response = client.post("/api/transactions", json={
        "amount": -25.50,
        "category": "Transport",
        "description": "Taxi",
        "date": datetime.date.today().isoformat()
    })
    print(f"Create Response: {response.status_code} - {response.json()}")
    assert response.status_code == 200
    t_data = response.json()
    assert t_data["amount"] == -25.50
    t_id = t_data["id"]
    
    print("\n[TestCase] GET /api/transactions")
    response = client.get("/api/transactions")
    print(f"List Response: {response.status_code}")
    assert response.status_code == 200
    txs = response.json()
    assert len(txs) > 0
    
    print("\n[TestCase] PUT /api/transactions/{id}")
    response = client.put(f"/api/transactions/{t_id}", json={
        "amount": -30.0
    })
    print(f"Update Response: {response.status_code} - {response.json()}")
    assert response.status_code == 200
    assert response.json()["amount"] == -30.0
    
    print("\n[TestCase] GET /api/balance")
    response = client.get("/api/balance")
    print(f"Balance Response: {response.status_code} - {response.json()}")
    assert response.status_code == 200
    assert "balance" in response.json()
    
    print("\n[TestCase] DELETE /api/transactions/{id}")
    response = client.delete(f"/api/transactions/{t_id}")
    print(f"Delete Response: {response.status_code}")
    assert response.status_code == 200
    
    # Confirm deletion
    response = client.get("/api/transactions")
    txs_final = response.json()
    assert not any(t['id'] == t_id for t in txs_final)
    
    print("\nALL API TESTS PASSED")

if __name__ == "__main__":
    test_api_endpoints()
