"""Financial-summary REST routes."""

from fastapi import APIRouter, Depends, HTTPException

from src.models.financial_summary import (
    AccountBreakdownDetailResponse,
    MonthlySummaryResponse,
    SpendingDistributionResponse,
)
from src.services.financial_summary_service import FinancialSummaryService

router = APIRouter(prefix="/api/financial-summary", tags=["financial-summary"])


def get_financial_summary_service():
    from src.database.init import get_db_session

    session = get_db_session()
    service = FinancialSummaryService(session=session)
    try:
        yield service
    finally:
        session.close()


@router.get(
    "/monthly/{month}",
    response_model=MonthlySummaryResponse,
    summary="Monthly financial summary",
    response_description="Income, expenses, net, and top categories for the month",
)
async def get_monthly_summary(
    month: str,
    service: FinancialSummaryService = Depends(get_financial_summary_service),
):
    """Return a financial summary for a specific month in YYYY-MM format."""
    try:
        return service.get_monthly_summary(month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/spending-distribution",
    response_model=SpendingDistributionResponse,
    summary="Spending distribution",
    response_description="Spending breakdown by category or account for the given period",
)
async def get_spending_distribution(
    start_date: str,
    end_date: str,
    group_by: str = "category",
    service: FinancialSummaryService = Depends(get_financial_summary_service),
):
    """Return a spending distribution breakdown for a date range."""
    try:
        return service.get_spending_distribution(start_date, end_date, group_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/account-breakdown",
    response_model=AccountBreakdownDetailResponse,
    summary="Account breakdown",
    response_description="Current balances grouped by asset type",
)
async def get_account_breakdown(
    service: FinancialSummaryService = Depends(get_financial_summary_service),
):
    """Return the current balance breakdown across all active accounts."""
    return service.get_account_breakdown()
