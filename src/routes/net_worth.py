"""Balance snapshots and net worth: what the accounts held, reconciled against the transactions."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from src.models.net_worth import FlowCheckRequest, SnapshotBulk, SnapshotCreate
from src.routes.deps import resolve_workspace_id
from src.services.net_worth_service import NetWorthService

router = APIRouter(prefix="/api", tags=["net-worth"])


def get_net_worth_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    try:
        yield NetWorthService(session)
    finally:
        session.close()


def _entry(service: NetWorthService, snapshot_id: int, account_id: int):
    return next(r for r in service.list(account_id) if r["id"] == snapshot_id)


@router.post("/balance-snapshots", summary="Record what an account held on a day")
def record_snapshot(body: SnapshotCreate, service: NetWorthService = Depends(get_net_worth_service)):
    """Create or replace the snapshot of an account on a day. The result carries the reconciliation with the
    transactions since the account's previous snapshot: ``ok``, ``gap`` (with the unexplained ``delta``),
    ``baseline`` (first snapshot) or ``valuation`` (brokerage accounts are never reconciled)."""
    try:
        snap = service.upsert(body.account_id, body.date, body.balance, body.note, source="user")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _entry(service, snap.id, snap.account_id)


@router.post("/balance-snapshots/bulk", summary="Record many snapshots at once")
def record_snapshots(body: SnapshotBulk, service: NetWorthService = Depends(get_net_worth_service)):
    try:
        ids = service.upsert_many([s.model_dump() for s in body.snapshots], source=body.source)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    entries = [r for r in service.list() if r["id"] in set(ids)]
    gaps = [e for e in entries if e["reconciliation"]["status"] == "gap"]
    return {"saved": len(ids), "gaps": len(gaps), "snapshots": entries}


@router.get("/balance-snapshots", summary="List snapshots with their reconciliation")
def list_snapshots(
    account_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    service: NetWorthService = Depends(get_net_worth_service),
):
    return {"snapshots": service.list(account_id, start_date, end_date)}


@router.delete("/balance-snapshots/{snapshot_id}", summary="Delete a snapshot")
def delete_snapshot(snapshot_id: int, service: NetWorthService = Depends(get_net_worth_service)):
    if not service.delete(snapshot_id):
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")
    return {"message": "Snapshot deleted"}


@router.post("/balance-snapshots/{snapshot_id}/adjust", summary="Book a snapshot's unexplained difference")
def adjust_snapshot(snapshot_id: int, service: NetWorthService = Depends(get_net_worth_service)):
    """Create the correcting transaction for a ``gap`` snapshot (not spending, not income). Prefer finding the
    missing transactions: use this when the difference is known and not worth chasing."""
    try:
        return service.adjust(snapshot_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/net-worth", summary="Net worth by month and account")
def net_worth(
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    service: NetWorthService = Depends(get_net_worth_service),
):
    """Month-end balance of every active account (``basis``: snapshot, derived from transactions around a
    snapshot, carried forward, or transactions only) plus liquid, invested and total per month. Default: the
    last 24 months."""
    try:
        return service.net_worth(start_month, end_month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/net-worth/check-flows", summary="Compare a sheet's monthly income/expenses with the transactions")
def check_flows(body: FlowCheckRequest, service: NetWorthService = Depends(get_net_worth_service)):
    try:
        return {"rows": service.check_flows([r.model_dump() for r in body.rows], body.include_transfers)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
