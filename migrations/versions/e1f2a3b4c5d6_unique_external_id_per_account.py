"""Unique (account_id, external_id) on transactions

The import deduplicates on the bank's reference before inserting; without a database guard two imports running at
once (a bank sync and a statement upload of the same rows) both pass the check and both insert. Partial index:
rows without a reference are not constrained. Idempotent; if a database already holds duplicates the index is not
created and a warning is printed (the rows must be settled by hand first).

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-11-21 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "uix_transactions_account_external_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "transactions" not in inspector.get_table_names():
        return
    if any(ix["name"] == INDEX for ix in inspector.get_indexes("transactions")):
        return
    duplicates = bind.execute(sa.text(
        "SELECT COUNT(*) FROM (SELECT account_id, external_id FROM transactions "
        "WHERE external_id IS NOT NULL GROUP BY account_id, external_id HAVING COUNT(*) > 1) d"
    )).scalar()
    if duplicates:
        print(f"WARNING: {duplicates} (account, external_id) pairs are duplicated; {INDEX} not created")
        return
    op.create_index(
        INDEX, "transactions", ["account_id", "external_id"], unique=True,
        sqlite_where=sa.text("external_id IS NOT NULL"), postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if any(ix["name"] == INDEX for ix in sa.inspect(bind).get_indexes("transactions")):
        op.drop_index(INDEX, table_name="transactions")
