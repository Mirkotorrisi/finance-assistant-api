"""Net worth: balance snapshots reconciled against the transactions.

Transactions stay the source of truth for flows. A snapshot says what an account held on a day; between two
snapshots of the same account the change in balance must equal the sum of its transactions, and the difference
(the *delta*) points at missing, extra or wrong rows. The first snapshot of an account is only a baseline: the
transactions may start after the account was opened, so an absolute comparison would just measure the opening
balance.

Two kinds of account:

* cash accounts (checking, savings, cash, credit, ...): the balance between snapshots is derived from the
  transactions, so a month with no snapshot still has a number;
* valuation accounts (brokerage, investment, retirement): the snapshot is a market value, which transactions
  cannot reproduce, so it is carried forward as is and never reconciled.

An account with no transactions up to a snapshot (cash, an account never imported) is ``untracked``: there is
nothing to compare with, so it is not a gap.
"""

from bisect import bisect_right
from calendar import monthrange
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.models import Account, BalanceSnapshot, Transaction
from src.services.investments import investment_texts, not_investment

VALUATION_TYPES = {"investment", "brokerage", "retirement", "pension", "crypto"}
TOLERANCE = 1.0  # sheets round to whole euros
ADJUSTMENT_CATEGORY = "rettifica_saldo"
DEFAULT_MONTHS = 24


def is_valuation(account: Account) -> bool:
    return (account.type or "").strip().lower() in VALUATION_TYPES


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def _next_month(year: int, month: int) -> Tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _parse_month(value: str) -> Tuple[int, int]:
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError:
        raise ValueError(f"Invalid month '{value}', expected YYYY-MM")
    return parsed.year, parsed.month


class _Flows:
    """Running sum of one account's transactions, to read the flow between two days without a query each."""

    def __init__(self, rows: List[Tuple[date, float]]):
        rows = sorted(rows)
        self.days = [d for d, _ in rows]
        self.cumulative: List[float] = []
        total = 0.0
        for _, amount in rows:
            total += amount
            self.cumulative.append(total)

    def upto(self, day: date) -> float:
        i = bisect_right(self.days, day)
        return self.cumulative[i - 1] if i else 0.0

    def between(self, after: date, upto: date) -> float:
        """Sum of the transactions in (after, upto]."""
        return self.upto(upto) - self.upto(after)

    def __bool__(self) -> bool:
        return bool(self.days)


