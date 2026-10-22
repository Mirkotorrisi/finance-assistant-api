"""Templates, validation, change preview and export: the building blocks of blueprint authoring."""

import pytest
from fastapi.testclient import TestClient

from app import app
from src.blueprint import Blueprint, build_template, diff_blueprints, list_templates
from src.blueprint.templates import LOCALES


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("locale", LOCALES)
def test_every_template_is_a_valid_blueprint_in_every_language(locale):
    templates = list_templates(locale)
    assert {t["key"] for t in templates} == {"personal", "family", "freelancer", "small_business"}
    for t in templates:
        blueprint = build_template(t["key"], locale)
        assert blueprint.categories and blueprint.groups and blueprint.name == t["name"]


def test_templates_are_translated_but_share_keys():
    it, en = build_template("family", "it"), build_template("family", "en")
    assert set(it.nodes()) == set(en.nodes()) and it.nodes()["children"].label != en.nodes()["children"].label
    assert it.nodes()["children"].label == "Figli" and en.nodes()["children"].label == "Children"


def test_family_template_separates_the_kids_from_the_household():
    blueprint = build_template("family", "it")
    assert blueprint.group_categories("kids") >= {"children", "school", "kids_goods"}
    assert "groceries" not in blueprint.group_categories("kids")
    assert blueprint.dimensions[0].key == "for_whom"


def test_freelancer_template_marks_business_costs_deductible():
    nodes = build_template("freelancer", "en").nodes()
    assert nodes["software"].attributes["deductible"] is True and nodes["personal"].attributes["deductible"] is False


def test_unknown_locale_falls_back_to_italian():
    assert build_template("personal", "xx").name == "Budget personale"


def test_template_endpoints(client):
    listed = client.get("/api/blueprint-templates?locale=en").json()
    assert {t["key"] for t in listed} == {"personal", "family", "freelancer", "small_business"}
    doc = client.get("/api/blueprint-templates/freelancer?locale=en").json()
    assert Blueprint.model_validate(doc).name == "Freelancer"
    assert client.get("/api/blueprint-templates/nope").status_code == 404


def test_validate_returns_the_normalised_document_and_explains_errors(client):
    ok = client.post("/api/blueprints/validate", json={"name": "X", "categories": [{"key": "a", "label": "A"}]}).json()
    assert ok["valid"] and ok["stats"]["categories"] == 1 and ok["blueprint"]["currency"] == "EUR"  # defaults filled in
    bad = client.post("/api/blueprints/validate", json={"name": "X", "groups": [{"key": "g", "label": "G", "members": ["nope"]}]})
    assert bad.status_code == 422 and "unknown category" in bad.text


def test_a_template_can_be_saved_into_a_new_project(client):
    doc = client.get("/api/blueprint-templates/family?locale=it").json()
    ws = client.post("/api/workspaces", json={"name": "Casa Rossi", "blueprint": doc}).json()
    saved = client.get(f"/api/workspaces/{ws['id']}/blueprint").json()["blueprint"]
    assert saved["name"] == "Famiglia" and len(saved["groups"]) == 3


# ----------------------------------------------------------------------------- diff

def bp(**changes):
    base = {"name": "P", "categories": [{"key": "food", "label": "Food"}, {"key": "fun", "label": "Fun", "children": [{"key": "bars", "label": "Bars"}]}]}
    return Blueprint.model_validate({**base, **changes})


def test_diff_reports_added_removed_renamed_and_moved_categories():
    new = Blueprint.model_validate({
        "name": "P2",
        "categories": [{"key": "food", "label": "Groceries"}, {"key": "bars", "label": "Bars"}, {"key": "gifts", "label": "Gifts"}],
    })
    diff = diff_blueprints(bp(), new)
    assert diff["name_changed"]
    assert [c["key"] for c in diff["categories"]["added"]] == ["gifts"]
    assert [c["key"] for c in diff["categories"]["removed"]] == ["fun"]
    assert diff["categories"]["renamed"] == [{"key": "food", "from": "Food", "to": "Groceries"}]
    assert diff["categories"]["moved"] == [{"key": "bars", "from": "fun", "to": None}]
    assert not diff["is_empty"]


