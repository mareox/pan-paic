"""Additional sanity tests for /api/query: header values, no-result case."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import paic.api.reports as reports_mod
from paic.api.reports import router
from paic.clients.models import PrismaResponse


@pytest.fixture()
def empty_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def fake_fetch(api_key, prod="prod", **kw):  # noqa: ARG001
        return PrismaResponse(status="success", result=[])

    monkeypatch.setattr(reports_mod, "fetch_prisma_ips", fake_fetch)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


_BASE: dict = {
    "api_key": "secret",
    "prod": "prod",
    "service_type": "all",
    "addr_type": "all",
    "filter": {},
    "mode": "exact",
    "format": "edl",
}


def test_empty_response_returns_empty_body(empty_client: TestClient) -> None:
    resp = empty_client.post("/api/query", json={**_BASE})
    assert resp.status_code == 200
    assert resp.headers["x-input-count"] == "0"
    assert resp.headers["x-output-count"] == "0"
    assert resp.text == ""


def test_x_source_prod_reflects_request(empty_client: TestClient) -> None:
    resp = empty_client.post("/api/query", json={**_BASE, "prod": "prod3"})
    assert resp.headers["x-source-prod"] == "prod3"


def test_query_validation_missing_api_key(empty_client: TestClient) -> None:
    body = {k: v for k, v in _BASE.items() if k != "api_key"}
    resp = empty_client.post("/api/query", json=body)
    assert resp.status_code == 422
