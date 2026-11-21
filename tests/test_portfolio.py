"""Portfolio at market value: symbol lookup, price cache, valued positions and the market snapshots."""

import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app import app
from src.market.providers import AlphaVantage, OpenFigi, RateLimited, pick_symbol, rank_symbols
from src.services.investments import parse_trade

BLUEPRINT = {
    "name": "Io",
    "categories": [
        {"key": "spesa", "label": "Spesa"},
        {"key": "investimenti", "label": "Investimenti", "kind": "investment"},
    ],
}
TODAY = date(2026, 11, 21)

FIGI = {
    "LU1829220216": [{"ticker": "ACWI", "exchCode": "IM", "name": "AMUNDI MSCI ACWI", "securityType": "ETP"},
                     {"ticker": "LYY0", "exchCode": "GR", "name": "AMUNDI MSCI ACWI", "securityType": "ETP"}],
    "US0378331005": [{"ticker": "AAPL", "exchCode": "US", "name": "APPLE INC", "securityType": "Common Stock"},
                     {"ticker": "APC", "exchCode": "GY", "name": "APPLE INC", "securityType": "Common Stock"}],
    "US58013MFT62": [{"ticker": "MCD 5.15 09/09/52", "exchCode": "NEW YORK", "name": "MCDONALD'S CORP", "securityType": "GLOBAL", "securityType2": "Corp"}],
}
SERIES = {
    "LYY0.DEX": {"2026-11-19": "599.00", "2026-11-20": "579.00"},
    "APC.DEX": {"2026-11-19": "300.00", "2026-11-20": "295.00"},
    "AAPL": {"2026-11-20": "342.56"},
}


class FakeMarket:
    """OpenFIGI and Alpha Vantage behind one MockTransport; counts the Alpha Vantage calls (the daily budget)."""

    def __init__(self):
        self.av_calls = 0
        self.limit_after = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openfigi.com":
            jobs = json.loads(request.content)
            return httpx.Response(200, json=[{"data": FIGI[j["idValue"]]} if j["idValue"] in FIGI else {"warning": "No identifier found."} for j in jobs])
        params = request.url.params
        self.av_calls += 1
        if self.limit_after is not None and self.av_calls > self.limit_after:
            return httpx.Response(200, json={"Information": "Thank you for using Alpha Vantage! Our standard API rate limit is 25 requests per day."})
        if params["function"] == "TIME_SERIES_DAILY":
            series = SERIES.get(params["symbol"])
            if series is None:
                return httpx.Response(200, json={"Error Message": "Invalid API call."})
            return httpx.Response(200, json={"Meta Data": {"2. Symbol": params["symbol"]}, "Time Series (Daily)": {d: {"4. close": c} for d, c in series.items()}})
        if params["function"] == "FX_DAILY":
            return httpx.Response(200, json={"Time Series FX (Daily)": {"2026-11-20": {"4. close": "1.1600"}}})
        return httpx.Response(404)


@pytest.fixture
def market(monkeypatch):
    fake = FakeMarket()
    import src.routes.portfolio as routes

    monkeypatch.setattr(routes, "make_alphavantage", lambda: AlphaVantage(api_key="k", transport=httpx.MockTransport(fake.handler)))
    monkeypatch.setattr(routes, "make_openfigi", lambda: OpenFigi(transport=httpx.MockTransport(fake.handler)))
    import src.services.portfolio_service as svc

    monkeypatch.setattr(svc.PortfolioService, "__init__", _fast_init(svc.PortfolioService.__init__))
    return fake


