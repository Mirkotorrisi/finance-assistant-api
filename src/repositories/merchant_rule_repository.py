from typing import List, Optional
from sqlalchemy.orm import Session
from src.database.models import MerchantRule


class MerchantRuleRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> List[MerchantRule]:
        return self.session.query(MerchantRule).order_by(MerchantRule.pattern).all()

    def get_by_id(self, rule_id: int) -> Optional[MerchantRule]:
        return self.session.query(MerchantRule).filter(MerchantRule.id == rule_id).first()

    def get_by_pattern(self, pattern: str) -> Optional[MerchantRule]:
        return (
            self.session.query(MerchantRule)
            .filter(MerchantRule.pattern == pattern.lower())
            .first()
        )

    def create(self, pattern: str, category: str) -> MerchantRule:
        rule = MerchantRule(pattern=pattern.lower(), category=category.lower())
        self.session.add(rule)
        self.session.commit()
        self.session.refresh(rule)
        return rule

    def update_category(self, rule: MerchantRule, category: str) -> MerchantRule:
        rule.category = category.lower()
        self.session.commit()
        self.session.refresh(rule)
        return rule

    def delete(self, rule: MerchantRule) -> None:
        self.session.delete(rule)
        self.session.commit()
