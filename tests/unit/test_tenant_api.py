"""Unit tests for the Tenant API endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from paic.api.tenants import router
from paic.db.base import Base
from paic.db.session import get_session


@pytest.fixture()
def client():
    """TestClient with in-memory SQLite (StaticPool) and overridden DB session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_session():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# POST /api/tenants
# ---------------------------------------------------------------------------

def test_create_tenant_returns_201(client: TestClient) -> None:
    resp = client.post("/api/tenants", json={"name": "acme", "api_key": "secret123"})
    assert resp.status_code == 201


def test_create_tenant_response_shape(client: TestClient) -> None:
    resp = client.post("/api/tenants", json={"name": "acme", "api_key": "secret123"})
    data = resp.json()
    assert "id" in data
    assert "name" in data
    assert data["name"] == "acme"
    assert "base_url" in data
    assert "poll_interval_sec" in data
    assert "last_fetch_at" in data
    assert "last_fetch_status" in data
    assert "created_at" in data


def test_create_tenant_api_key_not_in_response(client: TestClient) -> None:
    """api_key must never appear in the POST response."""
    resp = client.post("/api/tenants", json={"name": "acme", "api_key": "topsecret"})
    body = resp.text
    assert "topsecret" not in body
    assert "api_key" not in resp.json()


def test_create_tenant_custom_fields(client: TestClient) -> None:
    resp = client.post(
        "/api/tenants",
        json={
            "name": "custom",
            "api_key": "k",
            "base_url": "https://custom.example.com",
            "poll_interval_sec": 600,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["base_url"] == "https://custom.example.com"
    assert data["poll_interval_sec"] == 600


def test_create_tenant_duplicate_name_409(client: TestClient) -> None:
    client.post("/api/tenants", json={"name": "dup", "api_key": "k1"})
    resp = client.post("/api/tenants", json={"name": "dup", "api_key": "k2"})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/tenants
# ---------------------------------------------------------------------------

def test_get_tenants_empty(client: TestClient) -> None:
    resp = client.get("/api/tenants")
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_then_get_returns_tenant(client: TestClient) -> None:
    """POST a tenant then GET /api/tenants — tenant appears in list."""
    client.post("/api/tenants", json={"name": "widget-corp", "api_key": "my-key-xyz"})
    resp = client.get("/api/tenants")
    assert resp.status_code == 200
    tenants = resp.json()
    assert len(tenants) == 1
    assert tenants[0]["name"] == "widget-corp"


def test_get_tenants_api_key_not_in_response(client: TestClient) -> None:
    """api_key must never appear in GET list response."""
    client.post("/api/tenants", json={"name": "secure-corp", "api_key": "supersecretkey99"})
    resp = client.get("/api/tenants")
    body = resp.text
    assert "supersecretkey99" not in body
    for t in resp.json():
        assert "api_key" not in t


def test_get_tenants_multiple(client: TestClient) -> None:
    client.post("/api/tenants", json={"name": "a", "api_key": "ka"})
    client.post("/api/tenants", json={"name": "b", "api_key": "kb"})
    resp = client.get("/api/tenants")
    assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# GET /api/tenants/{id}
# ---------------------------------------------------------------------------

def test_get_tenant_by_id(client: TestClient) -> None:
    created = client.post("/api/tenants", json={"name": "single", "api_key": "k"}).json()
    resp = client.get(f"/api/tenants/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_tenant_not_found(client: TestClient) -> None:
    resp = client.get("/api/tenants/nonexistent-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/tenants/{id}
# ---------------------------------------------------------------------------

def test_update_tenant_name(client: TestClient) -> None:
    created = client.post("/api/tenants", json={"name": "old-name", "api_key": "k"}).json()
    resp = client.put(f"/api/tenants/{created['id']}", json={"name": "new-name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "new-name"


def test_update_tenant_not_found(client: TestClient) -> None:
    resp = client.put("/api/tenants/no-such-id", json={"name": "x"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/tenants/{id}
# ---------------------------------------------------------------------------

def test_delete_tenant(client: TestClient) -> None:
    created = client.post("/api/tenants", json={"name": "to-delete", "api_key": "k"}).json()
    resp = client.delete(f"/api/tenants/{created['id']}")
    assert resp.status_code == 204
    # Should be gone
    assert client.get(f"/api/tenants/{created['id']}").status_code == 404


def test_delete_tenant_not_found(client: TestClient) -> None:
    resp = client.delete("/api/tenants/ghost")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/tenants/{id}/test-connection
# ---------------------------------------------------------------------------

def test_test_connection_success(client: TestClient) -> None:
    created = client.post("/api/tenants", json={"name": "conn-test", "api_key": "real-key"}).json()
    resp = client.post(f"/api/tenants/{created['id']}/test-connection")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


def test_test_connection_not_found(client: TestClient) -> None:
    resp = client.post("/api/tenants/no-tenant/test-connection")
    assert resp.status_code == 404
