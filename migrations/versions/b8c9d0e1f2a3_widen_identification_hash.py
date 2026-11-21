"""Widen bank_account_links.identification_hash to 512 characters

The bank's stable account identity is an opaque token: UniCredit's is 133 characters, longer than the 128 first
chosen. Idempotent: databases created after the fix already have the wider column.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "bank_account_links" not in inspector.get_table_names():
        return
    column = next((c for c in inspector.get_columns("bank_account_links") if c["name"] == "identification_hash"), None)
    length = getattr(column["type"], "length", None) if column else None
    if length is not None and length >= 512:
        return
    with op.batch_alter_table("bank_account_links") as batch:
        batch.alter_column("identification_hash", type_=sa.String(length=512), existing_type=sa.String(length=128), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("bank_account_links") as batch:
        batch.alter_column("identification_hash", type_=sa.String(length=128), existing_type=sa.String(length=512), existing_nullable=False)
