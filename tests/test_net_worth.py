"""Balance snapshots: reconciled against the transactions, carried into a monthly net worth."""

import pytest
from fastapi.testclient import TestClient

from app import app

BLUEPRINT = {
    "name": "Io",
    "categories": [
        {"key": "spesa", "label": "Spesa"},
        {"key": "stipendio", "label": "Stipendio", "kind": "income"},
        {"key": "investimenti", "label": "Investimenti", "kind": "investment"},
    ],
}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client):
    ws = client.post("/api/workspaces", json={"name": "P", "blueprint": BLUEPRINT}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}

    def account(name, kind):
        return client.post("/api/accounts", json={"name": name, "account_type": kind}, headers=headers).json()["id"]

    return headers, account("Banca", "checking"), account("Broker", "investment"), account("Contanti", "cash")


def snap(client, headers, account, day, balance, note=None):
    res = client.post("/api/balance-snapshots", json={"account_id": account, "date": day, "balance": balance, "note": note}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def load(client, headers, account, rows):
    payload = [{"date": d, "amount": a, "description": t, "category": c} for d, a, t, c in rows]
    assert client.post("/api/imports", json={"account_id": account, "transactions": payload}, headers=headers).status_code == 200


def test_first_snapshot_is_a_baseline_and_a_consistent_one_is_ok(client, project):
    headers, bank, _, _ = project
    assert snap(client, headers, bank, "2026-01-31", 1000)["reconciliation"]["status"] == "baseline"
    load(client, headers, bank, [("2026-02-03", 2000, "Stipendio", "stipendio"), ("2026-02-10", -300, "Spesa coop", "spesa")])
    second = snap(client, headers, bank, "2026-02-28", 2700)
    assert second["reconciliation"] == {
        "status": "ok", "previous_date": "2026-01-31", "expected_change": 1700.0, "actual_change": 1700.0, "delta": 0.0,
    }


def test_a_gap_is_reported_and_can_be_booked_without_touching_spending(client, project):
    headers, bank, _, _ = project
    snap(client, headers, bank, "2026-01-31", 1000)
    load(client, headers, bank, [("2026-02-03", 2000, "Stipendio", "stipendio")])
    gap = snap(client, headers, bank, "2026-02-28", 2500)  # 500 less than the transactions explain
    assert gap["reconciliation"]["status"] == "gap"
    assert gap["reconciliation"]["delta"] == -500.0

    adjustment = client.post(f"/api/balance-snapshots/{gap['id']}/adjust", headers=headers).json()
    assert adjustment["amount"] == -500.0 and adjustment["is_transfer"] is True
    again = client.get("/api/balance-snapshots", headers=headers).json()["snapshots"]
    assert [s["reconciliation"]["status"] for s in again] == ["baseline", "ok"]
    assert client.post(f"/api/balance-snapshots/{gap['id']}/adjust", headers=headers).status_code == 400

    spending = client.get("/api/reports/spending", params={"start_date": "2026-01-01", "end_date": "2026-12-31"}, headers=headers).json()
    assert spending["total"] == 0.0  # the correction is not an expense


def test_rounded_sheets_are_within_tolerance(client, project):
    headers, bank, _, _ = project
    snap(client, headers, bank, "2026-01-31", 1000)
    load(client, headers, bank, [("2026-02-03", 100.40, "Rimborso", "stipendio")])
    assert snap(client, headers, bank, "2026-02-28", 1100)["reconciliation"]["status"] == "ok"


def test_brokerage_snapshots_are_market_values_not_reconciled(client, project):
    headers, _, broker, _ = project
    snap(client, headers, broker, "2026-01-31", 10000)
    second = snap(client, headers, broker, "2026-02-28", 9000)
    assert second["reconciliation"]["status"] == "valuation" and second["reconciliation"]["change"] == -1000.0


def test_same_day_snapshot_replaces_the_previous_one(client, project):
    headers, bank, _, _ = project
    snap(client, headers, bank, "2026-01-31", 1000)
    snap(client, headers, bank, "2026-01-31", 1200, note="corretto")
    rows = client.get("/api/balance-snapshots", headers=headers).json()["snapshots"]
    assert len(rows) == 1 and rows[0]["balance"] == 1200 and rows[0]["note"] == "corretto"


def test_unknown_account_and_other_workspaces_are_refused(client, project):
    headers, bank, _, _ = project
    assert client.post("/api/balance-snapshots", json={"account_id": 9999, "date": "2026-01-31", "balance": 1}, headers=headers).status_code == 404
    other = client.post("/api/workspaces", json={"name": "Altro", "blueprint": BLUEPRINT}).json()
    other_headers = {"X-Workspace-Id": str(other["id"])}
    assert client.post("/api/balance-snapshots", json={"account_id": bank, "date": "2026-01-31", "balance": 1}, headers=other_headers).status_code == 404
    snap(client, headers, bank, "2026-01-31", 1000)
    assert client.get("/api/balance-snapshots", headers=other_headers).json()["snapshots"] == []


def test_net_worth_derives_months_without_a_snapshot(client, project):
    headers, bank, broker, cash = project
    snap(client, headers, bank, "2026-01-31", 1000)
    load(client, headers, bank, [("2026-02-03", 2000, "Stipendio", "stipendio"), ("2026-03-05", -400, "Spesa", "spesa")])
    snap(client, headers, bank, "2026-03-31", 2600)
    snap(client, headers, broker, "2026-01-31", 5000)
    snap(client, headers, broker, "2026-03-31", 5200)
    snap(client, headers, cash, "2026-03-31", 100)

    body = client.get("/api/net-worth", params={"start_month": "2026-01", "end_month": "2026-03"}, headers=headers).json()
    months = {m["month"]: m for m in body["months"]}
    assert months["2026-02"]["balances"][str(bank)] == {"balance": 3000.0, "basis": "derived"}
    assert months["2026-01"]["balances"][str(broker)]["basis"] == "snapshot"
    assert months["2026-02"]["balances"][str(broker)] == {"balance": 5000.0, "basis": "carried"}
    assert months["2026-01"]["balances"][str(cash)] == {"balance": None, "basis": "none"}  # no transactions to work back with
    assert months["2026-02"]["balances"][str(bank)]["balance"] == 3000.0
    assert (months["2026-03"]["liquid"], months["2026-03"]["invested"], months["2026-03"]["total"]) == (2700.0, 5200.0, 7900.0)
    assert body["change"] == months["2026-03"]["total"] - months["2026-02"]["total"]
    assert body["unreconciled_snapshots"] == 0


def test_net_worth_flags_gaps_and_handles_an_empty_project(client, project):
    headers, bank, _, _ = project
    empty = client.get("/api/net-worth", headers=headers)
    assert empty.status_code == 200 and empty.json()["latest"]["total"] == 0.0
    load(client, headers, bank, [("2026-01-15", 10, "Rimborso", "stipendio")])
    snap(client, headers, bank, "2026-01-31", 1000)
    snap(client, headers, bank, "2026-02-28", 1500)  # no transactions explain it
    assert client.get("/api/net-worth", headers=headers).json()["unreconciled_snapshots"] == 1
    assert client.get("/api/net-worth", params={"start_month": "2026-13"}, headers=headers).status_code == 400


def test_bulk_and_flow_check(client, project):
    headers, bank, _, _ = project
    load(client, headers, bank, [("2026-01-05", 4205, "Stipendio", "stipendio"), ("2026-01-09", -1500, "Spesa", "spesa"), ("2026-01-20", -64, "Altro", "spesa")])
    bulk = client.post("/api/balance-snapshots/bulk", json={"snapshots": [
        {"account_id": bank, "date": "2026-01-31", "balance": 95841, "note": "gennaio"},
        {"account_id": bank, "date": "2026-02-28", "balance": 102027},
    ]}, headers=headers).json()
    assert bulk["saved"] == 2 and bulk["gaps"] == 1

    check = client.post("/api/net-worth/check-flows", json={"rows": [
        {"month": "2026-01", "account_id": bank, "income": 4205, "expenses": 1564},
        {"month": "2026-01", "account_id": bank, "income": 4000},
    ]}, headers=headers).json()["rows"]
    assert check[0]["status"] == "ok" and check[0]["actual_expenses"] == 1564.0
    assert check[1]["status"] == "mismatch" and check[1]["income_diff"] == 205.0
    assert client.post("/api/balance-snapshots/bulk", json={"snapshots": [{"account_id": 9999, "date": "2026-01-31", "balance": 1}]}, headers=headers).status_code == 404

    deleted = client.delete(f"/api/balance-snapshots/{bulk['snapshots'][0]['id']}", headers=headers)
    assert deleted.status_code == 200 and client.delete("/api/balance-snapshots/99999", headers=headers).status_code == 404


def test_an_account_without_transactions_is_untracked_not_a_gap(client, project):
    headers, bank, _, cash = project
    snap(client, headers, cash, "2026-01-31", 100)
    second = snap(client, headers, cash, "2026-02-28", 250)
    assert second["reconciliation"] == {"status": "untracked", "previous_date": "2026-01-31", "change": 150.0}
    assert client.get("/api/net-worth", headers=headers).json()["unreconciled_snapshots"] == 0
    assert client.post(f"/api/balance-snapshots/{second['id']}/adjust", headers=headers).status_code == 400

    # transactions that only start after the snapshot do not make it a gap either
    snap(client, headers, bank, "2026-01-31", 1000)
    early = snap(client, headers, bank, "2026-02-28", 1500)
    load(client, headers, bank, [("2026-03-10", -20, "Spesa", "spesa")])
    assert next(r for r in client.get("/api/balance-snapshots", headers=headers).json()["snapshots"] if r["id"] == early["id"])["reconciliation"]["status"] == "untracked"


def test_the_current_month_uses_a_snapshot_dated_later_in_it(client, project):
    from datetime import date, timedelta

    headers, bank, _, _ = project
    today = date.today()
    last_day = (date(today.year + (today.month == 12), today.month % 12 + 1, 1) - timedelta(days=1))
    snap(client, headers, bank, (today.replace(day=1) - timedelta(days=1)).isoformat(), 1000)
    snap(client, headers, bank, last_day.isoformat(), 4000)
    latest = client.get("/api/net-worth", headers=headers).json()["latest"]
    assert latest["balances"][str(bank)] == {"balance": 4000.0, "basis": "snapshot"}
