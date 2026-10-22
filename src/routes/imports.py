"""Statement import and transfer routes (workspace scoped)."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from src.models.imports import ImportRequest, ImportResult, PairRequest
from src.routes.deps import resolve_workspace_id
from src.services.import_service import ImportRequestError, ImportService

router = APIRouter(tags=["imports"])


def get_import_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    try:
        yield ImportService(session)
    finally:
        session.close()


def _guard(call):
    try:
        return call()
    except ImportRequestError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/api/imports", response_model=ImportResult, summary="Import a parsed statement")
async def import_statement(body: ImportRequest, service: ImportService = Depends(get_import_service)):
    """Add the new rows of a statement to an account, skipping the ones already stored.

    Safe to repeat or to overlap with earlier statements. Transfers between the workspace's own accounts are
    detected and left out of spending totals.
    """
    return _guard(
        lambda: service.import_transactions(
            body.account_id, [r.model_dump() for r in body.transactions], body.filename, body.file_hash
        )
    )


@router.get("/api/imports", summary="List imports")
async def list_imports(service: ImportService = Depends(get_import_service)) -> List[Dict[str, Any]]:
    return service.list_batches()


@router.delete("/api/imports/{batch_id}", summary="Undo an import")
async def undo_import(batch_id: int, service: ImportService = Depends(get_import_service)):
    """Remove every transaction the import added."""
    return _guard(lambda: service.undo_batch(batch_id))


@router.post("/api/transfers/detect", summary="Detect transfers between own accounts")
async def detect_transfers(
    include_unhinted: bool = False, dry_run: bool = False, service: ImportService = Depends(get_import_service)
):
    """Pair matching outflow/inflow across accounts. ``include_unhinted`` + ``dry_run`` lists suggestions to confirm."""
    pairs = service.detect_transfers(include_unhinted=include_unhinted, dry_run=dry_run)
    return {"dry_run": dry_run, "count": len(pairs), "pairs": pairs}


@router.post("/api/transfers/pair", summary="Mark two transactions as a transfer")
async def pair_transfer(body: PairRequest, service: ImportService = Depends(get_import_service)):
    return _guard(lambda: service.pair_transfer(body.first_id, body.second_id))


@router.delete("/api/transfers/{transaction_id}", summary="Unmark a transfer")
async def unmark_transfer(transaction_id: int, service: ImportService = Depends(get_import_service)):
    """Treat the transaction (and its partner) as normal spending/income again."""
    return _guard(lambda: service.unmark_transfer(transaction_id))
