"""Unit tests for the Prisma Access API client."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from paic.clients import (
    KNOWN_PRODS,
    PrismaAuthError,
    PrismaResponse,
    PrismaSchemaError,
    PrismaUpstreamError,
    discover_enums,
    fetch_prisma_ips,
    known_prods,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "prisma_response.json"

_FIXTURE_DATA: dict = json.loads(FIXTURE_PATH.read_text())

_BASE_URL = "https://api.test.datapath.prismaaccess.com"
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


def _patch_async_client(transport: httpx.MockTransport):
    """Context-managerless monkeypatch of httpx.AsyncClient inside the module."""
    import paic.clients.prisma as mod

    original = mod.httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):  # type: ignore[override]
            super().__init__(transport=transport)

    mod.httpx.AsyncClient = _Patched  # type: ignore[assignment]
    return mod, original


def _restore(mod, original) -> None:
    mod.httpx.AsyncClient = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_prisma_response() -> None:
    """fetch_prisma_ips returns a PrismaResponse on 200."""
    transport = _make_transport(200, _FIXTURE_DATA)
    mod, original = _patch_async_client(transport)
    try:
        result = await fetch_prisma_ips(_API_KEY, base_url_override=_BASE_URL)
    finally:
        _restore(mod, original)

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
    mod, original = _patch_async_client(transport)
    try:
        await fetch_prisma_ips(_API_KEY, base_url_override=_BASE_URL)
    finally:
        _restore(mod, original)

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
    mod, original = _patch_async_client(transport)
    try:
        await fetch_prisma_ips(
            _API_KEY,
            base_url_override=_BASE_URL,
            service_type="gp_gateway",
            addr_type="active",
        )
    finally:
        _restore(mod, original)

    body = json.loads(captured[0].content)
    assert body["serviceType"] == "gp_gateway"
    assert body["addrType"] == "active"


# ---------------------------------------------------------------------------
# Prod selector — URL templating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prod_default_url_is_api_prod() -> None:
    """Without override, default prod='prod' templates api.prod.datapath...."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_FIXTURE_DATA)

    transport = httpx.MockTransport(handler)
    mod, original = _patch_async_client(transport)
    try:
        await fetch_prisma_ips(_API_KEY)
    finally:
        _restore(mod, original)

    assert str(captured[0].url) == "https://api.prod.datapath.prismaaccess.com/getPrismaAccessIP/v2"


@pytest.mark.asyncio
async def test_prod_prod6_templates_correctly() -> None:
    """prod='prod6' templates api.prod6.datapath...."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_FIXTURE_DATA)

    transport = httpx.MockTransport(handler)
    mod, original = _patch_async_client(transport)
    try:
        await fetch_prisma_ips(_API_KEY, prod="prod6")
    finally:
        _restore(mod, original)

    assert "api.prod6.datapath.prismaaccess.com" in str(captured[0].url)


@pytest.mark.asyncio
async def test_prod_china_prod_templates_correctly() -> None:
    """The hyphenated 'china-prod' must template into the URL unchanged."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_FIXTURE_DATA)

    transport = httpx.MockTransport(handler)
    mod, original = _patch_async_client(transport)
    try:
        await fetch_prisma_ips(_API_KEY, prod="china-prod")
    finally:
        _restore(mod, original)

    assert "api.china-prod.datapath.prismaaccess.com" in str(captured[0].url)


@pytest.mark.asyncio
async def test_base_url_override_takes_precedence_over_prod() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_FIXTURE_DATA)

    transport = httpx.MockTransport(handler)
    mod, original = _patch_async_client(transport)
    try:
        await fetch_prisma_ips(
            _API_KEY, prod="prod6", base_url_override="https://api.example.com"
        )
    finally:
        _restore(mod, original)

    url = str(captured[0].url)
    assert "example.com" in url
    assert "prod6" not in url


@pytest.mark.asyncio
async def test_invalid_prod_raises_value_error() -> None:
    """A prod containing path / scheme characters must raise ValueError."""
    with pytest.raises(ValueError, match="Invalid prod"):
        await fetch_prisma_ips(_API_KEY, prod="evil/../../../etc")


