"""Pydantic schemas for the Webhook resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WebhookCreate(BaseModel):
    """Request body for creating a webhook."""

    tenant_id: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1, max_length=2048)
    secret: str = Field(..., min_length=1)
    active: bool = Field(default=True)


class WebhookUpdate(BaseModel):
    """Request body for updating a webhook (all fields optional)."""

    url: str | None = Field(default=None, min_length=1, max_length=2048)
    secret: str | None = Field(default=None, min_length=1)
    active: bool | None = None


class WebhookResponse(BaseModel):
    """Response shape — secret and ciphertext fields are never included."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    url: str
    active: bool
    created_at: datetime
