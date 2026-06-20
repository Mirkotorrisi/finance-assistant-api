"""Merchant rule routes: pattern → category mappings for transaction categorization."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.services.merchant_rule_service import MerchantRuleService

router = APIRouter(prefix="/api/merchant-rules", tags=["merchant-rules"])


def get_service():
    from src.database.init import get_db_session

    session = get_db_session()
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


@router.post("/recategorize", response_model=Dict[str, Any])
async def recategorize(
    body: RecategorizeRequest,
    service: MerchantRuleService = Depends(get_service),
):
    """Save rule and bulk-update all matching transactions in one shot."""
    return service.recategorize(body.pattern, body.category)
