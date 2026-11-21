"""The client profile document.

A profile is the advisor's memory of the person: their situation (income, debts, emergency fund, home, family,
pension), their goals, their attitude to risk and the Investment Policy Statement (IPS) they agreed to. It lives
in the database, versioned, next to the workspace's blueprint; the model never keeps it in its own memory.

Facts the agent collects in the interview are written with ``merge_profile`` (partial updates: dictionaries merge,
lists of keyed items are upserted by ``key``, other lists are replaced). The IPS is a commitment: the API records
its approval separately (hash of the approved policy), so a rewritten policy is "pending" until the user approves
it again from the app. Nothing in this document can mark itself approved.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = 1
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
ASSET_CLASSES = ("equity", "bonds", "cash", "real_estate", "commodities", "crypto", "other")
MAX_GOALS = 30
MAX_DEBTS = 30
MAX_TEXT = 2000


def _check_key(value: str, what: str) -> str:
    if not KEY_RE.match(value):
        raise ValueError(f"{what} key {value!r} must be lowercase letters, digits or underscores (max 64)")
    return value


class Income(BaseModel):
    net_monthly: float | None = Field(default=None, ge=0, description="Net income per month, EUR.")
    kind: Literal["employee", "self_employed", "mixed", "retired", "student", "other"] = "employee"
    stability: Literal["stable", "variable", "uncertain"] = "stable"
    months_per_year: int = Field(default=12, ge=12, le=15, description="13 or 14 when extra salaries are paid.")
    notes: str = Field(default="", max_length=MAX_TEXT)


class EmergencyFund(BaseModel):
    target_months: float = Field(default=6, ge=0, le=24, description="Months of expenses the fund should cover.")
    amount: float | None = Field(default=None, ge=0, description="What is set aside today, as the user states it.")
    account_ids: list[int] = Field(default_factory=list, description="Accounts that hold it (the app can read them).")
    notes: str = Field(default="", max_length=MAX_TEXT)


class Debt(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["mortgage", "personal_loan", "car_loan", "credit_card", "student_loan", "family", "other"] = "other"
    balance: float | None = Field(default=None, ge=0, description="Outstanding amount.")
    annual_rate: float | None = Field(default=None, ge=0, le=100, description="Interest rate, percent per year.")
    monthly_payment: float | None = Field(default=None, ge=0)
    end_date: date | None = None
    notes: str = Field(default="", max_length=MAX_TEXT)

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return _check_key(v, "debt")


class Housing(BaseModel):
    status: Literal["own_outright", "own_mortgage", "rent", "family", "other", "unknown"] = "unknown"
    monthly_cost: float | None = Field(default=None, ge=0, description="Rent or mortgage payment.")
    notes: str = Field(default="", max_length=MAX_TEXT)


class Household(BaseModel):
    adults: int = Field(default=1, ge=1, le=10)
    dependents: int = Field(default=0, ge=0, le=20)
    shared_finances: bool = Field(default=False, description="Money is pooled with a partner (joint accounts).")
    notes: str = Field(default="", max_length=MAX_TEXT)


class Pension(BaseModel):
    tfr: Literal["company", "pension_fund", "not_applicable", "unknown"] = "unknown"
    fund_name: str = Field(default="", max_length=200)
    line: str = Field(default="", max_length=120, description="The fund's investment line (e.g. 'bilanciata').")
    annual_contribution: float | None = Field(default=None, ge=0, description="The user's own yearly payments.")
    employer_contribution: float | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=MAX_TEXT)


class Situation(BaseModel):
    income: Income = Field(default_factory=Income)
    expenses_monthly: float | None = Field(
        default=None, ge=0, description="Average monthly spending as the user states it; the app computes its own."
    )
    emergency_fund: EmergencyFund = Field(default_factory=EmergencyFund)
    debts: list[Debt] = Field(default_factory=list)
    housing: Housing = Field(default_factory=Housing)
    household: Household = Field(default_factory=Household)
    pension: Pension = Field(default_factory=Pension)
    notes: str = Field(default="", max_length=MAX_TEXT)

    @field_validator("debts")
    @classmethod
    def _unique_debts(cls, debts: list[Debt]) -> list[Debt]:
        if len(debts) > MAX_DEBTS:
            raise ValueError(f"too many debts (max {MAX_DEBTS})")
        keys = [d.key for d in debts]
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes:
            raise ValueError(f"duplicate debt key(s): {', '.join(sorted(dupes))}")
        return debts


class Goal(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=120)
    amount: float | None = Field(default=None, ge=0, description="Target amount, EUR.")
    target_date: date | None = Field(default=None, description="When the money is needed.")
    horizon_years: float | None = Field(default=None, ge=0, le=80, description="Alternative to target_date.")
    priority: int = Field(default=3, ge=1, le=5, description="1 = most important.")
    funding_account_ids: list[int] = Field(default_factory=list, description="Accounts saving towards it.")
    status: Literal["active", "reached", "dropped"] = "active"
    notes: str = Field(default="", max_length=MAX_TEXT)

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return _check_key(v, "goal")


class Risk(BaseModel):
    tolerance: int | None = Field(default=None, ge=1, le=5, description="Willingness to bear losses, 1 low - 5 high.")
    tolerance_reason: str = Field(default="", max_length=MAX_TEXT)
    capacity: int | None = Field(
        default=None, ge=1, le=5, description="Ability to bear losses given horizon, income stability and reserves."
    )
    capacity_reason: str = Field(default="", max_length=MAX_TEXT)
    experience: Literal["none", "basic", "intermediate", "advanced", "unknown"] = "unknown"
    drawdown_reaction: Literal["sell", "hold", "buy_more", "unknown"] = Field(
        default="unknown", description="What they say they would do after a 30% fall."
    )
    notes: str = Field(default="", max_length=MAX_TEXT)


class AllocationTarget(BaseModel):
    asset_class: Literal["equity", "bonds", "cash", "real_estate", "commodities", "crypto", "other"]
    weight: float = Field(ge=0, le=100, description="Percent of the investable portfolio.")
    band: float = Field(default=5, ge=0, le=50, description="Rebalance when the actual weight drifts more than this.")
    notes: str = Field(default="", max_length=500, description="e.g. 'global equity ETF, accumulating'.")


class InvestmentPolicy(BaseModel):
    """The Investment Policy Statement: the rules, agreed in advance, that every recommendation is checked against."""

    objective: str = Field(default="", max_length=MAX_TEXT, description="What the portfolio is for, in the user's words.")
    horizon_years: float | None = Field(default=None, ge=0, le=80)
    target_allocation: list[AllocationTarget] = Field(default_factory=list)
    rebalance_rule: str = Field(default="", max_length=MAX_TEXT, description="When and how to rebalance.")
    contribution_plan: str = Field(default="", max_length=MAX_TEXT, description="How much goes in, how often, where.")
    constraints: list[str] = Field(default_factory=list, description="Things not to do (no single stocks, no leverage...).")
    review_cadence: Literal["monthly", "quarterly", "semiannual", "annual"] = "quarterly"
    notes: str = Field(default="", max_length=MAX_TEXT)

    @field_validator("constraints")
    @classmethod
    def _constraints(cls, items: list[str]) -> list[str]:
        cleaned = [c.strip() for c in items if c and c.strip()]
        if any(len(c) > 300 for c in cleaned):
            raise ValueError("each constraint must be at most 300 characters")
        return cleaned

    @model_validator(mode="after")
    def _weights(self) -> InvestmentPolicy:
        classes = [t.asset_class for t in self.target_allocation]
        dupes = {c for c in classes if classes.count(c) > 1}
        if dupes:
            raise ValueError(f"asset class listed twice in target_allocation: {', '.join(sorted(dupes))}")
        if self.target_allocation:
            total = sum(t.weight for t in self.target_allocation)
            if abs(total - 100) > 0.5:
                raise ValueError(f"target_allocation weights must add up to 100 (got {total:g})")
        return self

    def is_empty(self) -> bool:
        return not (self.objective or self.target_allocation or self.rebalance_rule or self.contribution_plan or self.constraints)

    def fingerprint(self) -> str:
        """Stable hash of the policy's content; the approval is bound to it."""
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ClientProfile(BaseModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    situation: Situation = Field(default_factory=Situation)
    goals: list[Goal] = Field(default_factory=list)
    risk: Risk = Field(default_factory=Risk)
    ips: InvestmentPolicy = Field(default_factory=InvestmentPolicy)
    notes: str = Field(
        default="", max_length=4000, description="Anything else the advisor should remember, in the user's words."
    )

    @field_validator("goals")
    @classmethod
    def _unique_goals(cls, goals: list[Goal]) -> list[Goal]:
        if len(goals) > MAX_GOALS:
            raise ValueError(f"too many goals (max {MAX_GOALS})")
        keys = [g.key for g in goals]
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes:
            raise ValueError(f"duplicate goal key(s): {', '.join(sorted(dupes))}")
        return goals

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def completeness(self) -> dict[str, bool]:
        """Which blocks of the interview are filled in: drives the discovery conversation."""
        s = self.situation
        return {
            "income": s.income.net_monthly is not None,
            "expenses": s.expenses_monthly is not None,
            "emergency_fund": s.emergency_fund.amount is not None,
            "debts": bool(s.debts) or "nessun debito" in s.notes.lower() or "no debts" in s.notes.lower(),
            "housing": s.housing.status != "unknown",
            "pension": s.pension.tfr != "unknown",
            "goals": bool(self.goals),
            "risk": self.risk.tolerance is not None and self.risk.capacity is not None,
            "ips": not self.ips.is_empty(),
        }


# ----------------------------------------------------------------------------- partial updates


def _merge(current: Any, update: Any) -> Any:
    if isinstance(current, dict) and isinstance(update, dict):
        out = dict(current)
        for k, v in update.items():
            out[k] = _merge(current.get(k), v) if k in current else v
        return out
    if isinstance(current, list) and isinstance(update, list):
        keyed = all(isinstance(i, dict) and "key" in i for i in current + update)
        if keyed and current:
            by_key = {i["key"]: i for i in current}
            for item in update:
                by_key[item["key"]] = _merge(by_key[item["key"]], item) if item["key"] in by_key else item
            return list(by_key.values())
        return update
    return update


def merge_profile(current: ClientProfile, patch: dict[str, Any]) -> ClientProfile:
    """``current`` with ``patch`` applied: nested dicts merge, keyed lists (goals, debts, target_allocation is
    keyed by asset_class and therefore replaced whole) upsert by ``key``, scalars and other lists are replaced.
    The result is validated like a full document."""
    merged = _merge(current.to_json(), patch)
    merged["schema_version"] = SCHEMA_VERSION
    return ClientProfile.model_validate(merged)
