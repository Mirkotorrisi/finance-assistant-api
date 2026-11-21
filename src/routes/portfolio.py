"""Portfolio at market value: instruments, prices, valued positions and the valuation snapshots."""

from datetime import date as Date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.market.providers import AlphaVantage, OpenFigi
from src.routes.deps import resolve_workspace_id
from src.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def get_portfolio_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    try:
        yield PortfolioService(session)
    finally:
        session.close()


# providers are built here so tests can swap them
def make_alphavantage() -> AlphaVantage:
    return AlphaVantage()


def make_openfigi() -> OpenFigi:
    return OpenFigi()


class HoldingIn(BaseModel):
    isin: Optional[str] = Field(default=None, min_length=12, max_length=12)
    symbol: Optional[str] = Field(default=None, max_length=40)
    name: Optional[str] = Field(default=None, max_length=200)
    quantity: Optional[float] = None
    price: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    asset_class: Optional[str] = Field(default=None, pattern="^(equity|bonds|cash|real_estate|commodities|crypto|other)$")
    type: Optional[str] = Field(default=None, pattern="^(etf|stock|bond|fund|certificate|other)$")


class HoldingsIn(BaseModel):
    account_id: int
    as_of: Optional[Date] = None
    holdings: List[HoldingIn]


class InstrumentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    type: Optional[str] = Field(default=None, pattern="^(etf|stock|bond|fund|certificate|other)$")
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    asset_class: Optional[str] = Field(default=None, pattern="^(equity|bonds|cash|real_estate|commodities|crypto|other)$")
    valuation: Optional[str] = Field(default=None, pattern="^(market|cost|manual)$")
    price_symbol: Optional[str] = Field(default=None, max_length=40, description="Alpha Vantage symbol, e.g. LYY0.DEX or AAPL.")
    manual_price: Optional[float] = Field(default=None, ge=0)
    manual_price_date: Optional[Date] = None


@router.get("", summary="Positions at market value")
def portfolio(service: PortfolioService = Depends(get_portfolio_service)) -> Dict[str, Any]:
    """Per broker (source cash account → securities account): every open position with quantity, average cost,
    last close and its date, value in EUR, unrealised gain; totals and the allocation by asset class. ``price_basis``
    says market | cost | manual | no_price."""
    return service.valued_positions()


@router.get("/instruments", summary="Instruments and their price settings")
def instruments(service: PortfolioService = Depends(get_portfolio_service)):
    service.sync_instruments()
    return service.list_instruments()


@router.put("/instruments/{instrument_id}", summary="Set an instrument's symbol, asset class or manual price")
def update_instrument(instrument_id: int, body: InstrumentUpdate, service: PortfolioService = Depends(get_portfolio_service)):
    try:
        return service.update_instrument(instrument_id, body.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/holdings", summary="Record the holdings a broker statement lists")
def record_holdings(body: HoldingsIn, service: PortfolioService = Depends(get_portfolio_service)):
    """Seeds or updates the instruments (name, ISIN, class) and keeps the statement's price as their manual price,
    used until a market close exists. Called by the gateway after reading a known broker statement."""
    return service.record_holdings(body.account_id, body.as_of, [h.model_dump() for h in body.holdings])


@router.post("/resolve", summary="Find price symbols for the instruments (OpenFIGI)")
def resolve(only_missing: bool = True, service: PortfolioService = Depends(get_portfolio_service)):
    figi = make_openfigi()
    try:
        return service.resolve_symbols(figi, only_missing=only_missing)
    finally:
        figi.close()


@router.post("/refresh", summary="Fetch today's prices and record the valuations")
def refresh(write: bool = True, force: bool = False, max_requests: int = 20, service: PortfolioService = Depends(get_portfolio_service)):
    """Pulls the daily closes (Alpha Vantage, 25 requests a day on the free plan) for every market-valued
    instrument not refreshed today, the exchange rates they need, then writes each broker's value as a ``market``
    balance on its securities account."""
    av = make_alphavantage()
    try:
        prices = service.refresh_prices(av, max_requests=max_requests, force=force)
    finally:
        av.close()
    valuations = service.write_valuations() if write else None
    return {"prices": prices, "valuations": valuations}


@router.post("/valuations", summary="Record today's valuations from the cached prices")
def valuations(service: PortfolioService = Depends(get_portfolio_service)):
    return service.write_valuations()