def _fast_init(original):
    def init(self, session, request_spacing=0.0):
        original(self, session, request_spacing=0.0)
    return init


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def broker(client):
    ws = client.post("/api/workspaces", json={"name": "P", "blueprint": BLUEPRINT}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}
    cash = client.post("/api/accounts", json={"name": "Trade Republic", "account_type": "checking"}, headers=headers).json()["id"]
    titoli = client.post("/api/accounts", json={"name": "Trade Republic titoli", "account_type": "investment"}, headers=headers).json()["id"]
    assert client.put(f"/api/accounts/{cash}", json={"securities_account_id": titoli}, headers=headers).status_code == 200
    rows = [
        {"date": "2026-10-01", "amount": -1000.0, "description": "Commercio Buy trade LU1829220216 AMUNDI MSCI ACWI, quantity: 2", "category": "investimenti"},
        {"date": "2026-10-15", "amount": -600.0, "description": "Commercio Buy trade US0378331005 APPLE INC., quantity: 2", "category": "investimenti"},
        {"date": "2026-11-16", "amount": 0.69, "description": "Rendimento Cash Dividend for ISIN US0378331005", "category": "investimenti"},
        {"date": "2026-10-20", "amount": -2481.7, "description": "Commercio Buy trade US58013MFT62 MCDONALD'S CORP, quantity: 3030.71", "category": "investimenti"},
        {"date": "2026-09-09", "amount": 49.72, "description": "Rendimento Interest Payment for ISIN US58013MFT62", "category": "investimenti"},
        {"date": "2026-10-05", "amount": -5000.0, "description": "Acquisto Deutsche Managed Euro Fund II", "category": "investimenti"},
        {"date": "2026-11-17", "amount": 26.36, "description": "Vendita Deutsche Managed Euro Fund II", "category": "investimenti"},
    ]
    assert client.post("/api/imports", json={"account_id": cash, "transactions": rows}, headers=headers).status_code == 200
    return headers, cash, titoli


def test_parse_trade_reads_interest_and_dividend_lines():
    coupon = parse_trade("Rendimento Interest Payment for ISIN US58013MFT62", 49.72, TODAY)
    assert coupon.kind == "dividend" and coupon.isin == "US58013MFT62"
    dividend = parse_trade("Rendimento Cash Dividend for ISIN US0378331005", 0.69, TODAY)
    assert dividend.kind == "dividend" and dividend.name == "US0378331005"  # no name on the line: the instrument table supplies it


def test_symbol_ranking_prefers_xetra_but_home_listing_for_us_isins():
    assert pick_symbol(FIGI["LU1829220216"], "LU1829220216") == ("LYY0.DEX", "GR", "AMUNDI MSCI ACWI")
    assert [s for s, _, _ in rank_symbols(FIGI["US0378331005"], "US0378331005")] == ["AAPL", "APC.DEX"]
    assert pick_symbol(FIGI["US0378331005"]) == ("APC.DEX", "GY", "APPLE INC")  # no ISIN hint: exchange order
    assert pick_symbol(FIGI["US58013MFT62"]) is None


def test_instruments_are_created_from_the_trades_and_resolved(client, broker, market):
    headers, cash, titoli = broker
    listed = client.get("/api/portfolio/instruments", headers=headers).json()
    by_key = {i["key"]: i for i in listed}
    assert by_key["LU1829220216"]["valuation"] == "market" and by_key["LU1829220216"]["price_symbol"] is None
    fund = by_key["deutsche managed euro fund ii"]
    assert fund["valuation"] == "cost" and fund["asset_class"] == "cash"

    resolved = client.post("/api/portfolio/resolve", headers=headers).json()
    assert resolved["resolved"] == 2 and resolved["unresolved"] == 1
    by_isin = {r["isin"]: r for r in resolved["instruments"]}
    assert by_isin["LU1829220216"]["symbol"] == "LYY0.DEX" and by_isin["US0378331005"]["symbol"] == "AAPL"
    assert by_isin["US58013MFT62"]["valuation"] == "cost" and "bond" in by_isin["US58013MFT62"]["error"]
    inst = {i["isin"]: i for i in client.get("/api/portfolio/instruments", headers=headers).json() if i["isin"]}
    assert inst["US0378331005"]["name"] == "APPLE INC." or inst["US0378331005"]["name"] == "APPLE INC"
    assert inst["LU1829220216"]["type"] == "etf" and inst["LU1829220216"]["asset_class"] == "equity"
    assert inst["US58013MFT62"]["asset_class"] == "bonds"


