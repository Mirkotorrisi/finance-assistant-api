"""Add instruments.symbol_candidates (other listings to try when a symbol gives no data)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-11-21 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "instruments" not in inspector.get_table_names():
        return
    if "symbol_candidates" in {c["name"] for c in inspector.get_columns("instruments")}:
        return
    with op.batch_alter_table("instruments") as batch:
        batch.add_column(sa.Column("symbol_candidates", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instruments") as batch:
        batch.drop_column("symbol_candidates")
