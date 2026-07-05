"""FastAPI application entry point for the finance assistant."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP
import uvicorn

from src.models import (
    AccountBalanceResponse,
    AccountBreakdownDetailResponse,
    AccountBreakdownResponse,
    AccountCreate,
    AccountItem,
    AccountResponse,
    AccountUpdate,
    BalanceResponse,
    DistributionItem,
    FinancialDataResponse,
    MonthlyDataResponse,
    MonthlySummaryResponse,
    SpendingDistributionResponse,
    TopCategoryItem,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
    TypeBreakdownItem,
)
from src.routes import (
    accounts_router,
    financial_data_router,
    financial_summary_router,
    health_router,
    merchant_rules_router,
    transactions_router,
    user_preferences_router,
)
from src.database.init import close_database, init_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Lifecycle events for the FastAPI application."""
    logger.info("Initializing database...")
    init_database()
    yield
    logger.info("Closing database...")
    close_database()


tags_metadata = [
    {
        "name": "health",
        "description": "Health check endpoint to verify the API is running.",
    },
    {
        "name": "transactions",
        "description": (
            "CRUD operations for financial transactions. "
            "Positive amounts represent income; negative amounts represent expenses."
        ),
    },
    {
        "name": "accounts",
        "description": (
            "CRUD operations for financial accounts such as checking, savings, "
            "investment, or retirement accounts."
        ),
    },
    {
        "name": "financial-data",
        "description": "Aggregated yearly financial data including net worth, savings, and monthly breakdowns.",
    },
    {
        "name": "financial-summary",
        "description": (
            "High-level aggregation endpoints used by UI components: monthly summaries, "
            "spending distribution, and account breakdowns."
        ),
    },
    {
        "name": "merchant-rules",
        "description": (
            "Merchant alias rules: map description patterns to a fixed category. "
            "Used to override LLM categorization for known merchants."
        ),
    },
    {
        "name": "preferences",
        "description": (
            "Per-user onboarding preferences: focus categories, custom categories, "
            "budget target. Keyed by a lightweight client-generated user_id (no auth system yet)."
        ),
    },
]

app = FastAPI(
    title="Finance Assistant API",
    description=(
        "A personal finance management API that provides CRUD operations for transactions "
        "and accounts, plus aggregated views such as monthly summaries, spending distribution, "
        "and account breakdowns.\n\n"
        "## Features\n"
        "- **Transactions** – create, read, update, and delete financial transactions\n"
        "- **Accounts** – manage checking, savings, investment, and retirement accounts\n"
        "- **Financial Data** – yearly aggregated net-worth and savings data\n"
        "- **Financial Summary** – monthly summaries, spending distribution, and account breakdown\n\n"
        "Interactive documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc)."
    ),
    version="2.0.0",
    contact={
        "name": "Finance Assistant",
        "url": "https://github.com/Mirkotorrisi/finance-assistant-api",
    },
    license_info={
        "name": "MIT",
    },
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(transactions_router)
app.include_router(accounts_router)
app.include_router(financial_data_router)
app.include_router(financial_summary_router)
app.include_router(merchant_rules_router)
app.include_router(user_preferences_router)

mcp = FastApiMCP(app)
mcp.mount_sse()

__all__ = [
    "app",
    "TransactionCreate",
    "TransactionUpdate",
    "TransactionResponse",
    "BalanceResponse",
    "AccountCreate",
    "AccountUpdate",
    "AccountResponse",
    "AccountBalanceResponse",
    "MonthlyDataResponse",
    "AccountBreakdownResponse",
    "FinancialDataResponse",
    "TopCategoryItem",
    "MonthlySummaryResponse",
    "DistributionItem",
    "SpendingDistributionResponse",
    "TypeBreakdownItem",
    "AccountItem",
    "AccountBreakdownDetailResponse",
]


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

