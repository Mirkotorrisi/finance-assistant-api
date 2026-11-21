"""The current balance of an account is its latest recorded balance plus the transactions since it.

The dashboard total, the account list, the single-account balance and the account breakdown all rest on the same
figure, so a bank sync (or a typed balance) moves them together; accounts that never had a recorded balance keep
summing their transactions, as before.
"""

import pytest
from app import app
from fastapi.testclient import TestClient

BLUEPRINT = {"name": "Io", "categories": [{"key": "spesa", "label": "Spesa"}, {"key": "stipendio", "label": "Stipendio", "kind": "income"}]}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client):
    ws = client.post("/api/workspaces", json={"name": "P", "blueprint": BLUEPRINT}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}
    bank = client.post("/api/accounts", json={"name": "Banca", "account_type": "checking"}, headers=headers).json()["id"]
    cash = client.post("/api/accounts", json={"name": "Contanti", "account_type": "cash"}, headers=headers).json()["id"]
    rows = [
        {"date": "2026-11-05", "amount": 2000.0, "description": "Stipendio", "category": "stipendio"},
        {"date": "2026-11-10", "amount": -300.0, "description": "Spesa coop", "category": "spesa"},
        {"date": "2026-11-21", "amount": -50.0, "description": "Spesa dopo il saldo", "category": "spesa"},
    ]
    assert client.post("/api/imports", json={"account_id": bank, "transactions": rows}, headers=headers).status_code == 200
    client.post("/api/imports", json={"account_id": cash, "transactions": [{"date": "2026-11-12", "amount": -20.0, "description": "Bar", "category": "spesa"}]}, headers=headers)
    return headers, bank, cash


def test_without_recorded_balances_the_transactions_decide(client, project):
    headers, bank, cash = project
    total = client.get("/api/transactions/balance", headers=headers).json()
    assert total["balance"] == 1630.0 and total["basis"] == "transactions" and total["anchored_accounts"] == 0
    accounts = {a["id"]: a for a in client.get("/api/accounts", headers=headers).json()}
    assert accounts[bank]["current_balance"] == 1650.0 and accounts[bank]["balance_basis"] == "transactions"
    assert accounts[cash]["current_balance"] == -20.0


def test_a_recorded_balance_anchors_every_balance_endpoint(client, project):
    headers, bank, cash = project
    # the bank said: on the 20th the account held 54_000 (the statements never had the opening balance)
    client.post("/api/balance-snapshots", json={"account_id": bank, "date": "2026-11-20", "balance": 54000.0}, headers=headers)
    expected = 54000.0 - 50.0  # plus the transaction booked after the recorded balance

    total = client.get("/api/transactions/balance", headers=headers).json()
    assert total["balance"] == expected - 20.0 and total["basis"] == "mixed" and total["anchored_accounts"] == 1

    assert client.get(f"/api/accounts/{bank}/balance", headers=headers).json()["balance"] == expected
    accounts = {a["id"]: a for a in client.get("/api/accounts", headers=headers).json()}
    assert accounts[bank]["current_balance"] == expected and accounts[bank]["balance_basis"] == "snapshot"
    assert accounts[cash]["balance_basis"] == "transactions"
    single = client.get(f"/api/accounts/{bank}", headers=headers).json()
    assert single["current_balance"] == expected

    breakdown = client.get("/api/financial-summary/account-breakdown", headers=headers).json()
    by_id = {a["account_id"]: a for a in breakdown["accounts"]}
    assert by_id[bank]["balance"] == expected and breakdown["total_balance"] == expected - 20.0


def test_an_older_recorded_balance_is_rolled_forward_with_the_transactions(client, project):
    headers, bank, _ = project
    client.post("/api/balance-snapshots", json={"account_id": bank, "date": "2026-11-01", "balance": 10000.0}, headers=headers)
    assert client.get(f"/api/accounts/{bank}/balance", headers=headers).json()["balance"] == 10000.0 + 2000.0 - 300.0 - 50.0
