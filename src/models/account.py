"""Pydantic models for account endpoints."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AccountCreate(BaseModel):
    """Payload for creating a new account."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Main Checking",
                "account_type": "checking",
                "currency": "EUR",
                "is_active": True,
                "current_balance": 1500.00,
            }
        }
    )

    name: str = Field(..., description="Display name for the account.")
    account_type: str = Field(
        ...,
        description=(
            "Account type. Common values: 'checking', 'savings', 'cash', "
            "'investment', 'brokerage', 'retirement'."
        ),
    )
    currency: Optional[str] = Field(default="EUR", description="ISO 4217 currency code.")
    is_active: Optional[bool] = Field(default=True, description="Whether the account is active.")
    current_balance: Optional[float] = Field(default=0.0, description="Initial balance for the account.")


class AccountUpdate(BaseModel):
    """Payload for partially updating an existing account. All fields are optional."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Renamed Checking",
                "type": "savings",
                "is_active": True,
            }
        }
    )

    name: Optional[str] = Field(default=None, description="New account name.")
    type: Optional[str] = Field(default=None, description="New account type.")
    is_active: Optional[bool] = Field(default=None, description="Set account active/inactive.")


class AccountResponse(BaseModel):
    """Representation of an account returned by the API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Main Checking",
                "type": "checking",
                "currency": "EUR",
                "is_active": True,
                "current_balance": 1500.00,
            }
        }
    )

    id: int = Field(..., description="Unique account identifier.")
    name: str = Field(..., description="Account display name.")
    type: str = Field(..., description="Account type (e.g. 'checking', 'savings', 'investment').")
    currency: str = Field(..., description="ISO 4217 currency code.")
    is_active: bool = Field(..., description="Whether the account is active.")
    current_balance: float = Field(..., description="Current balance of the account.")


class AccountBalanceResponse(BaseModel):
    """Balance for a specific account."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"account_id": 1, "balance": 1500.00}}
    )

    account_id: int = Field(..., description="Account identifier.")
    balance: float = Field(..., description="Current balance computed from all linked transactions.")
