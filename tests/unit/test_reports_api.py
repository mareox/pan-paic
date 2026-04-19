"""Unit tests for the stateless POST /api/query endpoint."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import paic.api.reports as reports_mod
from paic.api.reports import router
from paic.clients.models import AddressDetail, PrismaResponse, ResultEntry

# ---------------------------------------------------------------------------
# Helpers — build a fake Prisma response and patch fetch_prisma_ips
# ---------------------------------------------------------------------------


def _build_response() -> PrismaResponse:
    return PrismaResponse(
        status="success",
        result=[
            ResultEntry(
                serviceType="gp_gateway",
                addrType="active",
                addressDetails=[
                    AddressDetail(
                        address="1.1.1.1/32", serviceType="gp_gateway", addressType="active"
                    ),
                    AddressDetail(
                        address="2.2.2.2/32", serviceType="gp_gateway", addressType="active"
                    ),
                ],
            ),
            ResultEntry(
                serviceType="remote_network",
                addrType="active",
                addressDetails=[
                    AddressDetail(
                        address="10.0.0.0/24",
                        serviceType="remote_network",
                        addressType="active",
                    ),
                ],
            ),
        ],
    )


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def fake_fetch(api_key, prod="prod", **kw):  # noqa: ARG001
        return _build_response()

    monkeypatch.setattr(reports_mod, "fetch_prisma_ips", fake_fetch)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


_BASE_BODY: dict = {
    "api_key": "secret",
    "prod": "prod6",
    "service_type": "all",
    "addr_type": "all",
    "filter": {},
    "mode": "exact",
    "format": "json",
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_query_returns_200_with_json(client: TestClient) -> None:
    resp = client.post("/api/query", json={**_BASE_BODY})
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    body = resp.json()
    prefixes = [r["prefix"] for r in body["records"]]
    assert prefixes == ["1.1.1.1/32", "2.2.2.2/32", "10.0.0.0/24"]


def test_query_sets_x_headers(client: TestClient) -> None:
    resp = client.post("/api/query", json={**_BASE_BODY})
    assert resp.status_code == 200
    assert resp.headers["x-input-count"] == "3"
    assert resp.headers["x-output-count"] == "3"
    assert resp.headers["x-source-prod"] == "prod6"
    assert "x-waste-ratio" in resp.headers


@pytest.mark.parametrize(
    ("fmt", "expected_ct"),
    [
        ("csv", "text/csv"),
        ("edl", "text/plain"),
        ("xml", "application/xml"),
        ("yaml", "application/yaml"),
        ("plain", "text/plain"),
        ("json", "application/json"),
    ],
)
def test_query_format_dispatches_to_renderer(
    client: TestClient, fmt: str, expected_ct: str
) -> None:
    resp = client.post("/api/query", json={**_BASE_BODY, "format": fmt})
    assert resp.status_code == 200
    assert expected_ct in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Filter is honoured
# ---------------------------------------------------------------------------


def test_query_filter_restricts_records(client: TestClient) -> None:
    body = {**_BASE_BODY, "filter": {"service_types": ["remote_network"]}}
    resp = client.post("/api/query", json=body)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["summary"]["count"] == 1
    assert payload["records"][0]["prefix"] == "10.0.0.0/24"


# ---------------------------------------------------------------------------
# Aggregation modes
# ---------------------------------------------------------------------------


def test_query_lossless_collapses_adjacent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two adjacent /32s should collapse into a single /31 in lossless mode."""

    async def fake_fetch(api_key, prod="prod", **kw):  # noqa: ARG001
        return PrismaResponse(
            status="success",
            result=[
                ResultEntry(
                    serviceType="gp_gateway",
                    addrType="active",
                    addressDetails=[
                        AddressDetail(
                            address="1.1.1.0/32",
                            serviceType="gp_gateway",
                            addressType="active",
                        ),
                        AddressDetail(
                            address="1.1.1.1/32",
                            serviceType="gp_gateway",
                            addressType="active",
                        ),
                    ],
                ),
            ],
        )

    monkeypatch.setattr(reports_mod, "fetch_prisma_ips", fake_fetch)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)

    resp = c.post("/api/query", json={**_BASE_BODY, "mode": "lossless"})
    assert resp.status_code == 200
    prefixes = [r["prefix"] for r in resp.json()["records"]]
    assert prefixes == ["1.1.1.0/31"]
    assert resp.headers["x-input-count"] == "2"
    assert resp.headers["x-output-count"] == "1"


