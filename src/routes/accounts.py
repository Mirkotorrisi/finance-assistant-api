"""Account REST routes."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from src.models.account import (
    AccountBalanceResponse,
    AccountCreate,
    AccountResponse,
    AccountUpdate,
)
from src.services.account_service import AccountService

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def get_account_service():
    from src.database.init import get_db_session

    session = get_db_session()
    service = AccountService(session=session)
    try:
        yield service
    finally:
        session.close()


@router.get(
    "",
    response_model=List[AccountResponse],
    summary="List accounts",
    response_description="A list of accounts",
)
async def list_accounts(
    active_only: bool = True,
    service: AccountService = Depends(get_account_service),
):
    """Return all accounts, optionally limited to active ones."""
    return service.list_accounts(active_only=active_only)


@router.get(
    "/{account_id}",
    response_model=AccountResponse,
    summary="Get an account",
    response_description="The requested account",
)
async def get_account(
    account_id: int,
    service: AccountService = Depends(get_account_service),
):
    """Return a single account identified by account_id."""
    account = service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post(
    "",
    response_model=AccountResponse,
    status_code=201,
    summary="Create an account",
    response_description="The newly created account",
)
async def create_account(
    account: AccountCreate,
    service: AccountService = Depends(get_account_service),
):
    """Create a new financial account."""
    return service.create_account(
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        is_active=account.is_active,
        current_balance=account.current_balance,
    )


@router.put(
    "/{account_id}",
    response_model=AccountResponse,
    summary="Update an account",
    response_description="The updated account",
)
async def update_account(
    account_id: int,
    updates: AccountUpdate,
    service: AccountService = Depends(get_account_service),
):
    """Partially update an account identified by account_id."""
    updated = service.update_account(account_id, updates.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return updated


@router.delete(
    "/{account_id}",
    summary="Delete (deactivate) an account",
    response_description="Confirmation message",
)
async def delete_account(
    account_id: int,
    service: AccountService = Depends(get_account_service),
):
    """Deactivate an account identified by account_id."""
    success = service.delete_account(account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"message": "Account deleted successfully"}


@router.get(
    "/{account_id}/balance",
    response_model=AccountBalanceResponse,
    summary="Get account balance",
    response_description="Current balance for the account",
)
async def get_account_balance(
    account_id: int,
    service: AccountService = Depends(get_account_service),
):
    """Return the current balance for a specific account."""
    account = service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    balance = service.get_account_balance(account_id)
    return {"account_id": account_id, "balance": balance}
