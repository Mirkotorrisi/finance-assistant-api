"""Workspace (project) and blueprint REST routes."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from src.blueprint import Blueprint
from src.routes.deps import resolve_workspace_id
from src.models.workspace import BlueprintResponse, WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate
from src.services.workspace_service import WorkspaceError, WorkspaceService

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def get_workspace_service(x_user_id: Optional[str] = Header(default=None)):
    from src.database.init import get_unscoped_session

    session = get_unscoped_session()
    try:
        yield WorkspaceService(session, x_user_id)
    finally:
        session.close()


def _guard(call):
    try:
        return call()
    except WorkspaceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("", response_model=List[WorkspaceResponse], summary="List workspaces")
async def list_workspaces(service: WorkspaceService = Depends(get_workspace_service)):
    """The caller's workspaces plus unowned (legacy) ones."""
    return service.list()


@router.post("", response_model=WorkspaceResponse, status_code=201, summary="Create a workspace")
async def create_workspace(body: WorkspaceCreate, service: WorkspaceService = Depends(get_workspace_service)):
    """Create a project with its own accounts, transactions, rules and blueprint."""
    return service.create(body.name, body.description, body.blueprint)


@router.get("/current", response_model=WorkspaceResponse, summary="The workspace this request works in")
async def get_current_workspace(
    workspace_id: int = Depends(resolve_workspace_id), service: WorkspaceService = Depends(get_workspace_service)
):
    """Resolved from ``X-Workspace-Id`` / ``X-User-Id``, like every other scoped endpoint."""
    return _guard(lambda: service.get(workspace_id))


@router.get("/current/blueprint", response_model=BlueprintResponse, summary="Blueprint of the current workspace")
async def get_current_blueprint(
    workspace_id: int = Depends(resolve_workspace_id), service: WorkspaceService = Depends(get_workspace_service)
):
    return _guard(lambda: service.get_blueprint(workspace_id))


@router.post("/current/blueprint/preview", summary="Preview a blueprint change for the current workspace")
async def preview_current_blueprint(
    blueprint: Blueprint,
    workspace_id: int = Depends(resolve_workspace_id),
    service: WorkspaceService = Depends(get_workspace_service),
):
    return _guard(lambda: service.preview_blueprint(workspace_id, blueprint))


@router.get("/{workspace_id}", response_model=WorkspaceResponse, summary="Get a workspace")
async def get_workspace(workspace_id: int, service: WorkspaceService = Depends(get_workspace_service)):
    return _guard(lambda: service.get(workspace_id))


@router.put("/{workspace_id}", response_model=WorkspaceResponse, summary="Rename or describe a workspace")
async def update_workspace(workspace_id: int, body: WorkspaceUpdate, service: WorkspaceService = Depends(get_workspace_service)):
    return _guard(lambda: service.update(workspace_id, body.name, body.description))


@router.delete("/{workspace_id}", summary="Delete a workspace")
async def delete_workspace(workspace_id: int, force: bool = False, service: WorkspaceService = Depends(get_workspace_service)):
    """Refuses when the workspace has data unless ``force=true``, and never deletes the only workspace."""
    _guard(lambda: service.delete(workspace_id, force))
    return {"message": "Workspace deleted"}


@router.get("/{workspace_id}/blueprint", response_model=BlueprintResponse, summary="Get the blueprint")
async def get_blueprint(workspace_id: int, service: WorkspaceService = Depends(get_workspace_service)):
    return _guard(lambda: service.get_blueprint(workspace_id))


@router.put("/{workspace_id}/blueprint", response_model=BlueprintResponse, summary="Replace the blueprint")
async def put_blueprint(workspace_id: int, blueprint: Blueprint, service: WorkspaceService = Depends(get_workspace_service)):
    """Validates the document (keys, references, depth) and bumps the blueprint version."""
    return _guard(lambda: service.set_blueprint(workspace_id, blueprint))


@router.post("/{workspace_id}/blueprint/preview", summary="Preview a blueprint change")
async def preview_blueprint(workspace_id: int, blueprint: Blueprint, service: WorkspaceService = Depends(get_workspace_service)):
    """The structural diff and how many transactions would lose their category. Nothing is saved."""
    return _guard(lambda: service.preview_blueprint(workspace_id, blueprint))


@router.get("/{workspace_id}/blueprint/export", summary="Download the blueprint as a file")
async def export_blueprint(workspace_id: int, service: WorkspaceService = Depends(get_workspace_service)):
    """The blueprint document alone, ready to be imported into another project or shared."""
    data = _guard(lambda: service.get_blueprint(workspace_id))["blueprint"]
    filename = f"blueprint-{data.get('name', 'project')}".lower().replace(" ", "-") + ".json"
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
