"""Investments: what the user put into securities, what came back, and what that adds up to.

Transactions in a blueprint category of kind ``investment`` are kept out of spending, income and the monthly
net (``investment_texts`` / ``not_investment``) and read here instead. Each one is a trade, a dividend or a
contribution, recognised from the bank's wording (ISIN and quantity when the statement has them).

There are no market prices: the *realised* result is exact where every buy and sell of an instrument carries a
quantity (moving average cost); where it does not (a fund sold in tranches with no units on the statement) only
the cash flow is known, and the instrument is reported as such rather than guessed at.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import or_, true
from sqlalchemy.orm import Session

from src.blueprint import Blueprint
from src.database.models import Transaction, Workspace

_EPS = 1e-6
_ISIN = r"[A-Z]{2}[A-Z0-9]{9}[0-9]"
_ISIN_RE = re.compile(rf"\b({_ISIN})\b")
_QTY_RE = re.compile(r"quantity:\s*([0-9]+(?:[.,][0-9]+)?)", re.IGNORECASE)
_DIVIDEND_RE = re.compile(r"dividend|dividendo|cedola|coupon", re.IGNORECASE)
_SELL_RE = re.compile(r"\b(sell|vendita|venduto|rimborso)\b", re.IGNORECASE)
_BUY_RE = re.compile(r"\b(buy|acquisto|savings plan|piano di accumulo)\b", re.IGNORECASE)
# wording the bank puts before the instrument name
_LEAD_RE = re.compile(
    r"^(commercio\s+)?(buy trade|sell trade|savings plan execution|rendimento\s+cash\s+dividend\s+for\s+isin|"
    r"acquisto|vendita|to)\s+",
    re.IGNORECASE,
)


def _blueprint_of(session: Session) -> Optional[Blueprint]:
    workspace_id = session.info.get("workspace_id")
    workspace = session.get(Workspace, workspace_id) if workspace_id is not None else None
    try:
        return Blueprint.model_validate(workspace.blueprint) if workspace else None
    except ValueError:
        return None


def investment_texts(session: Session, blueprint: Optional[Blueprint] = None) -> Set[str]:
    """Category texts, as stored on transactions, that belong to an investment category."""
    blueprint = blueprint or _blueprint_of(session)
    if blueprint is None:
        return set()
    keys = blueprint.investment_keys()
    if not keys:
        return set()
    texts = {row[0] for row in session.query(Transaction.category).distinct() if row[0]}
    return {text for text in texts if blueprint.resolve_category(text) in keys}


def not_investment(texts: Set[str]):
    """SQL clause that keeps a transaction out of spending/income when its category is an investment."""
    if not texts:
        return true()
    return or_(Transaction.category.is_(None), Transaction.category.notin_(texts))


# --------------------------------------------------------------------------- reading a statement line


@dataclass
class Trade:
    kind: str  # buy | sell | dividend
    key: str  # ISIN, else the normalised name
    isin: Optional[str]
    name: str
    quantity: Optional[float]
    amount: float  # always positive: money out for a buy, money in for a sell or dividend
    day: date


def _name_of(description: str, isin: Optional[str]) -> str:
    text = _LEAD_RE.sub("", description.strip())
    text = _QTY_RE.sub("", text).strip(" ,;-")
    if isin:
        text = text.replace(isin, "").strip(" ,;-")
    return re.sub(r"\s+", " ", text)


def parse_trade(description: str, amount: float, day: date) -> Trade:
    """Read one investment statement line. The sign decides when the wording does not."""
    isin_match = _ISIN_RE.search(description)
    isin = isin_match.group(1) if isin_match else None
    qty_match = _QTY_RE.search(description)
    quantity = float(qty_match.group(1).replace(",", ".")) if qty_match else None
    if _DIVIDEND_RE.search(description) and amount > 0:
        kind = "dividend"
    elif amount < 0:
        kind = "buy"
    elif _SELL_RE.search(description) or not _BUY_RE.search(description):
        kind = "sell"
    else:  # money in on a line that reads like a purchase: a refund of it
        kind = "sell"
    name = _name_of(description, isin)
    key = isin or re.sub(r"[^a-z0-9]+", " ", name.lower()).strip() or "altro"
    return Trade(kind, key, isin, name or isin or "Altro", quantity, abs(amount), day)


# --------------------------------------------------------------------------- the portfolio


class InvestmentService:
    def __init__(self, session: Session):
        self.session = session

    def portfolio(self) -> Dict[str, Any]:
        texts = investment_texts(self.session)
        rows: List[Transaction] = []
        if texts:
            rows = (
                self.session.query(Transaction)
                .filter(Transaction.category.in_(texts), Transaction.is_transfer.is_(False))
                .order_by(Transaction.date, Transaction.id)
                .all()
            )
        trades = [parse_trade(t.description or "", t.amount, t.date) for t in rows]

        by_instrument: Dict[str, List[Trade]] = defaultdict(list)
        for trade in trades:
            by_instrument[trade.key].append(trade)

        positions = [self._position(key, items) for key, items in by_instrument.items()]
        positions.sort(key=lambda p: (-p["invested"], p["name"]))

        known = [p for p in positions if p["realized"] is not None]
        unresolved = [p for p in positions if p["realized"] is None and p["proceeds"] > 0]
        invested = sum(p["invested"] for p in positions)
        proceeds = sum(p["proceeds"] for p in positions)
        dividends = sum(p["dividends"] for p in positions)
        realized = sum(p["realized"] for p in known)
        return {
            "totals": {
                "invested": round(invested, 2),
                "proceeds": round(proceeds, 2),
                "dividends": round(dividends, 2),
                # money still out in investments: what went in, less what has come back from sales
                "net_invested": round(invested - proceeds, 2),
                "cost_basis_open": round(sum(p["open_cost"] for p in positions), 2),
                "realized": round(realized, 2),
                # realised gain/loss on closed or partly sold positions plus every dividend received
                "realized_result": round(realized + dividends, 2),
                "unresolved_instruments": len(unresolved),
                "unresolved_net_flow": round(sum(p["net_flow"] for p in unresolved), 2),
                "trades": len(trades),
            },
            "positions": positions,
            "by_month": self._by_month(trades),
            "note": (
                "No market prices: unrealised gains are not included. Realised results use average cost and need "
                "the quantity of every buy and sell; instruments without it only show their cash flow."
            ),
        }

    @staticmethod
    def _position(key: str, items: List[Trade]) -> Dict[str, Any]:
        names = [t.name for t in items if t.name and t.name != t.isin]
        name = max(names, key=len) if names else items[0].name
        isin = next((t.isin for t in items if t.isin), None)
        money = [t for t in items if t.kind in ("buy", "sell")]
        complete = bool(money) and all(t.quantity is not None for t in money)

        held_qty = held_cost = realized = 0.0
        for t in money:  # chronological: items arrive ordered by date
            if t.kind == "buy":
                held_qty += t.quantity or 0.0
                held_cost += t.amount
            elif complete:
                sold = min(t.quantity or 0.0, held_qty)
                avg = held_cost / held_qty if held_qty > _EPS else 0.0
                cost_sold = avg * sold
                realized += t.amount - cost_sold
                held_qty -= sold
                held_cost -= cost_sold

        invested = sum(t.amount for t in items if t.kind == "buy")
        proceeds = sum(t.amount for t in items if t.kind == "sell")
        dividends = sum(t.amount for t in items if t.kind == "dividend")
        sells = proceeds > 0
        if complete:
            status = "closed" if held_qty <= _EPS else "open"
            open_cost = max(held_cost, 0.0) if status == "open" else 0.0
        else:
            status = "open"
            open_cost = max(invested - proceeds, 0.0)
        # a position with no sale has nothing realised yet: 0, not unknown
        realized_value: Optional[float] = round(realized, 2) if complete else (0.0 if not sells else None)
        return {
            "key": key,
            "isin": isin,
            "name": name,
            "status": status,
            "trades": len(items),
            "invested": round(invested, 2),
            "proceeds": round(proceeds, 2),
            "dividends": round(dividends, 2),
            "net_flow": round(proceeds + dividends - invested, 2),
            "realized": realized_value,
            "result": round(realized_value + dividends, 2) if realized_value is not None else None,
            "quantity": round(held_qty, 6) if complete else None,
            "open_cost": round(open_cost, 2),
            "first_date": min(t.day for t in items).isoformat(),
            "last_date": max(t.day for t in items).isoformat(),
        }

    @staticmethod
    def _by_month(trades: List[Trade]) -> List[Dict[str, Any]]:
        months: Dict[str, Dict[str, float]] = defaultdict(lambda: {"invested": 0.0, "returned": 0.0})
        for t in trades:
            slot = months[t.day.strftime("%Y-%m")]
            if t.kind == "buy":
                slot["invested"] += t.amount
            else:
                slot["returned"] += t.amount
        return [
            {"month": m, "invested": round(v["invested"], 2), "returned": round(v["returned"], 2)}
            for m, v in sorted(months.items())
        ]
