"""Pydantic models for workspace (project) endpoints."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.blueprint import Blueprint


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Project name, e.g. 'Famiglia' or 'Studio'.")
    description: Optional[str] = None
    blueprint: Optional[Blueprint] = Field(
        default=None, description="Initial blueprint. When omitted, an empty one named after the project is used."
    )


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    owner_user_id: Optional[str] = None
    blueprint_version: int


class BlueprintResponse(BaseModel):
    workspace_id: int
    version: int
    blueprint: Dict[str, Any]
