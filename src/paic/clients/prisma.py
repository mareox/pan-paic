"""Async Prisma Access IP API client."""

from __future__ import annotations

import httpx

from paic.clients.models import PrismaResponse
from paic.core.settings import Settings

_DEFAULT_URL = "https://api.prod.datapath.prismaaccess.com"
_ENDPOINT_PATH = "/getPrismaAccessIP/v2"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PrismaError(Exception):
    """Base exception for all Prisma Access client errors."""


class PrismaAuthError(PrismaError):
    """Raised on HTTP 401 or 403 responses."""


class PrismaUpstreamError(PrismaError):
    """Raised on network errors or HTTP 5xx responses."""


class PrismaRateLimitError(PrismaUpstreamError):
    """Raised on HTTP 429 responses (subclass so generic handlers still catch)."""


class PrismaSchemaError(PrismaError):
    """Raised when the response body cannot be parsed into PrismaResponse."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _get_base_url(base_url: str | None) -> str:
    """Return base_url if provided, otherwise fall back to settings."""
    if base_url:
        return base_url.rstrip("/")
    settings = Settings()  # type: ignore[call-arg]
    return settings.prisma_base_url.rstrip("/")


async def fetch_prisma_ips(
    api_key: str,
    base_url: str | None = None,
    service_type: str = "all",
    addr_type: str = "all",
) -> PrismaResponse:
    """POST to the Prisma Access IP API and return a parsed PrismaResponse.

    Args:
        api_key: Prisma Access API key sent via ``header-api-key``.
        base_url: Override the API base URL. Defaults to settings.prisma_base_url.
        service_type: ``serviceType`` request body value (default ``"all"``).
        addr_type: ``addrType`` request body value (default ``"all"``).

    Returns:
        Parsed :class:`PrismaResponse`.

    Raises:
        PrismaAuthError: On 401/403.
        PrismaUpstreamError: On network errors or 5xx.
        PrismaSchemaError: When the response body cannot be parsed.
    """
    resolved_base = _get_base_url(base_url)
    url = f"{resolved_base}{_ENDPOINT_PATH}"
    headers = {"header-api-key": api_key}
    payload = {"serviceType": service_type, "addrType": addr_type}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise PrismaUpstreamError(f"Network error contacting Prisma API: {exc}") from exc

    if response.status_code in (401, 403):
        raise PrismaAuthError(
            f"Authentication failed (HTTP {response.status_code}): {response.text}"
        )

    if response.status_code == 429:
        raise PrismaRateLimitError(
            f"Prisma API rate limited (HTTP 429): {response.text}"
        )

    if response.status_code >= 500:
        raise PrismaUpstreamError(
            f"Prisma API returned server error (HTTP {response.status_code}): {response.text}"
        )

    try:
        data = response.json()
    except Exception as exc:
        raise PrismaSchemaError(f"Response is not valid JSON: {exc}") from exc

    try:
        return PrismaResponse.model_validate(data)
    except Exception as exc:
        raise PrismaSchemaError(f"Response does not match expected schema: {exc}") from exc


def discover_enums(response: PrismaResponse) -> dict[str, list[str]]:
    """Extract sorted unique serviceType and addrType values from a response.

    Args:
        response: A parsed :class:`PrismaResponse`.

    Returns:
        Dict with keys ``"serviceTypes"`` and ``"addrTypes"``, each a sorted list of
        unique string values found in the response results.
    """
    service_types: set[str] = set()
    addr_types: set[str] = set()

    for entry in response.result:
        service_types.add(entry.serviceType)
        addr_types.add(entry.addrType)

    return {
        "serviceTypes": sorted(service_types),
        "addrTypes": sorted(addr_types),
    }
