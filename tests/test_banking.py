"""Bank connections, account links, the scheduler's due list, and bank rows in imports."""

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
    bank = client.post("/api/accounts", json={"name": "UniCredit", "account_type": "checking"}, headers=headers).json()["id"]
    return headers, bank


CONSENT = {
    "aspsp_name": "UniCredit",
    "aspsp_country": "IT",
    "session_ref": "ref-1",
    "valid_until": "2027-05-20T10:00:00",
    "accounts": [
        {"identification_hash": "h-cc", "bank_uid": "uid-1", "iban_masked": "IT60 •••• 0123", "label": "Conto MyGenius", "currency": "EUR", "cash_account_type": "CACC"},
        {"identification_hash": "h-card", "bank_uid": "uid-2", "iban_masked": None, "label": "Genius Card", "currency": "EUR", "cash_account_type": "CARD"},
    ],
}


def test_connection_lifecycle_and_account_mapping(client, project):
    headers, bank = project
    created = client.post("/api/bank-connections", json=CONSENT, headers=headers)
    assert created.status_code == 201, created.text
    conn = created.json()
    assert conn["status"] == "active" and len(conn["accounts"]) == 2 and conn["accounts"][0]["account_id"] is None

    link = conn["accounts"][0]["id"]
    mapped = client.put(f"/api/bank-connections/{conn['id']}/links/{link}", json={"account_id": bank}, headers=headers).json()
    assert mapped["account_id"] == bank

    # the same app account cannot be fed by two bank accounts
    other = conn["accounts"][1]["id"]
    clash = client.put(f"/api/bank-connections/{conn['id']}/links/{other}", json={"account_id": bank}, headers=headers)
    assert clash.status_code == 400

    # creating the app account inline
    made = client.put(f"/api/bank-connections/{conn['id']}/links/{other}", json={"create_account": {"name": "Genius Card", "account_type": "prepaid"}}, headers=headers).json()
    assert made["account_id"] is not None
    assert {a["name"] for a in client.get("/api/accounts", headers=headers).json()} == {"UniCredit", "Genius Card"}

    # sync bookkeeping
    updated = client.put(f"/api/bank-connections/{conn['id']}", json={"last_sync_at": "2026-11-21T08:00:00", "last_sync_status": "ok", "sync_transactions": False}, headers=headers).json()
    assert updated["last_sync_status"] == "ok" and updated["sync_transactions"] is False
    assert client.put(f"/api/bank-connections/{conn['id']}", json={"status": "weird"}, headers=headers).status_code == 422

    listed = client.get("/api/bank-connections", headers=headers).json()
    assert [c["id"] for c in listed] == [conn["id"]] and listed[0]["accounts"][0]["account_id"] == bank

    assert client.delete(f"/api/bank-connections/{conn['id']}", headers=headers).status_code == 200
    assert client.get("/api/bank-connections", headers=headers).json() == []
    # the app accounts stay
    assert len(client.get("/api/accounts", headers=headers).json()) == 2


def test_renewal_keeps_the_links_and_refreshes_the_handles(client, project):
    headers, bank = project
    conn = client.post("/api/bank-connections", json=CONSENT, headers=headers).json()
    link = conn["accounts"][0]["id"]
    client.put(f"/api/bank-connections/{conn['id']}/links/{link}", json={"account_id": bank, "last_transaction_date": "2026-11-20"}, headers=headers)

    renewed_body = dict(CONSENT, session_ref="ref-2", valid_until="2027-11-20T10:00:00", renew_connection_id=conn["id"])
    renewed_body["accounts"] = [dict(CONSENT["accounts"][0], bank_uid="uid-9"), {"identification_hash": "h-new", "bank_uid": "uid-3", "label": "Nuovo", "currency": "EUR", "cash_account_type": "SVGS"}]
    renewed = client.post("/api/bank-connections", json=renewed_body, headers=headers).json()
    assert renewed["id"] == conn["id"] and renewed["session_ref"] == "ref-2"
    by_hash = {a["identification_hash"]: a for a in renewed["accounts"]}
    assert by_hash["h-cc"]["account_id"] == bank and by_hash["h-cc"]["bank_uid"] == "uid-9"
    assert by_hash["h-cc"]["last_transaction_date"] == "2026-11-20"
    assert "h-new" in by_hash and "h-card" in by_hash  # accounts no longer exposed keep their row


def test_connections_are_scoped_and_the_due_list_spans_workspaces(client, project):
    headers, _ = project
    other = client.post("/api/workspaces", json={"name": "Altro"}).json()
    other_headers = {"X-Workspace-Id": str(other["id"])}
    a = client.post("/api/bank-connections", json=CONSENT, headers=headers).json()
    b = client.post("/api/bank-connections", json=dict(CONSENT, session_ref="ref-b", aspsp_name="Revolut", aspsp_country="LT"), headers=other_headers).json()
    assert [c["id"] for c in client.get("/api/bank-connections", headers=headers).json()] == [a["id"]]
    assert client.get(f"/api/bank-connections/{a['id']}", headers=other_headers).status_code in (404, 405)

    due = client.get("/api/bank-connections/due", params={"max_age_hours": 12}).json()
    assert {(d["workspace_id"], d["connection_id"]) for d in due} == {(int(headers["X-Workspace-Id"]), a["id"]), (other["id"], b["id"])}
    client.put(f"/api/bank-connections/{a['id']}", json={"last_sync_at": "2099-01-01T00:00:00"}, headers=headers)
    assert [d["connection_id"] for d in client.get("/api/bank-connections/due").json()] == [b["id"]]
    client.put(f"/api/bank-connections/{b['id']}", json={"status": "expired"}, headers=other_headers)
    assert client.get("/api/bank-connections/due").json() == []

    expiring = client.get("/api/bank-connections/expiring", params={"within_days": 10000}).json()
    assert [e["connection_id"] for e in expiring] == [a["id"]]


