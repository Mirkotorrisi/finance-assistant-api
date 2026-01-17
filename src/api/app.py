"""FastAPI application for the finance assistant."""

import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager



from src.services.transaction_service import TransactionService
from src.services.financial_data_service import FinancialDataService
from src.services.account_service import AccountService
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

# Dependency to get AccountService instance
def get_account_service():
    session = _get_db_session()
    service = AccountService(session=session)
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

# Account models
class AccountCreate(BaseModel):
    name: str
    account_type: str
    currency: Optional[str] = "EUR"
    is_active: Optional[bool] = True
    current_balance: Optional[float] = 0.0

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = None

class AccountResponse(BaseModel):
    id: int
    name: str
    type: str
    currency: str
    is_active: bool
    current_balance: float

class AccountBalanceResponse(BaseModel):
    account_id: int
    balance: float

# Financial data response models
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
    """Get aggregated financial data for a specific year."""
    data = service.get_financial_data(year)
    return data

@app.post("/api/snapshots/populate")
async def populate_snapshots(
    service: AccountService = Depends(get_account_service)
):
    """Populate monthly snapshots from existing transaction data for all accounts.
    
    This endpoint:
    1. Finds all active accounts
    2. Groups transactions by year/month for each account
    3. Calculates monthly aggregates (income, expenses, balances)
    4. Creates or updates MonthlyAccountSnapshot records
    """
    from sqlalchemy import func
    from src.database.models import Transaction
    
    results = []
    accounts = service.list_accounts(active_only=True)
    
    for account in accounts:
        account_id = account['id']
        
        # Get all unique year/month combinations for this account's transactions
        periods = service.session.query(
            func.extract('year', Transaction.date).label('year'),
            func.extract('month', Transaction.date).label('month')
        ).filter(
            Transaction.account_id == account_id
        ).distinct().order_by('year', 'month').all()
        
        if not periods:
            continue
        
        running_balance = 0.0
        
        for year, month in periods:
            year = int(year)
            month = int(month)
            
            try:
                snapshot = service.populate_snapshot_from_transactions(
                    account_id=account_id,
                    year=year,
                    month=month,
                    starting_balance=running_balance,
                    overwrite=True
                )
                running_balance = snapshot['ending_balance']
                results.append({
                    "account_id": account_id,
                    "account_name": account['name'],
                    "year": year,
                    "month": month,
                    "status": "created/updated"
                })
            except Exception as e:
                results.append({
                    "account_id": account_id,
                    "account_name": account['name'],
                    "year": year,
                    "month": month,
                    "status": f"error: {str(e)}"
                })
    
    return {
        "message": f"Processed {len(results)} snapshots",
        "results": results
    }

# --- Account Endpoints ---

@app.get("/api/accounts", response_model=List[AccountResponse])
async def list_accounts(
    active_only: bool = True,
    service: AccountService = Depends(get_account_service)
):
    """List all accounts."""
    accounts = service.list_accounts(active_only=active_only)
    return accounts

@app.get("/api/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    service: AccountService = Depends(get_account_service)
):
    """Get a single account by ID."""
    account = service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account

@app.post("/api/accounts", response_model=AccountResponse)
async def create_account(
    account: AccountCreate,
    service: AccountService = Depends(get_account_service)
):
    """Create a new account."""
    return service.create_account(
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        is_active=account.is_active,
        current_balance=account.current_balance
    )

@app.put("/api/accounts/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    updates: AccountUpdate,
    service: AccountService = Depends(get_account_service)
):
    """Update an existing account."""
    updated = service.update_account(account_id, updates.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return updated

@app.delete("/api/accounts/{account_id}")
async def delete_account(
    account_id: int,
    service: AccountService = Depends(get_account_service)
):
    """Delete (deactivate) an account."""
    success = service.delete_account(account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"message": "Account deleted successfully"}

@app.get("/api/accounts/{account_id}/balance", response_model=AccountBalanceResponse)
async def get_account_balance(
    account_id: int,
    service: AccountService = Depends(get_account_service)
):
    """Get current balance for an account."""
    account = service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    balance = service.get_account_balance(account_id)
    return {"account_id": account_id, "balance": balance}
