"""Database mode selection and the persistent SQLite default."""

import pytest
from src.config.database import DatabaseConfig
from src.database import init as db_init
from src.database.models import Account


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("FINANCE_DB", "DB_PASSWORD", "DB_HOST", "FINANCE_DB_PATH"):
        monkeypatch.delenv(var, raising=False)


def test_defaults_to_sqlite_when_nothing_is_configured():
    assert DatabaseConfig.mode() == "sqlite"


@pytest.mark.parametrize("var,value", [("DB_PASSWORD", "secret"), ("DB_HOST", "db")])
def test_configured_postgres_keeps_working(monkeypatch, var, value):
    monkeypatch.setenv(var, value)
    assert DatabaseConfig.mode() == "postgres"


def test_finance_db_overrides_detection(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("FINANCE_DB", "sqlite")
    assert DatabaseConfig.mode() == "sqlite"
    monkeypatch.delenv("DB_PASSWORD")
    monkeypatch.setenv("FINANCE_DB", "postgres")
    assert DatabaseConfig.mode() == "postgres"


def test_sqlite_file_persists_across_restarts(monkeypatch, tmp_path):
    db_file = tmp_path / "nested" / "finance.db"
    monkeypatch.setenv("FINANCE_DB_PATH", str(db_file))

    db_init.init_database()
    with db_init.get_db_session() as session:
        session.add(Account(name="Cash", type="cash"))
        session.commit()
    db_init.close_database()
    assert db_file.exists()

    db_init.init_database()  # simulated restart
    with db_init.get_db_session() as session:
        assert [a.name for a in session.query(Account).all()] == ["Cash"]
    db_init.close_database()
