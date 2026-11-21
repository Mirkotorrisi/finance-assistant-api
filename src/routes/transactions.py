"""Transaction REST routes."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.routes.deps import resolve_workspace_id
from src.models.transaction import (
    BalanceResponse,
    BulkCategoryUpdate,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from src.services.transaction_service import TransactionService

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def get_transaction_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
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
def list_transactions(
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_id: Optional[int] = None,
    limit: Optional[int] = Query(default=None, ge=1, le=5000, description="Page size (newest first); all rows when omitted"),
    offset: int = Query(default=0, ge=0),
    service: TransactionService = Depends(get_transaction_service),
):
    """Return a list of transactions, newest first, optionally filtered by category, date range, or account.
    ``limit``/``offset`` page through them; without ``limit`` every matching row is returned."""
    return service.list_transactions(category, start_date, end_date, account_id, limit=limit, offset=offset)


@router.post(
    "",
    response_model=TransactionResponse,
    status_code=201,
    summary="Create a transaction",
    response_description="The newly created transaction",
)
def create_transaction(
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
def create_transactions_bulk(
    transactions: List[TransactionCreate],
    service: TransactionService = Depends(get_transaction_service),
):
    """Create multiple transactions in a single request."""
    return service.add_transactions_bulk([t.model_dump() for t in transactions])


class CategoryRemap(BaseModel):
    from_category: str
    to_category: str


@router.post("/remap-category", summary="Move all transactions of a category to another")
def remap_category(body: CategoryRemap, service: TransactionService = Depends(get_transaction_service)):
    """Case-insensitive on the source. Use it after removing a category from the blueprint."""
    return service.remap_category(body.from_category, body.to_category)


@router.put(
    "/bulk-category",
    response_model=List[TransactionResponse],
    summary="Bulk-update transaction categories",
    response_description="List of updated transactions",
)
def bulk_update_categories(
    payload: BulkCategoryUpdate,
    service: TransactionService = Depends(get_transaction_service),
):
    """Update the category of multiple transactions in one request."""
    results = []
    for item in payload.updates:
        updated = service.update_transaction(
            item.transaction_id, {"category": item.category}, source=item.source, confidence=item.confidence
        )
        if updated:
            results.append(updated)
    return results


@router.put(
    "/{transaction_id}",
    response_model=TransactionResponse,
    summary="Update a transaction",
    response_description="The updated transaction",
)
def update_transaction(
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
def delete_transaction(
    transaction_id: int,
    service: TransactionService = Depends(get_transaction_service),
):
    """Permanently delete a transaction identified by transaction_id."""
    success = service.delete_transaction(transaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"message": "Transaction deleted successfully"}


@router.get(
    "/categories",
    response_model=List[str],
    summary="Get distinct categories",
    response_description="Sorted list of distinct transaction category names",
)
def get_distinct_categories(service: TransactionService = Depends(get_transaction_service)):
    """Return every distinct category name present in stored transactions."""
    return service.get_distinct_categories()


@router.get(
    "/balance",
    response_model=BalanceResponse,
    summary="Get total balance",
    response_description="Sum of all transaction amounts",
)
def get_balance(service: TransactionService = Depends(get_transaction_service)):
    """The current total balance: each account's latest recorded balance (bank sync, typed, sheet) plus the
    transactions since it; accounts that never had one count their transactions."""
    return service.get_balance_details()
