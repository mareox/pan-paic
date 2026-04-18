"""Unit tests for the Prisma Access API client."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from paic.clients import (
    PrismaAuthError,
    PrismaResponse,
    PrismaSchemaError,
    PrismaUpstreamError,
    discover_enums,
    fetch_prisma_ips,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "prisma_response.json"

_FIXTURE_DATA: dict = json.loads(FIXTURE_PATH.read_text())

_BASE_URL = "https://api.test.datapath.prismaaccess.com"
_ENDPOINT = f"{_BASE_URL}/getPrismaAccessIP/v2"
_API_KEY = "test-api-key-12345"


def _make_transport(status_code: int, body: object | str) -> httpx.MockTransport:
    """Build an httpx.MockTransport that always returns the given status + body."""

    if isinstance(body, str):
        content = body.encode()
        media_type = "text/plain"
    else:
        content = json.dumps(body).encode()
        media_type = "application/json"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=content, headers={"content-type": media_type})

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_prisma_response() -> None:
    """fetch_prisma_ips returns a PrismaResponse on 200."""
    transport = _make_transport(200, _FIXTURE_DATA)
    import paic.clients.prisma as mod

    original = mod.httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):  # type: ignore[override]
            super().__init__(transport=transport)

    mod.httpx.AsyncClient = _Patched  # type: ignore[assignment]
    try:
        result = await fetch_prisma_ips(_API_KEY, base_url=_BASE_URL)
    finally:
        mod.httpx.AsyncClient = original  # type: ignore[assignment]

    assert isinstance(result, PrismaResponse)
    assert result.status == "success"
    assert len(result.result) == 3


@pytest.mark.asyncio
async def test_header_api_key_sent() -> None:
    """The request must include the header-api-key header with the correct value."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_FIXTURE_DATA)

    transport = httpx.MockTransport(handler)

    import paic.clients.prisma as mod

    original = mod.httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):  # type: ignore[override]
            super().__init__(transport=transport)

    mod.httpx.AsyncClient = _Patched  # type: ignore[assignment]
    try:
        await fetch_prisma_ips(_API_KEY, base_url=_BASE_URL)
    finally:
        mod.httpx.AsyncClient = original  # type: ignore[assignment]

    assert len(captured) == 1
    assert captured[0].headers["header-api-key"] == _API_KEY


