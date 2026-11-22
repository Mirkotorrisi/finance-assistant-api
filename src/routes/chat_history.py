"""Chat history: list, reopen, rename and delete the conversations with the assistant.

Sessions are personal (``X-User-Id``; a missing header is ``anonymous``) inside the current workspace. The gateway
writes the messages as the turns run; the UI reads them.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from src.models.chat_history import ChatMessageCreate, ChatSessionRename
from src.routes.deps import resolve_workspace_id
from src.services.chat_history_service import ChatHistoryService

router = APIRouter(prefix="/api/chat-sessions", tags=["chat-history"])

SESSION_ID = r"^[A-Za-z0-9_.:-]{1,80}$"


def get_chat_history_service(
    workspace_id: int = Depends(resolve_workspace_id),
    x_user_id: Optional[str] = Header(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,80}$"),
):
    from src.database.init import get_db_session

    session = get_db_session(workspace_id)
    try:
        yield ChatHistoryService(session, x_user_id or "anonymous")
    finally:
        session.close()


def _check_id(session_id: str) -> str:
    import re

    if not re.match(SESSION_ID, session_id):
        raise HTTPException(status_code=422, detail="Invalid session id")
    return session_id


@router.get("", summary="The user's conversations in this project, most recent first")
def list_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    search: Optional[str] = Query(default=None, max_length=200),
    service: ChatHistoryService = Depends(get_chat_history_service),
) -> list[dict[str, Any]]:
    return service.list_sessions(limit, search)


@router.delete("", summary="Delete every conversation of the user in this project")
def clear_sessions(service: ChatHistoryService = Depends(get_chat_history_service)) -> dict[str, int]:
    return {"deleted": service.clear()}


@router.get("/{session_id}", summary="A conversation with its messages")
def get_session(session_id: str, service: ChatHistoryService = Depends(get_chat_history_service)) -> dict[str, Any]:
    try:
        return service.get_session(_check_id(session_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{session_id}/transcript", summary="The last messages as role/content pairs")
def get_transcript(
    session_id: str,
    max_messages: int = Query(default=20, ge=1, le=200),
    max_chars: int = Query(default=12_000, ge=200, le=100_000),
    service: ChatHistoryService = Depends(get_chat_history_service),
) -> dict[str, Any]:
    """What an agent that lost the conversation needs to pick it up again. Empty for an unknown session."""
    return {"messages": service.transcript(_check_id(session_id), max_messages, max_chars)}


@router.post("/{session_id}/messages", status_code=201, summary="Append a message (creates the session on the first one)")
def append_message(
    session_id: str, body: ChatMessageCreate, service: ChatHistoryService = Depends(get_chat_history_service)
) -> dict[str, Any]:
    try:
        return service.append(
            _check_id(session_id), body.role, body.content, body.components, body.tools, body.error, body.backend
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.patch("/{session_id}", summary="Rename a conversation")
def rename_session(
    session_id: str, body: ChatSessionRename, service: ChatHistoryService = Depends(get_chat_history_service)
) -> dict[str, Any]:
    try:
        return service.rename(_check_id(session_id), body.title)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/{session_id}", summary="Delete a conversation")
def delete_session(session_id: str, service: ChatHistoryService = Depends(get_chat_history_service)) -> dict[str, str]:
    try:
        service.delete(_check_id(session_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"message": "deleted"}
