"""Add the chat history: sessions and their messages

Conversations with the assistant, so the chat page can list and reopen them (before this the messages lived only
in the browser tab). Idempotent, like the previous migrations (a fresh database already has the tables from
``create_all``).

Revision ID: f0a1b2c3d4e5
Revises: e1f2a3b4c5d6
Create Date: 2026-11-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "chat_sessions" not in tables:
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.String(length=80), primary_key=True),
            sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("user_id", sa.String(length=80), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("backend", sa.String(length=16), nullable=True),
            sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_chat_sessions_workspace_id", "chat_sessions", ["workspace_id"])
        op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
        op.create_index("ix_chat_sessions_updated_at", "chat_sessions", ["updated_at"])
    if "chat_messages" not in tables:
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("session_id", sa.String(length=80), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("components", sa.JSON(), nullable=True),
            sa.Column("tools", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_chat_messages_workspace_id", "chat_messages", ["workspace_id"])
        op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
