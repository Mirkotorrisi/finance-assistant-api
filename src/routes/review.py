"""Review queue routes: confirm categories by merchant."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.routes.deps import resolve_workspace_id
from src.services.review_service import ReviewError, ReviewService

router = APIRouter(prefix="/api/review", tags=["review"])


def get_review_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    try:
        yield ReviewService(session)
    finally:
        session.close()


class ConfirmRequest(BaseModel):
    merchant_key: str
    category: str = Field(..., description="A category of the project's blueprint (key, label or alias).")
    create_rule: bool = Field(default=True, description="Remember it: later imports of this merchant are categorized the same way.")


class AcceptRequest(BaseModel):
    merchant_key: Optional[str] = None
    transaction_ids: Optional[List[int]] = None
    all_unreviewed: bool = False
    create_rule: bool = False


def _guard(call):
    try:
        return call()
    except ReviewError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/queue", summary="Unconfirmed categories, grouped by merchant")
async def queue(limit: int = 50, service: ReviewService = Depends(get_review_service)):
    """Biggest amounts first. Each group carries the category currently assigned (the suggestion) and how sure it was."""
    return service.queue(limit)


@router.post("/confirm", summary="Set a merchant's category and remember it")
async def confirm(body: ConfirmRequest, service: ReviewService = Depends(get_review_service)):
    """Applies to every unconfirmed transaction of the merchant and, by default, saves a rule for the future."""
    return _guard(lambda: service.confirm(body.merchant_key, body.category, body.create_rule))


@router.post("/accept", summary="Confirm categories as they are")
async def accept(body: AcceptRequest, service: ReviewService = Depends(get_review_service)):
    """The suggestion was right: mark a merchant's (or the given) transactions as confirmed without changing them."""
    return _guard(lambda: service.accept(body.merchant_key, body.transaction_ids, body.all_unreviewed, body.create_rule))


@router.get("/coverage", summary="How much spending rests on confirmed categories")
async def coverage(flow: str = "expense", service: ReviewService = Depends(get_review_service)):
    return service.coverage(flow)
