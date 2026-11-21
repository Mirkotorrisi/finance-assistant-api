"""Pydantic models for the client profile and the advisor endpoints."""

from datetime import date as Date
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProfilePatch(BaseModel):
    """A partial update: only the fields given change (nested dicts merge, goals/debts upsert by key)."""

    patch: dict[str, Any] = Field(..., description="Subset of the profile document.")
    source: Literal["user", "agent"] = Field(default="agent", description="Who decided these facts.")


class ProfileResponse(BaseModel):
    workspace_id: int
    version: int
    updated_by: str
    updated_at: str | None = None
    profile: dict[str, Any]
    completeness: dict[str, bool]
    ips_status: Literal["none", "pending", "approved"]
    ips_approved_at: str | None = None


class DecisionCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    rationale: str = Field(..., min_length=10, max_length=4000, description="Why, in plain words, with the numbers.")
    data_refs: list[str] = Field(..., min_length=1, description="The figures used: tool or page, period, amount.")
    ips_refs: list[str] = Field(default_factory=list, description="The IPS points this follows (empty if there is no IPS yet).")
    date: Date | None = Field(default=None, description="Defaults to today.")
    status: Literal["proposed", "accepted", "rejected", "done"] = "proposed"


class DecisionUpdate(BaseModel):
    status: Literal["proposed", "accepted", "rejected", "done"] | None = None
    outcome: str | None = Field(default=None, max_length=4000, description="What happened, once known.")
    title: str | None = Field(default=None, min_length=3, max_length=200)
    rationale: str | None = Field(default=None, min_length=10, max_length=4000)