class NetWorthService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ helpers

    def _account(self, account_id: int) -> Optional[Account]:
        return self.session.query(Account).filter(Account.id == account_id).first()

    def _flows(self) -> Dict[int, _Flows]:
        rows: Dict[int, List[Tuple[date, float]]] = {}
        query = self.session.query(Transaction.account_id, Transaction.date, Transaction.amount).filter(
            Transaction.account_id.isnot(None)
        )
        for account_id, day, amount in query:
            rows.setdefault(account_id, []).append((day, amount))
        return {account_id: _Flows(r) for account_id, r in rows.items()}

    def _snapshots(self, account_id: Optional[int] = None) -> Dict[int, List[BalanceSnapshot]]:
        query = self.session.query(BalanceSnapshot)
        if account_id is not None:
            query = query.filter(BalanceSnapshot.account_id == account_id)
        grouped: Dict[int, List[BalanceSnapshot]] = {}
        for snap in query.order_by(BalanceSnapshot.account_id, BalanceSnapshot.date):
            grouped.setdefault(snap.account_id, []).append(snap)
        return grouped

    # ------------------------------------------------------------------ snapshots

    def upsert(self, account_id: int, day: date, balance: float, note: Optional[str] = None, source: str = "user") -> BalanceSnapshot:
        if self._account(account_id) is None:
            raise LookupError(f"Account {account_id} not found")
        snap = (
            self.session.query(BalanceSnapshot)
            .filter(BalanceSnapshot.account_id == account_id, BalanceSnapshot.date == day)
            .first()
        )
        if snap is None:
            snap = BalanceSnapshot(account_id=account_id, date=day, balance=round(balance, 2), note=note, source=source)
            self.session.add(snap)
        else:
            snap.balance = round(balance, 2)
            snap.source = source
            if note is not None:
                snap.note = note
        self.session.commit()
        self.session.refresh(snap)
        return snap

    def upsert_many(self, items: List[Dict[str, Any]], source: str = "import") -> List[int]:
        """Store several snapshots at once; unknown accounts fail the whole call before anything is written."""
        for item in items:
            if self._account(item["account_id"]) is None:
                raise LookupError(f"Account {item['account_id']} not found")
        ids = [self.upsert(i["account_id"], i["date"], i["balance"], i.get("note"), source).id for i in items]
        return ids

    def get(self, snapshot_id: int) -> Optional[BalanceSnapshot]:
        return self.session.query(BalanceSnapshot).filter(BalanceSnapshot.id == snapshot_id).first()

    def delete(self, snapshot_id: int) -> bool:
        snap = self.get(snapshot_id)
        if snap is None:
            return False
        self.session.delete(snap)
        self.session.commit()
        return True

    def _reconcile(self, account: Account, snaps: List[BalanceSnapshot], flows: Optional[_Flows]) -> Dict[int, Dict[str, Any]]:
        out: Dict[int, Dict[str, Any]] = {}
        valuation = is_valuation(account)
        for i, snap in enumerate(snaps):
            if i == 0:
                out[snap.id] = {"status": "baseline"}
                continue
            prev = snaps[i - 1]
            actual = round(snap.balance - prev.balance, 2)
            if valuation:
                out[snap.id] = {"status": "valuation", "previous_date": prev.date.isoformat(), "change": actual}
                continue
            if not flows or flows.days[0] > snap.date:
                # no transactions up to this snapshot: nothing to compare with, which is not the same as a gap
                out[snap.id] = {"status": "untracked", "previous_date": prev.date.isoformat(), "change": actual}
                continue
            expected = round(flows.between(prev.date, snap.date), 2)
            delta = round(actual - expected, 2)
            out[snap.id] = {
                "status": "ok" if abs(delta) <= TOLERANCE else "gap",
                "previous_date": prev.date.isoformat(),
                "expected_change": expected,
                "actual_change": actual,
                "delta": delta,
            }
        return out

    def list(self, account_id: Optional[int] = None, start: Optional[date] = None, end: Optional[date] = None) -> List[Dict[str, Any]]:
        """Snapshots with their reconciliation against the account's transactions, oldest first per account."""
        accounts = {a.id: a for a in self.session.query(Account)}
        flows = self._flows()
        result: List[Dict[str, Any]] = []
        for acc_id, snaps in self._snapshots(account_id).items():
            account = accounts.get(acc_id)
            if account is None:
                continue
            recon = self._reconcile(account, snaps, flows.get(acc_id))
            for snap in snaps:
                if (start and snap.date < start) or (end and snap.date > end):
                    continue
                result.append({**snap.to_dict(), "account_name": account.name, "reconciliation": recon[snap.id]})
        result.sort(key=lambda r: (r["date"], r["account_id"]))
        return result

    def adjust(self, snapshot_id: int) -> Dict[str, Any]:
        """Book the unexplained difference of a snapshot as a correcting transaction.

        The row is flagged as a transfer so it moves the balance without counting as spending or income.
        """
        snap = self.get(snapshot_id)
        if snap is None:
            raise LookupError(f"Snapshot {snapshot_id} not found")
        account = self._account(snap.account_id)
        entry = next((r for r in self.list(snap.account_id) if r["id"] == snap.id), None)
        recon = entry["reconciliation"] if entry else {}
        if recon.get("status") != "gap":
            raise ValueError("Nothing to adjust: this snapshot is already consistent with the transactions")
        delta = recon["delta"]
        transaction = Transaction(
            account_id=account.id,
            date=snap.date,
            amount=delta,
            category=ADJUSTMENT_CATEGORY,
            description="Rettifica saldo (da snapshot)",
            currency=account.currency or "EUR",
            category_source="user",
            reviewed=True,
            merchant_key="rettifica saldo",
            is_transfer=True,
        )
        self.session.add(transaction)
        self.session.commit()
        self.session.refresh(transaction)
        return transaction.to_dict()

    # ------------------------------------------------------------------ net worth

    def _balance_on(self, account: Account, day: date, snaps: List[BalanceSnapshot], flows: Optional[_Flows]) -> Dict[str, Any]:
        before = [s for s in snaps if s.date <= day]
        after = [s for s in snaps if s.date > day]
        if is_valuation(account):
            if not before:
                return {"balance": None, "basis": "none"}
            latest = before[-1]
            same_month = (latest.date.year, latest.date.month) == (day.year, day.month)
            return {"balance": latest.balance, "basis": "snapshot" if same_month else "carried"}
        if before:
            latest = before[-1]
            moved = flows.between(latest.date, day) if flows else 0.0
            same_month = (latest.date.year, latest.date.month) == (day.year, day.month)
            return {"balance": round(latest.balance + moved, 2), "basis": "snapshot" if same_month else "derived"}
        if after and flows:  # without transactions there is nothing to work back with: earlier values are unknown
            nxt = after[0]
            moved = flows.between(day, nxt.date) if flows else 0.0
            return {"balance": round(nxt.balance - moved, 2), "basis": "derived"}
        if flows:
            return {"balance": round(flows.upto(day), 2), "basis": "transactions"}
        return {"balance": None, "basis": "none"}

    def net_worth(self, start_month: Optional[str] = None, end_month: Optional[str] = None) -> Dict[str, Any]:
        today = date.today()
        accounts = self.session.query(Account).filter(Account.is_active.is_(True)).order_by(Account.name).all()
        flows = self._flows()
        snapshots = self._snapshots()

        end_y, end_m = _parse_month(end_month) if end_month else (today.year, today.month)
        if start_month:
            start_y, start_m = _parse_month(start_month)
        else:
            firsts = [s[0].date for s in snapshots.values() if s]
            firsts += [f.days[0] for f in flows.values() if f]
            if firsts:
                first = min(firsts)
                start_y, start_m = first.year, first.month
            else:
                start_y, start_m = end_y, end_m
            floor = (end_y * 12 + end_m - 1) - (DEFAULT_MONTHS - 1)
            if start_y * 12 + start_m - 1 < floor:
                start_y, start_m = divmod(floor, 12)
                start_m += 1

        months: List[Dict[str, Any]] = []
        y, m = start_y, start_m
        while (y, m) <= (end_y, end_m):
            day = _month_end(y, m)  # a snapshot dated later this month (or ahead of today) still belongs to it
            balances: Dict[str, Dict[str, Any]] = {}
            liquid = invested = 0.0
            for account in accounts:
                cell = self._balance_on(account, day, snapshots.get(account.id, []), flows.get(account.id))
                balances[str(account.id)] = cell
                if cell["balance"] is None:
                    continue
                if is_valuation(account):
                    invested += cell["balance"]
                else:
                    liquid += cell["balance"]
            months.append({
                "month": f"{y:04d}-{m:02d}",
                "date": day.isoformat(),
                "balances": balances,
                "liquid": round(liquid, 2),
                "invested": round(invested, 2),
                "total": round(liquid + invested, 2),
            })
            y, m = _next_month(y, m)

        gaps = sum(1 for r in self.list() if r["reconciliation"]["status"] == "gap")
        latest = months[-1] if months else None
        previous = months[-2] if len(months) > 1 else None
        return {
            "accounts": [
                {"id": a.id, "name": a.name, "type": a.type, "kind": "valuation" if is_valuation(a) else "cash"}
                for a in accounts
            ],
            "months": months,
            "latest": latest,
            "change": round(latest["total"] - previous["total"], 2) if latest and previous else None,
            "unreconciled_snapshots": gaps,
        }

    # ------------------------------------------------------------------ cross-check with a sheet's flows

    def check_flows(self, rows: List[Dict[str, Any]], include_transfers: bool = False) -> List[Dict[str, Any]]:
        """Compare the income/expenses a user's own sheet states with what the transactions add up to."""
        texts = investment_texts(self.session)
        out = []
        for row in rows:
            year, month = _parse_month(row["month"])
            first, last = date(year, month, 1), _month_end(year, month)
            query = self.session.query(func.sum(Transaction.amount)).filter(
                Transaction.account_id == row["account_id"],
                Transaction.date >= first,
                Transaction.date <= last,
                not_investment(texts),
            )
            if not include_transfers:
                query = query.filter(Transaction.is_transfer.is_(False))
            income = round(query.filter(Transaction.amount > 0).scalar() or 0.0, 2)
            expenses = round(abs(query.filter(Transaction.amount < 0).scalar() or 0.0), 2)
            item: Dict[str, Any] = {"month": row["month"], "account_id": row["account_id"], "actual_income": income, "actual_expenses": expenses}
            matches = True
            for key, actual in (("income", income), ("expenses", expenses)):
                declared = row.get(key)
                item[f"declared_{key}"] = declared
                if declared is None:
                    item[f"{key}_diff"] = None
                    continue
                diff = round(actual - declared, 2)
                item[f"{key}_diff"] = diff
                matches = matches and abs(diff) <= TOLERANCE
            item["status"] = "ok" if matches else "mismatch"
            out.append(item)
        return out
