"""Spending / income totals by category, blueprint group, account or month.

Everything here is a plain sum over the workspace's transactions: transfers between own accounts and
investments (see InvestmentService) are left out, and category names are mapped to the blueprint's keys so groups add up.
"""

import datetime
from collections import defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from src.blueprint import Blueprint
from src.database.models import Account, Transaction, Workspace
from src.services.coverage import coverage_totals
from src.services.investments import investment_texts, not_investment

GROUP_BYS = ("category", "group", "account", "month")


class SpendingReportService:
    def __init__(self, session: Session):
        self.session = session
        self.workspace_id: int = session.info["workspace_id"]

    def _blueprint(self) -> Blueprint:
        workspace = self.session.get(Workspace, self.workspace_id)
        return Blueprint.model_validate(workspace.blueprint)

    def report(
        self,
        start_date: str,
        end_date: str,
        group_by: str = "category",
        flow: str = "expense",
        account_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if group_by not in GROUP_BYS:
            raise ValueError(f"group_by must be one of {', '.join(GROUP_BYS)}")
        if flow not in ("expense", "income"):
            raise ValueError("flow must be 'expense' or 'income'")
        try:
            start = datetime.date.fromisoformat(start_date)
            end = datetime.date.fromisoformat(end_date)
        except ValueError:
            raise ValueError("Invalid date format. Use 'YYYY-MM-DD'")

        # the database groups by category, account, month and review state: the rows that come back are a few
        # dozen whatever the number of transactions, and the blueprint mapping below is done once per group
        year, month = extract("year", Transaction.date), extract("month", Transaction.date)
        query = (
            self.session.query(
                Transaction.category,
                Transaction.account_id,
                year,
                month,
                Transaction.reviewed,
                func.count(Transaction.id),
                func.sum(func.abs(Transaction.amount)),
            )
            .filter(
                Transaction.date >= start,
                Transaction.date <= end,
                Transaction.is_transfer.is_(False),
                not_investment(investment_texts(self.session)),  # securities are not spending or income
                Transaction.amount < 0 if flow == "expense" else Transaction.amount > 0,
            )
            .group_by(Transaction.category, Transaction.account_id, year, month, Transaction.reviewed)
        )
        if account_id is not None:
            query = query.filter(Transaction.account_id == account_id)
        rows = query.all()

        blueprint = self._blueprint()
        nodes = blueprint.nodes()
        accounts = {a.id: a.name for a in self.session.query(Account).all()}

        totals: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"amount": 0.0, "count": 0})
        grand_total = 0.0
        transaction_count = 0
        reviewed_amount = unreviewed_amount = 0.0
        reviewed_count = unreviewed_count = 0
        for category, row_account_id, row_year, row_month, reviewed, count, amount in rows:
            amount = float(amount or 0.0)
            grand_total += amount
            transaction_count += count
            if reviewed:
                reviewed_amount, reviewed_count = reviewed_amount + amount, reviewed_count + count
            else:
                unreviewed_amount, unreviewed_count = unreviewed_amount + amount, unreviewed_count + count
            key = blueprint.resolve_category(category)
            if group_by == "category":
                bucket = key or f"?{category}"
                label = nodes[key].label if key else category
                entries = [(bucket, label, {"category_key": key, "mapped": key is not None})]
            elif group_by == "group":
                group_keys = blueprint.groups_of(key) if key else []
                labels = {g.key: g.label for g in blueprint.groups}
                entries = [(g, labels[g], {}) for g in group_keys] or [("_ungrouped", "Senza gruppo", {})]
            elif group_by == "account":
                entries = [(str(row_account_id), accounts.get(row_account_id, "Senza conto"), {"account_id": row_account_id})]
            else:
                month_key = f"{int(row_year):04d}-{int(row_month):02d}"
                entries = [(month_key, month_key, {})]
            for bucket, label, extra in entries:
                slot = totals[bucket]
                slot["amount"] += amount
                slot["count"] += count
                slot.update({"key": bucket, "label": label, **extra})

        items: List[Dict[str, Any]] = sorted(totals.values(), key=lambda i: (-i["amount"], i["label"]))
        for item in items:
            item["amount"] = round(item["amount"], 2)
            item["share"] = round(item["amount"] / grand_total, 4) if grand_total else 0.0
        return {
            "workspace_id": self.workspace_id,
            "start_date": start_date,
            "end_date": end_date,
            "group_by": group_by,
            "flow": flow,
            "total": round(grand_total, 2),
            "transaction_count": transaction_count,
            # how much of this total rests on categories the user confirmed (the rest are suggestions)
            "coverage": coverage_totals(reviewed_amount, unreviewed_amount, reviewed_count, unreviewed_count),
            "items": items,
            # groups can overlap, so their amounts may add up to more than the total
            "note": "A category in several groups counts in each of them." if group_by == "group" else None,
        }


    def category_usage(self) -> List[Dict[str, Any]]:
        """Every category text found in the transactions, with the blueprint key it resolves to (None: not in it)."""
        blueprint = self._blueprint()
        rows = (
            self.session.query(Transaction.category, func.count(Transaction.id), func.sum(Transaction.amount))
            .filter(Transaction.is_transfer.is_(False))
            .group_by(Transaction.category)
            .all()
        )
        usage = [
            {
                "category": text,
                "key": blueprint.resolve_category(text),
                "transactions": count,
                "net_amount": round(total or 0.0, 2),
            }
            for text, count, total in rows
        ]
        return sorted(usage, key=lambda u: (u["key"] is not None, -u["transactions"], u["category"]))
