"""Pydantic models for the per-user onboarding preferences endpoints."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserPreferencesUpdate(BaseModel):
    """Partial update payload. All fields are optional and merged with the existing record."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "focus_categories": ["groceries", "transport"],
                "custom_categories": ["takeaway", "subscriptions"],
                "budget_amount": 1500.0,
                "budget_period": "monthly",
                "notes": "Vuole ridurre le spese di ristorazione.",
            }
        }
    )

    focus_categories: Optional[List[str]] = Field(default=None, description="Categorie su cui l'utente vuole focus nei report.")
    custom_categories: Optional[List[str]] = Field(default=None, description="Categorie che l'utente ha già in mente.")
    budget_amount: Optional[float] = Field(default=None, description="Budget target dell'utente.")
    budget_period: Optional[str] = Field(default=None, description="Periodo del budget (es. 'monthly').")
    notes: Optional[str] = Field(default=None, description="Contesto libero raccolto durante l'onboarding.")


class UserPreferencesResponse(BaseModel):
    """Representation of a user's preferences record returned by the API."""

    user_id: str = Field(..., description="Identificatore client-side dell'utente.")
    onboarding_completed: bool = Field(..., description="Se l'onboarding è stato confermato dall'utente.")
    focus_categories: List[str] = Field(default_factory=list)
    custom_categories: List[str] = Field(default_factory=list)
    budget_amount: Optional[float] = None
    budget_period: str = "monthly"
    notes: Optional[str] = None
