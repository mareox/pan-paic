"""SQLAlchemy engine, declarative base, and session factory."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def make_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine.

    If *database_url* is not provided, reads PAIC_DATABASE_URL from the
    environment (via Settings) at call time — not at import time.
    """
    if database_url is None:
        from paic.core.settings import Settings  # local import avoids circular

        database_url = Settings().database_url  # type: ignore[call-arg]

    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a sessionmaker bound to *engine*."""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Module-level singletons — initialised lazily so that import of this module
# does NOT immediately call Settings() (which needs env vars that tests set
# only after collection).  Accessing engine / SessionLocal triggers init.
# ---------------------------------------------------------------------------

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


def _get_session_local() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = make_session_factory(_get_engine())
    return _SessionLocal


class _EngineProxy:
    """Proxy so ``from paic.db.base import engine`` still works lazily."""

    def __getattr__(self, name: str) -> object:
        return getattr(_get_engine(), name)


class _SessionLocalProxy:
    """Proxy so ``SessionLocal()`` still works lazily."""

    def __call__(self, **kw: object) -> Session:
        return _get_session_local()(**kw)  # type: ignore[return-value]

    def __getattr__(self, name: str) -> object:
        return getattr(_get_session_local(), name)


engine: Engine = _EngineProxy()  # type: ignore[assignment]
SessionLocal: sessionmaker[Session] = _SessionLocalProxy()  # type: ignore[assignment]
