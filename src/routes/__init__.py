"""API route modules."""

from src.routes.accounts import router as accounts_router
from src.routes.financial_data import router as financial_data_router
from src.routes.financial_summary import router as financial_summary_router
from src.routes.health import router as health_router
from src.routes.transactions import router as transactions_router

__all__ = [
    "health_router",
    "transactions_router",
    "accounts_router",
    "financial_data_router",
    "financial_summary_router",
]
