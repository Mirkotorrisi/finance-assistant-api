"""Remove monthly_account_snapshots table

Revision ID: a1b2c3d4e5f6
Revises: 284d9a442238
Create Date: 2026-03-07 08:23:41.847132

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '284d9a442238'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the monthly_account_snapshots table."""
    op.drop_table('monthly_account_snapshots')


def downgrade() -> None:
    """Re-create the monthly_account_snapshots table."""
    op.create_table(
        'monthly_account_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('starting_balance', sa.Float(), nullable=False),
        sa.Column('ending_balance', sa.Float(), nullable=False),
        sa.Column('total_income', sa.Float(), nullable=False),
        sa.Column('total_expense', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'year', 'month', name='uix_account_year_month')
    )
    op.create_index(op.f('ix_monthly_account_snapshots_account_id'), 'monthly_account_snapshots', ['account_id'])
    op.create_index(op.f('ix_monthly_account_snapshots_year'), 'monthly_account_snapshots', ['year'])
    op.create_index(op.f('ix_monthly_account_snapshots_month'), 'monthly_account_snapshots', ['month'])
