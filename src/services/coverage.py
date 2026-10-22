"""How much of a total rests on categories the user has confirmed."""

from typing import Any, Dict, Iterable

from src.database.models import Transaction


def coverage_of(transactions: Iterable[Transaction]) -> Dict[str, Any]:
    """Confirmed vs unconfirmed amount (absolute values) over the given transactions."""
    reviewed = unreviewed = 0.0
    reviewed_count = unreviewed_count = 0
    for t in transactions:
        if t.reviewed:
            reviewed += abs(t.amount)
            reviewed_count += 1
        else:
            unreviewed += abs(t.amount)
            unreviewed_count += 1
    total = reviewed + unreviewed
    return {
        "total": round(total, 2),
        "reviewed_amount": round(reviewed, 2),
        "unreviewed_amount": round(unreviewed, 2),
        "reviewed_share": round(reviewed / total, 4) if total else 1.0,
        "reviewed_transactions": reviewed_count,
        "unreviewed_transactions": unreviewed_count,
    }
