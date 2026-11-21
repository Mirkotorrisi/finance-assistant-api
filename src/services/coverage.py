"""How much of a total rests on categories the user has confirmed."""

from typing import Any, Dict, Iterable

from sqlalchemy import case, func
from sqlalchemy.orm import Query

from src.database.models import Transaction


def coverage_totals(reviewed: float, unreviewed: float, reviewed_count: int, unreviewed_count: int) -> Dict[str, Any]:
    """The coverage figures from already aggregated amounts (absolute values) and counts."""
    total = reviewed + unreviewed
    return {
        "total": round(total, 2),
        "reviewed_amount": round(reviewed, 2),
        "unreviewed_amount": round(unreviewed, 2),
        "reviewed_share": round(reviewed / total, 4) if total else 1.0,
        "reviewed_transactions": reviewed_count,
        "unreviewed_transactions": unreviewed_count,
    }


def coverage_of(transactions: Iterable[Transaction]) -> Dict[str, Any]:
    """Confirmed vs unconfirmed amount (absolute values) over transactions already in memory."""
    reviewed = unreviewed = 0.0
    reviewed_count = unreviewed_count = 0
    for t in transactions:
        if t.reviewed:
            reviewed += abs(t.amount)
            reviewed_count += 1
        else:
            unreviewed += abs(t.amount)
            unreviewed_count += 1
    return coverage_totals(reviewed, unreviewed, reviewed_count, unreviewed_count)


def coverage_query(query: Query) -> Dict[str, Any]:
    """The same figures computed by the database over a ``Transaction`` query (nothing is loaded)."""
    reviewed = Transaction.reviewed.is_(True)
    row = query.with_entities(
        func.coalesce(func.sum(case((reviewed, func.abs(Transaction.amount)), else_=0.0)), 0.0),
        func.coalesce(func.sum(case((reviewed, 0.0), else_=func.abs(Transaction.amount))), 0.0),
        func.coalesce(func.sum(case((reviewed, 1), else_=0)), 0),
        func.coalesce(func.sum(case((reviewed, 0), else_=1)), 0),
    ).one()
    return coverage_totals(float(row[0]), float(row[1]), int(row[2]), int(row[3]))
