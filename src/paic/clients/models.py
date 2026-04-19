"""Pydantic models for Prisma Access IP API responses."""

from pydantic import BaseModel, ConfigDict


class AddressDetail(BaseModel):
    """A single address detail entry within a result."""

    model_config = ConfigDict(extra="allow")

    address: str
    serviceType: str
    addressType: str


class ResultEntry(BaseModel):
    """One entry in the result list: represents a zone/service grouping."""

    model_config = ConfigDict(extra="allow")

    serviceType: str
    addrType: str
    addressDetails: list[AddressDetail] = []


class PrismaResponse(BaseModel):
    """Top-level response from the Prisma Access IP API."""

    model_config = ConfigDict(extra="allow")

    status: str
    result: list[ResultEntry] = []
