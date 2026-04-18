"""Unit tests for api.reports export endpoint backed by a real Snapshot."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from paic.api.reports import router
from paic.core.crypto import seal
from paic.db.base import Base
from paic.db.models import Snapshot, Tenant
from paic.db.session import get_session


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def client(session_factory) -> TestClient:
    def override():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = override
    return TestClient(app)


def _seed_snapshot(session_factory, payload: dict[str, list[str]]) -> str:
    db = session_factory()
    try:
        ciphertext, nonce = seal("test-key")
        tenant = Tenant(name="t1", api_key_ciphertext=ciphertext, api_key_nonce=nonce)
        db.add(tenant)
        db.flush()
        snap = Snapshot(
            tenant_id=tenant.id,
            fetched_at=datetime.now(tz=UTC),
            payload_json=json.dumps(payload),
        )
        db.add(snap)
        db.commit()
        return tenant.id
    finally:
        db.close()


def test_export_unsupported_format_400(client: TestClient) -> None:
    resp = client.get("/api/reports/export?format=pdf")
    assert resp.status_code == 400
    assert "pdf" in resp.json()["detail"]


def test_export_json_empty_db(client: TestClient) -> None:
    resp = client.get("/api/reports/export?format=json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")


def test_export_default_format_is_json(client: TestClient) -> None:
    resp = client.get("/api/reports/export")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]


@pytest.mark.parametrize(
    ("fmt", "expected_ct"),
    [
        ("csv", "text/csv"),
        ("edl", "text/plain"),
        ("xml", "application/xml"),
        ("yaml", "text/yaml"),
        ("plain", "text/plain"),
    ],
)
def test_export_format_content_types(
    client: TestClient, session_factory, fmt: str, expected_ct: str
) -> None:
    _seed_snapshot(session_factory, {"gp_gateway": ["1.1.1.1", "2.2.2.2"]})
    resp = client.get(f"/api/reports/export?format={fmt}")
    assert resp.status_code == 200
    assert expected_ct in resp.headers["content-type"]


def test_export_service_type_filter(client: TestClient, session_factory) -> None:
    _seed_snapshot(session_factory, {"gp_gateway": ["1.1.1.1"], "remote_network": ["2.2.2.2"]})
    resp = client.get("/api/reports/export?format=json&service_type=gp_gateway")
    assert resp.status_code == 200
    body = resp.json()
    prefixes = [r["prefix"] for r in body["records"]]
    assert prefixes == ["1.1.1.1"]


def test_export_tenant_filter(client: TestClient, session_factory) -> None:
    _seed_snapshot(session_factory, {"gp_gateway": ["3.3.3.3"]})
    resp = client.get("/api/reports/export?format=json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["count"] == 1
