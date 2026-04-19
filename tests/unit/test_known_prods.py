"""Tests for the GET /api/known-prods endpoint and the underlying registry."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from paic.api.reports import router
from paic.clients.prisma import KNOWN_PRODS


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_endpoint_returns_200_and_prods_list() -> None:
    resp = _client().get("/api/known-prods")
    assert resp.status_code == 200
    body = resp.json()
    assert "prods" in body
    assert isinstance(body["prods"], list)


def test_endpoint_includes_canonical_prods() -> None:
    body = _client().get("/api/known-prods").json()
    prods = body["prods"]
    for required in ("prod", "prod1", "prod6", "china-prod"):
        assert required in prods, f"missing canonical prod {required!r}"


def test_endpoint_matches_registry() -> None:
    body = _client().get("/api/known-prods").json()
    assert body["prods"] == KNOWN_PRODS
