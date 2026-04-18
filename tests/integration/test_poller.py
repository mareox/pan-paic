"""Integration tests for the per-tenant PollerService and diffs API."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from paic.api.diffs import router as diffs_router
from paic.api.tenants import router as tenants_router
from paic.clients.models import AddressDetail, PrismaResponse, ResultEntry
from paic.clients.prisma import PrismaRateLimitError, PrismaSchemaError
from paic.core.crypto import seal
from paic.db.base import Base
from paic.db.models import Diff, Snapshot, Tenant
from paic.db.session import get_session
from paic.scheduler.poller import PollerService

# ---------------------------------------------------------------------------
# Helpers to build PrismaResponse fixtures
# ---------------------------------------------------------------------------


def _make_response(*entries: tuple[str, list[str]]) -> PrismaResponse:
    """Build a PrismaResponse from (service_type, [prefix, ...]) pairs."""
    result = []
    for svc, prefixes in entries:
        details = [
            AddressDetail(address=p, serviceType=svc, addressType="ip_address")
            for p in prefixes
        ]
        result.append(ResultEntry(serviceType=svc, addrType="ip_address", addressDetails=details))
    return PrismaResponse(status="success", result=result)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def db_session(session_factory):
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def tenant(db_session) -> Tenant:
    """Create a test tenant with encrypted API key."""
    ciphertext, nonce = seal("test-api-key")
    t = Tenant(
        name="test-corp",
        api_key_ciphertext=ciphertext,
        api_key_nonce=nonce,
        base_url="https://api.example.com",
        poll_interval_sec=900,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture()
def poller(session_factory):
    """PollerService backed by the test DB, scheduler in paused mode."""
    scheduler = AsyncIOScheduler()
    # Don't start the scheduler — we call run_once_for_tenant directly
    svc = PollerService(scheduler=scheduler)

    # Patch the module-level _get_session_local to return our test session factory
    with patch("paic.scheduler.poller._get_session_local", return_value=session_factory):
        yield svc


@pytest.fixture()
def client(engine, session_factory):
    """TestClient with both tenants + diffs routers and in-memory SQLite."""

    def override_get_session():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(tenants_router)
    app.include_router(diffs_router)
    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Diff math: 3 simulated polls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_polls_diff_math(poller, tenant, db_session, session_factory):
    """
    Poll 1: baseline — produces Snapshot, no Diff.
    Poll 2: adds 10.0.0.3 — Diff should show it added.
    Poll 3: removes 10.0.0.1 — Diff should show it removed.
    """
    base_prefixes = ["10.0.0.1", "10.0.0.2"]
    poll2_prefixes = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
    poll3_prefixes = ["10.0.0.2", "10.0.0.3"]

    responses = [
        _make_response(("remote_network", base_prefixes)),
        _make_response(("remote_network", poll2_prefixes)),
        _make_response(("remote_network", poll3_prefixes)),
    ]

    with patch("paic.scheduler.poller._get_session_local", return_value=session_factory):
        for resp in responses:
            with patch(
                "paic.scheduler.poller.fetch_prisma_ips",
                new=AsyncMock(return_value=resp),
            ):
                await poller.run_once_for_tenant(tenant)

    # Reload state
    db = session_factory()
    try:
        snapshots = (
            db.query(Snapshot)
            .filter(Snapshot.tenant_id == tenant.id)
            .order_by(Snapshot.fetched_at)
            .all()
        )
        diffs = (
            db.query(Diff)
            .filter(Diff.tenant_id == tenant.id)
            .order_by(Diff.computed_at)
            .all()
        )
    finally:
        db.close()

    # 3 snapshots, 2 diffs
    assert len(snapshots) == 3
    assert len(diffs) == 2

    # Poll 1: no diff (baseline)
    # Poll 2 diff: 10.0.0.3 added, nothing removed
    diff1 = diffs[0]
    added1 = json.loads(diff1.added_json)
    removed1 = json.loads(diff1.removed_json)
    assert "10.0.0.3" in added1.get("remote_network", [])
    assert removed1.get("remote_network", []) == []
    assert diff1.unchanged_count == 2  # 10.0.0.1 and 10.0.0.2

    # Poll 3 diff: 10.0.0.1 removed, nothing added
    diff2 = diffs[1]
    added2 = json.loads(diff2.added_json)
    removed2 = json.loads(diff2.removed_json)
    assert added2.get("remote_network", []) == []
    assert "10.0.0.1" in removed2.get("remote_network", [])
    assert diff2.unchanged_count == 2  # 10.0.0.2 and 10.0.0.3


# ---------------------------------------------------------------------------
# 429 → rate_limited status, no diff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_429_sets_rate_limited(poller, tenant, session_factory):
    """PrismaUpstreamError with 429 in message → last_fetch_status='rate_limited'."""
    with patch("paic.scheduler.poller._get_session_local", return_value=session_factory):
        with patch(
            "paic.scheduler.poller.fetch_prisma_ips",
            new=AsyncMock(side_effect=PrismaRateLimitError("HTTP 429 rate limited")),
        ):
            await poller.run_once_for_tenant(tenant)

    db = session_factory()
    try:
        t = db.get(Tenant, tenant.id)
        assert t is not None
        assert t.last_fetch_status == "rate_limited"
        # No snapshot or diff should have been created
        snapshots = db.query(Snapshot).filter(Snapshot.tenant_id == tenant.id).all()
        diffs = db.query(Diff).filter(Diff.tenant_id == tenant.id).all()
    finally:
        db.close()

    assert len(snapshots) == 0
    assert len(diffs) == 0


# ---------------------------------------------------------------------------
# PrismaSchemaError → schema_error status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_error_sets_status(poller, tenant, session_factory):
    """PrismaSchemaError → last_fetch_status='schema_error'."""
    with patch("paic.scheduler.poller._get_session_local", return_value=session_factory):
        with patch(
            "paic.scheduler.poller.fetch_prisma_ips",
            new=AsyncMock(side_effect=PrismaSchemaError("bad response")),
        ):
            await poller.run_once_for_tenant(tenant)

    db = session_factory()
    try:
        t = db.get(Tenant, tenant.id)
        assert t is not None
        assert t.last_fetch_status == "schema_error"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/tenants/{id}/diffs — paginated, most-recent first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_diffs_endpoint(client, tenant, session_factory):
    """After 2 diffs, GET /api/tenants/{id}/diffs returns them most-recent-first."""
    responses = [
        _make_response(("gp_gateway", ["192.168.1.1"])),
        _make_response(("gp_gateway", ["192.168.1.1", "192.168.1.2"])),
        _make_response(("gp_gateway", ["192.168.1.2"])),
    ]

    # Use a fresh poller so it shares the same session_factory as client
    scheduler = AsyncIOScheduler()
    poller = PollerService(scheduler=scheduler)

    with patch("paic.scheduler.poller._get_session_local", return_value=session_factory):
        for resp in responses:
            with patch(
                "paic.scheduler.poller.fetch_prisma_ips",
                new=AsyncMock(return_value=resp),
            ):
                await poller.run_once_for_tenant(tenant)

    resp = client.get(f"/api/tenants/{tenant.id}/diffs")
    assert resp.status_code == 200
    data = resp.json()

    # 2 diffs (poll 2 and poll 3), most-recent first
    assert len(data) == 2

    # First in list is most recent (poll 3 diff)
    latest = data[0]
    assert "removed" in latest
    assert "added" in latest
    assert "unchanged_count" in latest

    # Most-recent diff: removed 192.168.1.1
    assert "192.168.1.1" in latest["removed"].get("gp_gateway", [])


def test_get_diffs_tenant_not_found(client):
    """GET /api/tenants/nonexistent/diffs returns 404."""
    resp = client.get("/api/tenants/nonexistent-id/diffs")
    assert resp.status_code == 404


def test_get_diffs_empty(client, tenant):
    """GET /api/tenants/{id}/diffs with no diffs returns empty list."""
    resp = client.get(f"/api/tenants/{tenant.id}/diffs")
    assert resp.status_code == 200
    assert resp.json() == []
