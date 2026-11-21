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
        {"identification_hash": "h-cc-" + "x" * 130, "bank_uid": "uid-1", "iban_masked": "IT60 •••• 0123", "label": "Conto MyGenius", "currency": "EUR", "cash_account_type": "CACC"},
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
    long_hash = "h-cc-" + "x" * 130
    assert by_hash[long_hash]["account_id"] == bank and by_hash[long_hash]["bank_uid"] == "uid-9"
    assert by_hash[long_hash]["last_transaction_date"] == "2026-11-20"
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
    # the statement row that won carries the bank's reference now: the same movement is skipped next time
    resync = client.post("/api/imports", json={"account_id": bank, "source": "bank", "transactions": rows(
        ("2026-11-11", -45.0, "ESSELUNGA SPA", {"external_id": "B1"}),
    )}, headers=headers).json()
    assert resync["added_count"] == 0 and resync["skipped_count"] == 1
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


def test_bulk_resolve_settles_same_day_pairs_only(client, project):
    headers, bank = project
    client.post("/api/imports", json={"account_id": bank, "transactions": rows(
        ("2026-11-10", -45.0, "PAGAMENTO POS ESSELUNGA", {}),
        ("2026-11-12", -9.9, "NETFLIX.COM", {}),
    )}, headers=headers)
    client.post("/api/imports", json={"account_id": bank, "source": "bank", "transactions": rows(
        ("2026-11-10", -45.0, "ESSELUNGA SPA", {"external_id": "B1"}),     # same day
        ("2026-11-13", -9.9, "NETFLIX", {"external_id": "B2"}),           # one day later
    )}, headers=headers)
    assert len(client.get("/api/imports/suspects", headers=headers).json()) == 2
    done = client.post("/api/imports/suspects/resolve-bulk", json={"action": "delete_this", "max_day_gap": 0}, headers=headers).json()
    assert done == {"resolved": 1, "action": "delete_this", "max_day_gap": 0, "remaining": 1}
    left = client.get("/api/imports/suspects", headers=headers).json()
    assert left[0]["transaction"]["external_id"] == "B2"
    kept = [t for t in client.get("/api/transactions", headers=headers).json() if t["description"] == "PAGAMENTO POS ESSELUNGA"]
    assert kept[0]["external_id"] == "B1"  # the statement row inherited the bank's reference
    assert client.post("/api/imports/suspects/resolve-bulk", json={"action": "nope"}, headers=headers).status_code == 400


# ── mute bank rows (amount and date only) and the statements that give them words ─────────────────


def test_mute_bank_rows_are_dropped_when_a_statement_row_already_exists(client, project):
    headers, bank = project
    client.post("/api/imports", json={"account_id": bank, "transactions": rows(
        ("2026-11-10", -50.0, "Commercio Buy trade LU1829220216 AMUNDI, quantity: 0.1", {}),
    )}, headers=headers)
    synced = client.post("/api/imports", json={"account_id": bank, "source": "bank", "transactions": rows(
        ("2026-11-11", -50.0, "Movimento Trade Republic", {"mute": True, "category": "uncategorized", "category_source": "fallback"}),   # the same PAC, value date
        ("2026-11-20", -50.0, "Movimento Trade Republic", {"mute": True, "category": "uncategorized", "category_source": "fallback"}),   # a newer one: kept
    )}, headers=headers).json()
    assert synced["added_count"] == 1 and synced["absorbed_mute_rows"] == 1 and synced["suspect_duplicates"] == 0
    stored = client.get("/api/transactions", headers=headers).json()
    assert sorted((t["date"], t["description"][:9]) for t in stored) == [("2026-11-10", "Commercio"), ("2026-11-20", "Movimento")]


def test_a_statement_row_takes_over_the_mute_bank_row_in_place(client, project):
    headers, bank = project
    synced = client.post("/api/imports", json={"account_id": bank, "source": "bank", "transactions": rows(
        ("2026-11-20", -50.0, "Movimento Trade Republic", {"mute": True, "category": "uncategorized", "category_source": "fallback", "external_id": None}),
    )}, headers=headers).json()
    mute_id = synced["transactions"][0]["id"]
    assert synced["transactions"][0]["category"] == "uncategorized"

    # the next statement names it: same row, now with words, category and the statement's provenance
    uploaded = client.post("/api/imports", json={"account_id": bank, "transactions": rows(
        ("2026-11-19", -50.0, "Commercio Savings plan execution LU1829220216 AMUNDI, quantity: 0.1", {"category": "spesa"}),
        ("2026-11-19", -12.0, "PAGAMENTO POS BAR", {"category": "spesa"}),
    )}, headers=headers).json()
    assert uploaded["added_count"] == 1 and uploaded["absorbed_mute_rows"] == 1
    stored = {t["id"]: t for t in client.get("/api/transactions", headers=headers).json()}
    taken = stored[mute_id]
    assert taken["description"].startswith("Commercio Savings plan") and taken["source"] == "statement" and taken["date"] == "2026-11-19"
    assert taken["category"] == "spesa" and len(stored) == 2

    # re-uploading the same statement adds nothing
    again = client.post("/api/imports", json={"account_id": bank, "transactions": rows(
        ("2026-11-19", -50.0, "Commercio Savings plan execution LU1829220216 AMUNDI, quantity: 0.1", {"category": "spesa"}),
    )}, headers=headers).json()
    assert again["added_count"] == 0 and again["skipped_count"] == 1


def test_one_off_absorb_removes_only_the_mute_rows_with_a_twin(client, project):
    headers, bank = project
    # the statement was uploaded first; then the first version of the sync added mute rows without the flag
    client.post("/api/imports", json={"account_id": bank, "transactions": rows(
        ("2026-11-10", -50.0, "Commercio Buy trade LU1829220216 AMUNDI, quantity: 0.1", {}),
    )}, headers=headers)
    client.post("/api/imports", json={"account_id": bank, "source": "bank", "transactions": rows(
        ("2026-11-11", -50.0, "Movimento Trade Republic", {"category": "uncategorized", "category_source": "fallback"}),
        ("2026-11-11", -50.0, "Movimento Trade Republic", {"category": "uncategorized", "category_source": "fallback"}),
        ("2026-11-20", -7.0, "Movimento Trade Republic", {"category": "uncategorized", "category_source": "fallback"}),
    )}, headers=headers)
    assert len(client.get("/api/transactions", headers=headers).json()) == 4
    done = client.post("/api/imports/absorb-mute", params={"account_id": bank}, headers=headers).json()
    assert done == {"removed": 1, "kept": 2}  # one of the two identical mute rows had a twin; the 7 € one has none
    left = sorted((t["date"], t["amount"], t["source"]) for t in client.get("/api/transactions", headers=headers).json())
    assert left == [("2026-11-10", -50.0, "statement"), ("2026-11-11", -50.0, "bank"), ("2026-11-20", -7.0, "bank")]
    assert client.get("/api/imports/suspects", headers=headers).json() == []


def test_zone_aware_timestamps_are_stored_as_naive_utc(client, project):
    headers, bank = project
    consent = {**CONSENT, "valid_until": "2027-05-20T12:00:00+02:00", "session_ref": "ref-tz"}
    created = client.post("/api/bank-connections", json=consent, headers=headers).json()
    assert created["valid_until"] == "2027-05-20T10:00:00"
    updated = client.put(f"/api/bank-connections/{created['id']}", json={"last_sync_at": "2026-11-21T10:00:00+01:00"}, headers=headers)
    assert updated.status_code == 200, updated.text
    assert updated.json()["last_sync_at"] == "2026-11-21T09:00:00"
