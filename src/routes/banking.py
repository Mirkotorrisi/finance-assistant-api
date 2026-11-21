"""Bank connections (PSD2 consents) and their account links. The gateway drives the bank API; this stores the state."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.models.banking import (
    BankAccountLinkUpdate,
    BankConnectionCreate,
    BankConnectionUpdate,
)
from src.routes.deps import resolve_workspace_id
from src.services.banking_service import BankingService

router = APIRouter(prefix="/api", tags=["banking"])


def get_banking_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    try:
        yield BankingService(session)
    finally:
        session.close()


@router.get("/bank-connections/due", summary="Connections to sync (every workspace)")
async def due_connections(max_age_hours: float = 12) -> list[dict[str, Any]]:
    """For the gateway's scheduler: active connections whose last sync is older than ``max_age_hours``."""
    from src.database.init import get_unscoped_session

    session = get_unscoped_session()
    try:
        return BankingService.due(session, max_age_hours)
    finally:
        session.close()


@router.get("/bank-connections/expiring", summary="Consents about to expire (every workspace)")
async def expiring_connections(within_days: int = 14) -> list[dict[str, Any]]:
    from src.database.init import get_unscoped_session

    session = get_unscoped_session()
    try:
        return BankingService.expiring(session, within_days)
    finally:
        session.close()


@router.get("/bank-connections", summary="The bank connections of the current project")
async def list_connections(service: BankingService = Depends(get_banking_service)) -> list[dict[str, Any]]:
    """Each connection carries its bank, status, consent validity, last sync and the bank accounts it exposes
    with the app account each one feeds (``account_id``, null = not linked yet)."""
    return service.list()


@router.post("/bank-connections", status_code=201, summary="Register a consent")
async def create_connection(body: BankConnectionCreate, service: BankingService = Depends(get_banking_service)) -> dict[str, Any]:
    try:
        return service.create(body.model_dump(mode="python"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/bank-connections/{connection_id}", summary="Update a connection's settings or sync state")
async def update_connection(connection_id: int, body: BankConnectionUpdate, service: BankingService = Depends(get_banking_service)) -> dict[str, Any]:
    try:
        return service.update(connection_id, body.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/bank-connections/{connection_id}", summary="Forget a connection")
async def delete_connection(connection_id: int, service: BankingService = Depends(get_banking_service)) -> dict[str, str]:
    """Removes the connection and its account links; transactions and balances already imported stay. The
    gateway revokes the consent at the bank before calling this."""
    try:
        service.delete(connection_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"message": "Bank connection deleted"}


@router.put("/bank-connections/{connection_id}/links/{link_id}", summary="Map a bank account to an app account")
async def update_link(connection_id: int, link_id: int, body: BankAccountLinkUpdate, service: BankingService = Depends(get_banking_service)) -> dict[str, Any]:
    """Pick the app account this bank account feeds (``account_id``), create one (``create_account``), detach it
    (``unlink``) or enable/disable the sync of this account."""
    try:
        return service.update_link(connection_id, link_id, body.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