def test_diff_of_identical_blueprints_is_empty():
    assert diff_blueprints(bp(), bp())["is_empty"]


def test_diff_covers_groups_dimensions_and_rules():
    new = bp(groups=[{"key": "g", "label": "G", "members": ["food"]}], dimensions=[{"key": "d", "label": "D", "values": [{"key": "a", "label": "A"}]}], rules=[{"pattern": "coop", "category": "food"}])
    diff = diff_blueprints(bp(), new)
    assert diff["groups"]["added"] == ["g"] and diff["dimensions"]["added"] == ["d"] and diff["rules"]["added"] == 1


# ----------------------------------------------------------------------------- preview & export

def test_preview_counts_the_transactions_that_would_lose_their_category(client):
    ws = client.post("/api/workspaces", json={"name": "P", "blueprint": {"name": "P", "categories": [{"key": "food", "label": "Food"}, {"key": "fun", "label": "Fun"}]}}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}
    for category in ("food", "Fun", "Fun", "unknown"):
        client.post("/api/transactions", json={"amount": -1, "category": category, "description": "x"}, headers=headers)

    new = {"name": "P", "categories": [{"key": "food", "label": "Food"}]}  # drops "fun"
    preview = client.post(f"/api/workspaces/{ws['id']}/blueprint/preview", json=new).json()
    assert preview["impact"]["affected_transactions"] == 2
    assert preview["impact"]["by_category"] == [{"key": "fun", "label": "Fun", "transactions": 2, "texts": ["Fun"]}]
    assert [c["key"] for c in preview["diff"]["categories"]["removed"]] == ["fun"]
    # nothing was saved
    assert client.get(f"/api/workspaces/{ws['id']}/blueprint").json()["version"] == 1
    # the "current" alias resolves from the headers
    assert client.post("/api/workspaces/current/blueprint/preview", json=new, headers=headers).json()["workspace_id"] == ws["id"]


def test_preview_with_nothing_removed_has_no_impact(client):
    ws = client.post("/api/workspaces", json={"name": "P", "blueprint": bp().to_json()}).json()
    preview = client.post(f"/api/workspaces/{ws['id']}/blueprint/preview", json=bp().to_json()).json()
    assert preview["diff"]["is_empty"] and preview["impact"]["affected_transactions"] == 0


def test_preview_rejects_an_invalid_document(client):
    ws = client.post("/api/workspaces", json={"name": "P"}).json()
    res = client.post(f"/api/workspaces/{ws['id']}/blueprint/preview", json={"name": "x", "rules": [{"pattern": "a", "category": "nope"}]})
    assert res.status_code == 422


def test_export_downloads_a_file_that_imports_back(client):
    ws = client.post("/api/workspaces", json={"name": "Studio", "blueprint": build_template("freelancer", "en").to_json()}).json()
    res = client.get(f"/api/workspaces/{ws['id']}/blueprint/export")
    assert res.status_code == 200 and "attachment" in res.headers["content-disposition"] and ".json" in res.headers["content-disposition"]
    other = client.post("/api/workspaces", json={"name": "Copy", "blueprint": res.json()}).json()
    assert client.get(f"/api/workspaces/{other['id']}/blueprint").json()["blueprint"] == res.json()


def test_preview_is_refused_for_another_users_workspace(client):
    ws = client.post("/api/workspaces", json={"name": "Mine"}, headers={"X-User-Id": "alice"}).json()
    res = client.post(f"/api/workspaces/{ws['id']}/blueprint/preview", json={"name": "x"}, headers={"X-User-Id": "bob"})
    assert res.status_code == 403
