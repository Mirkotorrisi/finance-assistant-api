"""Market value of the portfolio: instruments, daily prices, valued positions and the valuation snapshots.

Positions come from the trades the statements already hold (``InvestmentService``): quantity held at average cost
per instrument and per account. This service adds what those lack: a symbol for each ISIN (OpenFIGI), a daily
close (Alpha Vantage, cached in ``prices``), exchange rates, and the value in EUR. The total per broker is written
as a ``BalanceSnapshot`` with source ``market`` on the broker's securities account, so net worth, the dashboard and
the advisor read it like any recorded balance; a balance the user or the bank recorded that day always wins.

Instruments without units (money-market funds sold in tranches, bonds by nominal, certificates) are valued at
``cost`` (net cash in): never guessed, and the position says so (``price_basis``).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.database.models import Account, BalanceSnapshot, FxRate, Instrument, Price
from src.market.providers import AlphaVantage, MarketError, OpenFigi, RateLimited, classify_listing, rank_symbols
from src.services.investments import InvestmentService
from src.services.net_worth_service import NetWorthService, is_valuation

logger = logging.getLogger(__name__)

CASH_LIKE = re.compile(r"managed euro fund|cash fund|money market|monetari|liquidit|cash plus|overnight", re.IGNORECASE)
ROBO = re.compile(r"robo|gestione patrimoniale|managed portfolio", re.IGNORECASE)
CERTIFICATE = re.compile(r"turbo|knock|certificat|leverage|faktor|mini future|warrant|optionsschein", re.IGNORECASE)
MAX_PRICE_AGE_DAYS = 7  # older closes are shown but flagged stale
SNAPSHOT_SOURCES_THAT_WIN = ("user", "bank", "import")


class PortfolioService:
    def __init__(self, session: Session, request_spacing: float = 13.0):
        self.session = session
        self.investments = InvestmentService(session)
        self.request_spacing = request_spacing  # Alpha Vantage's legacy 5-per-minute limit

    # ------------------------------------------------------------------ instruments

    def sync_instruments(self) -> List[Instrument]:
        """One instrument row per position key the statements produce (ISIN, else normalised name)."""
        by_key = {i.key: i for i in self.session.query(Instrument).all()}
        created = []
        for positions in self.investments.positions_by_account().values():
            for pos in positions:
                key = pos["key"]
                if key in by_key:
                    inst = by_key[key]
                    if pos.get("isin") and not inst.isin:
                        inst.isin = pos["isin"]
                    continue
                inst = Instrument(key=key, isin=pos.get("isin"), name=(pos.get("name") or key)[:200])
                if not inst.isin:
                    inst.valuation = "cost"
                    inst.price_source = None
                    if CASH_LIKE.search(inst.name):
                        inst.type, inst.asset_class = "fund", "cash"
                    elif ROBO.search(inst.name):
                        inst.type, inst.asset_class = "fund", "other"
                self.session.add(inst)
                by_key[key] = inst
                created.append(inst)
        self.session.commit()
        return created

    def list_instruments(self) -> List[Dict[str, Any]]:
        out = []
        for inst in self.session.query(Instrument).order_by(Instrument.name).all():
            data = inst.to_dict()
            last = self._last_price(inst)
            data["last_price"] = {"date": last.date.isoformat(), "close": last.close, "currency": last.currency} if last else None
            out.append(data)
        return out

    def update_instrument(self, instrument_id: int, changes: Dict[str, Any]) -> Dict[str, Any]:
        inst = self.session.get(Instrument, instrument_id)
        if inst is None:
            raise LookupError(f"Instrument {instrument_id} not found")
        for field in ("name", "type", "currency", "asset_class", "valuation", "price_symbol", "manual_price", "manual_price_date"):
            if field in changes and changes[field] is not None:
                setattr(inst, field, changes[field])
        if changes.get("price_symbol"):
            inst.price_source = "alphavantage"
            inst.last_error = None
        if changes.get("manual_price") is not None:
            inst.valuation = changes.get("valuation") or "manual"
            inst.manual_price_date = changes.get("manual_price_date") or date.today()
        inst.updated_at = datetime.utcnow()
        self.session.commit()
        return inst.to_dict()

    def resolve_symbols(self, figi: OpenFigi, only_missing: bool = True) -> Dict[str, Any]:
        """Find a priceable symbol for every instrument with an ISIN (OpenFIGI listings → exchange preference)."""
        self.sync_instruments()
        query = self.session.query(Instrument).filter(Instrument.isin.isnot(None))
        if only_missing:
            query = query.filter(Instrument.price_symbol.is_(None), Instrument.valuation == "market")
        targets = query.all()
        if not targets:
            return {"resolved": 0, "unresolved": 0, "instruments": []}
        try:
            listings = figi.listings([i.isin for i in targets])
        except MarketError as exc:
            return {"resolved": 0, "unresolved": len(targets), "error": str(exc), "instruments": []}
        report = []
        for inst in targets:
            found = listings.get(inst.isin) or []
            kind, asset_class = classify_listing(found)
            if kind != "other":
                inst.type = kind
            if inst.asset_class == "other" and asset_class != "other":
                inst.asset_class = asset_class
            if found and not inst.name.strip() or inst.name == inst.isin or "for isin" in inst.name.lower():
                inst.name = (found[0].get("name") or inst.name)[:200]
            ranked = rank_symbols(found, inst.isin)
            picked = ranked[0] if ranked else None
            if CERTIFICATE.search(inst.name or "") or any(CERTIFICATE.search(str(i.get("name") or "")) for i in found):
                # leveraged certificates: no exchange price here, and not a bond; valued at cost until a manual price
                inst.type, inst.asset_class, inst.valuation = "certificate", "other", "cost"
                inst.price_symbol = None
                inst.last_error = "certificate: no exchange price, valued at cost (set a manual price)"
                report.append({"isin": inst.isin, "name": inst.name, "symbol": None, "valuation": inst.valuation, "error": inst.last_error})
                continue
            if picked:
                inst.price_symbol, exch, _ = picked
                inst.symbol_candidates = [sym for sym, _, _ in ranked[1:6]]
                inst.price_source = "alphavantage"
                inst.last_error = None
            elif kind == "bond" or any(str(i.get("securityType2") or "").lower() in ("corp", "govt", "mtn") for i in found):
                inst.valuation = "cost"
                inst.type, inst.asset_class = "bond", "bonds" if inst.asset_class == "other" else inst.asset_class
                inst.last_error = "bond: no exchange price, valued at cost"
            else:
                inst.valuation = "cost" if not found else inst.valuation
                inst.last_error = "no listing on a supported exchange" if found else "ISIN unknown to OpenFIGI"
            report.append({"isin": inst.isin, "name": inst.name, "symbol": inst.price_symbol, "valuation": inst.valuation, "error": inst.last_error})
        self.session.commit()
        return {"resolved": sum(1 for r in report if r["symbol"]), "unresolved": sum(1 for r in report if not r["symbol"]), "instruments": report}

    # ------------------------------------------------------------------ prices

    def _last_price(self, inst: Instrument, upto: Optional[date] = None) -> Optional[Price]:
        query = self.session.query(Price).filter(Price.instrument_id == inst.id)
        if upto is not None:
            query = query.filter(Price.date <= upto)
        return query.order_by(Price.date.desc()).first()

    def _fetched_today(self, inst: Instrument, today: date) -> bool:
        row = self.session.query(Price).filter(Price.instrument_id == inst.id, Price.created_at >= datetime.combine(today, datetime.min.time())).first()
        return row is not None

    def refresh_prices(self, av: AlphaVantage, today: Optional[date] = None, max_requests: int = 20, force: bool = False) -> Dict[str, Any]:
        """Fetch the daily closes of every market-valued instrument not refreshed today, then the exchange rates
        the foreign ones need. Stops at ``max_requests`` or when the provider says the day's budget is spent."""
        today = today or date.today()
        if not av.configured():
            return {"requests": 0, "updated": [], "skipped": "ALPHAVANTAGE_API_KEY is not set"}
        self.sync_instruments()
        instruments = self.session.query(Instrument).filter(Instrument.valuation == "market", Instrument.price_symbol.isnot(None)).order_by(Instrument.id).all()
        requests = 0
        updated: List[str] = []
        errors: List[Dict[str, str]] = []
        currencies: set = set()

        def pace() -> None:
            if requests > 0 and self.request_spacing:
                time.sleep(self.request_spacing)

        for inst in instruments:
            if not force and self._fetched_today(inst, today):
                last = self._last_price(inst)
                if last and last.currency != "EUR":
                    currencies.add(last.currency)
                continue
            if requests >= max_requests:
                break
            # the symbol in use, then the other listings OpenFIGI knows: Alpha Vantage answers "Invalid API call"
            # for a symbol it lacks and, now and then, for one it has (a retry of the same symbol comes first)
            attempts = [inst.price_symbol, inst.price_symbol] + [c for c in (inst.symbol_candidates or []) if c != inst.price_symbol]
            quotes = None
            last_error = None
            for symbol in attempts:
                if requests >= max_requests:
                    break
                pace()
                try:
                    quotes = av.daily(symbol, inst.currency)
                    requests += 1
                except RateLimited as exc:
                    inst.last_error = f"rate limited: {exc}"
                    errors.append({"symbol": symbol, "error": "rate limited"})
                    self.session.commit()
                    return {"requests": requests, "updated": updated, "errors": errors, "stopped": "rate limited"}
                except MarketError as exc:
                    requests += 1
                    last_error = str(exc)[:300]
                    quotes = None
                    continue
                if quotes:
                    if symbol != inst.price_symbol:
                        inst.symbol_candidates = [c for c in (inst.symbol_candidates or []) if c != symbol] + [inst.price_symbol]
                        inst.price_symbol = symbol
                    break
                last_error = "no data for symbol"
            if not quotes:
                inst.last_error = last_error or "no data for symbol"
                errors.append({"symbol": inst.price_symbol, "error": (last_error or "no data")[:120]})
                continue
            self._store_quotes(inst, quotes)
            inst.currency = quotes[-1].currency
            inst.last_error = None
            updated.append(inst.price_symbol)
            if quotes[-1].currency != "EUR":
                currencies.add(quotes[-1].currency)
        self.session.commit()

        for ccy in sorted(currencies):
            if self._fx_fetched_today(ccy, today) and not force:
                continue
            if requests >= max_requests:
                break
            pace()
            try:
                rates = av.fx_daily("EUR", ccy)
                requests += 1
            except RateLimited:
                errors.append({"symbol": f"EUR{ccy}", "error": "rate limited"})
                break
            except MarketError as exc:
                requests += 1
                errors.append({"symbol": f"EUR{ccy}", "error": str(exc)[:120]})
                continue
            for q in rates[-120:]:
                row = self.session.query(FxRate).filter(FxRate.base == "EUR", FxRate.quote == ccy, FxRate.date == q.day).first()
                if row is None:
                    self.session.add(FxRate(base="EUR", quote=ccy, date=q.day, rate=q.close))
                else:
                    row.rate = q.close
            self.session.commit()
            updated.append(f"EUR{ccy}")
        return {"requests": requests, "updated": updated, "errors": errors}

    def _store_quotes(self, inst: Instrument, quotes) -> None:
        existing = {p.date: p for p in self.session.query(Price).filter(Price.instrument_id == inst.id, Price.date >= quotes[0].day).all()}
        for q in quotes[-120:]:
            row = existing.get(q.day)
            if row is None:
                self.session.add(Price(instrument_id=inst.id, date=q.day, close=q.close, currency=q.currency, created_at=datetime.utcnow()))
            else:
                row.close, row.currency, row.created_at = q.close, q.currency, datetime.utcnow()

    def _fx_fetched_today(self, ccy: str, today: date) -> bool:
        latest = self.session.query(FxRate).filter(FxRate.base == "EUR", FxRate.quote == ccy).order_by(FxRate.date.desc()).first()
        return latest is not None and (today - latest.date).days <= 3

    def _fx(self, ccy: str, upto: date) -> Optional[FxRate]:
        if ccy == "EUR":
            return None
        return self.session.query(FxRate).filter(FxRate.base == "EUR", FxRate.quote == ccy, FxRate.date <= upto).order_by(FxRate.date.desc()).first()

    # ------------------------------------------------------------------ valuation

    def valued_positions(self, today: Optional[date] = None) -> Dict[str, Any]:
        today = today or date.today()
        self.sync_instruments()
        instruments = {i.key: i for i in self.session.query(Instrument).all()}
        accounts = {a.id: a for a in self.session.query(Account).all()}
        groups = []
        unknown_total = 0
        for account_id, positions in self.investments.positions_by_account().items():
            source = accounts.get(account_id)
            target_id = (source.securities_account_id if source else None) or (account_id if source and is_valuation(source) else None)
            valued = []
            for pos in positions:
                if pos["status"] == "closed" and (pos.get("quantity") or 0) <= 1e-6:
                    continue
                inst = instruments.get(pos["key"])
                valued.append(self._value_position(pos, inst, today))
            value_known = sum(v["value"] for v in valued if v["value"] is not None)
            unknown = [v for v in valued if v["value"] is None]
            unknown_total += len(unknown)
            groups.append({
                "source_account_id": account_id,
                "source_account": source.name if source else None,
                "securities_account_id": target_id,
                "securities_account": accounts[target_id].name if target_id in accounts else None,
                "value": round(value_known, 2),
                "open_cost": round(sum(v["open_cost"] for v in valued), 2),
                "unrealized": round(sum(v["unrealized"] for v in valued if v["unrealized"] is not None), 2),
                "unknown_positions": len(unknown),
                "positions": valued,
            })
        total = sum(g["value"] for g in groups)
        allocation: Dict[str, float] = {}
        for g in groups:
            for v in g["positions"]:
                if v["value"]:
                    allocation[v["asset_class"]] = allocation.get(v["asset_class"], 0.0) + v["value"]
        return {
            "as_of": today.isoformat(),
            "total_value": round(total, 2),
            "allocation": [
                {"asset_class": k, "value": round(v, 2), "weight": round(100 * v / total, 1) if total else 0.0}
                for k, v in sorted(allocation.items(), key=lambda kv: -kv[1])
            ],
            "unknown_positions": unknown_total,
            "accounts": groups,
            "note": "Market values use the last available close (date shown per position); positions valued at cost show the net cash put in, not a market price.",
        }

    def _value_position(self, pos: Dict[str, Any], inst: Optional[Instrument], today: date) -> Dict[str, Any]:
        qty = pos.get("quantity")
        out = {
            **pos,
            "instrument_id": inst.id if inst else None,
            "asset_class": inst.asset_class if inst else "other",
            "type": inst.type if inst else "other",
            "symbol": inst.price_symbol if inst else None,
            "value": None, "unrealized": None, "price": None, "price_date": None, "price_currency": None, "fx": None,
            "price_basis": "unknown", "stale": False,
        }
        if inst and inst.name and inst.name != pos.get("name") and ("for isin" in (pos.get("name") or "").lower() or not pos.get("name")):
            out["name"] = inst.name
        net_in = max(pos["invested"] - pos["proceeds"], 0.0)
        if inst is None:
            return out
        if inst.valuation == "cost" or (qty is None and inst.valuation != "manual"):
            out.update(value=round(net_in, 2), unrealized=0.0, price_basis="cost")
            return out
        if inst.valuation == "manual" and inst.manual_price is not None and qty:
            value = qty * inst.manual_price
            out.update(value=round(value, 2), price=inst.manual_price, price_date=inst.manual_price_date.isoformat() if inst.manual_price_date else None, price_currency=inst.currency, price_basis="manual")
            out["unrealized"] = round(value - pos["open_cost"], 2)
            return out
        last = self._last_price(inst, today)
        if last is None or not qty:
            out["price_basis"] = "no_price" if last is None else "no_quantity"
            return out
        value = qty * last.close
        fx = self._fx(last.currency, today)
        if last.currency != "EUR":
            if fx is None:
                out.update(price=last.close, price_date=last.date.isoformat(), price_currency=last.currency, price_basis="no_fx")
                return out
            value = value / fx.rate
            out["fx"] = fx.rate
        out.update(
            value=round(value, 2), unrealized=round(value - pos["open_cost"], 2), price=last.close,
            price_date=last.date.isoformat(), price_currency=last.currency, price_basis="market",
            stale=(today - last.date).days > MAX_PRICE_AGE_DAYS,
        )
        return out

    def write_valuations(self, today: Optional[date] = None) -> Dict[str, Any]:
        """Record today's value of each broker's positions as a ``market`` snapshot on its securities account."""
        today = today or date.today()
        overview = self.valued_positions(today)
        net_worth = NetWorthService(self.session)
        written, skipped = [], []
        for g in overview["accounts"]:
            target = g["securities_account_id"]
            if target is None:
                skipped.append({"source_account_id": g["source_account_id"], "reason": "no securities account configured"})
                continue
            if g["value"] <= 0 and g["unknown_positions"]:
                skipped.append({"source_account_id": g["source_account_id"], "reason": "nothing could be valued"})
                continue
            existing = self.session.query(BalanceSnapshot).filter(BalanceSnapshot.account_id == target, BalanceSnapshot.date == today).first()
            if existing is not None and existing.source in SNAPSHOT_SOURCES_THAT_WIN:
                skipped.append({"securities_account_id": target, "reason": f"a {existing.source} balance exists for today"})
                continue
            net_worth.upsert(target, today, g["value"], note=None, source="market")
            written.append({"securities_account_id": target, "value": g["value"], "unknown_positions": g["unknown_positions"]})
        return {"as_of": today.isoformat(), "written": written, "skipped": skipped}
