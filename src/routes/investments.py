"""Investments: portfolio positions and the realised result, read from the statements."""

from fastapi import APIRouter, Depends

from src.routes.deps import resolve_workspace_id
from src.services.investments import InvestmentService

router = APIRouter(prefix="/api/investments", tags=["investments"])


def get_investment_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    try:
        yield InvestmentService(session)
    finally:
        session.close()


@router.get("", summary="Portfolio and realised result")
async def portfolio(service: InvestmentService = Depends(get_investment_service)):
    """Every instrument bought, sold or paid out in the blueprint's ``investment`` categories: amount invested,
    proceeds, dividends, quantity held and the realised gain or loss (average cost; ``null`` when a sale has no
    quantity to price it). There are no market prices, so unrealised gains are not included."""
    return service.portfolio()
