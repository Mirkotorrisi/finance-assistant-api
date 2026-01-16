"""FastAPI application for the finance assistant."""

import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

from src.business_logic.mcp_database import FinanceMCPDatabase
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


# Dependency to get FinanceMCPDatabase instance
def get_mcp_db():
    session = _get_db_session()
    db = FinanceMCPDatabase(db_session=session)
    try:
        yield db
    finally:
        # We don't close the session here because FinanceMCPDatabase might not own it 
        # based on my previous check of the code, but actually _get_db_session returns a new session usually.
        # Let's check if FinanceMCPDatabase closes it.
        # It has a close() method.
        # But if we pass a session, owns_session is False.
        # So we should close the session manually or let FastAPI dependency handle it if it was a generator yielding session.
        # Simplest is to let FinanceMCPDatabase create its own session or handle it here.
        # The existing code had `get_mcp_server` which likely did something similar.
        # Let's rely on FinanceMCPDatabase default init if possible, but that creates a new session every time.
        # Better:
        pass
    # Actually, FinanceMCPDatabase takes an optional session.
    # If we pass one, it sets owns_session=False.
    # If we don't, it calls get_db_session().
    # Let's just instantiate it.
    # db = FinanceMCPDatabase() 
    # try: yield db; finally: db.close() 

def get_db():
    db = FinanceMCPDatabase()
    try:
        yield db
    finally:
        db.close()

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
    db: FinanceMCPDatabase = Depends(get_db)
):
    """List transactions with optional filters."""
    return db.list_transactions(category, start_date, end_date)

@app.post("/api/transactions", response_model=TransactionResponse)
async def create_transaction(
    transaction: TransactionCreate,
    db: FinanceMCPDatabase = Depends(get_db)
):
    """Create a new transaction."""
    return db.add_transaction(
        amount=transaction.amount,
        category=transaction.category,
        description=transaction.description,
        date=transaction.date,
        currency=transaction.currency
    )

@app.post("/api/transactions/bulk", response_model=List[TransactionResponse])
async def create_transactions_bulk(
    transactions: List[TransactionCreate],
    db: FinanceMCPDatabase = Depends(get_db)
):
    """Create multiple transactions in bulk."""
    return db.add_transactions_bulk(
        [t.model_dump() for t in transactions]
    )

@app.put("/api/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: int,
    updates: TransactionUpdate,
    db: FinanceMCPDatabase = Depends(get_db)
):
    """Update an existing transaction."""
    updated = db.update_transaction(transaction_id, updates.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated

@app.delete("/api/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: int,
    db: FinanceMCPDatabase = Depends(get_db)
):
    """Delete a transaction."""
    success = db.delete_transaction(transaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"message": "Transaction deleted successfully"}

@app.get("/api/balance", response_model=BalanceResponse)
async def get_balance(db: FinanceMCPDatabase = Depends(get_db)):
    """Get total balance."""
    return {"balance": db.get_balance()}
