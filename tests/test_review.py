"""Provenance of categories, the review queue, merchant memory and coverage."""

import pytest
from fastapi.testclient import TestClient

from app import app
from src.services.merchant import merchant_key, normalize_text, resolve

BLUEPRINT = {
    "name": "Famiglia",
    "categories": [
        {"key": "casa", "label": "Casa", "children": [{"key": "spesa", "label": "Spesa"}, {"key": "utenze", "label": "Utenze"}]},
        {"key": "svago", "label": "Svago", "children": [{"key": "ristoranti", "label": "Ristoranti"}, {"key": "abbonamenti", "label": "Abbonamenti"}]},
    ],
    "groups": [{"key": "minchiate", "label": "Minchiate", "members": ["svago"]}],
}


def row(day, amount, description, category="spesa", source=None, confidence=None):
    data = {"date": day, "amount": amount, "description": description, "category": category}
    if source:
        data["category_source"] = source
    if confidence is not None:
        data["confidence"] = confidence
    return data


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client):
    ws = client.post("/api/workspaces", json={"name": "P", "blueprint": BLUEPRINT}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}
    account = client.post("/api/accounts", json={"name": "Banca A", "account_type": "checking"}, headers=headers).json()["id"]
    other = client.post("/api/accounts", json={"name": "Carta B", "account_type": "credit"}, headers=headers).json()["id"]
    return headers, account, other


