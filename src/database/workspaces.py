"""Low-level workspace helpers shared by the session factory, the services and the routes."""

from typing import Optional

from sqlalchemy.orm import Session

from src.blueprint import Blueprint
from src.database.models import Workspace

DEFAULT_WORKSPACE_NAME = "Personale"


def default_workspace_id(session: Session, owner_user_id: Optional[str] = None) -> int:
    """The workspace a request without an explicit one belongs to.

    Preference: one owned by ``owner_user_id``; else the oldest unowned (legacy / single-user) one; else a new
    "Personale" project is created (owned by ``owner_user_id`` when given).
    """
    if owner_user_id:
        owned = session.query(Workspace).filter(Workspace.owner_user_id == owner_user_id).order_by(Workspace.id).first()
        if owned:
            return owned.id
    shared = session.query(Workspace).filter(Workspace.owner_user_id.is_(None)).order_by(Workspace.id).first()
    if shared:
        return shared.id
    if not owner_user_id:
        any_ws = session.query(Workspace).order_by(Workspace.id).first()
        if any_ws:
            return any_ws.id
    return create_workspace(session, DEFAULT_WORKSPACE_NAME, owner_user_id=owner_user_id).id


def create_workspace(
    session: Session,
    name: str,
    owner_user_id: Optional[str] = None,
    description: Optional[str] = None,
    blueprint: Optional[Blueprint] = None,
) -> Workspace:
    blueprint = blueprint or Blueprint(name=name)
    workspace = Workspace(
        name=name,
        description=description,
        owner_user_id=owner_user_id,
        blueprint=blueprint.to_json(),
        blueprint_version=1,
    )
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace
