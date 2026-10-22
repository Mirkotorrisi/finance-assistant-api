"""upgrade_database: new, legacy (pre-workspace, untracked) and Alembic-tracked databases."""

import pytest
from sqlalchemy import create_engine, inspect, text

from src.database.migrate import BASELINE_REVISION, upgrade_database
from src.services.fingerprint import compute_fingerprint

LEGACY_SCHEMA = [
    """CREATE TABLE accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(200) NOT NULL, type VARCHAR(50) NOT NULL,
       currency VARCHAR(3) NOT NULL, is_active BOOLEAN NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
       current_balance FLOAT NOT NULL)""",
    """CREATE TABLE categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(100) NOT NULL UNIQUE, type VARCHAR(10) NOT NULL,
       color VARCHAR(7), created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)""",
    """CREATE TABLE transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER REFERENCES accounts(id), date DATE NOT NULL,
       amount FLOAT NOT NULL, category VARCHAR(100) NOT NULL, description VARCHAR(500) NOT NULL, currency VARCHAR(3),
       created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, category_id INTEGER REFERENCES categories(id))""",
    """CREATE TABLE merchant_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, pattern VARCHAR(200) NOT NULL,
       category VARCHAR(100) NOT NULL, created_at DATETIME NOT NULL)""",
    "CREATE UNIQUE INDEX ix_merchant_rules_pattern ON merchant_rules (pattern)",
    """INSERT INTO accounts (name, type, currency, is_active, created_at, updated_at, current_balance)
       VALUES ('Conto', 'checking', 'EUR', 1, '2026-01-01', '2026-01-01', 0)""",
    """INSERT INTO transactions (account_id, date, amount, category, description, currency, created_at, updated_at)
       VALUES (1, '2026-03-01', -42.5, 'Groceries', 'COOP  Milano', 'EUR', '2026-03-01', '2026-03-01'),
              (NULL, '2026-03-02', -9.9, 'caffè', 'Bar', 'EUR', '2026-03-02', '2026-03-02'),
              (NULL, '2026-03-03', 1500, 'Stipendio', 'ACME', 'EUR', '2026-03-03', '2026-03-03')""",
    "INSERT INTO merchant_rules (pattern, category, created_at) VALUES ('coop', 'Groceries', '2026-01-01')",
]


def legacy_engine(tmp_path, tracked: bool):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        for statement in LEGACY_SCHEMA:
            conn.execute(text(statement))
        if tracked:
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            conn.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": BASELINE_REVISION})
    return engine


def head_revision() -> str:
    from alembic.script import ScriptDirectory

    from src.database.migrate import alembic_config

    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def test_fresh_database_is_created_and_stamped_at_head(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    upgrade_database(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"workspaces", "accounts", "transactions", "merchant_rules", "import_batches", "user_preferences"} <= tables
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == head_revision()


@pytest.mark.parametrize("tracked", [False, True], ids=["untracked-legacy", "tracked-at-baseline"])
def test_legacy_data_moves_into_a_default_workspace(tmp_path, tracked):
    engine = legacy_engine(tmp_path, tracked)
    upgrade_database(engine)

    with engine.connect() as conn:
        workspaces = conn.execute(text("SELECT id, name, blueprint FROM workspaces")).fetchall()
        assert len(workspaces) == 1 and workspaces[0][1] == "Personale"
        ws_id = workspaces[0][0]
        for table in ("accounts", "transactions", "merchant_rules"):
            assert conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE workspace_id = :w"), {"w": ws_id}).scalar() >= 1
            assert conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE workspace_id IS NULL")).scalar() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar() == 3  # nothing lost
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == head_revision()

        import json

        blueprint = workspaces[0][2]
        blueprint = json.loads(blueprint) if isinstance(blueprint, str) else blueprint
        assert {c["key"] for c in blueprint["categories"]} == {"groceries", "caffe", "stipendio"}  # derived from the data

        # fingerprints were backfilled with the application's own function
        fp = conn.execute(text("SELECT fingerprint FROM transactions WHERE description = 'COOP  Milano'")).scalar()
        assert fp == compute_fingerprint(ws_id, 1, "2026-03-01", -42.5, "COOP Milano")
        assert conn.execute(text("SELECT COUNT(*) FROM transactions WHERE is_transfer")).scalar() == 0


def test_rules_become_unique_per_workspace_not_globally(tmp_path):
    engine = legacy_engine(tmp_path, tracked=False)
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO workspaces (name, blueprint, blueprint_version, created_at, updated_at) "
                          "VALUES ('Altro', '{}', 1, '2026-01-01', '2026-01-01')"))
        conn.execute(text("INSERT INTO merchant_rules (workspace_id, pattern, category, created_at) VALUES (2, 'coop', 'x', '2026-01-01')"))
    with pytest.raises(Exception, match="UNIQUE"):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO merchant_rules (workspace_id, pattern, category, created_at) VALUES (1, 'coop', 'y', '2026-01-01')"))


def test_upgrade_is_idempotent(tmp_path):
    engine = legacy_engine(tmp_path, tracked=False)
    upgrade_database(engine)
    upgrade_database(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM workspaces")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar() == 3


def test_migrated_schema_matches_the_models(tmp_path):
    """A migrated legacy database ends with the same columns as one created from the models."""
    legacy = legacy_engine(tmp_path, tracked=False)
    upgrade_database(legacy)
    fresh = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    upgrade_database(fresh)
    for table in ("accounts", "transactions", "merchant_rules", "workspaces", "import_batches"):
        assert {c["name"] for c in inspect(legacy).get_columns(table)} == {c["name"] for c in inspect(fresh).get_columns(table)}, table
