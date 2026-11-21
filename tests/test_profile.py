"""Client profile, IPS approval, decision log and the advisor review."""

import pytest
from app import app
from fastapi.testclient import TestClient
from src.profile import ClientProfile, merge_profile

BLUEPRINT = {
    "name": "Io",
    "categories": [
        {"key": "spesa", "label": "Spesa"},
        {"key": "stipendio", "label": "Stipendio", "kind": "income"},
        {"key": "investimenti", "label": "Investimenti", "kind": "investment"},
    ],
}

IPS = {
    "objective": "Pensione integrativa fra 25 anni",
    "horizon_years": 25,
    "target_allocation": [
        {"asset_class": "equity", "weight": 70},
        {"asset_class": "bonds", "weight": 20},
        {"asset_class": "cash", "weight": 10},
    ],
    "rebalance_rule": "Una volta l'anno o oltre la banda del 5%",
    "contribution_plan": "500 € al mese in PAC",
    "constraints": ["niente singoli titoli", "niente leva"],
}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client):
    ws = client.post("/api/workspaces", json={"name": "P", "blueprint": BLUEPRINT}).json()
    return {"X-Workspace-Id": str(ws["id"])}


def test_empty_profile_before_anything_is_saved(client, project):
    res = client.get("/api/workspaces/current/profile", headers=project)
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 0 and body["ips_status"] == "none"
    assert body["completeness"]["income"] is False
    assert body["profile"]["situation"]["income"]["kind"] == "employee"


def test_patch_merges_and_versions(client, project):
    first = client.patch(
        "/api/workspaces/current/profile",
        json={"patch": {"situation": {"income": {"net_monthly": 2500, "kind": "employee"}}}, "source": "agent"},
        headers=project,
    )
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1 and first.json()["updated_by"] == "agent"

    second = client.patch(
        "/api/workspaces/current/profile",
        json={"patch": {"goals": [{"key": "casa", "label": "Anticipo casa", "amount": 50000, "priority": 1}]}},
        headers=project,
    ).json()
    assert second["version"] == 2
    assert second["profile"]["situation"]["income"]["net_monthly"] == 2500  # untouched by the second patch
    assert second["completeness"]["income"] and second["completeness"]["goals"]

    # a goal with the same key is updated, not duplicated; another is added
    third = client.patch(
        "/api/workspaces/current/profile",
        json={"patch": {"goals": [{"key": "casa", "amount": 60000}, {"key": "auto", "label": "Auto", "amount": 15000}]}},
        headers=project,
    ).json()
    goals = {g["key"]: g for g in third["profile"]["goals"]}
    assert goals["casa"]["amount"] == 60000 and goals["casa"]["label"] == "Anticipo casa" and "auto" in goals

    versions = client.get("/api/workspaces/current/profile/versions", headers=project).json()["versions"]
    assert [v["version"] for v in versions] == [3, 2, 1]
    assert versions[-1]["profile"]["goals"] == []


def test_invalid_patch_is_refused_and_nothing_changes(client, project):
    client.patch("/api/workspaces/current/profile", json={"patch": {"notes": "ok"}}, headers=project)
    bad = client.patch(
        "/api/workspaces/current/profile",
        json={"patch": {"ips": {"target_allocation": [{"asset_class": "equity", "weight": 70}]}}},
        headers=project,
    )
    assert bad.status_code == 422 and "add up to 100" in bad.text
    assert client.get("/api/workspaces/current/profile", headers=project).json()["version"] == 1

    bad_key = client.patch(
        "/api/workspaces/current/profile", json={"patch": {"goals": [{"key": "Casa Nuova", "label": "x"}]}}, headers=project
    )
    assert bad_key.status_code == 422