def test_query_budget_mode_requires_budget(client: TestClient) -> None:
    body = {**_BASE_BODY, "mode": "budget"}
    resp = client.post("/api/query", json=body)
    assert resp.status_code == 400


def test_query_waste_mode_requires_max_waste(client: TestClient) -> None:
    body = {**_BASE_BODY, "mode": "waste"}
    resp = client.post("/api/query", json=body)
    assert resp.status_code == 400


def test_query_budget_mode_works(client: TestClient) -> None:
    resp = client.post("/api/query", json={**_BASE_BODY, "mode": "budget", "budget": 1})
    assert resp.status_code == 200
    assert resp.headers["x-output-count"] == "1"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_query_unsupported_format_400(client: TestClient) -> None:
    resp = client.post("/api/query", json={**_BASE_BODY, "format": "pdf"})
    assert resp.status_code == 400
    assert "pdf" in resp.json()["detail"]


def test_query_invalid_prod_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid prod selectors should bubble up from the client as 400."""

    async def fake_fetch(api_key, prod="prod", **kw):  # noqa: ARG001
        raise ValueError("Invalid prod selector 'evil/path'")

    monkeypatch.setattr(reports_mod, "fetch_prisma_ips", fake_fetch)
    resp = client.post("/api/query", json={**_BASE_BODY, "prod": "evil/path"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Upstream error mapping
# ---------------------------------------------------------------------------


def test_query_upstream_auth_error_maps_to_401(monkeypatch: pytest.MonkeyPatch) -> None:
    from paic.clients.prisma import PrismaAuthError

    async def fake_fetch(api_key, prod="prod", **kw):  # noqa: ARG001
        raise PrismaAuthError("nope")

    monkeypatch.setattr(reports_mod, "fetch_prisma_ips", fake_fetch)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    resp = c.post("/api/query", json={**_BASE_BODY})
    assert resp.status_code == 401


def test_query_upstream_rate_limit_maps_to_429(monkeypatch: pytest.MonkeyPatch) -> None:
    from paic.clients.prisma import PrismaRateLimitError

    async def fake_fetch(api_key, prod="prod", **kw):  # noqa: ARG001
        raise PrismaRateLimitError("slow down")

    monkeypatch.setattr(reports_mod, "fetch_prisma_ips", fake_fetch)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    resp = c.post("/api/query", json={**_BASE_BODY})
    assert resp.status_code == 429


def test_query_upstream_500_maps_to_502(monkeypatch: pytest.MonkeyPatch) -> None:
    from paic.clients.prisma import PrismaUpstreamError

    async def fake_fetch(api_key, prod="prod", **kw):  # noqa: ARG001
        raise PrismaUpstreamError("backend on fire")

    monkeypatch.setattr(reports_mod, "fetch_prisma_ips", fake_fetch)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    resp = c.post("/api/query", json={**_BASE_BODY})
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# /api/query/preview
# ---------------------------------------------------------------------------


def test_query_preview_returns_aggregate_result(client: TestClient) -> None:
    resp = client.post("/api/query/preview", json={**_BASE_BODY})
    assert resp.status_code == 200
    body = resp.json()
    # AggregateResult fields
    assert "output_prefixes" in body
    assert "input_count" in body
    assert "output_count" in body
    assert "waste_ratio" in body
    assert body["input_count"] == 3


def test_query_preview_honours_mode(client: TestClient) -> None:
    resp = client.post(
        "/api/query/preview",
        json={**_BASE_BODY, "mode": "budget", "budget": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["output_count"] == 1