def test_refresh_prices_values_positions_and_writes_a_market_snapshot(client, broker, market):
    headers, cash, titoli = broker
    client.post("/api/portfolio/resolve", headers=headers)
    out = client.post("/api/portfolio/refresh", headers=headers).json()
    assert market.av_calls == 3 and sorted(out["prices"]["updated"]) == ["AAPL", "EURUSD", "LYY0.DEX"]  # Apple on its US listing: one fx call

    portfolio = client.get("/api/portfolio", headers=headers).json()
    group = portfolio["accounts"][0]
    assert group["source_account_id"] == cash and group["securities_account_id"] == titoli
    by_key = {p["key"]: p for p in group["positions"]}
    acwi = by_key["LU1829220216"]
    assert acwi["price"] == 579.0 and acwi["price_date"] == "2026-11-20" and acwi["value"] == 1158.0 and acwi["unrealized"] == 158.0 and acwi["price_basis"] == "market"
    apple = by_key["US0378331005"]
    assert apple["value"] == round(2 * 342.56 / 1.16, 2) and apple["name"].startswith("APPLE") and apple["fx"] == 1.16
    bond = by_key["US58013MFT62"]
    assert bond["price_basis"] == "cost" and bond["value"] == 2481.7 and bond["asset_class"] == "bonds"
    fund = by_key["deutsche managed euro fund ii"]
    assert fund["price_basis"] == "cost" and fund["value"] == 5000.0 - 26.36 and fund["asset_class"] == "cash"
    apple_value = round(2 * 342.56 / 1.16, 2)
    assert group["value"] == round(1158.0 + apple_value + 2481.7 + 4973.64, 2)
    classes = {a["asset_class"]: a["value"] for a in portfolio["allocation"]}
    assert classes["equity"] == round(1158.0 + apple_value, 2) and classes["bonds"] == 2481.7 and classes["cash"] == 4973.64

    # the valuation landed on the securities account as a market balance, and net worth reads it
    assert out["valuations"]["written"][0]["securities_account_id"] == titoli
    snaps = client.get("/api/balance-snapshots", params={"account_id": titoli}, headers=headers).json()["snapshots"]
    assert len(snaps) == 1 and snaps[0]["source"] == "market" and snaps[0]["balance"] == group["value"]
    accounts = {a["id"]: a for a in client.get("/api/accounts", headers=headers).json()}
    assert accounts[titoli]["current_balance"] == group["value"]

    # a second refresh the same day costs no request; a user balance for today is never overwritten
    again = client.post("/api/portfolio/refresh", headers=headers).json()
    assert market.av_calls == 3 and again["prices"]["updated"] == []
    client.post("/api/balance-snapshots", json={"account_id": titoli, "date": date.today().isoformat(), "balance": 9999.0}, headers=headers)
    third = client.post("/api/portfolio/valuations", headers=headers).json()
    assert third["written"] == [] and "user balance" in third["skipped"][0]["reason"]


def test_a_dead_symbol_falls_through_to_the_next_listing_and_rate_limits_stop_cleanly(client, broker, market):
    headers, cash, titoli = broker
    client.post("/api/portfolio/resolve", headers=headers)
    apple = next(i for i in client.get("/api/portfolio/instruments", headers=headers).json() if i["isin"] == "US0378331005")
    assert apple["symbol_candidates"] == ["APC.DEX"]
    client.put(f"/api/portfolio/instruments/{apple['id']}", json={"price_symbol": "NOPE.DEX"}, headers=headers)
    out = client.post("/api/portfolio/refresh", headers=headers).json()
    # NOPE.DEX twice (retry), then the candidate APC.DEX answers; LYY0 one call: 4 requests, no fx (both EUR)
    assert market.av_calls == 4 and sorted(out["prices"]["updated"]) == ["APC.DEX", "LYY0.DEX"]
    apple = next(i for i in client.get("/api/portfolio/instruments", headers=headers).json() if i["isin"] == "US0378331005")
    assert apple["price_symbol"] == "APC.DEX" and "NOPE.DEX" in apple["symbol_candidates"]
    pos = next(p for p in client.get("/api/portfolio", headers=headers).json()["accounts"][0]["positions"] if p["key"] == "US0378331005")
    assert pos["price_currency"] == "EUR" and pos["value"] == 590.0

    market.limit_after = market.av_calls  # every further call is refused
    limited = client.post("/api/portfolio/refresh", params={"force": "true"}, headers=headers).json()
    assert limited["prices"]["stopped"] == "rate limited" and limited["prices"]["requests"] == 0


