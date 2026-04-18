"""FastAPI dependency for database sessions."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from paic.db.base import _get_session_local


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and close it when the request finishes."""
    db = _get_session_local()()
    try:
        yield db
    finally:
        db.close()
