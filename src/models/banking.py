"""Pydantic models for bank connections (PSD2 consents) and their account links."""

from datetime import date as Date
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.clock import to_naive_utc


class BankAccountIn(BaseModel):
    identification_hash: str = Field(..., max_length=512, description="The bank's stable identity of the account (an opaque token, can be long).")
    bank_uid: str | None = Field(default=None, max_length=64, description="Per-session handle used by the API calls.")
    iban_masked: str | None = Field(default=None, max_length=40, description="e.g. IT60 •••• 0123 (never the full IBAN).")
    label: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, max_length=3)
    cash_account_type: str | None = Field(default=None, max_length=8)


class BankConnectionCreate(BaseModel):
    provider: str = Field(default="enablebanking", max_length=32)
    aspsp_name: str = Field(..., max_length=120)
    aspsp_country: str = Field(..., min_length=2, max_length=2)
    psu_type: str = Field(default="personal", max_length=16)
    session_ref: str = Field(..., max_length=64, description="Key of the encrypted session in the gateway's store.")
    valid_until: datetime | None = None
    accounts: list[BankAccountIn] = Field(default_factory=list)
    renew_connection_id: int | None = Field(
        default=None, description="An existing connection to the same bank being renewed: keeps its account links."
    )

    @field_validator("valid_until")
    @classmethod
    def _naive_utc(cls, value: datetime | None) -> datetime | None:
        return to_naive_utc(value)  # the columns hold naive UTC; a zone-aware value would be shifted by the driver


class BankConnectionUpdate(BaseModel):
    status: Literal["active", "expired", "revoked", "error"] | None = None
    sync_balances: bool | None = None
    sync_transactions: bool | None = None
    last_sync_at: datetime | None = None
    last_sync_status: str | None = Field(default=None, max_length=16)
    last_error: str | None = None
    valid_until: datetime | None = None

    @field_validator("valid_until", "last_sync_at")
    @classmethod
    def _naive_utc(cls, value: datetime | None) -> datetime | None:
        return to_naive_utc(value)


class NewAccount(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    account_type: str = Field(default="checking", max_length=50)


class BankAccountLinkUpdate(BaseModel):
    account_id: int | None = Field(default=None, description="The app account this bank account feeds.")
    unlink: bool = Field(default=False, description="Detach from the app account.")
    create_account: NewAccount | None = Field(default=None, description="Create the app account and link it.")
    enabled: bool | None = None
    last_transaction_date: Date | None = None
    last_balance: float | None = None
    last_balance_date: Date | None = None
