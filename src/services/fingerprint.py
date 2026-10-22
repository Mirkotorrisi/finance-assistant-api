"""Stable identity of a statement row, used to import overlapping statements without duplicates."""

import hashlib
from datetime import date, datetime
from typing import Optional, Union


def normalize_description(description: Optional[str]) -> str:
    return " ".join(str(description or "").lower().split())


def compute_fingerprint(
    workspace_id: int,
    account_id: Optional[int],
    day: Union[date, datetime, str],
    amount: float,
    description: Optional[str],
) -> str:
    """Identical rows (same account, day, amount and text) share a fingerprint.

    Keep in sync with the frozen copy in migrations/versions/c3a9d1e7f205_add_workspaces.py.
    """
    key = (
        f"{workspace_id}|{account_id if account_id is not None else 'none'}|{str(day)[:10]}|"
        f"{float(amount):.2f}|{normalize_description(description)}"
    )
    return hashlib.sha256(key.encode()).hexdigest()
