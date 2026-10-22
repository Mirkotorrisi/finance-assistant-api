"""Statement import (dedup, batches), transfers between own accounts, and spending reports."""

import pytest
from fastapi.testclient import TestClient

from app import app

BLUEPRINT = {
    "name": "Famiglia",
    "categories": [
        {"key": "casa", "label": "Casa", "children": [{"key": "spesa", "label": "Spesa"}, {"key": "utenze", "label": "Utenze"}]},
        {"key": "svago", "label": "Svago", "children": [{"key": "ristoranti", "label": "Ristoranti"}, {"key": "abbonamenti", "label": "Abbonamenti"}]},
        {"key": "stipendio", "label": "Stipendio", "kind": "income"},
    ],
    "groups": [{"key": "minchiate", "label": "Minchiate", "members": ["svago"]}],
}


def row(day, amount, description, category="spesa"):
    return {"date": day, "amount": amount, "description": description, "category": category}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def banks(client):
    """Two accounts in a fresh workspace with a blueprint; returns (client headers, checking id, card id)."""
    ws = client.post("/api/workspaces", json={"name": "Famiglia", "blueprint": BLUEPRINT}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}
    checking = client.post("/api/accounts", json={"name": "Banca A", "account_type": "checking"}, headers=headers).json()["id"]
    card = client.post("/api/accounts", json={"name": "Carta B", "account_type": "credit"}, headers=headers).json()["id"]
    return headers, checking, card


