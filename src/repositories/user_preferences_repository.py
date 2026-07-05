from typing import Optional
from sqlalchemy.orm import Session
from src.database.models import UserPreferences

ALLOWED_FIELDS = {
    "focus_categories",
    "custom_categories",
    "budget_amount",
    "budget_period",
    "notes",
}


class UserPreferencesRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_user_id(self, user_id: str) -> Optional[UserPreferences]:
        return self.session.query(UserPreferences).filter(
            UserPreferences.user_id == user_id
        ).first()

    def get_or_create(self, user_id: str) -> UserPreferences:
        existing = self.get_by_user_id(user_id)
        if existing:
            return existing

        preferences = UserPreferences(
            user_id=user_id,
            onboarding_completed=False,
            focus_categories=[],
            custom_categories=[],
        )
        self.session.add(preferences)
        self.session.commit()
        self.session.refresh(preferences)
        return preferences

    def update(self, user_id: str, updates: dict) -> UserPreferences:
        preferences = self.get_or_create(user_id)

        for key, value in updates.items():
            if key in ALLOWED_FIELDS and value is not None:
                setattr(preferences, key, value)

        self.session.commit()
        self.session.refresh(preferences)
        return preferences

    def mark_onboarding_completed(self, user_id: str) -> UserPreferences:
        preferences = self.get_or_create(user_id)
        preferences.onboarding_completed = True
        self.session.commit()
        self.session.refresh(preferences)
        return preferences
