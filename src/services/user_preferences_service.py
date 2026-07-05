from typing import Any, Dict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database.models import Category
from src.repositories.category_repository import CategoryRepository
from src.repositories.user_preferences_repository import UserPreferencesRepository


class UserPreferencesService:
    def __init__(self, session: Session):
        self.session = session
        self.preferences_repo = UserPreferencesRepository(session)
        self.category_repo = CategoryRepository(session)

    def get_preferences(self, user_id: str) -> Dict[str, Any]:
        preferences = self.preferences_repo.get_or_create(user_id)
        return preferences.to_dict()

    def update_preferences(self, user_id: str, updates: dict) -> Dict[str, Any]:
        updated = self.preferences_repo.update(user_id, updates)

        if updates.get("custom_categories"):
            for category_name in updates["custom_categories"]:
                self._ensure_category_exists(category_name)

        return updated.to_dict()

    def confirm_onboarding(self, user_id: str) -> Dict[str, Any]:
        preferences = self.preferences_repo.mark_onboarding_completed(user_id)
        for category_name in preferences.custom_categories or []:
            self._ensure_category_exists(category_name)
        return preferences.to_dict()

    def _ensure_category_exists(self, category_name: str) -> None:
        if not category_name:
            return
        existing = self.category_repo.get_by_name(category_name)
        if existing:
            return
        try:
            self.category_repo.create(Category(name=category_name.lower(), type="expense"))
        except IntegrityError:
            self.session.rollback()
