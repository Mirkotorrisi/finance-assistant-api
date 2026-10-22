"""Workspace (project) management. Works on an unscoped session: it deals with workspaces themselves."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.blueprint import Blueprint
from src.database.models import Account, ImportBatch, MerchantRule, Transaction, Workspace
from src.database.workspaces import create_workspace


class WorkspaceError(Exception):
    """A workspace operation that the caller may not do (maps to HTTP 403/404/409)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class WorkspaceService:
    def __init__(self, session: Session, user_id: Optional[str] = None):
        self.session = session
        self.user_id = user_id

    # ------------------------------------------------------------------ access

    def _get(self, workspace_id: int) -> Workspace:
        workspace = self.session.get(Workspace, workspace_id)
        if workspace is None:
            raise WorkspaceError(404, f"Workspace {workspace_id} not found")
        if workspace.owner_user_id and self.user_id and workspace.owner_user_id != self.user_id:
            raise WorkspaceError(403, "This workspace belongs to another user")
        return workspace

    # ------------------------------------------------------------------ CRUD

    def list(self) -> List[Dict[str, Any]]:
        query = self.session.query(Workspace)
        if self.user_id:  # own projects and unowned (legacy) ones
            query = query.filter((Workspace.owner_user_id == self.user_id) | (Workspace.owner_user_id.is_(None)))
        return [w.to_dict() for w in query.order_by(Workspace.id).all()]

    def get(self, workspace_id: int) -> Dict[str, Any]:
        return self._get(workspace_id).to_dict()

    def create(self, name: str, description: Optional[str] = None, blueprint: Optional[Blueprint] = None) -> Dict[str, Any]:
        return create_workspace(self.session, name, self.user_id, description, blueprint).to_dict()

    def update(self, workspace_id: int, name: Optional[str], description: Optional[str]) -> Dict[str, Any]:
        workspace = self._get(workspace_id)
        if name is not None:
            workspace.name = name
        if description is not None:
            workspace.description = description
        self.session.commit()
        return workspace.to_dict()

    def delete(self, workspace_id: int, force: bool = False) -> None:
        workspace = self._get(workspace_id)
        if self.session.query(Workspace).count() <= 1:
            raise WorkspaceError(409, "Cannot delete the only workspace")
        counts = {
            model.__tablename__: self.session.query(model).filter(model.workspace_id == workspace_id).count()
            for model in (Account, Transaction, MerchantRule, ImportBatch)
        }
        if any(counts.values()) and not force:
            raise WorkspaceError(409, f"Workspace has data {counts}; pass force=true to delete it with its data")
        for model in (Transaction, ImportBatch, MerchantRule, Account):  # children before parents
            self.session.query(model).filter(model.workspace_id == workspace_id).delete()
        self.session.delete(workspace)
        self.session.commit()

    # ------------------------------------------------------------------ blueprint

    def get_blueprint(self, workspace_id: int) -> Dict[str, Any]:
        workspace = self._get(workspace_id)
        return {"workspace_id": workspace.id, "version": workspace.blueprint_version, "blueprint": workspace.blueprint}

    def set_blueprint(self, workspace_id: int, blueprint: Blueprint) -> Dict[str, Any]:
        workspace = self._get(workspace_id)
        workspace.blueprint = blueprint.to_json()
        workspace.blueprint_version = (workspace.blueprint_version or 1) + 1
        workspace.updated_at = datetime.utcnow()
        self.session.commit()
        return {"workspace_id": workspace.id, "version": workspace.blueprint_version, "blueprint": workspace.blueprint}
