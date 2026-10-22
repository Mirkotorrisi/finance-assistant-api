"""Database initialization and session management."""

import sys
from typing import Generator, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.config.database import DatabaseConfig
from src.database import scope  # noqa: F401  (registers the workspace scoping events)
from src.database.migrate import upgrade_database
from src.database.models import Base
from src.database.workspaces import default_workspace_id

# Global variables
engine = None
SessionLocal = None


def init_database() -> None:
    """Initialize the database connection and create tables if in development mode.
    
    This function:
    - Creates the database engine
    - Creates a session factory
    - In development mode: automatically creates all tables
    """
    global engine, SessionLocal

    if DatabaseConfig.mode() == "sqlite":
        _init_sqlite_file()
        return

    try:
        database_url = DatabaseConfig.get_database_url()
        
        # Check if password is set
        if not DatabaseConfig.PASSWORD:
            print("WARNING: DB_PASSWORD not set in environment variables. Database connection will fail.")
            print("Please set DB_PASSWORD in your .env file")
        
        # Create engine
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=False  # Set to True for SQL query logging
        )
        
        # Create session factory
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            print("✓ Database connection successful")
        
        # In development mode, create tables automatically
        if DatabaseConfig.is_development():
            print("Running in DEVELOPMENT mode - applying migrations...")
            upgrade_database(engine)
            _ensure_default_workspace()
            print("✓ Database schema up to date")
        else:
            print("Running in PRODUCTION mode - Skipping automatic table creation")
            
    except (OperationalError, Exception) as e:
        print(f"WARNING: Database initialization failed: {e}")
        print("Falling back to in-memory SQLite storage...")
        
        try:
            # Fallback to in-memory SQLite
            engine = create_engine(
                "sqlite:///:memory:",
                connect_args={"check_same_thread": False},
                poolclass=None,
                echo=False
            )
            
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            
            # Create tables
            Base.metadata.create_all(bind=engine)
            _ensure_default_workspace()
            print("✓ In-memory database initialized successfully")
            
        except Exception as fallback_error:
            print(f"CRITICAL: Failed to initialize in-memory fallback: {fallback_error}")
            raise fallback_error


def _init_sqlite_file() -> None:
    """Persistent local SQLite database: no server, tables created on startup."""
    global engine, SessionLocal

    path = DatabaseConfig.sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    upgrade_database(engine)
    _ensure_default_workspace()
    print(f"✓ SQLite database ready at {path}")


def _ensure_default_workspace() -> None:
    """A fresh database starts with a "Personale" project, so it is always the oldest (default) one."""
    session = SessionLocal()
    try:
        default_workspace_id(session)
    finally:
        session.close()


def get_db(workspace_id: Optional[int] = None) -> Generator[Session, None, None]:
    """Yield a workspace-scoped database session and close it afterwards."""
    db = get_db_session(workspace_id)
    try:
        yield db
    finally:
        db.close()


def get_db_session(workspace_id: Optional[int] = None) -> Session:
    """Open a session scoped to ``workspace_id`` (default: the default workspace).

    Note: The caller is responsible for closing the session.
    """
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    session = SessionLocal()
    if workspace_id is None:
        workspace_id = default_workspace_id(session)
    session.info["workspace_id"] = workspace_id
    return session


def get_unscoped_session() -> Session:
    """A session that sees every workspace. Only for workspace management and request resolution."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return SessionLocal()


def close_database() -> None:
    """Close database connections and dispose of the engine."""
    global engine
    
    if engine:
        engine.dispose()
        print("✓ Database connections closed")
