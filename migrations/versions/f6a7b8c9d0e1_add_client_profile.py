"""Add the client profile, its versions and the advisor's decision log

The advisor's memory of the person behind a workspace (situation, goals, risk, investment policy), kept in the
database and versioned, plus the log of recommendations and what became of them. Idempotent, like the previous
migrations (a fresh database already has the tables from ``create_all``).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "client_profiles" not in tables:
        op.create_table(
            "client_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("document", sa.JSON(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_by", sa.String(length=16), nullable=False, server_default="user"),
            sa.Column("ips_approved_at", sa.DateTime(), nullable=True),
            sa.Column("ips_approved_hash", sa.String(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_client_profiles_workspace_id", "client_profiles", ["workspace_id"], unique=True)
    if "client_profile_versions" not in tables:
        op.create_table(
            "client_profile_versions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("document", sa.JSON(), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=False, server_default="user"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("workspace_id", "version", name="uix_client_profile_versions_ws_version"),
        )
        op.create_index("ix_client_profile_versions_workspace_id", "client_profile_versions", ["workspace_id"])
    if "advisor_decisions" not in tables:
        op.create_table(
            "advisor_decisions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=False),
            sa.Column("data_refs", sa.JSON(), nullable=False),
            sa.Column("ips_refs", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
            sa.Column("profile_version", sa.Integer(), nullable=True),
            sa.Column("outcome", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_advisor_decisions_workspace_id", "advisor_decisions", ["workspace_id"])
        op.create_index("ix_advisor_decisions_date", "advisor_decisions", ["date"])


def downgrade() -> None:
    op.drop_table("advisor_decisions")
    op.drop_table("client_profile_versions")
    op.drop_table("client_profiles")
