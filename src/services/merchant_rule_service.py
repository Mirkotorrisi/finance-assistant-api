from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from src.repositories.merchant_rule_repository import MerchantRuleRepository
from src.repositories.transaction_repository import TransactionRepository
from src.services.transaction_service import TransactionService


class MerchantRuleService:
    def __init__(self, session: Session):
        self.session = session
        self.rule_repo = MerchantRuleRepository(session)
        self.tx_repo = TransactionRepository(session)
        self.tx_service = TransactionService(session)

    def list_rules(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self.rule_repo.list()]

    def create_rule(self, pattern: str, category: str) -> Dict[str, Any]:
        existing = self.rule_repo.get_by_pattern(pattern)
        if existing:
            updated = self.rule_repo.update_category(existing, category)
            return updated.to_dict()
        rule = self.rule_repo.create(pattern, category)
        return rule.to_dict()

    def delete_rule(self, rule_id: int) -> bool:
        rule = self.rule_repo.get_by_id(rule_id)
        if not rule:
            return False
        self.rule_repo.delete(rule)
        return True

    def recategorize(self, pattern: str, category: str) -> Dict[str, Any]:
        """Save rule + bulk-update all matching transactions."""
        self.tx_service._ensure_category_exists(category)
        rule = self.create_rule(pattern, category)
        updated_count = self.tx_repo.update_category_by_pattern(pattern, category)
        return {"rule": rule, "transactions_updated": updated_count}

    def apply_all_rules(self) -> int:
        """Apply every saved rule to existing transactions. Returns total rows updated."""
        total = 0
        for rule in self.rule_repo.list():
            total += self.tx_repo.update_category_by_pattern(rule.pattern, rule.category)
        return total

    def get_rules_as_list(self) -> List[Dict[str, str]]:
        """Return rules in lightweight format for use by the parser pre-check."""
        return [{"pattern": r.pattern, "category": r.category} for r in self.rule_repo.list()]
