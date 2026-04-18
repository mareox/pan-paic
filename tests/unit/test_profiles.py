"""Unit tests for the Profile API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from paic.api.profiles import router
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


# Minimal valid profile body.
_VALID_PROFILE = {
    "name": "test-profile",
    "mode": "lossless",
    "format": "json",
}

# A profile that also creates a tenant so render works.
_VALID_EXACT = {
    "name": "exact-profile",
    "mode": "exact",
    "format": "json",
}


def _create_tenant(client: TestClient, name: str = "acme") -> dict:
    """Helper stub — use render_client fixture for render tests instead."""
    raise NotImplementedError("Use render_client fixture instead")


@pytest.fixture()
def render_client():
    """TestClient with BOTH tenants and profiles routers for render tests."""
    from paic.api.tenants import router as tenant_router

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
    app.include_router(tenant_router)
    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# POST /api/profiles — validation
# ---------------------------------------------------------------------------


def test_create_profile_returns_201(client: TestClient) -> None:
    resp = client.post("/api/profiles", json=_VALID_PROFILE)
    assert resp.status_code == 201


def test_create_profile_bad_mode_rejected(client: TestClient) -> None:
    body = {**_VALID_PROFILE, "mode": "invalid_mode"}
    resp = client.post("/api/profiles", json=body)
    assert resp.status_code == 422


def test_create_profile_bad_format_rejected(client: TestClient) -> None:
    body = {**_VALID_PROFILE, "format": "docx"}
    resp = client.post("/api/profiles", json=body)
    assert resp.status_code == 422


def test_create_profile_budget_mode_without_budget_rejected(client: TestClient) -> None:
    body = {"name": "budget-no-val", "mode": "budget", "format": "json"}
    resp = client.post("/api/profiles", json=body)
    assert resp.status_code == 422


def test_create_profile_waste_mode_without_max_waste_rejected(client: TestClient) -> None:
    body = {"name": "waste-no-val", "mode": "waste", "format": "json"}
    resp = client.post("/api/profiles", json=body)
    assert resp.status_code == 422


def test_create_profile_budget_mode_with_budget_accepted(client: TestClient) -> None:
    body = {"name": "budget-ok", "mode": "budget", "budget": 10, "format": "json"}
    resp = client.post("/api/profiles", json=body)
    assert resp.status_code == 201


def test_create_profile_waste_mode_with_max_waste_accepted(client: TestClient) -> None:
    body = {"name": "waste-ok", "mode": "waste", "max_waste": 0.1, "format": "json"}
    resp = client.post("/api/profiles", json=body)
    assert resp.status_code == 201


def test_create_profile_response_shape(client: TestClient) -> None:
    resp = client.post("/api/profiles", json=_VALID_PROFILE)
    data = resp.json()
    for field in ("id", "name", "mode", "budget", "max_waste", "format",
                  "filter_spec_json", "schedule_cron", "created_at", "updated_at"):
        assert field in data, f"missing field: {field}"
    assert data["name"] == "test-profile"
    assert data["mode"] == "lossless"
    assert data["format"] == "json"


# ---------------------------------------------------------------------------
# Full CRUD round-trip
# ---------------------------------------------------------------------------


def test_crud_round_trip(client: TestClient) -> None:
    # Create
    resp = client.post("/api/profiles", json=_VALID_PROFILE)
    assert resp.status_code == 201
    profile_id = resp.json()["id"]

    # Read list
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Read single
    resp = client.get(f"/api/profiles/{profile_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == profile_id

    # Update
    resp = client.put(f"/api/profiles/{profile_id}", json={"name": "renamed-profile"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "renamed-profile"

    # Delete
    resp = client.delete(f"/api/profiles/{profile_id}")
    assert resp.status_code == 204

    # Gone
    resp = client.get(f"/api/profiles/{profile_id}")
    assert resp.status_code == 404


def test_get_profiles_empty(client: TestClient) -> None:
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_profile_not_found(client: TestClient) -> None:
    resp = client.get("/api/profiles/nonexistent")
    assert resp.status_code == 404


def test_update_profile_not_found(client: TestClient) -> None:
    resp = client.put("/api/profiles/no-such-id", json={"name": "x"})
    assert resp.status_code == 404


def test_delete_profile_not_found(client: TestClient) -> None:
    resp = client.delete("/api/profiles/ghost")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Name uniqueness → 409
# ---------------------------------------------------------------------------


def test_duplicate_name_returns_409(client: TestClient) -> None:
    client.post("/api/profiles", json=_VALID_PROFILE)
    resp = client.post("/api/profiles", json=_VALID_PROFILE)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Render endpoint
# ---------------------------------------------------------------------------


def test_render_returns_200_with_json_content_type(render_client: TestClient) -> None:
    # Create tenant.
    tenant_resp = render_client.post(
        "/api/tenants", json={"name": "acme", "api_key": "secret"}
    )
    assert tenant_resp.status_code == 201
    tenant_id = tenant_resp.json()["id"]

    # Create profile.
    profile_resp = render_client.post(
        "/api/profiles", json={"name": "render-test", "mode": "lossless", "format": "json"}
    )
    assert profile_resp.status_code == 201
    profile_id = profile_resp.json()["id"]

    # Render.
    resp = render_client.get(f"/api/profiles/{profile_id}/render?tenant_id={tenant_id}")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]


def test_render_returns_correct_content_type_per_format(render_client: TestClient) -> None:
    tenant_resp = render_client.post(
        "/api/tenants", json={"name": "acme2", "api_key": "secret"}
    )
    tenant_id = tenant_resp.json()["id"]

    format_ct_pairs = [
        ("csv", "text/csv"),
        ("edl", "text/plain"),
        ("yaml", "application/yaml"),
        ("plain", "text/plain"),
        ("xml", "application/xml"),
    ]
    for fmt, expected_ct in format_ct_pairs:
        profile_resp = render_client.post(
            "/api/profiles",
            json={"name": f"render-{fmt}", "mode": "lossless", "format": fmt},
        )
        assert profile_resp.status_code == 201, f"failed to create profile for {fmt}"
        profile_id = profile_resp.json()["id"]

        resp = render_client.get(f"/api/profiles/{profile_id}/render?tenant_id={tenant_id}")
        assert resp.status_code == 200, f"render failed for {fmt}: {resp.text}"
        assert expected_ct in resp.headers["content-type"], (
            f"wrong content-type for {fmt}: {resp.headers['content-type']}"
        )


def test_render_tenant_not_found_returns_404(render_client: TestClient) -> None:
    profile_resp = render_client.post(
        "/api/profiles", json={"name": "orphan-render", "mode": "exact", "format": "json"}
    )
    profile_id = profile_resp.json()["id"]
    resp = render_client.get(f"/api/profiles/{profile_id}/render?tenant_id=nonexistent")
    assert resp.status_code == 404


def test_render_profile_not_found_returns_404(render_client: TestClient) -> None:
    tenant_resp = render_client.post(
        "/api/tenants", json={"name": "acme3", "api_key": "secret"}
    )
    tenant_id = tenant_resp.json()["id"]
    resp = render_client.get(f"/api/profiles/nonexistent/render?tenant_id={tenant_id}")
    assert resp.status_code == 404


def test_render_with_filter_spec(render_client: TestClient) -> None:
    """Render with a filter_spec_json that restricts service_type."""
    import json

    tenant_resp = render_client.post(
        "/api/tenants", json={"name": "filtered-tenant", "api_key": "secret"}
    )
    tenant_id = tenant_resp.json()["id"]

    filter_spec = json.dumps({"service_types": ["remote_network"]})
    profile_resp = render_client.post(
        "/api/profiles",
        json={
            "name": "filtered-profile",
            "mode": "lossless",
            "format": "json",
            "filter_spec_json": filter_spec,
        },
    )
    assert profile_resp.status_code == 201
    profile_id = profile_resp.json()["id"]

    resp = render_client.get(f"/api/profiles/{profile_id}/render?tenant_id={tenant_id}")
    assert resp.status_code == 200
    data = resp.json()
    # Only remote_network prefixes from stub should appear.
    assert data["summary"]["count"] > 0
