"""Investments: kept out of spending and income, read as a portfolio with a realised result."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import app
from src.blueprint import Blueprint
from src.services.investments import parse_trade

BLUEPRINT = {
    "name": "Io",
    "categories": [
        {"key": "spesa", "label": "Spesa"},
        {"key": "stipendio", "label": "Stipendio", "kind": "income"},
        {
            "key": "investimenti",
            "label": "Investimenti",
            "kind": "investment",
            "aliases": ["Investments"],
            "children": [{"key": "etf", "label": "ETF"}],
        },
    ],
}
D = date(2026, 3, 1)


# ----------------------------------------------------------------------------- reading a statement line

def test_buy_with_isin_and_quantity():
    t = parse_trade("Commercio Buy trade US0378331005 APPLE INC., quantity: 4.44247", -999.89, D)
    assert (t.kind, t.isin, t.key, t.name, t.quantity, t.amount) == ("buy", "US0378331005", "US0378331005", "APPLE INC.", 4.44247, 999.89)


def test_sell_dividend_savings_plan_and_funds_without_isin():
    assert parse_trade("Commercio Sell trade US07134L1070 BATT.OIL COR. B DL-,0001, quantity: 100", 1759, D).kind == "sell"
    div = parse_trade("Rendimento Cash Dividend for ISIN IE0007UPSEA3", 8.54, D)
    assert (div.kind, div.key, div.quantity) == ("dividend", "IE0007UPSEA3", None)
    plan = parse_trade("Savings plan execution LU1681048804 Amundi S&P 500 UCITS ETF, quantity: 0.8", -100, D)
    assert (plan.kind, plan.isin) == ("buy", "LU1681048804")
    fund = parse_trade("Vendita Deutsche Managed Euro Fund II", 46.83, D)
    assert (fund.kind, fund.isin, fund.name, fund.quantity) == ("sell", None, "Deutsche Managed Euro Fund II", None)
    assert parse_trade("To Robo portfolio", -200, D).name == "Robo portfolio"


def test_the_sign_decides_when_the_wording_is_silent():
    assert parse_trade("Movimento titoli", -50, D).kind == "buy"
    assert parse_trade("Movimento titoli", 50, D).kind == "sell"


# ----------------------------------------------------------------------------- blueprint

def test_investment_kind_covers_descendants():
    bp = Blueprint.model_validate(BLUEPRINT)
    assert bp.investment_keys() == {"investimenti", "etf"}


# ----------------------------------------------------------------------------- end to end

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client):
    ws = client.post("/api/workspaces", json={"name": "P", "blueprint": BLUEPRINT}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}
    account = client.post("/api/accounts", json={"name": "Broker", "account_type": "checking"}, headers=headers).json()["id"]
    return headers, account


def row(day, amount, description, category="investimenti"):
    return {"date": day, "amount": amount, "description": description, "category": category}


ROWS = [
    row("2026-03-01", -1000, "Buy trade US0000000001 ACME CORP, quantity: 10"),
    row("2026-03-10", -1200, "Buy trade US0000000001 ACME CORP, quantity: 10"),
    row("2026-04-01", 700, "Sell trade US0000000001 ACME CORP, quantity: 5"),
    row("2026-04-20", 5, "Rendimento Cash Dividend for ISIN US0000000001"),
    row("2026-03-05", -500, "Buy trade US0000000002 BETA SPA, quantity: 2"),
    row("2026-05-05", 450, "Sell trade US0000000002 BETA SPA, quantity: 2"),
    row("2026-03-06", -1000, "Acquisto Fondo Monetario"),
    row("2026-05-06", 400, "Vendita Fondo Monetario"),
    row("2026-03-02", -80, "Supermercato", category="spesa"),
    row("2026-03-25", 2000, "Stipendio marzo", category="stipendio"),
]


def load(client, headers, account):
    res = client.post("/api/imports", json={"account_id": account, "transactions": ROWS}, headers=headers)
    assert res.status_code == 200, res.text


def test_portfolio_positions_and_realised_result(client, project):
    headers, account = project
    load(client, headers, account)
    body = client.get("/api/investments", headers=headers).json()
    positions = {p["key"]: p for p in body["positions"]}

    acme = positions["US0000000001"]  # average cost 110: selling 5 for 700 realises 150
    assert (acme["invested"], acme["proceeds"], acme["dividends"]) == (2200.0, 700.0, 5.0)
    assert (acme["realized"], acme["result"], acme["status"], acme["quantity"], acme["open_cost"]) == (150.0, 155.0, "open", 15.0, 1650.0)

    beta = positions["US0000000002"]  # bought and sold in full: a loss of 50
    assert (beta["status"], beta["realized"], beta["quantity"], beta["open_cost"]) == ("closed", -50.0, 0.0, 0.0)

    fund = positions["fondo monetario"]  # no quantity: only the cash flow is known
    assert (fund["realized"], fund["result"], fund["net_flow"]) == (None, None, -600.0)

    totals = body["totals"]
    assert totals["invested"] == 3700.0 and totals["proceeds"] == 1550.0 and totals["dividends"] == 5.0
    assert totals["realized"] == 100.0 and totals["realized_result"] == 105.0
    assert (totals["unresolved_instruments"], totals["unresolved_net_flow"]) == (1, -600.0)
    assert [m["month"] for m in body["by_month"]] == ["2026-03", "2026-04", "2026-05"]


def test_investments_are_not_spending_income_or_net(client, project):
    headers, account = project
    load(client, headers, account)

    spending = client.get("/api/reports/spending", params={"start_date": "2026-01-01", "end_date": "2026-12-31"}, headers=headers).json()
    assert spending["total"] == 80.0 and [i["key"] for i in spending["items"]] == ["spesa"]
    income = client.get("/api/reports/spending", params={"start_date": "2026-01-01", "end_date": "2026-12-31", "flow": "income"}, headers=headers).json()
    assert income["total"] == 2000.0

    summary = client.get("/api/financial-summary/monthly/2026-03", headers=headers).json()
    assert (summary["income"], summary["expenses"], summary["net"]) == (2000.0, 80.0, 1920.0)
    dist = client.get("/api/financial-summary/spending-distribution", params={"start_date": "2026-01-01", "end_date": "2026-12-31"}, headers=headers).json()
    assert [d["name"] for d in dist["distribution"]] == ["Spesa"]

    year = client.get("/api/financial-data/2026", headers=headers)
    if year.status_code == 200:
        march = next(m for m in year.json()["monthlyData"] if m["month"] in ("Mar", "March"))
        assert (march["income"], march["expenses"]) == (2000.0, 80.0)


def test_without_an_investment_category_nothing_changes(client):
    ws = client.post("/api/workspaces", json={"name": "Q", "blueprint": {"name": "Q", "categories": [{"key": "spesa", "label": "Spesa"}]}}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}
    account = client.post("/api/accounts", json={"name": "B", "account_type": "checking"}, headers=headers).json()["id"]
    client.post("/api/imports", json={"account_id": account, "transactions": [row("2026-03-01", -10, "Caffe", category="spesa")]}, headers=headers)
    assert client.get("/api/investments", headers=headers).json()["totals"]["trades"] == 0
    spending = client.get("/api/reports/spending", params={"start_date": "2026-01-01", "end_date": "2026-12-31"}, headers=headers).json()
    assert spending["total"] == 10.0