def test_ips_approval_is_bound_to_the_policy_text(client, project):
    # nothing to approve yet
    assert client.post("/api/workspaces/current/profile/ips/approve", headers=project).status_code == 400

    client.patch("/api/workspaces/current/profile", json={"patch": {"ips": IPS}}, headers=project)
    assert client.get("/api/workspaces/current/profile", headers=project).json()["ips_status"] == "pending"

    approved = client.post("/api/workspaces/current/profile/ips/approve", headers=project).json()
    assert approved["ips_status"] == "approved" and approved["ips_approved_at"]

    # editing anything but the policy keeps the approval
    same = client.patch("/api/workspaces/current/profile", json={"patch": {"notes": "ciao"}}, headers=project).json()
    assert same["ips_status"] == "approved"

    # rewriting the policy makes it pending again, whoever did it
    changed = client.patch(
        "/api/workspaces/current/profile",
        json={"patch": {"ips": {"rebalance_rule": "Ogni mese"}}, "source": "agent"},
        headers=project,
    ).json()
    assert changed["ips_status"] == "pending" and changed["ips_approved_at"] is None


def test_put_replaces_the_whole_document(client, project):
    client.patch("/api/workspaces/current/profile", json={"patch": {"notes": "vecchio"}}, headers=project)
    doc = ClientProfile().to_json()
    doc["situation"]["housing"] = {"status": "rent", "monthly_cost": 900}
    res = client.put("/api/workspaces/current/profile", json=doc, headers=project)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["profile"]["notes"] == "" and body["profile"]["situation"]["housing"]["status"] == "rent"
    assert body["version"] == 2


def test_profiles_are_isolated_between_workspaces(client, project):
    other = client.post("/api/workspaces", json={"name": "Altro"}).json()
    client.patch("/api/workspaces/current/profile", json={"patch": {"notes": "mio"}}, headers=project)
    assert client.get("/api/workspaces/current/profile", headers={"X-Workspace-Id": str(other["id"])}).json()["version"] == 0
    client.post(
        "/api/advisor/decisions",
        json={"title": "Fondo emergenza", "rationale": "Mancano 3 mesi di spese al fondo di emergenza", "data_refs": ["advisor_review 2026-11: months_covered 3"]},
        headers=project,
    )
    assert client.get("/api/advisor/decisions", headers={"X-Workspace-Id": str(other["id"])}).json() == []
    assert len(client.get("/api/advisor/decisions", headers=project).json()) == 1


def test_decisions_need_evidence_and_track_their_status(client, project):
    no_refs = client.post(
        "/api/advisor/decisions",
        json={"title": "Compra tutto", "rationale": "Perché sì, è una buona idea", "data_refs": []},
        headers=project,
    )
    assert no_refs.status_code == 422

    blank_refs = client.post(
        "/api/advisor/decisions",
        json={"title": "Compra tutto", "rationale": "Perché sì, è una buona idea", "data_refs": ["  "]},
        headers=project,
    )
    assert blank_refs.status_code == 422 and "data reference" in blank_refs.text

    client.patch("/api/workspaces/current/profile", json={"patch": {"ips": IPS}}, headers=project)
    created = client.post(
        "/api/advisor/decisions",
        json={
            "title": "Portare il fondo emergenza a 6 mesi",
            "rationale": "Il fondo copre 3,2 mesi di spese medie (1.900 €/mese); l'IPS chiede 6 mesi prima di investire.",
            "data_refs": ["advisor_review 2026-11-21: emergency_fund.months_covered=3.2", "spending_report 2025-12..2026-11: expenses_monthly_avg=1900"],
            "ips_refs": ["constraints: fondo emergenza prima"],
        },
        headers=project,
    )
    assert created.status_code == 201, created.text
    decision = created.json()
    assert decision["status"] == "proposed" and decision["profile_version"] == 1

    updated = client.put(f"/api/advisor/decisions/{decision['id']}", json={"status": "accepted"}, headers=project).json()
    assert updated["status"] == "accepted"
    assert client.get("/api/advisor/decisions", params={"status": "accepted"}, headers=project).json()[0]["id"] == decision["id"]
    assert client.get("/api/advisor/decisions", params={"status": "nope"}, headers=project).status_code == 400
    assert client.put("/api/advisor/decisions/999", json={"status": "done"}, headers=project).status_code == 404


