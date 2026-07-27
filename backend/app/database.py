"""
database.py — SQLAlchemy engine, session factory, and Base declarative.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a DB session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Create all tables defined via Base subclasses. Called at app startup."""
    from app.models import project, image, schedule, worker, plan  # noqa: F401  (import to register models)
    Base.metadata.create_all(bind=engine)
    _migrate_columns()


def _migrate_columns() -> None:
    """
    Additive column migrations for existing databases — create_all() only
    creates missing tables, it never alters existing ones. Each statement is
    idempotent; failures are logged and skipped so startup never breaks.
    """
    from sqlalchemy import text

    statements = [
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS mwpi_state JSON",
        "ALTER TABLE inference_results ADD COLUMN IF NOT EXISTS class_ratios_raw JSON",
        "ALTER TABLE inference_results ADD COLUMN IF NOT EXISTS class_ratios JSON",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS client_name VARCHAR(255)",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS client_whatsapp_number VARCHAR(32)",
    ]
    for stmt in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as exc:  # e.g. SQLite lacks IF NOT EXISTS on ADD COLUMN
            import logging
            logging.getLogger(__name__).warning(f"Column migration skipped ({stmt!r}): {exc}")
