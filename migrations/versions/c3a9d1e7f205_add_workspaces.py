"""Add workspaces (projects), import batches and per-transaction import bookkeeping

Existing data moves into a default "Personale" workspace whose blueprint lists the categories already in use.
Idempotent: tables created by ``create_all`` beforehand and already-added columns are left alone.

Revision ID: c3a9d1e7f205
Revises: b7e3f0a1c9d2
Create Date: 2026-10-22 12:00:00.000000

"""
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a9d1e7f205'
down_revision: Union[str, Sequence[str], None] = 'b7e3f0a1c9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCOPED_TABLES = ("accounts", "transactions", "merchant_rules")


def _slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")[:64] or "x"


def _fingerprint(workspace_id, account_id, day, amount, description) -> str:
    """Frozen copy of src.services.fingerprint.compute_fingerprint (migrations must not drift with the app)."""
    text = " ".join(str(description or "").lower().split())
    key = f"{workspace_id}|{account_id if account_id is not None else 'none'}|{str(day)[:10]}|{float(amount):.2f}|{text}"
    return hashlib.sha256(key.encode()).hexdigest()


def _columns(inspector, table):
    return {c["name"] for c in inspector.get_columns(table)}


def _create_workspaces_tables(inspector) -> None:
    tables = set(inspector.get_table_names())
    if "workspaces" not in tables:
        op.create_table(
            "workspaces",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("owner_user_id", sa.String(length=64), nullable=True),
            sa.Column("blueprint", sa.JSON(), nullable=False),
            sa.Column("blueprint_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_workspaces_owner_user_id", "workspaces", ["owner_user_id"])
    if "import_batches" not in tables:
        op.create_table(
            "import_batches",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("workspace_id", sa.Integer(), nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=True),
            sa.Column("filename", sa.String(length=300), nullable=True),
            sa.Column("file_hash", sa.String(length=64), nullable=True),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("added_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_import_batches_workspace_id", "import_batches", ["workspace_id"])
        op.create_index("ix_import_batches_file_hash", "import_batches", ["file_hash"])


def _default_workspace_id(bind, inspector) -> int:
    row = bind.execute(sa.text("SELECT id FROM workspaces ORDER BY id LIMIT 1")).fetchone()
    if row:
        return row[0]
    names = []
    if "transactions" in inspector.get_table_names():
        names = [r[0] for r in bind.execute(sa.text("SELECT DISTINCT category FROM transactions WHERE category IS NOT NULL"))]
    seen = {}
    for raw in names:
        seen.setdefault(_slugify(raw), raw.strip())
    blueprint = {
        "schema_version": 1,
        "name": "Personale",
        "description": "Created from the categories already in use.",
        "currency": "EUR",
        "instructions": "",
        "categories": [{"key": k, "label": label, "description": "", "examples": [], "kind": "expense",
                        "attributes": {}, "children": []} for k, label in sorted(seen.items())],
        "groups": [], "dimensions": [], "reports": [], "rules": [], "settings": {"detect_transfers": True},
    }
    now = datetime.utcnow()
    workspaces = sa.table(
        "workspaces",
        sa.column("name"), sa.column("blueprint", sa.JSON()), sa.column("blueprint_version"),
        sa.column("created_at"), sa.column("updated_at"),
    )
    bind.execute(workspaces.insert().values(
        name="Personale", blueprint=blueprint, blueprint_version=1, created_at=now, updated_at=now
    ))
    return bind.execute(sa.text("SELECT id FROM workspaces ORDER BY id LIMIT 1")).fetchone()[0]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _create_workspaces_tables(inspector)
    default_id = _default_workspace_id(bind, inspector)

    # ---- workspace_id on the scoped tables: add, backfill, make required
    for table in SCOPED_TABLES:
        if table not in sa.inspect(bind).get_table_names():
            continue
        if "workspace_id" not in _columns(sa.inspect(bind), table):
            with op.batch_alter_table(table) as batch:
                batch.add_column(sa.Column("workspace_id", sa.Integer(), nullable=True))
        bind.execute(sa.text(f"UPDATE {table} SET workspace_id = :ws WHERE workspace_id IS NULL"), {"ws": default_id})
        with op.batch_alter_table(table) as batch:
            batch.alter_column("workspace_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(f"fk_{table}_workspace_id", "workspaces", ["workspace_id"], ["id"])
        if "ix_%s_workspace_id" % table not in {i["name"] for i in sa.inspect(bind).get_indexes(table)}:
            op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])

    # ---- transactions: import bookkeeping
    inspector = sa.inspect(bind)
    if "transactions" in inspector.get_table_names():
        cols = _columns(inspector, "transactions")
        with op.batch_alter_table("transactions") as batch:
            if "fingerprint" not in cols:
                batch.add_column(sa.Column("fingerprint", sa.String(length=64), nullable=True))
            if "import_batch_id" not in cols:
                batch.add_column(sa.Column("import_batch_id", sa.Integer(), nullable=True))
            if "is_transfer" not in cols:
                batch.add_column(sa.Column("is_transfer", sa.Boolean(), nullable=False, server_default=sa.false()))
            if "transfer_pair_id" not in cols:
                batch.add_column(sa.Column("transfer_pair_id", sa.Integer(), nullable=True))
        idx = {i["name"] for i in sa.inspect(bind).get_indexes("transactions")}
        if "ix_transactions_fingerprint" not in idx:
            op.create_index("ix_transactions_fingerprint", "transactions", ["fingerprint"])
        if "ix_transactions_import_batch_id" not in idx:
            op.create_index("ix_transactions_import_batch_id", "transactions", ["import_batch_id"])
        rows = bind.execute(sa.text(
            "SELECT id, workspace_id, account_id, date, amount, description FROM transactions WHERE fingerprint IS NULL"
        )).fetchall()
        for row in rows:
            bind.execute(
                sa.text("UPDATE transactions SET fingerprint = :fp WHERE id = :id"),
                {"fp": _fingerprint(row[1], row[2], row[3], row[4], row[5]), "id": row[0]},
            )

    # ---- merchant rules: a pattern is unique per workspace, not globally
    if "merchant_rules" in sa.inspect(bind).get_table_names():
        indexes = {i["name"]: i for i in sa.inspect(bind).get_indexes("merchant_rules")}
        legacy = indexes.get("ix_merchant_rules_pattern")
        if legacy and legacy.get("unique"):
            op.drop_index("ix_merchant_rules_pattern", table_name="merchant_rules")
            op.create_index("ix_merchant_rules_pattern", "merchant_rules", ["pattern"])
        uniques = {u["name"] for u in sa.inspect(bind).get_unique_constraints("merchant_rules")}
        if "uix_merchant_rules_workspace_pattern" not in uniques:
            with op.batch_alter_table("merchant_rules") as batch:
                batch.create_unique_constraint("uix_merchant_rules_workspace_pattern", ["workspace_id", "pattern"])


def downgrade() -> None:
    raise NotImplementedError("Downgrading below workspaces would merge projects; restore from a backup instead.")