def test_review_gathers_the_figures_and_the_failing_checks(client, project):
    bank = client.post("/api/accounts", json={"name": "Banca", "account_type": "checking"}, headers=project).json()["id"]
    saving = client.post("/api/accounts", json={"name": "Risparmio", "account_type": "savings"}, headers=project).json()["id"]
    rows = []
    for month in range(1, 7):
        rows.append({"date": f"2026-{month:02d}-02", "amount": 2000, "description": "Stipendio", "category": "stipendio"})
        rows.append({"date": f"2026-{month:02d}-10", "amount": -1500, "description": "Spesa coop", "category": "spesa"})
    assert client.post("/api/imports", json={"account_id": bank, "transactions": rows}, headers=project).status_code == 200
    client.post("/api/balance-snapshots", json={"account_id": saving, "date": "2026-06-30", "balance": 3000}, headers=project)
    client.post("/api/balance-snapshots", json={"account_id": bank, "date": "2026-06-30", "balance": 3000}, headers=project)

    client.patch(
        "/api/workspaces/current/profile",
        json={"patch": {
            "situation": {
                "emergency_fund": {"target_months": 6, "account_ids": [saving]},
                "debts": [{"key": "prestito", "label": "Prestito auto", "balance": 8000, "annual_rate": 7.5, "monthly_payment": 250}],
            },
            "ips": IPS,
        }},
        headers=project,
    )

    from datetime import date
    from unittest.mock import patch as mock_patch

    from src.services import advisor_service

    with mock_patch.object(advisor_service, "date", wraps=date) as fake_date:
        fake_date.today.return_value = date(2026, 6, 30)
        res = client.get("/api/advisor/review", params={"months": 6}, headers=project)
    assert res.status_code == 200, res.text
    review = res.json()

    flow = review["cash_flow"]
    assert flow["months_with_data"] == 6 and flow["income_total"] == 12000 and flow["expenses_total"] == 9000
    assert flow["saving_rate"] == 0.25 and flow["expenses_monthly_avg"] == 1500

    fund = review["emergency_fund"]
    assert fund["basis"] == "accounts" and fund["amount"] == 3000 and fund["months_covered"] == 2.0
    assert fund["target_amount"] == 9000 and fund["shortfall"] == 6000

    assert review["net_worth"]["total"] == 6000
    assert review["allocation"]["current"] == {"cash": 100.0, "invested": 0.0}
    assert review["allocation"]["cash_weight_drift"] == 90.0

    keys = {c["key"]: c for c in review["checks"]}
    assert keys["emergency_short"]["severity"] == "critical" and keys["emergency_short"]["data"]["shortfall"] == 6000
    assert keys["expensive_debt"]["data"]["debts"][0]["key"] == "prestito"
    assert keys["ips_pending"]["severity"] == "warning"
    assert "negative_saving" not in keys and "no_transactions" not in keys


def test_review_on_an_empty_project_says_what_is_missing(client, project):
    review = client.get("/api/advisor/review", headers=project).json()
    keys = {c["key"] for c in review["checks"]}
    assert {"ips_missing", "no_transactions", "emergency_unknown", "profile_incomplete", "no_balances"} <= keys
    assert review["cash_flow"]["saving_rate"] is None and review["allocation"]["current"] is None


def test_merge_profile_replaces_unkeyed_lists_and_keeps_schema_version():
    base = merge_profile(ClientProfile(), {"ips": {"constraints": ["a", "b"]}})
    merged = merge_profile(base, {"ips": {"constraints": ["c"]}, "schema_version": 99})
    assert merged.ips.constraints == ["c"] and merged.schema_version == 1
