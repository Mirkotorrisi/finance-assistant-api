"""Per-user onboarding preferences routes."""

from fastapi import APIRouter, Depends

from src.models.user_preferences import UserPreferencesResponse, UserPreferencesUpdate
from src.services.user_preferences_service import UserPreferencesService

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


def get_preferences_service():
    from src.database.init import get_db_session

    session = get_db_session()
    service = UserPreferencesService(session=session)
    try:
        yield service
    finally:
        session.close()


@router.get(
    "/{user_id}",
    response_model=UserPreferencesResponse,
    summary="Get a user's onboarding preferences",
    response_description="The user's preferences (auto-created if missing)",
)
async def get_preferences(
    user_id: str,
    service: UserPreferencesService = Depends(get_preferences_service),
):
    """Return the preferences record for user_id, creating an empty one if it doesn't exist yet."""
    return service.get_preferences(user_id)


@router.put(
    "/{user_id}",
    response_model=UserPreferencesResponse,
    summary="Partially update a user's onboarding preferences",
    response_description="The updated preferences",
)
async def update_preferences(
    user_id: str,
    updates: UserPreferencesUpdate,
    service: UserPreferencesService = Depends(get_preferences_service),
):
    """Merge the given fields into the user's preferences record."""
    return service.update_preferences(user_id, updates.model_dump(exclude_unset=True))


@router.post(
    "/{user_id}/confirm",
    response_model=UserPreferencesResponse,
    summary="Confirm onboarding for a user",
    response_description="The preferences marked as onboarding_completed",
)
async def confirm_preferences(
    user_id: str,
    service: UserPreferencesService = Depends(get_preferences_service),
):
    """Mark onboarding as completed for user_id, after the user reviews the draft in the UI."""
    return service.confirm_onboarding(user_id)
