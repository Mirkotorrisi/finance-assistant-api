"""Merchant rule routes: pattern → category mappings for transaction categorization."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.routes.deps import resolve_workspace_id
from src.services.merchant_rule_service import MerchantRuleService

router = APIRouter(prefix="/api/merchant-rules", tags=["merchant-rules"])


def get_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    service = MerchantRuleService(session=session)
    try:
        yield service
    finally:
        session.close()


class MerchantRuleCreate(BaseModel):
    pattern: str
    category: str


class RecategorizeRequest(BaseModel):
    pattern: str
    category: str


@router.get("", response_model=List[Dict[str, Any]])
async def list_rules(service: MerchantRuleService = Depends(get_service)):
    """List all merchant alias rules."""
    return service.list_rules()


@router.post("", response_model=Dict[str, Any], status_code=201)
async def create_rule(
    body: MerchantRuleCreate,
    service: MerchantRuleService = Depends(get_service),
):
    """Create or update a merchant alias rule (does not touch existing transactions)."""
    return service.create_rule(body.pattern, body.category)


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: int,
    service: MerchantRuleService = Depends(get_service),
):
    """Delete a merchant alias rule by ID."""
    if not service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Rule deleted"}


class ResolveRequest(BaseModel):
    descriptions: List[str]


@router.post("/resolve", response_model=List[Dict[str, Any]])
async def resolve_merchants(body: ResolveRequest, service: MerchantRuleService = Depends(get_service)):
    """For each description: its normalised merchant key and the category of the most specific saved rule that
    matches it (null when none does). Rules come from confirmations in the review queue and from the blueprint."""
    return service.resolve(body.descriptions)


@router.post("/recategorize", response_model=Dict[str, Any])
async def recategorize(
    body: RecategorizeRequest,
    service: MerchantRuleService = Depends(get_service),
):
    """Save rule and bulk-update all matching transactions in one shot."""
    return service.recategorize(body.pattern, body.category)
