"""Engine/session setup and schema migrations."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def make_engine(settings: Settings) -> Engine:
    url = settings.resolved_database_url
    kwargs: dict = {}
    if url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


def upgrade_schema(engine: Engine) -> None:
    """Apply Alembic migrations up to head (idempotent)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


class Database:
    def __init__(self, settings: Settings):
        self.engine = make_engine(settings)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def session(self) -> Iterator[Session]:
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()
