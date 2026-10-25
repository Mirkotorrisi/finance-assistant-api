"""Add balance snapshots

What an account held on a day, as observed by the user. Checkpoints to reconcile transactions against, and the
record of accounts that have no transactions or whose value is not a cash balance. Idempotent, like the previous
migrations (a fresh database already has the table from ``create_all``).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "balance_snapshots" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "balance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("account_id", "date", name="uix_balance_snapshots_account_date"),
    )
    op.create_index("ix_balance_snapshots_workspace_id", "balance_snapshots", ["workspace_id"])
    op.create_index("ix_balance_snapshots_account_id", "balance_snapshots", ["account_id"])
    op.create_index("ix_balance_snapshots_date", "balance_snapshots", ["date"])


def downgrade() -> None:
    op.drop_table("balance_snapshots")
