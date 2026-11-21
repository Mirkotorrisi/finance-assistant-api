"""One clock for the API.

Timestamps (``created_at``, ``updated_at``, ``last_sync_at``, ...) are **naive UTC**: the columns are ``DateTime``
without time zone on both SQLite and Postgres, so a zone-aware value would be silently shifted or truncated by the
driver. Business dates (transaction dates, snapshot days, "today" for valuations) are the user's local calendar day,
``date.today()``: a purchase made at 23:30 in Rome belongs to that day, not to the UTC one.
"""

from datetime import date, datetime, timezone


def utc_now() -> datetime:
    """Current time as a naive UTC datetime (what the DateTime columns store)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: datetime | None) -> datetime | None:
    """A zone-aware datetime from a client becomes naive UTC; a naive one is taken as UTC already."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def today() -> date:
    """The user's local calendar day."""
    return date.today()
