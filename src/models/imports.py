"""Pydantic models for import and transfer endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ImportRow(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    amount: float = Field(..., description="Negative for expenses, positive for income.")
    description: str
    category: Optional[str] = Field(default=None, description="Defaults to 'other'.")
    currency: Optional[str] = None
    category_source: Optional[str] = Field(
        default=None,
        description="Who chose the category: file (the bank's column), rule, ai, fallback or user. Default file.",
    )
    confidence: Optional[float] = Field(default=None, ge=0, le=1, description="Confidence of an AI-chosen category.")


class ImportRequest(BaseModel):
    account_id: int = Field(..., description="The account (bank, card, ...) this statement belongs to.")
    transactions: List[ImportRow]
    filename: Optional[str] = None
    file_hash: Optional[str] = Field(default=None, description="sha256 of the uploaded file, to flag re-uploads.")


class ImportResult(BaseModel):
    batch_id: Optional[int] = None
    row_count: int
    added_count: int
    skipped_count: int
    invalid_rows: List[str] = []
    duplicate_file: bool = False
    transfers_detected: int = 0
    transactions: List[Dict[str, Any]] = []


class PairRequest(BaseModel):
    first_id: int
    second_id: int
