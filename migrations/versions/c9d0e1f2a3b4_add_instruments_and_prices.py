"""Add instruments, daily prices, fx rates and the cash→securities account link

Market values for the portfolio: securities identified by ISIN and priced through a symbol, a daily close cache,
exchange rates, and ``accounts.securities_account_id`` (the investment account whose value the trades booked on a
cash account build). Idempotent, like the previous migrations.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-21 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    columns = {c["name"] for c in inspector.get_columns("accounts")}
    if "securities_account_id" not in columns:
        with op.batch_alter_table("accounts") as batch:
            batch.add_column(sa.Column("securities_account_id", sa.Integer(), sa.ForeignKey("accounts.id", name="fk_accounts_securities_account"), nullable=True))

    if "instruments" not in tables:
        op.create_table(
            "instruments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("isin", sa.String(length=12), nullable=True),
            sa.Column("key", sa.String(length=120), nullable=False, unique=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("type", sa.String(length=16), nullable=False, server_default="other"),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
            sa.Column("asset_class", sa.String(length=16), nullable=False, server_default="other"),
            sa.Column("valuation", sa.String(length=8), nullable=False, server_default="market"),
            sa.Column("price_symbol", sa.String(length=40), nullable=True),
            sa.Column("symbol_candidates", sa.JSON(), nullable=True),
            sa.Column("price_source", sa.String(length=24), nullable=True),
            sa.Column("manual_price", sa.Float(), nullable=True),
            sa.Column("manual_price_date", sa.Date(), nullable=True),
            sa.Column("last_error", sa.String(length=300), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_instruments_isin", "instruments", ["isin"], unique=True)
    else:
        inst_columns = {c["name"] for c in inspector.get_columns("instruments")}
        if "symbol_candidates" not in inst_columns:  # databases that ran the first version of this migration
            with op.batch_alter_table("instruments") as batch:
                batch.add_column(sa.Column("symbol_candidates", sa.JSON(), nullable=True))
    if "prices" not in tables:
        op.create_table(
            "prices",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("close", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
            sa.Column("source", sa.String(length=24), nullable=False, server_default="alphavantage"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("instrument_id", "date", name="uix_prices_instrument_date"),
        )
        op.create_index("ix_prices_instrument_id", "prices", ["instrument_id"])
        op.create_index("ix_prices_date", "prices", ["date"])
    if "fx_rates" not in tables:
        op.create_table(
            "fx_rates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("base", sa.String(length=3), nullable=False),
            sa.Column("quote", sa.String(length=3), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("rate", sa.Float(), nullable=False),
            sa.Column("source", sa.String(length=24), nullable=False, server_default="alphavantage"),
            sa.UniqueConstraint("base", "quote", "date", name="uix_fx_rates_pair_date"),
        )
        op.create_index("ix_fx_rates_date", "fx_rates", ["date"])


def downgrade() -> None:
    op.drop_table("fx_rates")
    op.drop_table("prices")
    op.drop_table("instruments")
    with op.batch_alter_table("accounts") as batch:
        batch.drop_column("securities_account_id")
