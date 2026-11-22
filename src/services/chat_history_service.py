"""Chat history: the conversations with the assistant, per workspace and user.

The gateway appends a message as each turn starts (the user's) and ends (the assistant's); the UI lists and
reopens the sessions. Sessions are personal: every call is filtered by the ``user_id`` the request identifies as,
on top of the workspace scope the session already enforces.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.clock import utc_now
from src.database.models import ChatMessage, ChatSession

ROLES = ("user", "assistant")
TITLE_MAX = 60
MAX_LIST = 200


def derive_title(text: str) -> str:
    """The first words of a message, on one line, cut at a word boundary with an ellipsis."""
    flat = " ".join((text or "").split())
    if len(flat) <= TITLE_MAX:
        return flat
    cut = flat[: TITLE_MAX + 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:.") + "…"


class ChatHistoryService:
    def __init__(self, session: Session, user_id: str):
        self.session = session
        self.user_id = user_id
        self.workspace_id: int = session.info["workspace_id"]

    # ------------------------------------------------------------------ sessions

    def _query(self):
        return self.session.query(ChatSession).filter(ChatSession.user_id == self.user_id)

    def _get(self, session_id: str) -> ChatSession:
        row = self._query().filter(ChatSession.id == session_id).one_or_none()
        if row is None:
            raise LookupError(f"Chat session {session_id} not found")
        return row

    def list_sessions(self, limit: int = 50, search: str | None = None) -> list[dict[str, Any]]:
        """Most recently active first; ``search`` matches the title or any message text."""
        q = self._query()
        if search and search.strip():
            needle = f"%{search.strip().lower()}%"
            matching = (
                self.session.query(ChatMessage.session_id)
                .filter(func.lower(ChatMessage.content).like(needle))
                .distinct()
            )
            q = q.filter((func.lower(ChatSession.title).like(needle)) | (ChatSession.id.in_(matching)))
        rows = q.order_by(ChatSession.updated_at.desc()).limit(max(1, min(limit, MAX_LIST))).all()
        return [r.to_dict() for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any]:
        row = self._get(session_id)
        messages = (
            self.session.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
            .all()
        )
        return {**row.to_dict(), "messages": [m.to_dict() for m in messages]}

    def rename(self, session_id: str, title: str) -> dict[str, Any]:
        row = self._get(session_id)
        clean = " ".join(title.split())
        if not clean:
            raise ValueError("The title cannot be empty")
        row.title = clean[:200]
        row.updated_at = utc_now()
        self.session.commit()
        return row.to_dict()

    def delete(self, session_id: str) -> None:
        row = self._get(session_id)
        self.session.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete(synchronize_session=False)
        self.session.delete(row)
        self.session.commit()

    def clear(self) -> int:
        """Delete every session of this user in the workspace; returns how many."""
        ids = [r.id for r in self._query().all()]
        if ids:
            self.session.query(ChatMessage).filter(ChatMessage.session_id.in_(ids)).delete(synchronize_session=False)
            self._query().delete(synchronize_session=False)
            self.session.commit()
        return len(ids)

    # ------------------------------------------------------------------ messages

    def append(
        self,
        session_id: str,
        role: str,
        content: str,
        components: list[dict[str, Any]] | None = None,
        tools: list[str] | None = None,
        error: str | None = None,
        backend: str | None = None,
    ) -> dict[str, Any]:
        """Add a message, creating the session on its first one (titled after the first user message).

        A session that exists for another user is not touched: the id is the client's, and a collision would let
        one browser read another's conversation, so it is refused.
        """
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        row = self.session.query(ChatSession).filter(ChatSession.id == session_id).one_or_none()
        if row is not None and row.user_id != self.user_id:
            raise PermissionError("This chat session belongs to another user")
        now = utc_now()
        if row is None:
            row = ChatSession(id=session_id, user_id=self.user_id, title="", backend=backend, message_count=0, created_at=now)
            self.session.add(row)
        if not row.title and role == "user" and content.strip():
            row.title = derive_title(content)
        if backend:
            row.backend = backend
        row.message_count = (row.message_count or 0) + 1
        row.updated_at = now
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content or "",
            components=components or None,
            tools=tools or None,
            error=error,
            created_at=now,
        )
        self.session.add(message)
        try:
            self.session.commit()
        except IntegrityError:
            # the id exists in another workspace (the scoped lookup above cannot see it): same answer as above
            self.session.rollback()
            raise PermissionError("This chat session id is already in use")
        return {"session": row.to_dict(), "message": message.to_dict()}

    def transcript(self, session_id: str, max_messages: int = 20, max_chars: int = 12_000) -> list[dict[str, str]]:
        """The last messages as plain role/content pairs, within a size budget, for an agent that lost the
        conversation (gateway restart, expired session) to pick it up again."""
        rows = (
            self.session.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.session_id.in_(self._query().with_entities(ChatSession.id)))
            .order_by(ChatMessage.id.desc())
            .limit(max(1, max_messages))
            .all()
        )
        out: list[dict[str, str]] = []
        budget = max_chars
        for m in rows:  # newest first; stop when the budget is spent
            text = (m.content or "").strip()
            if not text:
                continue
            if len(text) > budget:
                if not out:  # at least the latest message, cut
                    out.append({"role": m.role, "content": text[-budget:]})
                break
            budget -= len(text)
            out.append({"role": m.role, "content": text})
        out.reverse()
        return out
