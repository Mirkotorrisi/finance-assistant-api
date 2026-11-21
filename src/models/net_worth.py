"""Pydantic models for balance snapshots and the net-worth endpoints."""

from datetime import date as Date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SnapshotCreate(BaseModel):
    account_id: int
    date: Date = Field(..., description="The day the balance was observed, YYYY-MM-DD (e.g. the last day of the month).")
    balance: float = Field(..., description="What the account held that day. Brokerage accounts: market value.")
    note: Optional[str] = Field(default=None, max_length=500, description="Why the month was unusual, if it was.")


class SnapshotBulk(BaseModel):
    snapshots: List[SnapshotCreate]
    source: Literal["import", "user", "bank"] = Field(
        default="import", description="'import' for a sheet or file, 'user' for typed values, 'bank' for a bank sync."
    )


class FlowCheckRow(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")
    account_id: int
    income: Optional[float] = Field(default=None, description="Income the user's own sheet states for the month.")
    expenses: Optional[float] = Field(default=None, description="Expenses (positive number) the sheet states.")


class FlowCheckRequest(BaseModel):
    rows: List[FlowCheckRow]
    include_transfers: bool = Field(default=False, description="Count moves between own accounts as income/expenses.")
