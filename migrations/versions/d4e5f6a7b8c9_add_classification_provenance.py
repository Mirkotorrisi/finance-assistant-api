"""Add classification provenance to transactions

Who decided each category (and how sure), whether the user confirmed it, and a merchant key used to group and
remember merchants. Existing rows are 'legacy' and unreviewed: the data is not wrong, it is just not confirmed.
Idempotent, like the previous migrations.

Revision ID: d4e5f6a7b8c9
Revises: c3a9d1e7f205
Create Date: 2026-10-22 18:00:00.000000

"""
import re
import unicodedata
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3a9d1e7f205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOISE = {
    "pagamento", "pos", "acquisto", "carta", "addebito", "sdd", "bonifico", "operazione", "transazione", "trn",
    "ref", "rif", "payment", "purchase", "card", "contactless", "debit", "visa", "mastercard", "nfc", "pagobancomat",
}


def _merchant_key(description) -> str:
    """Frozen copy of src.services.merchant.merchant_key (migrations must not drift with the app)."""
    ascii_text = unicodedata.normalize("NFKD", description or "").encode("ascii", "ignore").decode().lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", ascii_text) if t]
    kept = [t for t in tokens if not any(c.isdigit() for c in t) and len(t) > 1 and t not in _NOISE]
    return " ".join(kept[:2]) or "unknown"


def upgrade() -> None:
    bind = op.get_bind()
    if "transactions" not in sa.inspect(bind).get_table_names():
        return
    cols = {c["name"] for c in sa.inspect(bind).get_columns("transactions")}
    with op.batch_alter_table("transactions") as batch:
        if "category_source" not in cols:
            batch.add_column(sa.Column("category_source", sa.String(length=16), nullable=False, server_default="legacy"))
        if "confidence" not in cols:
            batch.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        if "reviewed" not in cols:
            batch.add_column(sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "merchant_key" not in cols:
            batch.add_column(sa.Column("merchant_key", sa.String(length=120), nullable=True))
    if "ix_transactions_merchant_key" not in {i["name"] for i in sa.inspect(bind).get_indexes("transactions")}:
        op.create_index("ix_transactions_merchant_key", "transactions", ["merchant_key"])
    for row in bind.execute(sa.text("SELECT id, description FROM transactions WHERE merchant_key IS NULL")).fetchall():
        bind.execute(sa.text("UPDATE transactions SET merchant_key = :k WHERE id = :id"), {"k": _merchant_key(row[1]), "id": row[0]})


def downgrade() -> None:
    raise NotImplementedError("Restore from a backup instead of dropping provenance.")