@pytest.mark.asyncio
async def test_payload_shape() -> None:
    """The POST body must include serviceType and addrType keys."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_FIXTURE_DATA)

    transport = httpx.MockTransport(handler)

    import paic.clients.prisma as mod

    original = mod.httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):  # type: ignore[override]
            super().__init__(transport=transport)

    mod.httpx.AsyncClient = _Patched  # type: ignore[assignment]
    try:
        await fetch_prisma_ips(
            _API_KEY, base_url=_BASE_URL, service_type="gp_gateway", addr_type="active"
        )
    finally:
        mod.httpx.AsyncClient = original  # type: ignore[assignment]

    body = json.loads(captured[0].content)
    assert body["serviceType"] == "gp_gateway"
    assert body["addrType"] == "active"


# ---------------------------------------------------------------------------
# Error path: 401 → PrismaAuthError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_raises_prisma_auth_error() -> None:
    transport = _make_transport(401, "Unauthorized")

    import paic.clients.prisma as mod

    original = mod.httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):  # type: ignore[override]
            super().__init__(transport=transport)

    mod.httpx.AsyncClient = _Patched  # type: ignore[assignment]
    try:
        with pytest.raises(PrismaAuthError):
            await fetch_prisma_ips(_API_KEY, base_url=_BASE_URL)
    finally:
        mod.httpx.AsyncClient = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_403_raises_prisma_auth_error() -> None:
    transport = _make_transport(403, "Forbidden")

    import paic.clients.prisma as mod

    original = mod.httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):  # type: ignore[override]
            super().__init__(transport=transport)

    mod.httpx.AsyncClient = _Patched  # type: ignore[assignment]
    try:
        with pytest.raises(PrismaAuthError):
            await fetch_prisma_ips(_API_KEY, base_url=_BASE_URL)
    finally:
        mod.httpx.AsyncClient = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Error path: 503 → PrismaUpstreamError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_503_raises_prisma_upstream_error() -> None:
    transport = _make_transport(503, "Service Unavailable")

    import paic.clients.prisma as mod

    original = mod.httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):  # type: ignore[override]
            super().__init__(transport=transport)

    mod.httpx.AsyncClient = _Patched  # type: ignore[assignment]
    try:
        with pytest.raises(PrismaUpstreamError):
            await fetch_prisma_ips(_API_KEY, base_url=_BASE_URL)
    finally:
        mod.httpx.AsyncClient = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Error path: malformed JSON → PrismaSchemaError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_json_raises_prisma_schema_error() -> None:
    transport = _make_transport(200, "not json {{{{")

    import paic.clients.prisma as mod

    original = mod.httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):  # type: ignore[override]
            super().__init__(transport=transport)

    mod.httpx.AsyncClient = _Patched  # type: ignore[assignment]
    try:
        with pytest.raises(PrismaSchemaError):
            await fetch_prisma_ips(_API_KEY, base_url=_BASE_URL)
    finally:
        mod.httpx.AsyncClient = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_missing_required_keys_raises_prisma_schema_error() -> None:
    """A JSON object that is missing 'status' should raise PrismaSchemaError."""
    bad_body = {"result": []}  # missing 'status'
    transport = _make_transport(200, bad_body)

    import paic.clients.prisma as mod

    original = mod.httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):  # type: ignore[override]
            super().__init__(transport=transport)

    mod.httpx.AsyncClient = _Patched  # type: ignore[assignment]
    try:
        with pytest.raises(PrismaSchemaError):
            await fetch_prisma_ips(_API_KEY, base_url=_BASE_URL)
    finally:
        mod.httpx.AsyncClient = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Network error → PrismaUpstreamError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_error_raises_prisma_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)

    import paic.clients.prisma as mod

    original = mod.httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):  # type: ignore[override]
            super().__init__(transport=transport)

    mod.httpx.AsyncClient = _Patched  # type: ignore[assignment]
    try:
        with pytest.raises(PrismaUpstreamError):
            await fetch_prisma_ips(_API_KEY, base_url=_BASE_URL)
    finally:
        mod.httpx.AsyncClient = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# discover_enums
# ---------------------------------------------------------------------------


def test_discover_enums_returns_sorted_unique_values() -> None:
    response = PrismaResponse.model_validate(_FIXTURE_DATA)
    enums = discover_enums(response)

    assert "serviceTypes" in enums
    assert "addrTypes" in enums
    assert enums["serviceTypes"] == sorted(set(enums["serviceTypes"]))
    assert enums["addrTypes"] == sorted(set(enums["addrTypes"]))
    # Fixture has gp_gateway, gp_portal, remote_network
    assert "gp_gateway" in enums["serviceTypes"]
    assert "remote_network" in enums["serviceTypes"]
    assert "gp_portal" in enums["serviceTypes"]


def test_discover_enums_empty_response() -> None:
    response = PrismaResponse(status="success", result=[])
    enums = discover_enums(response)
    assert enums == {"serviceTypes": [], "addrTypes": []}


def test_discover_enums_deduplicates() -> None:
    """Duplicate serviceType/addrType across entries should appear only once."""
    data = {
        "status": "success",
        "result": [
            {"serviceType": "gp_gateway", "addrType": "active", "addressDetails": []},
            {"serviceType": "gp_gateway", "addrType": "active", "addressDetails": []},
            {"serviceType": "remote_network", "addrType": "active", "addressDetails": []},
        ],
    }
    response = PrismaResponse.model_validate(data)
    enums = discover_enums(response)
    assert enums["serviceTypes"] == ["gp_gateway", "remote_network"]
    assert enums["addrTypes"] == ["active"]


def test_fixture_json_is_valid() -> None:
    """The fixture file must parse and contain at least 2 service types and 2 addr types."""
    response = PrismaResponse.model_validate(_FIXTURE_DATA)
    enums = discover_enums(response)
    assert len(enums["serviceTypes"]) >= 2
    assert len(enums["addrTypes"]) >= 2
