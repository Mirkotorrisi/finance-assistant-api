"""Database configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class DatabaseConfig:
    """Database configuration settings."""
    
    # Connection details - can be overridden via environment variables
    HOST = os.getenv("DB_HOST", "ai-financial-assistant-bollette.e.aivencloud.com")
    PORT = int(os.getenv("DB_PORT", "22782"))
    DATABASE = os.getenv("DB_NAME", "defaultdb")
    USER = os.getenv("DB_USER", "avnadmin")
    PASSWORD = os.getenv("DB_PASSWORD", "")
    SSL_MODE = os.getenv("DB_SSL_MODE", "disable")
    
    @classmethod
    def mode(cls) -> str:
        """Which database to use: ``sqlite`` (a local file) or ``postgres``.

        ``FINANCE_DB`` forces one. Otherwise Postgres is used only when it has been configured
        (``DB_PASSWORD`` or ``DB_HOST`` set, as in Docker Compose or a remote database) and a
        local SQLite file is the zero-setup default.
        """
        forced = os.getenv("FINANCE_DB", "").strip().lower()
        if forced in ("sqlite", "postgres"):
            return forced
        return "postgres" if (os.getenv("DB_PASSWORD") or os.getenv("DB_HOST")) else "sqlite"

    @classmethod
    def sqlite_path(cls) -> Path:
        """Location of the SQLite file (``FINANCE_DB_PATH``, default ~/.finance-assistant/finance.db)."""
        return Path(os.getenv("FINANCE_DB_PATH", str(Path.home() / ".finance-assistant" / "finance.db")))

    @classmethod
    def resolve_url(cls) -> str:
        """SQLAlchemy URL for the selected mode (SQLite file or Postgres)."""
        if cls.mode() == "sqlite":
            return f"sqlite:///{cls.sqlite_path()}"
        return cls.get_database_url()

    @classmethod
    def get_database_url(cls) -> str:
        """Get the database URL for SQLAlchemy.
        
        Returns:
            Database connection URL
        """
        return (
            f"postgresql://{cls.USER}:{cls.PASSWORD}@"
            f"{cls.HOST}:{cls.PORT}/{cls.DATABASE}?sslmode={cls.SSL_MODE}"
        )
    
    @classmethod
    def is_development(cls) -> bool:
        """Check if the application is running in development mode.
        
        Returns:
            True if in development mode, False otherwise
        """
        env = os.getenv("ENVIRONMENT", "development").lower()
        return env == "development"
