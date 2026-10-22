"""Workspace + blueprint endpoints, and per-request workspace resolution."""

import pytest
from fastapi.testclient import TestClient

from app import app

FAMILY = {
    "name": "Famiglia",
    "categories": [
        {"key": "figli", "label": "Figli", "children": [{"key": "scuola", "label": "Scuola"}]},
        {"key": "svago", "label": "Svago", "children": [{"key": "ristoranti", "label": "Ristoranti"}]},
    ],
    "groups": [{"key": "minchiate", "label": "Minchiate", "members": ["svago"]}],
}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def ws_headers(workspace_id, user=None):
    headers = {"X-Workspace-Id": str(workspace_id)}
    if user:
        headers["X-User-Id"] = user
    return headers


def test_a_default_workspace_exists_and_serves_requests_without_a_header(client):
    listed = client.get("/api/workspaces").json()
    assert len(listed) == 1 and listed[0]["name"] == "Personale"
    assert client.post("/api/accounts", json={"name": "Main", "account_type": "checking"}).status_code == 201
    assert [a["name"] for a in client.get("/api/accounts").json()] == ["Main"]


def test_data_is_isolated_between_workspaces_through_the_api(client):
    family = client.post("/api/workspaces", json={"name": "Famiglia"}).json()
    client.post("/api/accounts", json={"name": "Personal", "account_type": "checking"})
    client.post("/api/accounts", json={"name": "Family card", "account_type": "checking"}, headers=ws_headers(family["id"]))
    client.post("/api/transactions", json={"amount": -5, "category": "x", "description": "default tx"})
    client.post("/api/transactions", json={"amount": -99, "category": "x", "description": "family tx"}, headers=ws_headers(family["id"]))

    assert [a["name"] for a in client.get("/api/accounts").json()] == ["Personal"]
    assert [a["name"] for a in client.get("/api/accounts", headers=ws_headers(family["id"])).json()] == ["Family card"]
    assert client.get("/api/transactions/balance").json()["balance"] == -5
    assert client.get("/api/transactions/balance", headers=ws_headers(family["id"])).json()["balance"] == -99


def test_unknown_workspace_is_404_and_foreign_workspace_is_403(client):
    assert client.get("/api/accounts", headers=ws_headers(999)).status_code == 404
    mine = client.post("/api/workspaces", json={"name": "Mine"}, headers={"X-User-Id": "alice"}).json()
    assert mine["owner_user_id"] == "alice"
    assert client.get("/api/accounts", headers=ws_headers(mine["id"], "alice")).status_code == 200
    assert client.get("/api/accounts", headers=ws_headers(mine["id"], "bob")).status_code == 403
    assert client.get(f"/api/workspaces/{mine['id']}", headers={"X-User-Id": "bob"}).status_code == 403


def test_list_shows_own_and_unowned_workspaces_only(client):
    client.post("/api/workspaces", json={"name": "Alice's"}, headers={"X-User-Id": "alice"})
    client.post("/api/workspaces", json={"name": "Bob's"}, headers={"X-User-Id": "bob"})
    names = {w["name"] for w in client.get("/api/workspaces", headers={"X-User-Id": "alice"}).json()}
    assert names == {"Personale", "Alice's"}


def test_a_user_without_a_workspace_falls_back_to_the_shared_one(client):
    shared = client.get("/api/workspaces").json()[0]["id"]
    client.post("/api/accounts", json={"name": "Legacy", "account_type": "cash"})
    assert [a["name"] for a in client.get("/api/accounts", headers={"X-User-Id": "newcomer"}).json()] == ["Legacy"]
    assert shared


def test_blueprint_is_validated_and_versioned(client):
    created = client.post("/api/workspaces", json={"name": "Famiglia"}).json()
    url = f"/api/workspaces/{created['id']}/blueprint"
    assert client.get(url).json()["version"] == 1

    saved = client.put(url, json=FAMILY)
    assert saved.status_code == 200 and saved.json()["version"] == 2
    assert client.get(url).json()["blueprint"]["groups"][0]["key"] == "minchiate"

    bad = client.put(url, json={**FAMILY, "groups": [{"key": "g", "label": "G", "members": ["nope"]}]})
    assert bad.status_code == 422 and "unknown category" in bad.text
    assert client.get(url).json()["version"] == 2  # a rejected document changes nothing


def test_create_with_an_initial_blueprint(client):
    created = client.post("/api/workspaces", json={"name": "Famiglia", "blueprint": FAMILY}).json()
    categories = client.get(f"/api/workspaces/{created['id']}/blueprint").json()["blueprint"]["categories"]
    assert [c["key"] for c in categories] == ["figli", "svago"]


def test_delete_requires_force_when_there_is_data_and_never_removes_the_last_workspace(client):
    only = client.get("/api/workspaces").json()[0]["id"]
    assert client.delete(f"/api/workspaces/{only}").status_code == 409  # the only one

    other = client.post("/api/workspaces", json={"name": "Temp"}).json()
    client.post("/api/accounts", json={"name": "A", "account_type": "cash"}, headers=ws_headers(other["id"]))
    assert client.delete(f"/api/workspaces/{other['id']}").status_code == 409  # has data
    assert client.delete(f"/api/workspaces/{other['id']}?force=true").status_code == 200
    assert client.get(f"/api/workspaces/{other['id']}").status_code == 404
    assert client.get("/api/accounts").json() == []  # the other workspace was untouched


def test_rename_and_describe(client):
    created = client.post("/api/workspaces", json={"name": "Old"}).json()
    updated = client.put(f"/api/workspaces/{created['id']}", json={"name": "New", "description": "d"}).json()
    assert (updated["name"], updated["description"]) == ("New", "d")


def test_current_workspace_follows_the_request_headers(client):
    default = client.get("/api/workspaces/current").json()
    assert default["name"] == "Personale"
    other = client.post("/api/workspaces", json={"name": "Studio", "blueprint": FAMILY}).json()
    current = client.get("/api/workspaces/current", headers=ws_headers(other["id"]))
    assert current.json()["id"] == other["id"]
    blueprint = client.get("/api/workspaces/current/blueprint", headers=ws_headers(other["id"])).json()
    assert [c["key"] for c in blueprint["blueprint"]["categories"]] == ["figli", "svago"]
