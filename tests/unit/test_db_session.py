"""Unit tests for db.session and db.base."""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from paic.db.base import Base, make_engine, make_session_factory
from paic.db.session import get_session


def test_make_engine_sqlite() -> None:
    engine = make_engine("sqlite:///:memory:")
    assert engine is not None
    engine.dispose()


def test_make_engine_defaults_to_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """make_engine() with no arg reads from Settings (DATABASE_URL)."""
    monkeypatch.setenv("PAIC_DATABASE_URL", "sqlite:///:memory:")
    engine = make_engine()
    assert engine is not None
    engine.dispose()


def test_make_session_factory_returns_sessionmaker() -> None:
    engine = make_engine("sqlite:///:memory:")
    factory = make_session_factory(engine)
    assert factory is not None
    session = factory()
    session.close()
    engine.dispose()


def test_get_session_yields_and_closes() -> None:
    """get_session() yields a Session and closes it after iteration."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Patch the internal session local to use our test DB
    with patch("paic.db.session._get_session_local", return_value=TestSession):
        gen = get_session()
        session = next(gen)
        assert session is not None
        # Exhaust the generator to trigger finally close
        try:
            next(gen)
        except StopIteration:
            pass

    Base.metadata.drop_all(engine)
    engine.dispose()
