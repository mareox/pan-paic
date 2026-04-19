"""Pydantic schemas for the Profile resource (file-backed storage, no ORM)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from paic.renderers import SUPPORTED_FORMATS

VALID_MODES: set[str] = {"exact", "lossless", "budget", "waste"}


class Profile(BaseModel):
    """Persistent profile shape — also the response shape returned by the API."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str | None = None
    mode: Literal["exact", "lossless", "budget", "waste"]
    budget: int | None = Field(default=None, ge=1)
    max_waste: float | None = Field(default=None, ge=0.0, le=1.0)
    format: str
    filter_spec_json: str | None = None
    saved_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class ProfileCreate(BaseModel):
    """Request body for POST /api/profiles."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    mode: Literal["exact", "lossless", "budget", "waste"]
    budget: int | None = Field(default=None, ge=1)
    max_waste: float | None = Field(default=None, ge=0.0, le=1.0)
    format: str = Field(..., min_length=1, max_length=16)
    filter_spec_json: str | None = None

    @model_validator(mode="after")
    def _validate_mode_params(self) -> ProfileCreate:
        if self.format not in SUPPORTED_FORMATS:
            raise ValueError(
                f"format {self.format!r} is not supported. Choose from: {SUPPORTED_FORMATS}"
            )
        if self.mode == "budget" and self.budget is None:
            raise ValueError("budget is required when mode='budget'")
        if self.mode == "waste" and self.max_waste is None:
            raise ValueError("max_waste is required when mode='waste'")
        return self


class ProfileUpdate(BaseModel):
    """Request body for PUT /api/profiles/{id} — all fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    mode: Literal["exact", "lossless", "budget", "waste"] | None = None
    budget: int | None = Field(default=None, ge=1)
    max_waste: float | None = Field(default=None, ge=0.0, le=1.0)
    format: str | None = Field(default=None, min_length=1, max_length=16)
    filter_spec_json: str | None = None

    @model_validator(mode="after")
    def _validate_format(self) -> ProfileUpdate:
        if self.format is not None and self.format not in SUPPORTED_FORMATS:
            raise ValueError(
                f"format {self.format!r} is not supported. Choose from: {SUPPORTED_FORMATS}"
            )
        return self
