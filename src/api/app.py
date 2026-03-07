"""FastAPI application for the finance assistant."""

import logging
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from contextlib import asynccontextmanager



from src.services.transaction_service import TransactionService
from src.services.financial_data_service import FinancialDataService
from src.services.account_service import AccountService
from src.services.financial_summary_service import FinancialSummaryService
from src.database.init import init_database, close_database, get_db_session as _get_db_session

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for the FastAPI application."""
    # Startup
    logger.info("Initializing database...")
    init_database()
    yield
    # Shutdown
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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency to get TransactionService instance
def get_transaction_service():
    session = _get_db_session()
    service = TransactionService(session=session)
    try:
        yield service
    finally:
        session.close()

# Dependency to get FinancialDataService instance
def get_financial_data_service():
    session = _get_db_session()
    service = FinancialDataService(session=session)
    try:
        yield service
    finally:
        session.close()

# Dependency to get AccountService instance
def get_account_service():
    session = _get_db_session()
    service = AccountService(session=session)
    try:
        yield service
    finally:
        session.close()

# Dependency to get FinancialSummaryService instance
def get_financial_summary_service():
    session = _get_db_session()
    service = FinancialSummaryService(session=session)
    try:
        yield service
    finally:
        session.close()

# --- Pydantic Models ---

class TransactionCreate(BaseModel):
    """Payload for creating a new transaction."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": -45.50,
                "category": "groceries",
                "description": "Weekly supermarket shopping",
                "date": "2024-01-15",
                "currency": "EUR",
                "account_id": 1,
            }
        }
    )

    amount: float = Field(
        ...,
        description="Transaction amount. Use negative values for expenses and positive values for income.",
    )
    category: str = Field(..., description="Category name (e.g. 'groceries', 'salary').")
    description: str = Field(..., description="Human-readable description of the transaction.")
    date: Optional[str] = Field(
        default=None,
        description="ISO 8601 date string (YYYY-MM-DD). Defaults to today when omitted.",
    )
    currency: Optional[str] = Field(default="EUR", description="ISO 4217 currency code.")
    account_id: Optional[int] = Field(default=None, description="ID of the account this transaction belongs to.")


class TransactionUpdate(BaseModel):
    """Payload for partially updating an existing transaction. All fields are optional."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": -50.00,
                "category": "groceries",
                "description": "Updated supermarket bill",
                "date": "2024-01-16",
                "currency": "EUR",
                "account_id": 1,
            }
        }
    )

    amount: Optional[float] = Field(default=None, description="New transaction amount.")
    category: Optional[str] = Field(default=None, description="New category.")
    description: Optional[str] = Field(default=None, description="New description.")
    date: Optional[str] = Field(default=None, description="New date in YYYY-MM-DD format.")
    currency: Optional[str] = Field(default=None, description="New currency code.")
    account_id: Optional[int] = Field(default=None, description="New account ID.")


class TransactionResponse(BaseModel):
    """Representation of a transaction returned by the API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "date": "2024-01-15",
                "amount": -45.50,
                "category": "groceries",
                "description": "Weekly supermarket shopping",
                "currency": "EUR",
                "account_id": 1,
            }
        }
    )

    id: int = Field(..., description="Unique transaction identifier.")
    date: str = Field(..., description="Transaction date in ISO 8601 format (YYYY-MM-DD).")
    amount: float = Field(..., description="Transaction amount (negative = expense, positive = income).")
    category: str = Field(..., description="Category of the transaction.")
    description: str = Field(..., description="Description of the transaction.")
    currency: str = Field(..., description="ISO 4217 currency code.")
    account_id: Optional[int] = Field(default=None, description="Account ID associated with this transaction.")


class BalanceResponse(BaseModel):
    """Total balance computed from all transactions."""

    model_config = ConfigDict(json_schema_extra={"example": {"balance": 2350.75}})

    balance: float = Field(..., description="Current total balance across all transactions.")


