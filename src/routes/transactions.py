"""Transaction REST routes."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from src.models.transaction import (
    BalanceResponse,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from src.services.transaction_service import TransactionService

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def get_transaction_service():
    from src.database.init import get_db_session

    session = get_db_session()
    service = TransactionService(session=session)
    try:
        yield service
    finally:
        session.close()


@router.get(
    "",
    response_model=List[TransactionResponse],
    summary="List transactions",
    response_description="A list of transactions matching the given filters",
)
async def list_transactions(
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_id: Optional[int] = None,
    service: TransactionService = Depends(get_transaction_service),
):
    """Return a list of transactions, optionally filtered by category, date range, or account."""
    return service.list_transactions(category, start_date, end_date, account_id)


@router.post(
    "",
    response_model=TransactionResponse,
    status_code=201,
    summary="Create a transaction",
    response_description="The newly created transaction",
)
async def create_transaction(
    transaction: TransactionCreate,
    service: TransactionService = Depends(get_transaction_service),
):
    """Create a single financial transaction."""
    try:
        return service.add_transaction(
            amount=transaction.amount,
            category=transaction.category,
            description=transaction.description,
            date=transaction.date,
            currency=transaction.currency,
            account_id=transaction.account_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/bulk",
    response_model=List[TransactionResponse],
    status_code=201,
    summary="Bulk-create transactions",
    response_description="List of newly created transactions",
)
async def create_transactions_bulk(
    transactions: List[TransactionCreate],
    service: TransactionService = Depends(get_transaction_service),
):
    """Create multiple transactions in a single request."""
    return service.add_transactions_bulk([t.model_dump() for t in transactions])


@router.put(
    "/{transaction_id}",
    response_model=TransactionResponse,
    summary="Update a transaction",
    response_description="The updated transaction",
)
async def update_transaction(
    transaction_id: int,
    updates: TransactionUpdate,
    service: TransactionService = Depends(get_transaction_service),
):
    """Partially update a transaction identified by transaction_id."""
    updated = service.update_transaction(transaction_id, updates.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated


@router.delete(
    "/{transaction_id}",
    summary="Delete a transaction",
    response_description="Confirmation message",
)
async def delete_transaction(
    transaction_id: int,
    service: TransactionService = Depends(get_transaction_service),
):
    """Permanently delete a transaction identified by transaction_id."""
    success = service.delete_transaction(transaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"message": "Transaction deleted successfully"}


@router.get(
    "/balance",
    response_model=BalanceResponse,
    summary="Get total balance",
    response_description="Sum of all transaction amounts",
)
async def get_balance(service: TransactionService = Depends(get_transaction_service)):
    """Return the total balance calculated by summing every transaction amount."""
    return {"balance": service.get_balance()}
