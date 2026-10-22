"""The review queue: unconfirmed categories grouped by merchant, so one answer settles many transactions."""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.blueprint import Blueprint
from src.database.models import Transaction, Workspace
from src.services.coverage import coverage_of
from src.services.merchant import UNKNOWN, merchant_key as compute_merchant_key
from src.services.merchant_rule_service import MerchantRuleService


class ReviewError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ReviewService:
    def __init__(self, session: Session):
        self.session = session
        self.workspace_id: int = session.info["workspace_id"]

    def _blueprint(self) -> Optional[Blueprint]:
        workspace = self.session.get(Workspace, self.workspace_id)
        try:
            return Blueprint.model_validate(workspace.blueprint) if workspace else None
        except ValueError:
            return None

    def _unreviewed(self) -> List[Transaction]:
        return (
            self.session.query(Transaction)
            .filter(Transaction.reviewed.is_(False), Transaction.is_transfer.is_(False))
            .all()
        )

    @staticmethod
    def _key_of(t: Transaction) -> str:
        return t.merchant_key or compute_merchant_key(t.description)

    # ------------------------------------------------------------------ queue

    def queue(self, limit: int = 50) -> Dict[str, Any]:
        blueprint = self._blueprint()
        nodes = blueprint.nodes() if blueprint else {}
        groups: Dict[str, List[Transaction]] = defaultdict(list)
        for t in self._unreviewed():
            groups[self._key_of(t)].append(t)

        out: List[Dict[str, Any]] = []
        for key, members in groups.items():
            by_category = Counter(t.category for t in members)
            top_text, top_count = by_category.most_common(1)[0]
            resolved = blueprint.resolve_category(top_text) if blueprint else None
            confidences = [t.confidence for t in members if t.confidence is not None and t.category == top_text]
            sources = Counter(t.category_source for t in members if t.category == top_text)
            descriptions = list(dict.fromkeys(t.description for t in members))
            out.append({
                "merchant_key": key,
                "transactions": len(members),
                "net_amount": round(sum(t.amount for t in members), 2),
                "total_amount": round(sum(abs(t.amount) for t in members), 2),
                "descriptions": descriptions[:3],
                "transaction_ids": [t.id for t in members][:50],
                "suggestion": {
                    "category": top_text,
                    "key": resolved,
                    "label": nodes[resolved].label if resolved else None,
                    "transactions": top_count,
                    "confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
                    "source": sources.most_common(1)[0][0],
                },
                "mixed": len(by_category) > 1,  # the merchant's transactions were given different categories
            })
        out.sort(key=lambda g: -g["total_amount"])  # the biggest amounts first: they move the totals most
        return {
            "total_groups": len(out),
            "unreviewed_transactions": sum(g["transactions"] for g in out),
            "groups": out[:limit],
            "coverage": self.coverage(),
        }

    # ------------------------------------------------------------------ decisions

    def _category_key(self, category: str) -> str:
        blueprint = self._blueprint()
        if blueprint is None or not blueprint.categories:
            return category  # a project without a blueprint accepts any name
        key = blueprint.resolve_category(category)
        if key is None:
            raise ReviewError(422, f"{category!r} is not a category of this project's blueprint")
        if blueprint.nodes()[key].children:
            raise ReviewError(422, f"{category!r} has subcategories: choose one of them")
        return key

    def confirm(self, merchant_key: str, category: str, create_rule: bool = True) -> Dict[str, Any]:
        """Give every unconfirmed transaction of a merchant this category, and remember it for next time."""
        key = self._category_key(category)
        rows = [t for t in self._unreviewed() if self._key_of(t) == merchant_key]
        for t in rows:
            t.category, t.category_source, t.reviewed, t.confidence = key, "user", True, None
        self.session.commit()
        rule_created = False
        if create_rule and merchant_key != UNKNOWN:
            MerchantRuleService(self.session).create_rule(merchant_key, key)
            rule_created = True
        return {"merchant_key": merchant_key, "category": key, "transactions_updated": len(rows), "rule_created": rule_created}

    def accept(
        self,
        merchant_key: Optional[str] = None,
        transaction_ids: Optional[List[int]] = None,
        all_unreviewed: bool = False,
        create_rule: bool = False,
    ) -> Dict[str, Any]:
        """Confirm the categories as they are (the suggestion was right)."""
        if not (merchant_key or transaction_ids or all_unreviewed):
            raise ReviewError(422, "Say what to accept: a merchant_key, transaction_ids, or all_unreviewed")
        rows = self._unreviewed()
        if merchant_key:
            rows = [t for t in rows if self._key_of(t) == merchant_key]
        if transaction_ids:
            wanted = set(transaction_ids)
            rows = [t for t in rows if t.id in wanted]
        rule_created = False
        if create_rule and merchant_key and merchant_key != UNKNOWN and rows:
            top = Counter(t.category for t in rows).most_common(1)[0][0]
            MerchantRuleService(self.session).create_rule(merchant_key, self._category_key(top))
            rule_created = True
        for t in rows:
            t.category_source, t.reviewed = "user", True
        self.session.commit()
        return {"transactions_accepted": len(rows), "rule_created": rule_created}

    # ------------------------------------------------------------------ coverage

    def coverage(self, flow: str = "expense") -> Dict[str, Any]:
        rows = self.session.query(Transaction).filter(
            Transaction.is_transfer.is_(False),
            Transaction.amount < 0 if flow == "expense" else Transaction.amount > 0,
        ).all()
        return coverage_of(rows)