# Account models
class AccountCreate(BaseModel):
    """Payload for creating a new account."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Main Checking",
                "account_type": "checking",
                "currency": "EUR",
                "is_active": True,
                "current_balance": 1500.00,
            }
        }
    )

    name: str = Field(..., description="Display name for the account.")
    account_type: str = Field(
        ...,
        description=(
            "Account type. Common values: 'checking', 'savings', 'cash', "
            "'investment', 'brokerage', 'retirement'."
        ),
    )
    currency: Optional[str] = Field(default="EUR", description="ISO 4217 currency code.")
    is_active: Optional[bool] = Field(default=True, description="Whether the account is active.")
    current_balance: Optional[float] = Field(default=0.0, description="Initial balance for the account.")


class AccountUpdate(BaseModel):
    """Payload for partially updating an existing account. All fields are optional."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Renamed Checking",
                "type": "savings",
                "is_active": True,
            }
        }
    )

    name: Optional[str] = Field(default=None, description="New account name.")
    type: Optional[str] = Field(default=None, description="New account type.")
    is_active: Optional[bool] = Field(default=None, description="Set account active/inactive.")


class AccountResponse(BaseModel):
    """Representation of an account returned by the API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Main Checking",
                "type": "checking",
                "currency": "EUR",
                "is_active": True,
                "current_balance": 1500.00,
            }
        }
    )

    id: int = Field(..., description="Unique account identifier.")
    name: str = Field(..., description="Account display name.")
    type: str = Field(..., description="Account type (e.g. 'checking', 'savings', 'investment').")
    currency: str = Field(..., description="ISO 4217 currency code.")
    is_active: bool = Field(..., description="Whether the account is active.")
    current_balance: float = Field(..., description="Current balance of the account.")


class AccountBalanceResponse(BaseModel):
    """Balance for a specific account."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"account_id": 1, "balance": 1500.00}}
    )

    account_id: int = Field(..., description="Account identifier.")
    balance: float = Field(..., description="Current balance computed from all linked transactions.")


# Financial data response models
class MonthlyDataResponse(BaseModel):
    """Aggregated financial data for a single month."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "month": "Jan",
                "netWorth": 25000.00,
                "expenses": 1200.50,
                "income": 3000.00,
                "net": 1799.50,
            }
        }
    )

    month: str = Field(..., description="Short month label (e.g. 'Jan', 'Feb').")
    netWorth: float = Field(..., description="Cumulative net worth at the end of the month.")
    expenses: float = Field(..., description="Total expenses for the month.")
    income: float = Field(..., description="Total income for the month.")
    net: float = Field(..., description="Net savings for the month (income minus expenses).")


class AccountBreakdownResponse(BaseModel):
    """High-level account breakdown by asset category."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "liquidity": 5000.00,
                "investments": 20000.00,
                "otherAssets": 500.00,
            }
        }
    )

    liquidity: float = Field(..., description="Total balance across liquid accounts (checking, savings, cash).")
    investments: float = Field(
        ..., description="Total balance across investment accounts (investment, brokerage, retirement)."
    )
    otherAssets: float = Field(..., description="Total balance across all other account types.")


class FinancialDataResponse(BaseModel):
    """Aggregated financial data for a full calendar year."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "year": 2024,
                "currentNetWorth": 25500.00,
                "netSavings": 5500.00,
                "monthlyData": [
                    {
                        "month": "Jan",
                        "netWorth": 20000.00,
                        "expenses": 1200.50,
                        "income": 3000.00,
                        "net": 1799.50,
                    }
                ],
                "accountBreakdown": {
                    "liquidity": 5000.00,
                    "investments": 20000.00,
                    "otherAssets": 500.00,
                },
            }
        }
    )

    year: int = Field(..., description="Calendar year for this dataset.")
    currentNetWorth: float = Field(..., description="Current total net worth across all accounts.")
    netSavings: float = Field(..., description="Total net savings accumulated during the year.")
    monthlyData: List[MonthlyDataResponse] = Field(
        ..., description="Month-by-month breakdown of income, expenses, and net worth."
    )
    accountBreakdown: AccountBreakdownResponse = Field(
        ..., description="Current balance split by asset category."
    )


# Financial summary models (UI-driven aggregation)
class TopCategoryItem(BaseModel):
    """A single spending category entry in a monthly summary."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"category": "groceries", "amount": 320.00, "count": 8}
        }
    )

    category: str = Field(..., description="Category name.")
    amount: float = Field(..., description="Total amount spent in this category.")
    count: int = Field(..., description="Number of transactions in this category.")


