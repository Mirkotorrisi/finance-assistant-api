"""Bring any database (new, legacy, or tracked by Alembic) to the current schema.

History: the first tables were created with ``create_all`` before Alembic tracked them, and the original
migrations assume a pre-existing schema. So:

* a database with no tables is created from the models and stamped at head;
* a database with tables but no ``alembic_version`` is stamped at the last pre-workspace revision;
* then ``alembic upgrade head`` runs. The migrations are idempotent, so missing tables created here first
  never clash with them.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from src.database.models import Base

BASELINE_REVISION = "b7e3f0a1c9d2"  # schema before workspaces
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def alembic_config(connection=None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def upgrade_database(engine: Engine) -> None:
    with engine.begin() as connection:
        existing = set(inspect(connection).get_table_names())
        config = alembic_config(connection)
        Base.metadata.create_all(connection)  # only creates what is missing
        if "alembic_version" not in existing:
            command.stamp(config, "head" if not existing else BASELINE_REVISION)
        command.upgrade(config, "head")