def do_import(client, headers, account, rows, **extra):
    res = client.post("/api/imports", json={"account_id": account, "transactions": rows, **extra}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_import_assigns_the_account_and_is_idempotent(client, banks):
    headers, checking, _ = banks
    rows = [row("2026-03-01", -42.5, "COOP MILANO"), row("2026-03-02", -9.9, "BAR SPORT", "ristoranti")]

    first = do_import(client, headers, checking, rows, filename="marzo.csv", file_hash="abc")
    assert (first["added_count"], first["skipped_count"], first["duplicate_file"]) == (2, 0, False)
    assert {t["account_id"] for t in first["transactions"]} == {checking}

    again = do_import(client, headers, checking, rows, filename="marzo.csv", file_hash="abc")
    assert (again["added_count"], again["skipped_count"], again["duplicate_file"], again["batch_id"]) == (0, 2, True, None)
    assert len(client.get("/api/transactions", headers=headers).json()) == 2


def test_overlapping_statements_only_add_the_new_rows(client, banks):
    headers, checking, _ = banks
    do_import(client, headers, checking, [row("2026-03-01", -10, "A"), row("2026-03-02", -20, "B")])
    second = do_import(client, headers, checking, [row("2026-03-02", -20, "B"), row("2026-03-03", -30, "C")])
    assert second["added_count"] == 1 and second["transactions"][0]["description"] == "C"


def test_identical_real_purchases_are_kept_and_never_collapsed(client, banks):
    headers, checking, _ = banks
    coffee = row("2026-03-01", -1.2, "BAR CENTRALE")
    assert do_import(client, headers, checking, [coffee, coffee])["added_count"] == 2
    assert do_import(client, headers, checking, [coffee, coffee])["added_count"] == 0  # same statement again
    assert do_import(client, headers, checking, [coffee, coffee, coffee])["added_count"] == 1  # a third coffee appeared


def test_the_same_row_on_two_accounts_is_two_transactions(client, banks):
    headers, checking, card = banks
    r = row("2026-03-01", -15, "AMAZON")
    assert do_import(client, headers, checking, [r])["added_count"] == 1
    assert do_import(client, headers, card, [r])["added_count"] == 1


def test_manually_added_transactions_take_part_in_dedup(client, banks):
    headers, checking, _ = banks
    client.post("/api/transactions", json={"amount": -7, "category": "spesa", "description": "Edicola", "date": "2026-03-04", "account_id": checking}, headers=headers)
    assert do_import(client, headers, checking, [row("2026-03-04", -7, "edicola")])["added_count"] == 0  # case-insensitive text


def test_bad_rows_are_reported_and_good_ones_imported(client, banks):
    headers, checking, _ = banks
    result = do_import(client, headers, checking, [row("2026-03-01", -5, "ok"), {"date": "not-a-date", "amount": -1, "description": "bad"}])
    assert result["added_count"] == 1 and len(result["invalid_rows"]) == 1


def test_account_must_exist_in_the_workspace(client, banks):
    headers, checking, _ = banks
    other = client.post("/api/workspaces", json={"name": "Altro"}).json()
    res = client.post("/api/imports", json={"account_id": checking, "transactions": []}, headers={"X-Workspace-Id": str(other["id"])})
    assert res.status_code == 404  # checking belongs to another workspace


def test_the_same_statement_can_be_imported_in_two_workspaces(client, banks):
    headers, checking, _ = banks
    rows = [row("2026-03-01", -5, "shared")]
    do_import(client, headers, checking, rows)
    other = client.post("/api/workspaces", json={"name": "Studio"}).json()
    oh = {"X-Workspace-Id": str(other["id"])}
    acc = client.post("/api/accounts", json={"name": "S", "account_type": "checking"}, headers=oh).json()["id"]
    assert do_import(client, oh, acc, rows)["added_count"] == 1


def test_undo_removes_exactly_what_the_import_added(client, banks):
    headers, checking, _ = banks
    do_import(client, headers, checking, [row("2026-03-01", -1, "keep")])
    batch = do_import(client, headers, checking, [row("2026-03-02", -2, "drop")])["batch_id"]
    assert client.delete(f"/api/imports/{batch}", headers=headers).json()["transactions_removed"] == 1
    assert [t["description"] for t in client.get("/api/transactions", headers=headers).json()] == ["keep"]
    assert len(client.get("/api/imports", headers=headers).json()) == 1
    assert client.delete(f"/api/imports/{batch}", headers=headers).status_code == 404


# ----------------------------------------------------------------------------- transfers

def import_card_payment(client, headers, checking, card):
    do_import(client, headers, checking, [row("2026-03-05", -500, "BONIFICO PAGAMENTO CARTA", "utenze"), row("2026-03-06", -30, "COOP", "spesa")])
    return do_import(client, headers, card, [row("2026-03-06", 500, "PAGAMENTO RICEVUTO", "stipendio"), row("2026-03-02", -80, "RISTORANTE", "ristoranti")])


def test_a_card_payment_is_detected_as_a_transfer_and_left_out_of_spending(client, banks):
    headers, checking, card = banks
    result = import_card_payment(client, headers, checking, card)
    assert result["transfers_detected"] == 1

    transactions = {t["description"]: t for t in client.get("/api/transactions", headers=headers).json()}
    out, inn = transactions["BONIFICO PAGAMENTO CARTA"], transactions["PAGAMENTO RICEVUTO"]
    assert out["is_transfer"] and inn["is_transfer"] and out["transfer_pair_id"] == inn["id"]
    assert not transactions["COOP"]["is_transfer"]

    summary = client.get("/api/financial-summary/monthly/2026-03", headers=headers).json()
    assert summary["expenses"] == 110.0 and summary["income"] == 0.0  # COOP 30 + RISTORANTE 80, not the 500 twice
    assert client.get("/api/transactions/balance", headers=headers).json()["balance"] == -110.0  # balances still add up


def test_ambiguous_or_keywordless_pairs_are_not_paired_automatically(client, banks):
    headers, checking, card = banks
    do_import(client, headers, checking, [row("2026-03-05", -100, "PAGAMENTO XYZ")])  # no transfer keyword
    result = do_import(client, headers, card, [row("2026-03-05", 100, "ACCREDITO")])
    assert result["transfers_detected"] == 0

    suggestions = client.post("/api/transfers/detect?include_unhinted=true&dry_run=true", headers=headers).json()
    assert suggestions["count"] == 1 and suggestions["pairs"][0]["hinted"] is False
    assert not any(t["is_transfer"] for t in client.get("/api/transactions", headers=headers).json())  # dry run changed nothing

    ids = {t["description"]: t["id"] for t in client.get("/api/transactions", headers=headers).json()}
    client.post("/api/transfers/pair", json={"first_id": ids["PAGAMENTO XYZ"], "second_id": ids["ACCREDITO"]}, headers=headers)
    assert client.get("/api/financial-summary/monthly/2026-03", headers=headers).json()["expenses"] == 0.0


def test_two_equal_inflows_make_a_pair_ambiguous(client, banks):
    headers, checking, card = banks
    do_import(client, headers, checking, [row("2026-03-05", -100, "BONIFICO")])
    result = do_import(client, headers, card, [row("2026-03-05", 100, "ACCREDITO A"), row("2026-03-06", 100, "ACCREDITO B")])
    assert result["transfers_detected"] == 0


def test_unmarking_a_transfer_restores_it_to_spending(client, banks):
    headers, checking, card = banks
    import_card_payment(client, headers, checking, card)
    out = next(t for t in client.get("/api/transactions", headers=headers).json() if t["description"] == "BONIFICO PAGAMENTO CARTA")
    assert set(client.delete(f"/api/transfers/{out['id']}", headers=headers).json()["cleared"]) == {out["id"], out["transfer_pair_id"]}
    assert client.get("/api/financial-summary/monthly/2026-03", headers=headers).json()["expenses"] == 610.0


def test_undoing_an_import_releases_the_transfer_partner(client, banks):
    headers, checking, card = banks
    do_import(client, headers, checking, [row("2026-03-05", -500, "BONIFICO PAGAMENTO CARTA")])
    batch = do_import(client, headers, card, [row("2026-03-06", 500, "PAGAMENTO RICEVUTO")])["batch_id"]
    client.delete(f"/api/imports/{batch}", headers=headers)
    assert not client.get("/api/transactions", headers=headers).json()[0]["is_transfer"]


def test_detection_can_be_switched_off_in_the_blueprint(client, banks):
    headers, checking, card = banks
    ws_id = headers["X-Workspace-Id"]
    client.put(f"/api/workspaces/{ws_id}/blueprint", json={**BLUEPRINT, "settings": {"detect_transfers": False}})
    assert import_card_payment(client, headers, checking, card)["transfers_detected"] == 0


# ----------------------------------------------------------------------------- reports

def seed_report(client, headers, checking, card):
    import_card_payment(client, headers, checking, card)
    do_import(client, headers, checking, [row("2026-03-10", -12.99, "NETFLIX", "abbonamenti"), row("2026-03-12", -25, "Boh negozio", "misc"), row("2026-03-27", 2000, "ACME", "stipendio")])


def report(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in {"start_date": "2026-03-01", "end_date": "2026-03-31", **params}.items())
    res = client.get(f"/api/reports/spending?{query}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_report_by_group_gives_the_minchiate_total(client, banks):
    headers, checking, card = banks
    seed_report(client, headers, checking, card)
    by_group = report(client, headers, group_by="group")
    items = {i["key"]: i for i in by_group["items"]}
    assert items["minchiate"]["amount"] == 92.99  # ristorante 80 + netflix 12.99
    assert items["_ungrouped"]["amount"] == 55.0  # coop 30 + "misc" 25, outside every group
    assert by_group["total"] == 147.99  # the 500 card payment is not spending


def test_report_by_category_maps_names_to_the_blueprint_and_flags_unknown_ones(client, banks):
    headers, checking, card = banks
    seed_report(client, headers, checking, card)
    items = {i["label"]: i for i in report(client, headers, group_by="category")["items"]}
    assert items["Ristoranti"]["mapped"] and items["Ristoranti"]["category_key"] == "ristoranti"
    assert items["misc"]["mapped"] is False and items["misc"]["amount"] == 25.0


def test_report_by_account_month_and_income(client, banks):
    headers, checking, card = banks
    seed_report(client, headers, checking, card)
    by_account = {i["label"]: i["amount"] for i in report(client, headers, group_by="account")["items"]}
    assert by_account == {"Banca A": 67.99, "Carta B": 80.0}
    assert [i["key"] for i in report(client, headers, group_by="month")["items"]] == ["2026-03"]
    income = report(client, headers, flow="income")
    assert income["total"] == 2000.0 and income["transaction_count"] == 1  # the card's +500 is a transfer


def test_report_rejects_bad_parameters(client, banks):
    headers, *_ = banks
    assert client.get("/api/reports/spending?start_date=x&end_date=y", headers=headers).status_code == 400
    assert client.get("/api/reports/spending?start_date=2026-01-01&end_date=2026-01-31&group_by=zzz", headers=headers).status_code == 400
