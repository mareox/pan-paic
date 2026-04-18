"""Shared domain types for PAIC."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PrefixRecord(BaseModel):
    """A single egress IP prefix record from Prisma Access."""

    prefix: str
    service_type: str
    addr_type: str
    region: str | None = None
    country: str | None = None
    location_name: str | None = None
    ip_version: Literal[4, 6]
