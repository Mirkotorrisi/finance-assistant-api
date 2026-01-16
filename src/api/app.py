"""FastAPI application for the finance assistant."""

import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager


from src.services.transaction_service import TransactionService
from src.services.financial_data_service import FinancialDataService
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


app = FastAPI(
    title="Finance Assistant API",
    description="A simple CRUD API for personal finance management",
    version="2.0.0",
    lifespan=lifespan
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

# --- Pydantic Models ---

class TransactionCreate(BaseModel):
    amount: float
    category: str
    description: str
    date: Optional[str] = None
    currency: Optional[str] = "EUR"

class TransactionUpdate(BaseModel):
    amount: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None
    currency: Optional[str] = None

class TransactionResponse(BaseModel):
    id: int
    date: str  # ISO format date
    amount: float
    category: str
    description: str
    currency: str

class BalanceResponse(BaseModel):
    balance: float

# Financial Data Models
class MonthlyDataResponse(BaseModel):
    month: str
    netWorth: float
    expenses: float
    income: float
    net: float

class AccountBreakdownResponse(BaseModel):
    liquidity: float
    investments: float
    otherAssets: float

class FinancialDataResponse(BaseModel):
    year: int
    currentNetWorth: float
    netSavings: float
    monthlyData: List[MonthlyDataResponse]
    accountBreakdown: AccountBreakdownResponse

# --- Endpoints ---

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

@app.get("/api/transactions", response_model=List[TransactionResponse])
async def list_transactions(
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    service: TransactionService = Depends(get_transaction_service)
):
    """List transactions with optional filters."""
    return service.list_transactions(category, start_date, end_date)

@app.post("/api/transactions", response_model=TransactionResponse)
async def create_transaction(
    transaction: TransactionCreate,
    service: TransactionService = Depends(get_transaction_service)
):
    """Create a new transaction."""
    return service.add_transaction(
        amount=transaction.amount,
        category=transaction.category,
        description=transaction.description,
        date=transaction.date,
        currency=transaction.currency
    )

@app.post("/api/transactions/bulk", response_model=List[TransactionResponse])
async def create_transactions_bulk(
    transactions: List[TransactionCreate],
    service: TransactionService = Depends(get_transaction_service)
):
    """Create multiple transactions in bulk."""
    return service.add_transactions_bulk(
        [t.model_dump() for t in transactions]
    )

@app.put("/api/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: int,
    updates: TransactionUpdate,
    service: TransactionService = Depends(get_transaction_service)
):
    """Update an existing transaction."""
    updated = service.update_transaction(transaction_id, updates.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated

@app.delete("/api/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: int,
    service: TransactionService = Depends(get_transaction_service)
):
    """Delete a transaction."""
    success = service.delete_transaction(transaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"message": "Transaction deleted successfully"}

@app.get("/api/balance", response_model=BalanceResponse)
async def get_balance(service: TransactionService = Depends(get_transaction_service)):
    """Get total balance."""
    return {"balance": service.get_balance()}

@app.get("/api/financial-data/{year}", response_model=FinancialDataResponse)
async def get_financial_data(
    year: int,
    service: FinancialDataService = Depends(get_financial_data_service)
):
    """Get aggregated financial data for a specific year.
    
    Returns monthly data for all 12 months, current net worth, net savings,
    and account breakdown by category.
    """
    try:
        data = service.get_financial_data_for_year(year)
        return data
    except Exception as e:
        logger.error(f"Error getting financial data for year {year}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