class MonthlySummaryResponse(BaseModel):
    """Monthly financial summary including income, expenses, and top spending categories."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "month": "2024-01",
                "income": 3000.00,
                "expenses": 1200.50,
                "net": 1799.50,
                "top_categories": [
                    {"category": "groceries", "amount": 320.00, "count": 8},
                    {"category": "transport", "amount": 180.00, "count": 5},
                ],
            }
        }
    )

    month: str = Field(..., description="Month in YYYY-MM format.")
    income: float = Field(..., description="Total income for the month.")
    expenses: float = Field(..., description="Total expenses for the month.")
    net: float = Field(..., description="Net amount (income minus expenses).")
    top_categories: List[TopCategoryItem] = Field(
        ..., description="Top 5 spending categories for the month."
    )


class DistributionItem(BaseModel):
    """A single item in a spending distribution breakdown."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "groceries",
                "amount": 320.00,
                "percent": 26.67,
                "count": 8,
            }
        }
    )

    name: str = Field(..., description="Category or account name.")
    amount: float = Field(..., description="Total spending amount for this item.")
    percent: float = Field(..., description="Percentage of total spending represented by this item.")
    count: int = Field(..., description="Number of transactions contributing to this item.")


class SpendingDistributionResponse(BaseModel):
    """Spending distribution breakdown for a date range grouped by category or account."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "group_by": "category",
                "total_amount": 1200.50,
                "distribution": [
                    {"name": "groceries", "amount": 320.00, "percent": 26.67, "count": 8},
                    {"name": "transport", "amount": 180.00, "percent": 15.00, "count": 5},
                ],
            }
        }
    )

    start_date: str = Field(..., description="Start date of the period (YYYY-MM-DD).")
    end_date: str = Field(..., description="End date of the period (YYYY-MM-DD).")
    group_by: str = Field(..., description="Grouping method used: 'category' or 'account'.")
    total_amount: float = Field(..., description="Total spending amount across all items.")
    distribution: List[DistributionItem] = Field(
        ..., description="Spending items sorted by amount descending."
    )


class TypeBreakdownItem(BaseModel):
    """Amount and percentage for a single account-type bucket."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"amount": 5000.00, "percent": 22.22}}
    )

    amount: float = Field(..., description="Total balance for this account type.")
    percent: float = Field(..., description="Percentage of total balance represented by this type.")


class AccountItem(BaseModel):
    """Individual account entry in an account breakdown response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "account_id": 1,
                "name": "Main Checking",
                "type": "checking",
                "category": "liquidity",
                "balance": 5000.00,
                "percent": 22.22,
                "currency": "EUR",
            }
        }
    )

    account_id: int = Field(..., description="Unique account identifier.")
    name: str = Field(..., description="Account display name.")
    type: str = Field(..., description="Raw account type (e.g. 'checking', 'retirement').")
    category: str = Field(
        ..., description="Asset category: 'liquidity', 'investments', or 'other'."
    )
    balance: float = Field(..., description="Current balance for this account.")
    percent: float = Field(..., description="Percentage of total balance represented by this account.")
    currency: str = Field(..., description="ISO 4217 currency code.")


class AccountBreakdownDetailResponse(BaseModel):
    """Detailed account breakdown grouped by asset type with individual account entries."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_balance": 22500.00,
                "by_type": {
                    "liquidity": {"amount": 5000.00, "percent": 22.22},
                    "investments": {"amount": 17000.00, "percent": 75.56},
                    "other": {"amount": 500.00, "percent": 2.22},
                },
                "accounts": [
                    {
                        "account_id": 2,
                        "name": "Retirement Fund",
                        "type": "retirement",
                        "category": "investments",
                        "balance": 17000.00,
                        "percent": 75.56,
                        "currency": "EUR",
                    },
                    {
                        "account_id": 1,
                        "name": "Main Checking",
                        "type": "checking",
                        "category": "liquidity",
                        "balance": 5000.00,
                        "percent": 22.22,
                        "currency": "EUR",
                    },
                ],
            }
        }
    )

    total_balance: float = Field(..., description="Total balance across all active accounts.")
    by_type: Dict[str, TypeBreakdownItem] = Field(
        ...,
        description="Breakdown by asset category. Keys are 'liquidity', 'investments', and 'other'.",
    )
    accounts: List[AccountItem] = Field(
        ..., description="Individual account entries sorted by balance descending."
    )

# --- Endpoints ---

@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    response_description="API health status",
)
async def health():
    """Return a simple status object confirming the API is running."""
    return {"status": "healthy"}

