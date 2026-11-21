"""The advisor's review: the profile and the IPS set next to what the data says, in one call.

Nothing here is advice. It gathers the figures an advisor needs (net worth, cash flow of the last months, the
investments, the emergency fund against the target, debts, the policy's approval) and lists the checks that fail,
each with the numbers behind it, so that whatever the agent recommends can cite them.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from src.profile import ClientProfile
from src.services.investments import InvestmentService
from src.services.net_worth_service import NetWorthService
from src.services.profile_service import ProfileService
from src.services.spending_report_service import SpendingReportService

logger = logging.getLogger(__name__)

EXPENSIVE_DEBT_RATE = 5.0  # percent per year: above this, repaying beats most expected returns after tax
MIN_SAVING_RATE = 0.10


def _months_back(today: date, months: int) -> date:
    y, m = today.year, today.month - months + 1
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, 1)


class AdvisorService:
    def __init__(self, session: Session):
        self.session = session
        self.profiles = ProfileService(session)

    def review(self, months: int = 12, today: date | None = None) -> dict[str, Any]:
        today = today or date.today()
        months = max(1, min(months, 60))
        start = _months_back(today, months)
        end = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
        period = {"start_date": start.isoformat(), "end_date": end.isoformat(), "months": months}

        profile_response = self.profiles.get()
        profile = ClientProfile.model_validate(profile_response["profile"])

        reports = SpendingReportService(self.session)
        expenses = reports.report(start.isoformat(), end.isoformat(), "month", "expense")
        income = reports.report(start.isoformat(), end.isoformat(), "month", "income")
        cash_flow = self._cash_flow(expenses, income, months)

        net_worth = NetWorthService(self.session).net_worth(end_month=f"{today.year:04d}-{today.month:02d}")
        latest = net_worth.get("latest") or {}
        wealth = {
            "month": latest.get("month"),
            "liquid": latest.get("liquid"),
            "invested": latest.get("invested"),
            "total": latest.get("total"),
            "change_on_previous_month": net_worth.get("change"),
            "unreconciled_snapshots": net_worth.get("unreconciled_snapshots", 0),
            "accounts": net_worth.get("accounts", []),
            # a total of 0 with no account that has a figure means "unknown", not "nothing"
            "has_balances": any(c.get("balance") is not None for c in (latest.get("balances") or {}).values()),
        }

        investments = InvestmentService(self.session).portfolio()
        inv_totals = investments.get("totals", {})

        emergency = self._emergency_fund(profile, cash_flow, latest)
        debts = self._debts(profile)
        allocation = self._allocation(profile, latest)
        try:
            from src.services.portfolio_service import PortfolioService

            valued = PortfolioService(self.session).valued_positions(today)
            allocation["invested_by_asset_class"] = valued["allocation"]
            allocation["invested_value"] = valued["total_value"]
            allocation["unknown_positions"] = valued["unknown_positions"]
            if valued["total_value"]:
                allocation["note"] = (
                    "The invested part is split by asset class from the valued positions (last close, or cost where "
                    "no price exists); cash is the liquid balance of the accounts."
                )
        except Exception:  # noqa: BLE001 - the review must not fail because of the market data
            logger.exception("Advisor review: portfolio valuation unavailable")

        checks = self._checks(profile, profile_response, cash_flow, emergency, debts, expenses, wealth)
        open_decisions = self.profiles.list_decisions("proposed") + self.profiles.list_decisions("accepted")

        return {
            "as_of": today.isoformat(),
            "period": period,
            "profile": profile_response,
            "cash_flow": cash_flow,
            "net_worth": wealth,
            "investments": {
                "net_invested": inv_totals.get("net_invested"),
                "realized_result": inv_totals.get("realized_result"),
                "dividends": inv_totals.get("dividends"),
                "positions": len(investments.get("positions", [])),
                "unresolved_instruments": inv_totals.get("unresolved_instruments", 0),
                "note": investments.get("note"),
            },
            "emergency_fund": emergency,
            "debts": debts,
            "allocation": allocation,
            "checks": checks,
            "open_decisions": open_decisions,
            "note": (
                "Figures are sums of the stored transactions and recorded balances; coverage says how much of the "
                "spending rests on confirmed categories. Market values are the balances the user recorded for "
                "investment accounts: there are no market prices yet."
            ),
        }

    # ------------------------------------------------------------------ pieces

    @staticmethod
    def _cash_flow(expenses: dict[str, Any], income: dict[str, Any], months: int) -> dict[str, Any]:
        by_month: dict[str, dict[str, float]] = {}
        for item in expenses["items"]:
            by_month.setdefault(item["key"], {"income": 0.0, "expenses": 0.0})["expenses"] = item["amount"]
        for item in income["items"]:
            by_month.setdefault(item["key"], {"income": 0.0, "expenses": 0.0})["income"] = item["amount"]
        rows = [
            {"month": m, "income": v["income"], "expenses": v["expenses"], "saved": round(v["income"] - v["expenses"], 2)}
            for m, v in sorted(by_month.items())
        ]
        covered = len(rows)
        total_income, total_expenses = income["total"], expenses["total"]
        saving_rate = round((total_income - total_expenses) / total_income, 4) if total_income else None
        return {
            "months_requested": months,
            "months_with_data": covered,
            "income_total": total_income,
            "expenses_total": total_expenses,
            "saved_total": round(total_income - total_expenses, 2),
            "income_monthly_avg": round(total_income / covered, 2) if covered else None,
            "expenses_monthly_avg": round(total_expenses / covered, 2) if covered else None,
            "saving_rate": saving_rate,
            "expenses_coverage": expenses["coverage"],
            "by_month": rows,
        }

    @staticmethod
    def _emergency_fund(profile: ClientProfile, cash_flow: dict[str, Any], latest: dict[str, Any]) -> dict[str, Any]:
        fund = profile.situation.emergency_fund
        monthly = profile.situation.expenses_monthly or cash_flow.get("expenses_monthly_avg")
        amount = fund.amount
        basis = "reported"
        if fund.account_ids and latest.get("balances"):
            held = [latest["balances"].get(str(i), {}).get("balance") for i in fund.account_ids]
            known = [b for b in held if b is not None]
            if known:
                amount = round(sum(known), 2)
                basis = "accounts"
        months_covered = round(amount / monthly, 1) if amount is not None and monthly else None
        target_amount = round(fund.target_months * monthly, 2) if monthly else None
        return {
            "amount": amount,
            "basis": basis if amount is not None else "unknown",
            "monthly_expenses_used": monthly,
            "target_months": fund.target_months,
            "target_amount": target_amount,
            "months_covered": months_covered,
            "shortfall": round(max(target_amount - amount, 0), 2) if target_amount is not None and amount is not None else None,
        }

    @staticmethod
    def _debts(profile: ClientProfile) -> dict[str, Any]:
        debts = profile.situation.debts
        expensive = [d for d in debts if d.annual_rate is not None and d.annual_rate > EXPENSIVE_DEBT_RATE]
        return {
            "count": len(debts),
            "balance_total": round(sum(d.balance or 0 for d in debts), 2),
            "monthly_payments": round(sum(d.monthly_payment or 0 for d in debts), 2),
            "expensive_threshold_rate": EXPENSIVE_DEBT_RATE,
            "expensive": [
                {"key": d.key, "label": d.label, "balance": d.balance, "annual_rate": d.annual_rate} for d in expensive
            ],
        }

    @staticmethod
    def _allocation(profile: ClientProfile, latest: dict[str, Any]) -> dict[str, Any]:
        liquid, invested = latest.get("liquid"), latest.get("invested")
        total = (liquid or 0) + (invested or 0)
        current = (
            {"cash": round(100 * (liquid or 0) / total, 1), "invested": round(100 * (invested or 0) / total, 1)}
            if total
            else None
        )
        target_cash = next((t.weight for t in profile.ips.target_allocation if t.asset_class == "cash"), None)
        drift = None
        if current is not None and target_cash is not None:
            drift = round(current["cash"] - target_cash, 1)
        return {
            "current": current,
            "target": [t.model_dump(mode="json") for t in profile.ips.target_allocation],
            "cash_weight_drift": drift,
            "note": (
                "Only cash vs invested is known: the split of the invested part by asset class needs instrument "
                "prices, not available yet. Treat the cash weight as the one measurable drift."
            ),
        }

    @staticmethod
    def _checks(
        profile: ClientProfile,
        profile_response: dict[str, Any],
        cash_flow: dict[str, Any],
        emergency: dict[str, Any],
        debts: dict[str, Any],
        expenses: dict[str, Any],
        wealth: dict[str, Any],
    ) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []

        def add(key: str, severity: str, message: str, **data: Any) -> None:
            checks.append({"key": key, "severity": severity, "message": message, "data": data})

        missing = [k for k, ok in profile_response["completeness"].items() if not ok and k != "ips"]
        if missing:
            add("profile_incomplete", "info", "Some interview blocks are still empty", missing=missing)
        if profile_response["ips_status"] == "none":
            add("ips_missing", "warning", "There is no investment policy yet: propose one before any portfolio advice")
        elif profile_response["ips_status"] == "pending":
            add("ips_pending", "warning", "The investment policy changed since it was approved: ask the user to approve it")
        if cash_flow["months_with_data"] == 0:
            add("no_transactions", "warning", "No income or expenses in the period: import statements first")
        else:
            rate = cash_flow["saving_rate"]
            if rate is not None and rate < 0:
                add("negative_saving", "critical", "Spending exceeds income over the period", saving_rate=rate)
            elif rate is not None and rate < MIN_SAVING_RATE:
                add("low_saving_rate", "warning", "Saving rate is thin", saving_rate=rate, threshold=MIN_SAVING_RATE)
            cov = expenses["coverage"]
            share = cov.get("reviewed_share") if isinstance(cov, dict) else None
            if share is not None and share < 0.7:
                add("low_coverage", "info", "A large part of the spending rests on unconfirmed categories", reviewed_share=share)
        if emergency["amount"] is None:
            add("emergency_unknown", "warning", "The emergency fund is not known: ask where it is and how much")
        elif emergency["shortfall"]:
            add(
                "emergency_short",
                "critical",
                "The emergency fund is below target: fill it before investing more",
                months_covered=emergency["months_covered"],
                target_months=emergency["target_months"],
                shortfall=emergency["shortfall"],
            )
        if debts["expensive"]:
            add(
                "expensive_debt",
                "critical",
                "Debt above the threshold rate: repaying it beats most expected after-tax returns",
                debts=debts["expensive"],
                threshold_rate=debts["expensive_threshold_rate"],
            )
        if wealth.get("unreconciled_snapshots"):
            add("unreconciled", "info", "Some recorded balances do not match the transactions", count=wealth["unreconciled_snapshots"])
        if not wealth.get("has_balances"):
            add("no_balances", "info", "No recorded balances or transactions: net worth is unknown until the user records them")
        return checks
