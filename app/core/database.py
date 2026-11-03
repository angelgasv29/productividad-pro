"""Engine SQLite de nivel corporativo, sesiones y pragmas obligatorios."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Base declarativa moderna de SQLAlchemy 2.0."""


def _sqlite_connect_args(url: str) -> dict[str, Any]:
    if url.startswith("sqlite"):
        return {"check_same_thread": False, "timeout": 30}
    return {}


engine: Engine = create_engine(
    settings.database_url,
    connect_args=_sqlite_connect_args(settings.database_url),
    pool_pre_ping=True,
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Aplica los pragmas en *cada* conexión nueva.

    WAL permite lecturas concurrentes mientras se escribe; busy_timeout evita
    bloqueos espurios; foreign_keys es imprescindible para las cascadas.
    """

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute("PRAGMA busy_timeout = 5000;")
        cursor.execute("PRAGMA temp_store = MEMORY;")
    finally:
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI: una sesión por request, cerrada siempre."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crea las tablas si no existen (usado por run.py y los tests)."""

    from app import models  # noqa: F401  (registra el metadata)

    settings.ensure_directories()
    if settings.database_url.startswith("sqlite:///"):
        raw = settings.database_url.removeprefix("sqlite:///")
        if raw and raw != ":memory:":
            Path(raw).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
