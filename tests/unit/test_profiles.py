"""Unit tests for the Profile API endpoints (YAML-file backed)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import paic.api.reports as reports_mod
from paic.api.profiles import _store
from paic.api.profiles import router as profile_router
from paic.api.reports import router as reports_router
from paic.clients.models import AddressDetail, PrismaResponse, ResultEntry
from paic.storage import ProfileStore


@pytest.fixture()
def store(tmp_path: Path) -> ProfileStore:
    return ProfileStore(tmp_path / "profiles")


@pytest.fixture()
def client(store: ProfileStore) -> TestClient:
    app = FastAPI()
    app.include_router(profile_router)
    app.dependency_overrides[_store] = lambda: store
    return TestClient(app)


@pytest.fixture()
def render_client(monkeypatch: pytest.MonkeyPatch, store: ProfileStore) -> TestClient:
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
                        AddressDetail(
                            address="2.2.2.0/24",
                            serviceType="remote_network",
                            addressType="active",
                        ),
                    ],
                ),
            ],
        )

    monkeypatch.setattr(reports_mod, "fetch_prisma_ips", fake_fetch)

    app = FastAPI()
    app.include_router(profile_router)
    app.include_router(reports_router)
    app.dependency_overrides[_store] = lambda: store
    return TestClient(app)


_VALID = {"name": "test-profile", "mode": "lossless", "format": "json"}


def test_create_profile_returns_201(client: TestClient) -> None:
    assert client.post("/api/profiles", json=_VALID).status_code == 201


def test_create_profile_bad_mode_rejected(client: TestClient) -> None:
    assert client.post("/api/profiles", json={**_VALID, "mode": "nope"}).status_code == 422


def test_create_profile_bad_format_rejected(client: TestClient) -> None:
    assert client.post("/api/profiles", json={**_VALID, "format": "docx"}).status_code == 422


def test_budget_mode_without_budget_rejected(client: TestClient) -> None:
    assert client.post(
        "/api/profiles", json={"name": "x", "mode": "budget", "format": "json"}
    ).status_code == 422


def test_waste_mode_without_max_waste_rejected(client: TestClient) -> None:
    assert client.post(
        "/api/profiles", json={"name": "y", "mode": "waste", "format": "json"}
    ).status_code == 422


def test_budget_mode_with_budget_accepted(client: TestClient) -> None:
    body = {"name": "b", "mode": "budget", "budget": 10, "format": "json"}
    assert client.post("/api/profiles", json=body).status_code == 201


def test_waste_mode_with_max_waste_accepted(client: TestClient) -> None:
    body = {"name": "w", "mode": "waste", "max_waste": 0.1, "format": "json"}
    assert client.post("/api/profiles", json=body).status_code == 201


def test_response_shape(client: TestClient) -> None:
    data = client.post("/api/profiles", json=_VALID).json()
    expected = (
        "id", "name", "mode", "budget", "max_waste", "format", "filter_spec_json", "saved_at",
    )
    for field in expected:
        assert field in data, f"missing field: {field}"


def test_no_credential_fields(client: TestClient) -> None:
    data = client.post("/api/profiles", json=_VALID).json()
    for forbidden in ("api_key", "api_key_ciphertext", "api_key_nonce", "tenant_id"):
        assert forbidden not in data


def test_crud_round_trip(client: TestClient) -> None:
    pid = client.post("/api/profiles", json=_VALID).json()["id"]
    assert len(client.get("/api/profiles").json()) == 1
    assert client.get(f"/api/profiles/{pid}").json()["id"] == pid
    upd = client.put(f"/api/profiles/{pid}", json={"name": "renamed"})
    assert upd.json()["name"] == "renamed"
    assert client.delete(f"/api/profiles/{pid}").status_code == 204
    assert client.get(f"/api/profiles/{pid}").status_code == 404


def test_list_empty(client: TestClient) -> None:
    assert client.get("/api/profiles").json() == []


def test_get_missing_404(client: TestClient) -> None:
    assert client.get("/api/profiles/nope").status_code == 404


def test_update_missing_404(client: TestClient) -> None:
    assert client.put("/api/profiles/nope", json={"name": "x"}).status_code == 404


def test_delete_missing_404(client: TestClient) -> None:
    assert client.delete("/api/profiles/nope").status_code == 404


def test_duplicate_name_409(client: TestClient) -> None:
    client.post("/api/profiles", json=_VALID)
    assert client.post("/api/profiles", json=_VALID).status_code == 409


def test_export_returns_yaml(client: TestClient) -> None:
    pid = client.post("/api/profiles", json=_VALID).json()["id"]
    resp = client.get(f"/api/profiles/{pid}/export")
    assert resp.status_code == 200
    assert "yaml" in resp.headers["content-type"]
    assert b"# Egress IP Condenser" in resp.content
    assert "attachment" in resp.headers["content-disposition"]


def test_export_missing_404(client: TestClient) -> None:
    assert client.get("/api/profiles/nope/export").status_code == 404


def test_import_round_trips(client: TestClient) -> None:
    body_in = {"name": "exp", "mode": "lossless", "format": "json"}
    pid = client.post("/api/profiles", json=body_in).json()["id"]
    body = client.get(f"/api/profiles/{pid}/export").content
    client.delete(f"/api/profiles/{pid}")
    files = {"file": ("p.yaml", body, "application/x-yaml")}
    resp = client.post("/api/profiles/import", files=files)
    assert resp.status_code == 201
    assert resp.json()["name"] == "exp"


def test_import_duplicate_409(client: TestClient) -> None:
    pid = client.post("/api/profiles", json=_VALID).json()["id"]
    body = client.get(f"/api/profiles/{pid}/export").content
    files = {"file": ("p.yaml", body, "application/x-yaml")}
    resp = client.post("/api/profiles/import", files=files)
    assert resp.status_code == 409


_AUTH = {
    "api_key": "shh",
    "prod": "prod",
    "service_type": "all",
    "addr_type": "all",
    "filter": {},
    "mode": "exact",
    "format": "json",
}


def test_render_returns_200(render_client: TestClient) -> None:
    pid = render_client.post(
        "/api/profiles", json={"name": "render-test", "mode": "lossless", "format": "json"}
    ).json()["id"]
    resp = render_client.post(f"/api/profiles/{pid}/render", json=_AUTH)
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]


def test_render_uses_profile_format(render_client: TestClient) -> None:
    for fmt, ct in [
        ("csv", "text/csv"),
        ("edl", "text/plain"),
        ("yaml", "application/yaml"),
        ("plain", "text/plain"),
        ("xml", "application/xml"),
    ]:
        pid = render_client.post(
            "/api/profiles", json={"name": f"render-{fmt}", "mode": "lossless", "format": fmt}
        ).json()["id"]
        resp = render_client.post(f"/api/profiles/{pid}/render", json=_AUTH)
        assert resp.status_code == 200, resp.text
        assert ct in resp.headers["content-type"]


def test_render_profile_not_found(render_client: TestClient) -> None:
    assert render_client.post("/api/profiles/nope/render", json=_AUTH).status_code == 404


def test_render_with_filter(render_client: TestClient) -> None:
    import json

    pid = render_client.post(
        "/api/profiles",
        json={
            "name": "filtered",
            "mode": "lossless",
            "format": "json",
            "filter_spec_json": json.dumps({"service_types": ["remote_network"]}),
        },
    ).json()["id"]
    resp = render_client.post(f"/api/profiles/{pid}/render", json=_AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["count"] == 1
    assert data["records"][0]["prefix"] == "2.2.2.0/24"
