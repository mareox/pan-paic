"""Pydantic schemas for the Tenant resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    """Request body for creating a tenant."""

    name: str = Field(..., min_length=1, max_length=255)
    api_key: str = Field(..., min_length=1)
    base_url: str = Field(default="https://api.prod.datapath.prismaaccess.com")
    poll_interval_sec: int = Field(default=900, ge=300, le=86400)


class TenantUpdate(BaseModel):
    """Request body for updating a tenant (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    api_key: str | None = Field(default=None, min_length=1)
    base_url: str | None = None
    poll_interval_sec: int | None = Field(default=None, ge=300, le=86400)


class TenantResponse(BaseModel):
    """Response shape — api_key and ciphertext fields are never included."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_url: str
    poll_interval_sec: int
    last_fetch_at: datetime | None
    last_fetch_status: str | None
    created_at: datetime


class TestConnectionResponse(BaseModel):
    """Response from the test-connection action."""

    success: bool
    detail: str
