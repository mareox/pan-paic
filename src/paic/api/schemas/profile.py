"""Pydantic schemas for the Profile resource."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from paic.renderers import SUPPORTED_FORMATS

VALID_MODES: set[str] = {"exact", "lossless", "budget", "waste"}


class ProfileCreate(BaseModel):
    """Request body for creating a profile."""

    name: str = Field(..., min_length=1, max_length=255)
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
    """Request body for updating a profile (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
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


class ProfileResponse(BaseModel):
    """Response shape for a Profile."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    mode: str
    budget: int | None
    max_waste: float | None
    format: str
    filter_spec_json: str | None
    created_at: datetime
    updated_at: datetime
