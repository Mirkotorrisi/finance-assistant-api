"""Shared test helpers."""

from src.database.workspaces import create_workspace


def scope_session(session, name: str = "Test"):
    """Give a hand-built session a workspace, like the application's session factory does."""
    workspace = create_workspace(session, name)
    session.info["workspace_id"] = workspace.id
    return workspace
