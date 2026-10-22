"""PUT /api/accounts/{id} accepts the account type as `account_type` (like creation) or `type`."""

from fastapi.testclient import TestClient

from app import app


def _create(client):
    res = client.post("/api/accounts", json={"name": "Main", "account_type": "checking"})
    assert res.status_code == 201
    return res.json()["id"]


def test_update_accepts_account_type_like_creation():
    with TestClient(app) as client:
        account_id = _create(client)
        res = client.put(f"/api/accounts/{account_id}", json={"account_type": "savings"})
        assert res.status_code == 200 and res.json()["type"] == "savings"


def test_update_still_accepts_type_and_prefers_it():
    with TestClient(app) as client:
        account_id = _create(client)
        assert client.put(f"/api/accounts/{account_id}", json={"type": "cash"}).json()["type"] == "cash"
        both = client.put(f"/api/accounts/{account_id}", json={"type": "investment", "account_type": "savings"})
        assert both.json()["type"] == "investment"


def test_update_unrelated_fields_leaves_type_alone():
    with TestClient(app) as client:
        account_id = _create(client)
        res = client.put(f"/api/accounts/{account_id}", json={"name": "Renamed"})
        assert res.json()["name"] == "Renamed" and res.json()["type"] == "checking"
