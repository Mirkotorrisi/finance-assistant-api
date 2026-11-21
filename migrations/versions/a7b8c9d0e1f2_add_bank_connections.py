"""Add bank connections (PSD2 consents), the bank account links and the provenance of transactions

Transactions get ``source`` (statement | bank | manual | adjustment), ``external_id`` (the bank's reference) and
``duplicate_of`` (a suspect twin to settle). Idempotent, like the previous migrations.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-21 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    columns = {c["name"] for c in inspector.get_columns("transactions")}
    with op.batch_alter_table("transactions") as batch:
        if "source" not in columns:
            batch.add_column(sa.Column("source", sa.String(length=16), nullable=False, server_default="statement"))
        if "external_id" not in columns:
            batch.add_column(sa.Column("external_id", sa.String(length=128), nullable=True))
        if "duplicate_of" not in columns:
            batch.add_column(sa.Column("duplicate_of", sa.Integer(), nullable=True))
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("transactions")}
    if "ix_transactions_external_id" not in indexes:
        op.create_index("ix_transactions_external_id", "transactions", ["external_id"])

    if "bank_connections" not in tables:
        op.create_table(
            "bank_connections",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="enablebanking"),
            sa.Column("aspsp_name", sa.String(length=120), nullable=False),
            sa.Column("aspsp_country", sa.String(length=2), nullable=False),
            sa.Column("psu_type", sa.String(length=16), nullable=False, server_default="personal"),
            sa.Column("session_ref", sa.String(length=64), nullable=False, unique=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("valid_until", sa.DateTime(), nullable=True),
            sa.Column("sync_balances", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sync_transactions", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_sync_at", sa.DateTime(), nullable=True),
            sa.Column("last_sync_status", sa.String(length=16), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_bank_connections_workspace_id", "bank_connections", ["workspace_id"])
    if "bank_account_links" not in tables:
        op.create_table(
            "bank_account_links",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("connection_id", sa.Integer(), sa.ForeignKey("bank_connections.id"), nullable=False),
            sa.Column("identification_hash", sa.String(length=128), nullable=False),
            sa.Column("bank_uid", sa.String(length=64), nullable=True),
            sa.Column("iban_masked", sa.String(length=40), nullable=True),
            sa.Column("label", sa.String(length=200), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=True),
            sa.Column("cash_account_type", sa.String(length=8), nullable=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_transaction_date", sa.Date(), nullable=True),
            sa.Column("last_balance", sa.Float(), nullable=True),
            sa.Column("last_balance_date", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("connection_id", "identification_hash", name="uix_bank_account_links_conn_hash"),
        )
        op.create_index("ix_bank_account_links_workspace_id", "bank_account_links", ["workspace_id"])
        op.create_index("ix_bank_account_links_connection_id", "bank_account_links", ["connection_id"])
        op.create_index("ix_bank_account_links_account_id", "bank_account_links", ["account_id"])


def downgrade() -> None:
    op.drop_table("bank_account_links")
    op.drop_table("bank_connections")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_column("duplicate_of")
        batch.drop_column("external_id")
        batch.drop_column("source")