def test_manual_price_and_missing_securities_account(client, broker, market):
    headers, cash, titoli = broker
    client.put(f"/api/accounts/{cash}", json={"securities_account_id": None}, headers=headers)
    client.post("/api/portfolio/resolve", headers=headers)
    apple = next(i for i in client.get("/api/portfolio/instruments", headers=headers).json() if i["isin"] == "US0378331005")
    client.put(f"/api/portfolio/instruments/{apple['id']}", json={"manual_price": 100.0, "valuation": "manual"}, headers=headers)
    portfolio = client.get("/api/portfolio", headers=headers).json()
    pos = next(p for p in portfolio["accounts"][0]["positions"] if p["key"] == "US0378331005")
    assert pos["price_basis"] == "manual" and pos["value"] == 200.0
    written = client.post("/api/portfolio/valuations", headers=headers).json()
    assert written["written"] == [] and written["skipped"][0]["reason"] == "no securities account configured"


def test_alphavantage_client_maps_rate_limits(market):
    av = AlphaVantage(api_key="k", transport=httpx.MockTransport(market.handler))
    market.limit_after = 0
    with pytest.raises(RateLimited):
        av.daily("LYY0.DEX")


def test_parse_trade_reads_broker_statement_wording():
    buy = parse_trade("Buy trade IE00BM67HV82 XDWI Xtrackers MSCI World Industrials UCITS ETF (Acc), quantity: 2.42477636, price: 73.78", -178.9, TODAY)
    assert buy.kind == "buy" and buy.isin == "IE00BM67HV82" and buy.quantity == 2.42477636
    assert buy.name == "XDWI Xtrackers MSCI World Industrials UCITS ETF (Acc)"
    sell = parse_trade("Sell trade IS3Q, quantity: 9.57492113, price: 68.01", 651.19, TODAY)
    assert sell.kind == "sell" and sell.key == "is3q" and sell.name == "IS3Q"
    assert parse_trade("Cash Dividend IUSU", 6.37, TODAY).key == "iusu"


