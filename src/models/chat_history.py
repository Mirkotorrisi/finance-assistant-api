"""Pydantic models of the chat history endpoints."""

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ChatMessageCreate(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(default="", max_length=200_000)
    components: Optional[List[dict[str, Any]]] = None
    tools: Optional[List[str]] = None
    error: Optional[str] = Field(default=None, max_length=5_000)
    backend: Optional[str] = Field(default=None, max_length=16)


class ChatSessionRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)
