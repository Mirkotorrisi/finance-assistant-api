"""Request-level dependencies: which workspace (project) a request works in."""

from typing import Optional

from fastapi import Header, HTTPException

from src.database.workspaces import default_workspace_id


def resolve_workspace_id(
    x_workspace_id: Optional[int] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> int:
    """``X-Workspace-Id`` if given, else the caller's default workspace.

    ``X-User-Id`` is the lightweight client identity (no authentication yet): a workspace owned by someone
    else is refused, an unowned (legacy) one is open to everybody.
    """
    from src.database.init import get_unscoped_session
    from src.database.models import Workspace

    session = get_unscoped_session()
    try:
        if x_workspace_id is None:
            return default_workspace_id(session, x_user_id)
        workspace = session.get(Workspace, x_workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail=f"Workspace {x_workspace_id} not found")
        if workspace.owner_user_id and x_user_id and workspace.owner_user_id != x_user_id:
            raise HTTPException(status_code=403, detail="This workspace belongs to another user")
        return workspace.id
    finally:
        session.close()