def test_statement_holdings_seed_instruments_and_value_positions_until_a_close_exists(client, market):
    ws = client.post("/api/workspaces", json={"name": "R", "blueprint": BLUEPRINT}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}
    robo = client.post("/api/accounts", json={"name": "Revolut investimenti", "account_type": "investment"}, headers=headers).json()["id"]
    rows = [
        {"date": "2026-11-10", "amount": 200.0, "description": "Revolut investimenti: versamento", "category": "spesa"},
        {"date": "2026-11-10", "amount": -178.9, "description": "Buy trade IE00BM67HV82 XDWI Xtrackers MSCI World Industrials UCITS ETF (Acc), quantity: 2.42477636, price: 73.78", "category": "investimenti"},
        {"date": "2026-11-16", "amount": -3.78, "description": "Revolut investimenti: robo management fee", "category": "spesa"},
    ]
    assert client.post("/api/imports", json={"account_id": robo, "transactions": rows}, headers=headers).status_code == 200
    seeded = client.post("/api/portfolio/holdings", json={"account_id": robo, "as_of": "2026-11-21", "holdings": [
        {"symbol": "XDWI", "name": "Xtrackers MSCI World Industrials UCITS ETF (Acc)", "isin": "IE00BM67HV82", "quantity": 2.42477636, "price": 69.70, "currency": "EUR", "asset_class": "equity", "type": "etf"},
    ]}, headers=headers).json()
    assert seeded["instruments_created"] + seeded["instruments_updated"] == 1
    inst = next(i for i in client.get("/api/portfolio/instruments", headers=headers).json() if i["isin"] == "IE00BM67HV82")
    assert inst["manual_price"] == 69.7 and inst["manual_price_date"] == "2026-11-21" and inst["valuation"] == "market" and inst["type"] == "etf"

    portfolio = client.get("/api/portfolio", headers=headers).json()
    group = portfolio["accounts"][0]
    assert group["securities_account_id"] == robo  # an investment account is its own securities account
    pos = group["positions"][0]
    assert pos["price_basis"] == "manual" and pos["value"] == round(2.42477636 * 69.7, 2) and pos["price_date"] == "2026-11-21"
    assert group["cash"] == round(200.0 - 178.9 - 3.78, 2)  # the money sitting in the account counts too
    assert group["value"] == round(pos["value"] + group["cash"], 2)
    classes = {a["asset_class"]: a["value"] for a in portfolio["allocation"]}
    assert classes["cash"] == group["cash"]

    written = client.post("/api/portfolio/valuations", headers=headers).json()
    assert written["written"] == [{"securities_account_id": robo, "value": group["value"], "unknown_positions": 0}]


def test_two_cash_accounts_feeding_one_securities_account_write_one_summed_snapshot(client, market):
    ws = client.post("/api/workspaces", json={"name": "S", "blueprint": BLUEPRINT}).json()
    headers = {"X-Workspace-Id": str(ws["id"])}
    a = client.post("/api/accounts", json={"name": "Cash A", "account_type": "checking"}, headers=headers).json()["id"]
    b = client.post("/api/accounts", json={"name": "Cash B", "account_type": "checking"}, headers=headers).json()["id"]
    titoli = client.post("/api/accounts", json={"name": "Titoli", "account_type": "investment"}, headers=headers).json()["id"]
    for acc in (a, b):
        client.put(f"/api/accounts/{acc}", json={"securities_account_id": titoli}, headers=headers)
        client.post("/api/imports", json={"account_id": acc, "transactions": [
            {"date": "2026-10-01", "amount": -5000.0, "description": "Acquisto Deutsche Managed Euro Fund II", "category": "investimenti"},
        ]}, headers=headers)
    written = client.post("/api/portfolio/valuations", headers=headers).json()
    assert written["written"] == [{"securities_account_id": titoli, "value": 10000.0, "unknown_positions": 0}]


def test_reading_the_portfolio_writes_nothing_once_instruments_exist_and_cached_prices_match_lookups(client, broker, market):
    from src.database.init import get_db_session
    from src.database.models import Instrument
    from src.services.portfolio_service import PortfolioService

    headers, cash, titoli = broker
    client.post("/api/portfolio/resolve", headers=headers)
    client.post("/api/portfolio/refresh", headers=headers)
    first = client.get("/api/portfolio", headers=headers).json()
    assert client.get("/api/portfolio", headers=headers).json() == first

    with get_db_session(int(headers["X-Workspace-Id"])) as session:
        service = PortfolioService(session)
        assert service.sync_instruments() == []  # nothing new: the read stays read-only
        instruments = session.query(Instrument).all()
        direct = {i.id: service._last_price(i, date.today()) for i in instruments}  # uncached lookups
        direct_fx = service._fx("USD", date.today())
        service._preload(date.today())
        for inst in instruments:
            cached = service._last_price(inst, date.today())
            assert (cached.id if cached else None) == (direct[inst.id].id if direct[inst.id] else None)
        assert service._fx("USD", date.today()).id == direct_fx.id
        assert service._fx("EUR", date.today()) is None
        # a lookup for another date is not served from the cache
        assert service._last_price(instruments[0], date(2000, 1, 1)) is None
