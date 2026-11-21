"""Client profile, investment policy approval and the advisor's decision log and review."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.models.profile import (
    DecisionCreate,
    DecisionUpdate,
    ProfilePatch,
    ProfileResponse,
)
from src.profile import ClientProfile
from src.routes.deps import resolve_workspace_id
from src.services.advisor_service import AdvisorService
from src.services.profile_service import ProfileService

router = APIRouter(prefix="/api", tags=["advisor"])


def get_profile_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    try:
        yield ProfileService(session)
    finally:
        session.close()


def get_advisor_service(workspace_id: int = Depends(resolve_workspace_id)):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    try:
        yield AdvisorService(session)
    finally:
        session.close()


@router.get("/workspaces/current/profile", response_model=ProfileResponse, summary="The client profile of the current project")
def get_profile(service: ProfileService = Depends(get_profile_service)):
    """Situation, goals, risk and investment policy, with ``completeness`` (which interview blocks are filled) and
    ``ips_status``: ``none`` (no policy), ``pending`` (changed since the user approved it) or ``approved``."""
    return service.get()


@router.put("/workspaces/current/profile", response_model=ProfileResponse, summary="Replace the client profile")
def put_profile(profile: ClientProfile, source: str = "user", service: ProfileService = Depends(get_profile_service)):
    if source not in ("user", "agent"):
        raise HTTPException(status_code=400, detail="source must be 'user' or 'agent'")
    return service.replace(profile, source)


@router.patch("/workspaces/current/profile", response_model=ProfileResponse, summary="Update part of the client profile")
def patch_profile(body: ProfilePatch, service: ProfileService = Depends(get_profile_service)):
    """Merge a partial document: nested fields merge, goals and debts are upserted by ``key``, everything else is
    replaced. The result must validate as a whole profile (422 otherwise)."""
    try:
        return service.patch(body.patch, body.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/workspaces/current/profile/versions", summary="Past versions of the profile")
def profile_versions(service: ProfileService = Depends(get_profile_service)) -> dict[str, Any]:
    return {"versions": service.versions()}


@router.post("/workspaces/current/profile/ips/approve", response_model=ProfileResponse, summary="Approve the investment policy")
def approve_ips(service: ProfileService = Depends(get_profile_service)):
    """Binds the approval to the current policy text: a later change makes it ``pending`` again. The app's
    Advisor page calls this; agents must not."""
    try:
        return service.approve_ips()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/profiles/validate", summary="Validate a profile document without saving it")
def validate_profile(profile: ClientProfile) -> dict[str, Any]:
    return {"valid": True, "profile": profile.to_json(), "completeness": profile.completeness(), "ips_fingerprint": profile.ips.fingerprint()}


# ---------------------------------------------------------------------- decisions


@router.get("/advisor/decisions", summary="The advisor's decision log")
def list_decisions(status: str | None = None, service: ProfileService = Depends(get_profile_service)) -> list[dict[str, Any]]:
    try:
        return service.list_decisions(status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/advisor/decisions", status_code=201, summary="Log a recommendation")
def log_decision(body: DecisionCreate, service: ProfileService = Depends(get_profile_service)) -> dict[str, Any]:
    """A decision must name the figures it rests on (``data_refs``) and, when there is a policy, the IPS points it
    follows (``ips_refs``)."""
    try:
        return service.log_decision(body.title, body.rationale, body.data_refs, body.ips_refs, body.date, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/advisor/decisions/{decision_id}", summary="Update a decision's status or outcome")
def update_decision(decision_id: int, body: DecisionUpdate, service: ProfileService = Depends(get_profile_service)) -> dict[str, Any]:
    try:
        return service.update_decision(decision_id, body.model_dump(exclude_none=True))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------- review


@router.get("/advisor/review", summary="Everything an advisor needs for a review, in one call")
def advisor_review(months: int = 12, service: AdvisorService = Depends(get_advisor_service)) -> dict[str, Any]:
    """Profile and IPS status, cash flow of the last ``months``, net worth, investments, emergency fund against its
    target, debts, the measurable allocation drift and the checks that fail, each with its figures. Not advice:
    the material advice must cite."""
    return service.review(months)
