"""Spending report routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from src.routes.deps import resolve_workspace_id
from src.services.spending_report_service import SpendingReportService

router = APIRouter(prefix="/api/reports", tags=["reports"])


def get_report_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    try:
        yield SpendingReportService(session)
    finally:
        session.close()


@router.get("/spending", summary="Spending (or income) totals")
async def spending_report(
    start_date: str,
    end_date: str,
    group_by: str = "category",
    flow: str = "expense",
    account_id: Optional[int] = None,
    service: SpendingReportService = Depends(get_report_service),
):
    """Totals grouped by category, blueprint group, account or month. Transfers between own accounts are excluded."""
    try:
        return service.report(start_date, end_date, group_by, flow, account_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
