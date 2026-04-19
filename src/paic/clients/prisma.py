"""Async Prisma Access IP API client.

PAIC v0.2 is stateless: it never persists API keys.  Each call accepts a
plaintext ``api_key`` together with a ``prod`` selector that maps onto the
``api.<prod>.datapath.prismaaccess.com`` URL family used by Prisma Access.
A ``base_url_override`` escape hatch is preserved for sovereign clouds and
future endpoints that don't yet appear in :data:`KNOWN_PRODS`.
"""

from __future__ import annotations

import re

import httpx

from paic.clients.models import PrismaResponse

_ENDPOINT_PATH = "/getPrismaAccessIP/v2"

# ---------------------------------------------------------------------------
# Prod registry
# ---------------------------------------------------------------------------

KNOWN_PRODS: list[str] = [
    "prod",
    "prod1",
    "prod2",
    "prod3",
    "prod4",
    "prod5",
    "prod6",
    "china-prod",
]

# Permissive prod-name regex: lowercase alphanumerics + hyphen.  Strict enough
# to prevent URL injection (no ``/``, ``:``, ``.``, etc.) yet permissive enough
# to accept future prod names without code changes.
_PROD_RE = re.compile(r"^[a-z0-9-]+$")


def known_prods() -> list[str]:
    """Return a copy of :data:`KNOWN_PRODS` (safe to mutate)."""
    return list(KNOWN_PRODS)


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


def _resolve_url(prod: str, base_url_override: str | None) -> str:
    """Return the full POST endpoint URL.

    ``base_url_override`` (if truthy) takes precedence over ``prod``.  Otherwise
    ``prod`` is validated against :data:`_PROD_RE` and used to template
    ``api.<prod>.datapath.prismaaccess.com``.
    """
    if base_url_override:
        return f"{base_url_override.rstrip('/')}{_ENDPOINT_PATH}"

    if not _PROD_RE.match(prod):
        raise ValueError(
            f"Invalid prod selector {prod!r}: must match {_PROD_RE.pattern}"
        )
    return f"https://api.{prod}.datapath.prismaaccess.com{_ENDPOINT_PATH}"


async def fetch_prisma_ips(
    api_key: str,
    prod: str = "prod",
    *,
    base_url_override: str | None = None,
    service_type: str = "all",
    addr_type: str = "all",
    base_url: str | None = None,
) -> PrismaResponse:
    """POST to the Prisma Access IP API and return a parsed PrismaResponse.

    Args:
        api_key: Prisma Access API key sent via ``header-api-key``.
        prod: Prisma cloud selector — used to template the URL as
            ``api.<prod>.datapath.prismaaccess.com``.  Defaults to ``"prod"``.
        base_url_override: Full base URL (no path) to use instead of the
            ``prod``-templated URL.  Useful for sovereign clouds and tests.
        service_type: ``serviceType`` request body value (default ``"all"``).
        addr_type: ``addrType`` request body value (default ``"all"``).
        base_url: Backwards-compatible alias for ``base_url_override`` so older
            callers (and tests) keep working.

    Returns:
        Parsed :class:`PrismaResponse`.

    Raises:
        PrismaAuthError: On 401/403.
        PrismaUpstreamError: On network errors or 5xx.
        PrismaRateLimitError: On 429.
        PrismaSchemaError: When the response body cannot be parsed.
        ValueError: When ``prod`` fails validation and no override is set.
    """
    override = base_url_override if base_url_override is not None else base_url
    url = _resolve_url(prod, override)
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
        Dict with keys ``"serviceTypes"`` and ``"addrTypes"``, each a sorted list
        of unique string values found in the response results.
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
