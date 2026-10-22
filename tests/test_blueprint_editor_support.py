"""What the blueprint editor relies on: aliases, category usage, remapping and impact detail."""

import pytest
from fastapi.testclient import TestClient

from app import app
from src.blueprint import Blueprint


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def make_project(client, blueprint):
    ws = client.post("/api/workspaces", json={"name": "P", "blueprint": blueprint}).json()
    return ws["id"], {"X-Workspace-Id": str(ws["id"])}


def add(client, headers, category, amount=-10.0, description="x"):
    client.post("/api/transactions", json={"amount": amount, "category": category, "description": description}, headers=headers)


BASE = {"name": "P", "categories": [{"key": "office", "label": "Spese d'ufficio"}, {"key": "food", "label": "Cibo"}]}


def test_aliases_resolve_old_names_without_rewriting_data():
    blueprint = Blueprint.model_validate({"name": "x", "categories": [{"key": "office", "label": "Studio", "aliases": ["Spese d'ufficio", "UFFICIO"]}]})
    assert blueprint.resolve_category("spese d'ufficio") == "office"
    assert blueprint.resolve_category("Ufficio") == "office"
    assert blueprint.resolve_category("Studio") == "office"
    assert blueprint.resolve_category("altro") is None


def test_a_renamed_label_keeps_working_through_its_alias(client):
    ws_id, headers = make_project(client, BASE)
    add(client, headers, "Spese d'ufficio", -50)
    renamed = {"name": "P", "categories": [{"key": "office", "label": "Studio", "aliases": ["Spese d'ufficio"]}, {"key": "food", "label": "Cibo"}]}
    client.put(f"/api/workspaces/{ws_id}/blueprint", json=renamed)
    report = client.get("/api/reports/spending?start_date=2000-01-01&end_date=2100-01-01&group_by=category", headers=headers).json()
    item = next(i for i in report["items"] if i["category_key"] == "office")
    assert item["mapped"] and item["amount"] == 50.0 and item["label"] == "Studio"


def test_category_usage_lists_unknown_categories_first_and_skips_transfers(client):
    ws_id, headers = make_project(client, BASE)
    add(client, headers, "cibo", -20)
    add(client, headers, "Cibo", -5)
    add(client, headers, "misc", -7)
    add(client, headers, "misc", -3)
    add(client, headers, "viaggi", -1)
    transfer = client.post("/api/transactions", json={"amount": -999, "category": "giro", "description": "t"}, headers=headers).json()
    client.put(f"/api/transactions/{transfer['id']}", json={"is_transfer": True}, headers=headers)

    usage = client.get("/api/reports/category-usage", headers=headers).json()
    # "cibo" and "Cibo" are the blueprint's "food": added transactions are stored under its stable key
    assert [(u["category"], u["key"], u["transactions"]) for u in usage] == [("misc", None, 2), ("viaggi", None, 1), ("food", "food", 2)]
    assert next(u for u in usage if u["category"] == "misc")["net_amount"] == -10.0


def test_remap_moves_every_transaction_of_a_category_case_insensitively(client):
    ws_id, headers = make_project(client, BASE)
    add(client, headers, "Misc")
    add(client, headers, "misc")
    add(client, headers, "other")
    result = client.post("/api/transactions/remap-category", json={"from_category": "MISC", "to_category": "Cibo"}, headers=headers).json()
    assert result["transactions_updated"] == 2
    categories = sorted(t["category"] for t in client.get("/api/transactions", headers=headers).json())
    assert categories == ["Cibo", "Cibo", "other"]


def test_remap_does_not_touch_another_workspace(client):
    _, mine = make_project(client, BASE)
    _, other = make_project(client, BASE)
    add(client, mine, "misc")
    add(client, other, "misc")
    client.post("/api/transactions/remap-category", json={"from_category": "misc", "to_category": "food"}, headers=mine)
    assert [t["category"] for t in client.get("/api/transactions", headers=other).json()] == ["misc"]


def test_preview_lists_the_exact_texts_to_reassign(client):
    ws_id, headers = make_project(client, BASE)
    add(client, headers, "Spese d'ufficio")
    add(client, headers, "office")
    add(client, headers, "Cibo")
    preview = client.post(f"/api/workspaces/{ws_id}/blueprint/preview", json={"name": "P", "categories": [{"key": "food", "label": "Cibo"}]}).json()
    entry = preview["impact"]["by_category"][0]
    assert entry["key"] == "office" and entry["transactions"] == 2 and entry["texts"] == ["office"]  # both spellings were stored as the key