# ---------------------------------------------------------------------------
# Error path: 401 → PrismaAuthError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_raises_prisma_auth_error() -> None:
    transport = _make_transport(401, "Unauthorized")
    mod, original = _patch_async_client(transport)
    try:
        with pytest.raises(PrismaAuthError):
            await fetch_prisma_ips(_API_KEY, base_url_override=_BASE_URL)
    finally:
        _restore(mod, original)


@pytest.mark.asyncio
async def test_403_raises_prisma_auth_error() -> None:
    transport = _make_transport(403, "Forbidden")
    mod, original = _patch_async_client(transport)
    try:
        with pytest.raises(PrismaAuthError):
            await fetch_prisma_ips(_API_KEY, base_url_override=_BASE_URL)
    finally:
        _restore(mod, original)


# ---------------------------------------------------------------------------
# Error path: 503 → PrismaUpstreamError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_503_raises_prisma_upstream_error() -> None:
    transport = _make_transport(503, "Service Unavailable")
    mod, original = _patch_async_client(transport)
    try:
        with pytest.raises(PrismaUpstreamError):
            await fetch_prisma_ips(_API_KEY, base_url_override=_BASE_URL)
    finally:
        _restore(mod, original)


# ---------------------------------------------------------------------------
# Error path: malformed JSON → PrismaSchemaError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_json_raises_prisma_schema_error() -> None:
    transport = _make_transport(200, "not json {{{{")
    mod, original = _patch_async_client(transport)
    try:
        with pytest.raises(PrismaSchemaError):
            await fetch_prisma_ips(_API_KEY, base_url_override=_BASE_URL)
    finally:
        _restore(mod, original)


@pytest.mark.asyncio
async def test_missing_required_keys_raises_prisma_schema_error() -> None:
    bad_body = {"result": []}  # missing 'status'
    transport = _make_transport(200, bad_body)
    mod, original = _patch_async_client(transport)
    try:
        with pytest.raises(PrismaSchemaError):
            await fetch_prisma_ips(_API_KEY, base_url_override=_BASE_URL)
    finally:
        _restore(mod, original)


# ---------------------------------------------------------------------------
# Network error → PrismaUpstreamError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_error_raises_prisma_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    mod, original = _patch_async_client(transport)
    try:
        with pytest.raises(PrismaUpstreamError):
            await fetch_prisma_ips(_API_KEY, base_url_override=_BASE_URL)
    finally:
        _restore(mod, original)


# ---------------------------------------------------------------------------
# Backwards-compat: old `base_url=` kwarg still works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_url_alias_still_supported() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_FIXTURE_DATA)

    transport = httpx.MockTransport(handler)
    mod, original = _patch_async_client(transport)
    try:
        await fetch_prisma_ips(_API_KEY, base_url=_BASE_URL)
    finally:
        _restore(mod, original)

    assert _BASE_URL in str(captured[0].url)


# ---------------------------------------------------------------------------
# discover_enums + known_prods
# ---------------------------------------------------------------------------


def test_discover_enums_returns_sorted_unique_values() -> None:
    response = PrismaResponse.model_validate(_FIXTURE_DATA)
    enums = discover_enums(response)

    assert "serviceTypes" in enums
    assert "addrTypes" in enums
    assert enums["serviceTypes"] == sorted(set(enums["serviceTypes"]))
    assert enums["addrTypes"] == sorted(set(enums["addrTypes"]))
    assert "gp_gateway" in enums["serviceTypes"]


def test_discover_enums_empty_response() -> None:
    response = PrismaResponse(status="success", result=[])
    enums = discover_enums(response)
    assert enums == {"serviceTypes": [], "addrTypes": []}


def test_known_prods_includes_canonical_set() -> None:
    prods = known_prods()
    assert "prod" in prods
    assert "prod6" in prods
    assert "china-prod" in prods


def test_known_prods_returns_copy() -> None:
    a = known_prods()
    a.append("mutated")
    assert "mutated" not in KNOWN_PRODS