def rows(*items):
    return [{"date": d, "amount": a, "description": t, "category": "spesa", **extra} for d, a, t, extra in items]


def test_bank_rows_dedupe_on_external_id_then_fingerprint(client, project):
    headers, bank = project
    first = client.post("/api/imports", json={"account_id": bank, "source": "bank", "transactions": rows(
        ("2026-11-10", -12.5, "CARTA 1234 COOP", {"external_id": "E1"}),
        ("2026-11-10", -12.5, "CARTA 1234 COOP", {"external_id": "E2"}),  # a second identical purchase: different id
        ("2026-11-11", 1500.0, "STIPENDIO ACME", {"external_id": "E3"}),
    )}, headers=headers).json()
    assert first["added_count"] == 3 and first["suspect_duplicates"] == 0
    assert {t["source"] for t in first["transactions"]} == {"bank"}

    again = client.post("/api/imports", json={"account_id": bank, "source": "bank", "transactions": rows(
        ("2026-11-10", -12.5, "CARTA 1234 COOP (reworded)", {"external_id": "E1"}),  # same id, new wording: known
        ("2026-11-12", -3.0, "BAR", {"external_id": "E4"}),
    )}, headers=headers).json()
    assert again["added_count"] == 1 and again["skipped_count"] == 1

    assert client.post("/api/imports", json={"account_id": bank, "source": "nope", "transactions": []}, headers=headers).status_code == 400


def test_bank_rows_that_resemble_statement_rows_are_kept_and_flagged(client, project):
    headers, bank = project
    # the statement came first (no external ids), then the bank API brings the same movements, worded differently
    statement = client.post("/api/imports", json={"account_id": bank, "transactions": rows(
        ("2026-11-10", -45.0, "PAGAMENTO POS ESSELUNGA MILANO", {}),
        ("2026-11-13", -45.0, "PAGAMENTO POS ESSELUNGA MILANO", {}),
        ("2026-11-15", -9.9, "NETFLIX", {}),
    )}, headers=headers).json()
    assert statement["added_count"] == 3
    statement_ids = {t["description"] + t["date"]: t["id"] for t in statement["transactions"]}

    synced = client.post("/api/imports", json={"account_id": bank, "source": "bank", "transactions": rows(
        ("2026-11-11", -45.0, "ESSELUNGA SPA", {"external_id": "B1"}),      # settles on the 10th: twin of the first POS row
        ("2026-11-13", -45.0, "ESSELUNGA SPA", {"external_id": "B2"}),      # twin of the second
        ("2026-11-20", -45.0, "ESSELUNGA SPA", {"external_id": "B3"}),      # nothing near: genuinely new
        ("2026-11-15", -9.9, "NETFLIX", {"external_id": "B4"}),             # exact fingerprint: skipped
    )}, headers=headers).json()
    assert synced["added_count"] == 3 and synced["skipped_count"] == 1 and synced["suspect_duplicates"] == 2
    by_ext = {t["external_id"]: t for t in synced["transactions"]}
    assert by_ext["B1"]["duplicate_of"] == statement_ids["PAGAMENTO POS ESSELUNGA MILANO2026-11-10"]
    assert by_ext["B2"]["duplicate_of"] == statement_ids["PAGAMENTO POS ESSELUNGA MILANO2026-11-13"]
    assert by_ext["B3"]["duplicate_of"] is None

    suspects = client.get("/api/imports/suspects", headers=headers).json()
    assert len(suspects) == 2 and all(s["twin"]["source"] == "statement" for s in suspects)

    # settle: the first is the same movement (drop the bank row), the second too but keep the bank row
    r1 = client.post(f"/api/imports/suspects/{by_ext['B1']['id']}/resolve", json={"action": "delete_this"}, headers=headers)
    assert r1.status_code == 200
    r2 = client.post(f"/api/imports/suspects/{by_ext['B2']['id']}/resolve", json={"action": "delete_twin"}, headers=headers)
    assert r2.status_code == 200
    assert client.get("/api/imports/suspects", headers=headers).json() == []
    remaining = client.get("/api/transactions", headers=headers).json()
    descriptions = sorted(t["description"] for t in remaining)
    assert descriptions == ["ESSELUNGA SPA", "ESSELUNGA SPA", "NETFLIX", "PAGAMENTO POS ESSELUNGA MILANO"]
    assert client.post(f"/api/imports/suspects/{by_ext['B3']['id']}/resolve", json={"action": "keep_both"}, headers=headers).status_code == 404


def test_a_statement_row_claimed_once_is_not_claimed_twice(client, project):
    headers, bank = project
    client.post("/api/imports", json={"account_id": bank, "transactions": rows(("2026-11-10", -20.0, "BAR ROSSI", {}))}, headers=headers)
    synced = client.post("/api/imports", json={"account_id": bank, "source": "bank", "transactions": rows(
        ("2026-11-10", -20.0, "ROSSI SRL", {"external_id": "X1"}),
        ("2026-11-11", -20.0, "ROSSI SRL", {"external_id": "X2"}),
    )}, headers=headers).json()
    flagged = [t for t in synced["transactions"] if t["duplicate_of"]]
    assert len(flagged) == 1 and flagged[0]["external_id"] == "X1"  # the closest one claims the twin
