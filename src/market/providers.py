"""Price and symbol providers. Both are thin, synchronous httpx clients with a transport hook for tests.

Alpha Vantage's free tier allows 25 requests a day: callers budget them (``PriceService`` refreshes each instrument
at most once a day and spaces the calls). Milan listings are not available there; ETFs are priced on Xetra
(``.DEX``), US stocks on their US ticker, other listings on London (``.LON``) when nothing else exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"

# FIGI exchange code → Alpha Vantage suffix, in order of preference
EXCHANGE_SUFFIX: Sequence[Tuple[str, str]] = (
    ("GY", ".DEX"),  # Xetra
    ("GR", ".DEX"),  # German composite: the Xetra line carries the same ticker
    ("GF", ".FRK"),  # Frankfurt floor
    ("US", ""),
    ("LN", ".LON"),
    ("TT", ".TRT"),
)


class MarketError(Exception):
    pass


class RateLimited(MarketError):
    """The provider refused the call: the daily budget is spent."""


@dataclass
class Quote:
    day: date
    close: float
    currency: str


# ---------------------------------------------------------------------- OpenFIGI: ISIN → tickers


class OpenFigi:
    def __init__(self, api_key: Optional[str] = None, transport: Optional[httpx.BaseTransport] = None, timeout: float = 20.0):
        self.api_key = api_key or os.getenv("OPENFIGI_API_KEY") or None
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def listings(self, isins: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Every listing OpenFIGI knows for each ISIN: [{ticker, exchCode, name, securityType, securityType2}]."""
        if not isins:
            return {}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-OPENFIGI-APIKEY"] = self.api_key
        out: Dict[str, List[Dict[str, Any]]] = {}
        for start in range(0, len(isins), 10):  # 10 jobs per request without a key
            chunk = list(isins[start:start + 10])
            response = self._http.post(OPENFIGI_URL, json=[{"idType": "ID_ISIN", "idValue": i} for i in chunk], headers=headers)
            if response.status_code == 429:
                raise RateLimited("OpenFIGI rate limit")
            if response.status_code >= 400:
                raise MarketError(f"OpenFIGI {response.status_code}: {response.text[:200]}")
            for isin, item in zip(chunk, response.json()):
                out[isin] = list(item.get("data") or [])
        return out


def rank_symbols(listings: List[Dict[str, Any]], isin: Optional[str] = None) -> List[Tuple[str, str, str]]:
    """Every (Alpha Vantage symbol, exchange code, name) worth trying, best first. US securities are priced on
    their home listing first (complete on Alpha Vantage), everything else on Xetra first; the US OTC line of a
    European stock (e.g. PITAF for Poste Italiane) comes last but does answer."""
    order = list(EXCHANGE_SUFFIX)
    if isin and isin.upper().startswith("US"):
        order.sort(key=lambda e: 0 if e[0] == "US" else 1)
    out: List[Tuple[str, str, str]] = []
    seen = set()
    for exch, suffix in order:
        for item in listings:
            if item.get("exchCode") == exch and item.get("ticker"):
                symbol = f"{item['ticker']}{suffix}"
                if symbol not in seen:
                    seen.add(symbol)
                    out.append((symbol, exch, item.get("name") or ""))
    return out


def pick_symbol(listings: List[Dict[str, Any]], isin: Optional[str] = None) -> Optional[Tuple[str, str, str]]:
    ranked = rank_symbols(listings, isin)
    return ranked[0] if ranked else None


def classify_listing(listings: List[Dict[str, Any]]) -> Tuple[str, str]:
    """(instrument type, asset class) guessed from OpenFIGI's security type."""
    kinds = {str(i.get("securityType") or "").lower() for i in listings} | {str(i.get("securityType2") or "").lower() for i in listings}
    if any("etp" in k or "etf" in k for k in kinds):
        return "etf", "equity"
    if any("common stock" in k or "equity" in k for k in kinds):
        return "stock", "equity"
    if any("bond" in k or "mtn" in k or "note" in k for k in kinds):
        return "bond", "bonds"
    if any("fund" in k for k in kinds):
        return "fund", "other"
    return "other", "other"


# ---------------------------------------------------------------------- Alpha Vantage: prices and fx


class AlphaVantage:
    def __init__(self, api_key: Optional[str] = None, transport: Optional[httpx.BaseTransport] = None, timeout: float = 30.0):
        self.api_key = api_key or os.getenv("ALPHAVANTAGE_API_KEY") or ""
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise MarketError("ALPHAVANTAGE_API_KEY is not set")
        response = self._http.get(ALPHAVANTAGE_URL, params={**params, "apikey": self.api_key})
        if response.status_code >= 400:
            raise MarketError(f"Alpha Vantage {response.status_code}")
        data = response.json()
        note = data.get("Information") or data.get("Note")
        if note:
            if "rate limit" in str(note).lower() or "per day" in str(note).lower() or "premium" in str(note).lower():
                raise RateLimited(str(note)[:200])
            raise MarketError(str(note)[:200])
        if data.get("Error Message"):
            raise MarketError(str(data["Error Message"])[:200])
        return data

    def daily(self, symbol: str, currency_hint: str = "EUR") -> List[Quote]:
        """The last ~100 daily closes of a symbol (oldest first). Alpha Vantage does not state the currency: the
        suffix decides (.DEX/.FRK EUR, .LON GBX→GBP pence, none USD)."""
        data = self._get({"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact"})
        series = data.get("Time Series (Daily)") or {}
        currency = symbol_currency(symbol, currency_hint)
        quotes = []
        for day, row in series.items():
            try:
                close = float(row.get("4. close"))
            except (TypeError, ValueError):
                continue
            if currency == "GBX":
                close, currency = close / 100.0, "GBP"
            quotes.append(Quote(date.fromisoformat(day), close, currency))
        return sorted(quotes, key=lambda q: q.day)

    def fx_daily(self, base: str, quote: str) -> List[Quote]:
        data = self._get({"function": "FX_DAILY", "from_symbol": base, "to_symbol": quote, "outputsize": "compact"})
        series = data.get("Time Series FX (Daily)") or {}
        out = []
        for day, row in series.items():
            try:
                out.append(Quote(date.fromisoformat(day), float(row.get("4. close")), quote))
            except (TypeError, ValueError):
                continue
        return sorted(out, key=lambda q: q.day)

    def search(self, keywords: str) -> List[Dict[str, Any]]:
        data = self._get({"function": "SYMBOL_SEARCH", "keywords": keywords})
        return [
            {"symbol": m.get("1. symbol"), "name": m.get("2. name"), "region": m.get("4. region"), "currency": m.get("8. currency")}
            for m in data.get("bestMatches") or []
        ]


def symbol_currency(symbol: str, default: str = "EUR") -> str:
    if "." not in symbol:
        return "USD"
    suffix = symbol.rsplit(".", 1)[1].upper()
    return {"DEX": "EUR", "FRK": "EUR", "PAR": "EUR", "AMS": "EUR", "BRU": "EUR", "LON": "GBX", "TRT": "CAD", "TRV": "CAD"}.get(suffix, default)
