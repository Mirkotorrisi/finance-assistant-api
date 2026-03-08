"""Pydantic models for transaction endpoints."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TransactionCreate(BaseModel):
    """Payload for creating a new transaction."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": -45.50,
                "category": "groceries",
                "description": "Weekly supermarket shopping",
                "date": "2024-01-15",
                "currency": "EUR",
                "account_id": 1,
            }
        }
    )

    amount: float = Field(
        ...,
        description="Transaction amount. Use negative values for expenses and positive values for income.",
    )
    category: str = Field(..., description="Category name (e.g. 'groceries', 'salary').")
    description: str = Field(..., description="Human-readable description of the transaction.")
    date: Optional[str] = Field(
        default=None,
        description="ISO 8601 date string (YYYY-MM-DD). Defaults to today when omitted.",
    )
    currency: Optional[str] = Field(default="EUR", description="ISO 4217 currency code.")
    account_id: Optional[int] = Field(default=None, description="ID of the account this transaction belongs to.")


class TransactionUpdate(BaseModel):
    """Payload for partially updating an existing transaction. All fields are optional."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": -50.00,
                "category": "groceries",
                "description": "Updated supermarket bill",
                "date": "2024-01-16",
                "currency": "EUR",
                "account_id": 1,
            }
        }
    )

    amount: Optional[float] = Field(default=None, description="New transaction amount.")
    category: Optional[str] = Field(default=None, description="New category.")
    description: Optional[str] = Field(default=None, description="New description.")
    date: Optional[str] = Field(default=None, description="New date in YYYY-MM-DD format.")
    currency: Optional[str] = Field(default=None, description="New currency code.")
    account_id: Optional[int] = Field(default=None, description="New account ID.")


class TransactionResponse(BaseModel):
    """Representation of a transaction returned by the API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "date": "2024-01-15",
                "amount": -45.50,
                "category": "groceries",
                "description": "Weekly supermarket shopping",
                "currency": "EUR",
                "account_id": 1,
            }
        }
    )

    id: int = Field(..., description="Unique transaction identifier.")
    date: str = Field(..., description="Transaction date in ISO 8601 format (YYYY-MM-DD).")
    amount: float = Field(..., description="Transaction amount (negative = expense, positive = income).")
    category: str = Field(..., description="Category of the transaction.")
    description: str = Field(..., description="Description of the transaction.")
    currency: str = Field(..., description="ISO 4217 currency code.")
    account_id: Optional[int] = Field(default=None, description="Account ID associated with this transaction.")


class BalanceResponse(BaseModel):
    """Total balance computed from all transactions."""

    model_config = ConfigDict(json_schema_extra={"example": {"balance": 2350.75}})

    balance: float = Field(..., description="Current total balance across all transactions.")
