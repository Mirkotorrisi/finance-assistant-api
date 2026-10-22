"""Charts show the blueprint's labels, and spellings of one category add up."""

import datetime

import pytest
from fastapi.testclient import TestClient

from app import app
from src.database import init as db_init
from src.database.models import Transaction

BLUEPRINT = {
    "name": "P",
    "categories": [
        {"key": "dining_out", "label": "Ristoranti e bar", "aliases": ["Ristoranti"]},
        {"key": "groceries", "label": "Spesa"},
    ],
}


@pytest.fixture
def project():
    with TestClient(app) as client:
        ws = client.post("/api/workspaces", json={"name": "P", "blueprint": BLUEPRINT}).json()
        headers = {"X-Workspace-Id": str(ws["id"])}
        # rows written straight to the table, as they are in an older database: the key, an old label, an unknown name
        session = db_init.get_db_session(ws["id"])
        for day, amount, description, category in [
            (1, -10, "Pizza", "dining_out"), (2, -5, "Bar", "Ristoranti"), (3, -20, "Coop", "groceries"), (4, -7, "Boh", "misc"),
        ]:
            session.add(Transaction(date=datetime.date(2026, 3, day), amount=amount, category=category, description=description))
        session.commit()
        session.close()
        yield client, headers


def test_top_categories_use_labels_and_merge_spellings(project):
    client, headers = project
    summary = client.get("/api/financial-summary/monthly/2026-03", headers=headers).json()
    categories = {c["category"]: c["amount"] for c in summary["top_categories"]}
    # "dining_out" (the key) and "Ristoranti" (an old label) are one category; "misc" is unknown and shown as it is
    assert categories == {"Spesa": 20.0, "Ristoranti e bar": 15.0, "misc": 7.0}


def test_spending_distribution_uses_labels_too(project):
    client, headers = project
    dist = client.get("/api/financial-summary/spending-distribution?start_date=2026-03-01&end_date=2026-03-31", headers=headers).json()
    assert {i["name"]: i["amount"] for i in dist["distribution"]} == {"Spesa": 20.0, "Ristoranti e bar": 15.0, "misc": 7.0}
