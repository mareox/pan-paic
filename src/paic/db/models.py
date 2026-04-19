"""ORM models.

PAIC v0.2 is stateless w.r.t. Prisma data: only :class:`Profile` (a settings
bundle: filter spec + aggregation mode + budget + format) is persisted.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from paic.db.base import Base


class Profile(Base):
    """Named aggregation profile bundling mode, format, and filter spec.

    Profiles store *settings only* — they never include credentials or any
    Prisma response data.  When a profile is "applied", the caller supplies a
    fresh ``api_key`` + ``prod`` in the request body.
    """

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_waste: Mapped[float | None] = mapped_column(Float, nullable=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    filter_spec_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