@app.get(
    "/api/transactions",
    response_model=List[TransactionResponse],
    tags=["transactions"],
    summary="List transactions",
    response_description="A list of transactions matching the given filters",
)
async def list_transactions(
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_id: Optional[int] = None,
    service: TransactionService = Depends(get_transaction_service)
):
    """Return a list of transactions, optionally filtered by category, date range, or account.

    - **category**: Filter by category name (case-insensitive exact match)
    - **start_date**: Include only transactions on or after this date (YYYY-MM-DD)
    - **end_date**: Include only transactions on or before this date (YYYY-MM-DD)
    - **account_id**: Filter by account ID
    """
    return service.list_transactions(category, start_date, end_date, account_id)

@app.post(
    "/api/transactions",
    response_model=TransactionResponse,
    status_code=201,
    tags=["transactions"],
    summary="Create a transaction",
    response_description="The newly created transaction",
)
async def create_transaction(
    transaction: TransactionCreate,
    service: TransactionService = Depends(get_transaction_service)
):
    """Create a single financial transaction.

    - Use **negative amounts** for expenses (e.g. `-45.50`)
    - Use **positive amounts** for income (e.g. `3000.00`)
    - `category` is created automatically if it does not yet exist
    - `account_id` must refer to an existing account when provided
    """
    try:
        return service.add_transaction(
            amount=transaction.amount,
            category=transaction.category,
            description=transaction.description,
            date=transaction.date,
            currency=transaction.currency,
            account_id=transaction.account_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post(
    "/api/transactions/bulk",
    response_model=List[TransactionResponse],
    status_code=201,
    tags=["transactions"],
    summary="Bulk-create transactions",
    response_description="List of newly created transactions",
)
async def create_transactions_bulk(
    transactions: List[TransactionCreate],
    service: TransactionService = Depends(get_transaction_service)
):
    """Create multiple transactions in a single request.

    Accepts an array of transaction objects and returns the full list of created
    transactions. Useful for importing historical data.
    """
    return service.add_transactions_bulk(
        [t.model_dump() for t in transactions]
    )

@app.put(
    "/api/transactions/{transaction_id}",
    response_model=TransactionResponse,
    tags=["transactions"],
    summary="Update a transaction",
    response_description="The updated transaction",
)
async def update_transaction(
    transaction_id: int,
    updates: TransactionUpdate,
    service: TransactionService = Depends(get_transaction_service)
):
    """Partially update a transaction identified by **transaction_id**.

    Only the fields included in the request body are updated; omitted fields
    remain unchanged.
    """
    updated = service.update_transaction(transaction_id, updates.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated

@app.delete(
    "/api/transactions/{transaction_id}",
    tags=["transactions"],
    summary="Delete a transaction",
    response_description="Confirmation message",
)
async def delete_transaction(
    transaction_id: int,
    service: TransactionService = Depends(get_transaction_service)
):
    """Permanently delete a transaction identified by **transaction_id**."""
    success = service.delete_transaction(transaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"message": "Transaction deleted successfully"}

@app.get(
    "/api/balance",
    response_model=BalanceResponse,
    tags=["transactions"],
    summary="Get total balance",
    response_description="Sum of all transaction amounts",
)
async def get_balance(service: TransactionService = Depends(get_transaction_service)):
    """Return the total balance calculated by summing every transaction amount.

    A positive result means net income; a negative result means net spending.
    """
    return {"balance": service.get_balance()}

@app.get(
    "/api/financial-data/{year}",
    response_model=FinancialDataResponse,
    tags=["financial-data"],
    summary="Get yearly financial data",
    response_description="Aggregated financial data for the requested year",
)
async def get_financial_data(
    year: int,
    service: FinancialDataService = Depends(get_financial_data_service)
):
    """Return aggregated financial data for a specific calendar **year**.

    The response includes:
    - **currentNetWorth** – total net worth at the time of the request
    - **netSavings** – net savings accumulated during the year
    - **monthlyData** – month-by-month breakdown (income, expenses, net worth)
    - **accountBreakdown** – current balances split by asset category
    """
    data = service.get_financial_data(year)
    return data

# --- Account Endpoints ---

@app.get(
    "/api/accounts",
    response_model=List[AccountResponse],
    tags=["accounts"],
    summary="List accounts",
    response_description="A list of accounts",
)
async def list_accounts(
    active_only: bool = True,
    service: AccountService = Depends(get_account_service)
):
    """Return all accounts, optionally limited to active ones.

    - **active_only** (default `true`) – when `true`, only accounts with `is_active=true` are returned
    """
    accounts = service.list_accounts(active_only=active_only)
    return accounts

@app.get(
    "/api/accounts/{account_id}",
    response_model=AccountResponse,
    tags=["accounts"],
    summary="Get an account",
    response_description="The requested account",
)
async def get_account(
    account_id: int,
    service: AccountService = Depends(get_account_service)
):
    """Return a single account identified by **account_id**."""
    account = service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account

@app.post(
    "/api/accounts",
    response_model=AccountResponse,
    status_code=201,
    tags=["accounts"],
    summary="Create an account",
    response_description="The newly created account",
)
async def create_account(
    account: AccountCreate,
    service: AccountService = Depends(get_account_service)
):
    """Create a new financial account.

    Supported **account_type** values:
    - Liquid: `checking`, `savings`, `cash`
    - Investments: `investment`, `brokerage`, `retirement`
    - Other: any other string (e.g. `credit`)
    """
    return service.create_account(
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        is_active=account.is_active,
        current_balance=account.current_balance
    )

@app.put(
    "/api/accounts/{account_id}",
    response_model=AccountResponse,
    tags=["accounts"],
    summary="Update an account",
    response_description="The updated account",
)
async def update_account(
    account_id: int,
    updates: AccountUpdate,
    service: AccountService = Depends(get_account_service)
):
    """Partially update an account identified by **account_id**.

    Only the fields supplied in the request body are modified.
    """
    updated = service.update_account(account_id, updates.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return updated

@app.delete(
    "/api/accounts/{account_id}",
    tags=["accounts"],
    summary="Delete (deactivate) an account",
    response_description="Confirmation message",
)
async def delete_account(
    account_id: int,
    service: AccountService = Depends(get_account_service)
):
    """Deactivate an account identified by **account_id**.

    The account is marked as inactive rather than hard-deleted so that its
    historical transactions remain intact.
    """
    success = service.delete_account(account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"message": "Account deleted successfully"}

@app.get(
    "/api/accounts/{account_id}/balance",
    response_model=AccountBalanceResponse,
    tags=["accounts"],
    summary="Get account balance",
    response_description="Current balance for the account",
)
async def get_account_balance(
    account_id: int,
    service: AccountService = Depends(get_account_service)
):
    """Return the current balance for a specific account.

    The balance is computed by summing all transactions linked to the account.
    """
    account = service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    balance = service.get_account_balance(account_id)
    return {"account_id": account_id, "balance": balance}

# --- Financial Summary Endpoints (UI-driven aggregation) ---

@app.get(
    "/api/summary/monthly/{month}",
    response_model=MonthlySummaryResponse,
    tags=["financial-summary"],
    summary="Monthly financial summary",
    response_description="Income, expenses, net, and top categories for the month",
)
async def get_monthly_summary(
    month: str,
    service: FinancialSummaryService = Depends(get_financial_summary_service)
):
    """Return a financial summary for a specific month.

    - **month**: Month in `YYYY-MM` format (e.g. `2024-01`)

    The response includes total income, total expenses, net amount, and the top 5
    spending categories for that month.
    """
    try:
        return service.get_monthly_summary(month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get(
    "/api/distribution/spending",
    response_model=SpendingDistributionResponse,
    tags=["financial-summary"],
    summary="Spending distribution",
    response_description="Spending breakdown by category or account for the given period",
)
async def get_spending_distribution(
    start_date: str,
    end_date: str,
    group_by: str = "category",
    service: FinancialSummaryService = Depends(get_financial_summary_service)
):
    """Return a spending distribution breakdown for a date range.

    - **start_date**: Start of the period in `YYYY-MM-DD` format
    - **end_date**: End of the period in `YYYY-MM-DD` format
    - **group_by**: Grouping dimension – `category` (default) or `account`

    Only expense transactions (negative amounts) are included in the distribution.
    """
    try:
        return service.get_spending_distribution(start_date, end_date, group_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get(
    "/api/breakdown/accounts",
    response_model=AccountBreakdownDetailResponse,
    tags=["financial-summary"],
    summary="Account breakdown",
    response_description="Current balances grouped by asset type",
)
async def get_account_breakdown(
    service: FinancialSummaryService = Depends(get_financial_summary_service)
):
    """Return the current balance breakdown across all active accounts.

    Accounts are grouped into three asset categories:
    - **liquidity** – checking, savings, cash
    - **investments** – investment, brokerage, retirement
    - **other** – all remaining account types

    Each category includes the total amount and its percentage of the overall
    portfolio. Individual account details are also returned, sorted by balance.
    """
    return service.get_account_breakdown()
