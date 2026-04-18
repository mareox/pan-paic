"""Pydantic schemas for the EmailRecipient resource."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    if not _EMAIL_RE.match(value):
        raise ValueError(f"Invalid email address: {value!r}")
    return value.lower()


class EmailRecipientCreate(BaseModel):
    """Request body for adding an email recipient to a tenant."""

    tenant_id: str = Field(..., min_length=1)
    address: str = Field(..., min_length=3, max_length=320)
    active: bool = Field(default=True)

    @field_validator("address")
    @classmethod
    def address_must_be_email(cls, v: str) -> str:
        return _validate_email(v)


class EmailRecipientResponse(BaseModel):
    """Response shape for an email recipient."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    address: str
    active: bool
    created_at: datetime