def do_import(client, headers, account, rows):
    res = client.post("/api/imports", json={"account_id": account, "transactions": rows}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def by_description(client, headers):
    return {t["description"]: t for t in client.get("/api/transactions", headers=headers).json()}


# ----------------------------------------------------------------------------- merchant identity

def test_merchant_key_ignores_bank_noise_numbers_and_dates():
    assert merchant_key("PAGAMENTO POS COOP LOMBARDIA MILANO 12/03 CARTA *4821") == merchant_key("COOP LOMBARDIA MILANO 0345")
    assert merchant_key("SDD ENEL ENERGIA 998877") == "enel energia"
    assert merchant_key("PAGAMENTO POS COOP LOMBARDIA MILANO") == "coop lombardia"  # the city is not part of the identity
    assert merchant_key("1234 56") == "unknown" and merchant_key("") == "unknown"
    assert normalize_text("Caffè  Müller") == "caffe muller"


def test_a_longer_rule_wins_and_rules_match_raw_or_normalised_text():
    rules = [{"pattern": "amazon", "category": "shopping"}, {"pattern": "amazon prime", "category": "abbonamenti"}]
    found = {r["description"]: r["category"] for r in resolve(["AMAZON PRIME VIDEO 12", "AMAZON EU SARL", "Bar Sport"], rules)}
    assert found == {"AMAZON PRIME VIDEO 12": "abbonamenti", "AMAZON EU SARL": "shopping", "Bar Sport": None}


# ----------------------------------------------------------------------------- provenance

def test_import_records_who_decided_and_only_user_decisions_are_confirmed(client, project):
    headers, account, _ = project
    do_import(client, headers, account, [
        row("2026-03-01", -10, "A file row", "spesa"),
        row("2026-03-02", -11, "B rule row", "spesa", source="rule"),
        row("2026-03-03", -12, "C ai row", "Ristoranti", source="ai", confidence=0.9),
        row("2026-03-04", -13, "D user row", "utenze", source="user"),
    ])
    t = by_description(client, headers)
    assert [(t[d]["category_source"], t[d]["reviewed"]) for d in ("A file row", "B rule row", "C ai row", "D user row")] == [
        ("file", False), ("rule", True), ("ai", False), ("user", True)]
    assert t["C ai row"]["confidence"] == 0.9
    assert t["C ai row"]["category"] == "ristoranti" and t["C ai row"]["category_label"] == "Ristoranti"  # stored as the key
    assert t["A file row"]["merchant_key"] == "file row"


def test_an_unknown_source_is_an_invalid_row(client, project):
    headers, account, _ = project
    result = do_import(client, headers, account, [row("2026-03-01", -1, "x", source="magic")])
    assert result["added_count"] == 0 and "category_source" in result["invalid_rows"][0]


def test_edits_made_by_the_user_are_confirmed_but_ai_suggestions_are_not(client, project):
    headers, account, _ = project
    added = client.post("/api/transactions", json={"amount": -5, "category": "Ristoranti", "description": "Pizza"}, headers=headers).json()
    assert (added["category"], added["reviewed"], added["category_source"]) == ("ristoranti", True, "user")

    imported = do_import(client, headers, account, [row("2026-03-01", -9, "Mystery", "spesa", source="ai", confidence=0.4)])["transactions"][0]
    assert imported["reviewed"] is False
    edited = client.put(f"/api/transactions/{imported['id']}", json={"category": "Utenze"}, headers=headers).json()
    assert (edited["category"], edited["category_source"], edited["reviewed"], edited["confidence"]) == ("utenze", "user", True, None)

    other = do_import(client, headers, account, [row("2026-03-02", -9, "Other", "spesa", source="ai", confidence=0.4)])["transactions"][0]
    suggested = client.put("/api/transactions/bulk-category", json={"updates": [{"transaction_id": other["id"], "category": "Spesa", "source": "ai", "confidence": 0.6}]}, headers=headers).json()[0]
    assert suggested["reviewed"] is False and suggested["confidence"] == 0.6
    confirmed = client.put("/api/transactions/bulk-category", json={"updates": [{"transaction_id": other["id"], "category": "Spesa"}]}, headers=headers).json()[0]
    assert confirmed["reviewed"] is True


def test_remap_and_recategorize_count_as_user_decisions(client, project):
    headers, account, _ = project
    do_import(client, headers, account, [row("2026-03-01", -9, "COOP A", "misc", source="ai", confidence=0.3), row("2026-03-02", -9, "NETFLIX", "misc2", source="ai", confidence=0.3)])
    client.post("/api/transactions/remap-category", json={"from_category": "misc", "to_category": "Spesa"}, headers=headers)
    client.post("/api/merchant-rules/recategorize", json={"pattern": "netflix", "category": "abbonamenti"}, headers=headers)
    t = by_description(client, headers)
    assert t["COOP A"]["reviewed"] and t["NETFLIX"]["reviewed"]


def test_category_filter_matches_key_label_and_old_names(client, project):
    headers, account, _ = project
    ws_id = headers["X-Workspace-Id"]
    do_import(client, headers, account, [row("2026-03-01", -9, "Pizza", "Ristoranti"), row("2026-03-02", -9, "Cena", "ristoranti"), row("2026-03-03", -9, "Altro", "spesa")])
    for spelling in ("ristoranti", "Ristoranti", "RISTORANTI"):
        assert len(client.get(f"/api/transactions?category={spelling}", headers=headers).json()) == 2
    blueprint = BLUEPRINT | {"categories": [BLUEPRINT["categories"][0], {"key": "svago", "label": "Svago", "children": [{"key": "ristoranti", "label": "Locali", "aliases": ["Ristoranti"]}, {"key": "abbonamenti", "label": "Abbonamenti"}]}]}
    client.put(f"/api/workspaces/{ws_id}/blueprint", json=blueprint)
    assert len(client.get("/api/transactions?category=Locali", headers=headers).json()) == 2  # the new label finds them
    assert client.get("/api/transactions?category=Locali", headers=headers).json()[0]["category_label"] == "Locali"


# ----------------------------------------------------------------------------- queue

def seed_queue(client, headers, a, b):
    do_import(client, headers, a, [
        row("2026-03-02", -40, "PAGAMENTO POS COOP LOMBARDIA MILANO 12/03", "spesa", source="ai", confidence=0.9),
        row("2026-03-09", -60, "COOP LOMBARDIA 0345", "spesa", source="ai", confidence=0.7),
        row("2026-03-10", -12.99, "NETFLIX.COM", "abbonamenti", source="ai", confidence=0.95),
        row("2026-03-11", -5, "Boh negozio", "ristoranti", source="ai", confidence=0.3),
        row("2026-03-05", -500, "BONIFICO PAGAMENTO CARTA", "utenze", source="ai", confidence=0.5),
        row("2026-03-13", -20, "ENEL ENERGIA", "utenze", source="rule"),  # already confirmed
    ])
    do_import(client, headers, b, [row("2026-03-06", 500, "PAGAMENTO RICEVUTO", "utenze", source="ai", confidence=0.5), row("2026-03-14", -30, "Coop Lombardia", "ristoranti", source="ai", confidence=0.4)])


def test_queue_groups_one_merchant_across_spellings_and_banks_biggest_first(client, project):
    headers, a, b = project
    seed_queue(client, headers, a, b)
    queue = client.get("/api/review/queue", headers=headers).json()
    keys = [g["merchant_key"] for g in queue["groups"]]
    assert keys[0] == "coop lombardia" and "enel energia" not in keys  # confirmed rows are not queued
    assert "bonifico" not in " ".join(keys)  # the 500 transfer is excluded
    coop = queue["groups"][0]
    assert coop["transactions"] == 3 and coop["total_amount"] == 130.0 and coop["mixed"] is True
    assert coop["suggestion"]["key"] == "spesa" and coop["suggestion"]["transactions"] == 2
    assert coop["suggestion"]["confidence"] == 0.8 and coop["suggestion"]["source"] == "ai"
    assert queue["unreviewed_transactions"] == 5 and queue["total_groups"] == 3


def test_confirming_a_merchant_settles_all_its_transactions_and_remembers_it(client, project):
    headers, a, b = project
    seed_queue(client, headers, a, b)
    done = client.post("/api/review/confirm", json={"merchant_key": "coop lombardia", "category": "Spesa"}, headers=headers).json()
    assert done == {"merchant_key": "coop lombardia", "category": "spesa", "transactions_updated": 3, "rule_created": True}
    coops = [t for t in client.get("/api/transactions", headers=headers).json() if t["merchant_key"] == "coop lombardia"]
    assert {(t["category"], t["category_source"], t["reviewed"]) for t in coops} == {("spesa", "user", True)}

    rule = client.post("/api/merchant-rules/resolve", json={"descriptions": ["COOP LOMBARDIA 9911 ROMA", "Bar Sport"]}, headers=headers).json()
    assert [r["category"] for r in rule] == ["spesa", None]  # a later statement is recognised without any AI
    assert "coop lombardia" not in [g["merchant_key"] for g in client.get("/api/review/queue", headers=headers).json()["groups"]]


def test_confirm_can_skip_the_rule_and_rejects_names_outside_the_blueprint(client, project):
    headers, a, b = project
    seed_queue(client, headers, a, b)
    no_rule = client.post("/api/review/confirm", json={"merchant_key": "netflix com", "category": "abbonamenti", "create_rule": False}, headers=headers).json()
    assert no_rule["rule_created"] is False and client.get("/api/merchant-rules", headers=headers).json() == []
    assert client.post("/api/review/confirm", json={"merchant_key": "boh negozio", "category": "Inventata"}, headers=headers).status_code == 422
    assert client.post("/api/review/confirm", json={"merchant_key": "boh negozio", "category": "Casa"}, headers=headers).status_code == 422  # has subcategories


def test_a_project_without_a_blueprint_accepts_any_category_name(client):
    ws = client.post("/api/workspaces", json={"name": "Vuoto"}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}
    acc = client.post("/api/accounts", json={"name": "A", "account_type": "cash"}, headers=headers).json()["id"]
    do_import(client, headers, acc, [row("2026-03-01", -5, "Boh negozio", "x", source="ai", confidence=0.2)])
    done = client.post("/api/review/confirm", json={"merchant_key": "boh negozio", "category": "Cose varie"}, headers=headers).json()
    assert done["category"] == "Cose varie" and done["transactions_updated"] == 1


def test_accept_confirms_suggestions_without_changing_them(client, project):
    headers, a, b = project
    seed_queue(client, headers, a, b)
    done = client.post("/api/review/accept", json={"merchant_key": "netflix com", "create_rule": True}, headers=headers).json()
    assert done == {"transactions_accepted": 1, "rule_created": True}
    netflix = by_description(client, headers)["NETFLIX.COM"]
    assert (netflix["category"], netflix["reviewed"]) == ("abbonamenti", True)
    assert client.get("/api/merchant-rules", headers=headers).json()[0]["category"] == "abbonamenti"
    assert client.post("/api/review/accept", json={}, headers=headers).status_code == 422
    everything = client.post("/api/review/accept", json={"all_unreviewed": True}, headers=headers).json()
    assert everything["transactions_accepted"] == 4  # 3 coop + boh; transfers are never in the queue
    assert client.get("/api/review/queue", headers=headers).json()["total_groups"] == 0


def test_the_unknown_merchant_group_never_creates_a_rule(client, project):
    headers, a, _ = project
    do_import(client, headers, a, [row("2026-03-01", -5, "12345 678", "spesa", source="ai", confidence=0.2)])
    done = client.post("/api/review/confirm", json={"merchant_key": "unknown", "category": "spesa"}, headers=headers).json()
    assert done["transactions_updated"] == 1 and done["rule_created"] is False


# ----------------------------------------------------------------------------- coverage

def test_reports_say_how_much_of_the_total_is_confirmed(client, project):
    headers, a, b = project
    seed_queue(client, headers, a, b)
    params = "start_date=2026-03-01&end_date=2026-03-31"
    report = client.get(f"/api/reports/spending?{params}&group_by=group", headers=headers).json()
    cov = report["coverage"]
    # spending = coop 40+60+30, netflix 12.99, boh 5 (unconfirmed) + enel 20 (confirmed); the 500 transfer is out
    assert cov["total"] == 167.99 and cov["reviewed_amount"] == 20.0 and cov["unreviewed_amount"] == 147.99
    assert cov["reviewed_share"] == round(20 / 167.99, 4) and cov["unreviewed_transactions"] == 5

    client.post("/api/review/accept", json={"all_unreviewed": True}, headers=headers)
    assert client.get(f"/api/reports/spending?{params}", headers=headers).json()["coverage"]["reviewed_share"] == 1.0
    assert client.get("/api/review/coverage", headers=headers).json()["unreviewed_amount"] == 0.0


def test_coverage_of_an_empty_period_is_complete(client, project):
    headers, *_ = project
    cov = client.get("/api/reports/spending?start_date=2020-01-01&end_date=2020-01-31", headers=headers).json()["coverage"]
    assert cov["total"] == 0 and cov["reviewed_share"] == 1.0


def test_review_is_scoped_to_the_workspace(client, project):
    headers, a, b = project
    seed_queue(client, headers, a, b)
    other = client.post("/api/workspaces", json={"name": "Altro"}).json()
    assert client.get("/api/review/queue", headers={"X-Workspace-Id": str(other["id"])}).json()["total_groups"] == 0
    client.post("/api/review/accept", json={"all_unreviewed": True}, headers={"X-Workspace-Id": str(other["id"])})
    assert client.get("/api/review/queue", headers=headers).json()["total_groups"] == 3  # untouched
