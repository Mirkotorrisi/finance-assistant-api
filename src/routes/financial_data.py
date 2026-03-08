"""Financial-data REST routes."""

from fastapi import APIRouter, Depends

from src.models.financial_data import FinancialDataResponse
from src.services.financial_data_service import FinancialDataService

router = APIRouter(prefix="/api/financial-data", tags=["financial-data"])


def get_financial_data_service():
    from src.database.init import get_db_session

    session = get_db_session()
    service = FinancialDataService(session=session)
    try:
        yield service
    finally:
        session.close()


@router.get(
    "/{year}",
    response_model=FinancialDataResponse,
    summary="Get yearly financial data",
    response_description="Aggregated financial data for the requested year",
)
async def get_financial_data(
    year: int,
    service: FinancialDataService = Depends(get_financial_data_service),
):
    """Return aggregated financial data for a specific calendar year."""
    return service.get_financial_data(year)
