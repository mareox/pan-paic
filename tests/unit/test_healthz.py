"""Tests for the /healthz endpoint."""

from fastapi.testclient import TestClient

from paic.api.main import app

client = TestClient(app)


def test_healthz_returns_200() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_returns_ok_body() -> None:
    response = client.get("/healthz")
    assert response.json() == {"status": "ok"}
