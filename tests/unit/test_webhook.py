"""Unit tests for webhook dispatch and CRUD API."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from paic.api.webhooks import router
from paic.core.crypto import seal
from paic.db.base import Base
from paic.db.models import Webhook
from paic.db.session import get_session
from paic.notifier.webhook import dispatch

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
def db_session(engine):
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(engine):
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


def _make_webhook(
    db_session,
    url: str = "https://example.com/hook",
    secret: str = "topsecret",
) -> Webhook:
    """Helper: create and persist a Webhook with an encrypted secret."""
    ciphertext, nonce = seal(secret)
    wh = Webhook(
        tenant_id="tenant-abc",
        url=url,
        secret_ciphertext=ciphertext,
        secret_nonce=nonce,
        active=True,
    )
    db_session.add(wh)
    db_session.commit()
    db_session.refresh(wh)
    return wh


def _make_payload(tenant_id: str = "tenant-abc") -> dict[str, Any]:
    return {
        "ts": int(time.time()),
        "tenant_id": tenant_id,
        "diff_summary": "Added 2 prefixes, removed 1",
        "link": "https://paic.example.com/diffs/123",
    }


class _RecordingSleep:
    """Captures sleep durations instead of actually sleeping."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _patched_client(transport: httpx.MockTransport):
    """Return a context-manager-compatible AsyncClient subclass using *transport*."""
    import paic.notifier.webhook as _mod

    class _PatchedClient(_mod.httpx.AsyncClient):
        def __init__(self, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            super().__init__(**kwargs)

    return _mod, _PatchedClient


# ---------------------------------------------------------------------------
# dispatch() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_happy_path_single_attempt(db_session) -> None:
    """200 response → 1 DeliveryAttempt, status_code=200, no error."""
    wh = _make_webhook(db_session)
    payload = _make_payload()
    sleep_rec = _RecordingSleep()

    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"ok"))
    _mod, _PatchedClient = _patched_client(transport)
    original = _mod.httpx.AsyncClient
    _mod.httpx.AsyncClient = _PatchedClient  # type: ignore[assignment]
    try:
        attempts = await dispatch(wh, payload, session=db_session, sleep_fn=sleep_rec)
    finally:
        _mod.httpx.AsyncClient = original  # type: ignore[assignment]

    assert len(attempts) == 1
    assert attempts[0].attempt_n == 1
    assert attempts[0].status_code == 200
    assert attempts[0].error is None
    assert sleep_rec.calls == []


@pytest.mark.asyncio
async def test_dispatch_retry_then_success(db_session) -> None:
    """502 on first attempt, 200 on second → 2 DeliveryAttempt rows."""
    wh = _make_webhook(db_session)
    payload = _make_payload()
    sleep_rec = _RecordingSleep()

    call_count = 0

    def _handler(req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(502, content=b"bad gateway")
        return httpx.Response(200, content=b"ok")

    transport = httpx.MockTransport(_handler)
    _mod, _PatchedClient = _patched_client(transport)
    original = _mod.httpx.AsyncClient
    _mod.httpx.AsyncClient = _PatchedClient  # type: ignore[assignment]
    try:
        attempts = await dispatch(wh, payload, session=db_session, sleep_fn=sleep_rec)
    finally:
        _mod.httpx.AsyncClient = original  # type: ignore[assignment]

    assert len(attempts) == 2
    assert attempts[0].attempt_n == 1
    assert attempts[0].status_code == 502
    assert attempts[1].attempt_n == 2
    assert attempts[1].status_code == 200
    assert attempts[1].error is None
    # First retry delay should be 60s
    assert sleep_rec.calls == [60]


@pytest.mark.asyncio
async def test_dispatch_all_fail(db_session) -> None:
    """All 5 attempts return 500 → 5 DeliveryAttempt rows, last has error."""
    wh = _make_webhook(db_session)
    payload = _make_payload()
    sleep_rec = _RecordingSleep()

    transport = httpx.MockTransport(lambda req: httpx.Response(500, content=b"error"))
    _mod, _PatchedClient = _patched_client(transport)
    original = _mod.httpx.AsyncClient
    _mod.httpx.AsyncClient = _PatchedClient  # type: ignore[assignment]
    try:
        attempts = await dispatch(
            wh, payload, session=db_session, sleep_fn=sleep_rec, max_attempts=5
        )
    finally:
        _mod.httpx.AsyncClient = original  # type: ignore[assignment]

    assert len(attempts) == 5
    assert all(a.status_code == 500 for a in attempts)
    assert attempts[-1].error is not None
    assert "500" in attempts[-1].error


@pytest.mark.asyncio
async def test_dispatch_no_retry_on_401(db_session) -> None:
    """401 (non-retryable 4xx) → 1 attempt only."""
    wh = _make_webhook(db_session)
    payload = _make_payload()
    sleep_rec = _RecordingSleep()

    transport = httpx.MockTransport(lambda req: httpx.Response(401, content=b"unauthorized"))
    _mod, _PatchedClient = _patched_client(transport)
    original = _mod.httpx.AsyncClient
    _mod.httpx.AsyncClient = _PatchedClient  # type: ignore[assignment]
    try:
        attempts = await dispatch(wh, payload, session=db_session, sleep_fn=sleep_rec)
    finally:
        _mod.httpx.AsyncClient = original  # type: ignore[assignment]

    assert len(attempts) == 1
    assert attempts[0].status_code == 401
    assert sleep_rec.calls == []


@pytest.mark.asyncio
async def test_dispatch_retry_schedule(db_session) -> None:
    """Retry delays match [0, 60, 300, 900, 3600] — sleep_fn records args."""
    wh = _make_webhook(db_session)
    payload = _make_payload()
    sleep_rec = _RecordingSleep()

    transport = httpx.MockTransport(lambda req: httpx.Response(503, content=b"unavailable"))
    _mod, _PatchedClient = _patched_client(transport)
    original = _mod.httpx.AsyncClient
    _mod.httpx.AsyncClient = _PatchedClient  # type: ignore[assignment]
    try:
        await dispatch(wh, payload, session=db_session, sleep_fn=sleep_rec, max_attempts=5)
    finally:
        _mod.httpx.AsyncClient = original  # type: ignore[assignment]

    # Attempt 1 is immediate (delay=0, no sleep call), then 60, 300, 900, 3600
    assert sleep_rec.calls == [60, 300, 900, 3600]


# ---------------------------------------------------------------------------
# Signature headers on outbound request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_sends_signature_headers(db_session) -> None:
    """Outbound request must include X-PAIC-Signature and X-PAIC-Timestamp."""
    wh = _make_webhook(db_session)
    payload = _make_payload()
    sleep_rec = _RecordingSleep()
    captured: list[httpx.Request] = []

    def _handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, content=b"ok")

    transport = httpx.MockTransport(_handler)
    _mod, _PatchedClient = _patched_client(transport)
    original = _mod.httpx.AsyncClient
    _mod.httpx.AsyncClient = _PatchedClient  # type: ignore[assignment]
    try:
        await dispatch(wh, payload, session=db_session, sleep_fn=sleep_rec)
    finally:
        _mod.httpx.AsyncClient = original  # type: ignore[assignment]

    assert len(captured) == 1
    req = captured[0]
    assert "x-paic-signature" in req.headers
    assert req.headers["x-paic-signature"].startswith("sha256=")
    assert "x-paic-timestamp" in req.headers


# ---------------------------------------------------------------------------
# CRUD API — webhook secret never in GET responses
# ---------------------------------------------------------------------------


def test_create_webhook_returns_201(client: TestClient) -> None:
    resp = client.post(
        "/api/webhooks",
        json={"tenant_id": "t1", "url": "https://hook.example.com/", "secret": "mysecret"},
    )
    assert resp.status_code == 201


def test_create_webhook_secret_not_in_response(client: TestClient) -> None:
    resp = client.post(
        "/api/webhooks",
        json={"tenant_id": "t1", "url": "https://hook.example.com/", "secret": "supersecret99"},
    )
    assert resp.status_code == 201
    body = resp.text
    assert "supersecret99" not in body
    data = resp.json()
    assert "secret" not in data
    assert "secret_ciphertext" not in data
    assert "secret_nonce" not in data


def test_list_webhooks_secret_not_in_response(client: TestClient) -> None:
    client.post(
        "/api/webhooks",
        json={"tenant_id": "t1", "url": "https://hook.example.com/", "secret": "topsecret123"},
    )
    resp = client.get("/api/webhooks", params={"tenant_id": "t1"})
    assert resp.status_code == 200
    body = resp.text
    assert "topsecret123" not in body
    for wh in resp.json():
        assert "secret" not in wh
        assert "secret_ciphertext" not in wh


def test_get_webhook_secret_not_in_response(client: TestClient) -> None:
    created = client.post(
        "/api/webhooks",
        json={"tenant_id": "t1", "url": "https://hook.example.com/", "secret": "verysecret"},
    ).json()
    resp = client.get(f"/api/webhooks/{created['id']}")
    assert resp.status_code == 200
    assert "verysecret" not in resp.text
    assert "secret" not in resp.json()


def test_get_webhook_not_found(client: TestClient) -> None:
    resp = client.get("/api/webhooks/nonexistent")
    assert resp.status_code == 404


def test_update_webhook(client: TestClient) -> None:
    created = client.post(
        "/api/webhooks",
        json={"tenant_id": "t1", "url": "https://old.example.com/", "secret": "s"},
    ).json()
    resp = client.put(
        f"/api/webhooks/{created['id']}",
        json={"url": "https://new.example.com/", "active": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == "https://new.example.com/"
    assert data["active"] is False


def test_update_webhook_not_found(client: TestClient) -> None:
    resp = client.put("/api/webhooks/no-such", json={"url": "https://x.com/"})
    assert resp.status_code == 404


def test_delete_webhook(client: TestClient) -> None:
    created = client.post(
        "/api/webhooks",
        json={"tenant_id": "t1", "url": "https://hook.example.com/", "secret": "s"},
    ).json()
    resp = client.delete(f"/api/webhooks/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/webhooks/{created['id']}").status_code == 404


def test_delete_webhook_not_found(client: TestClient) -> None:
    resp = client.delete("/api/webhooks/ghost")
    assert resp.status_code == 404


def test_list_webhooks_filters_by_tenant(client: TestClient) -> None:
    client.post(
        "/api/webhooks",
        json={"tenant_id": "t1", "url": "https://a.example.com/", "secret": "s1"},
    )
    client.post(
        "/api/webhooks",
        json={"tenant_id": "t2", "url": "https://b.example.com/", "secret": "s2"},
    )
    resp = client.get("/api/webhooks", params={"tenant_id": "t1"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["tenant_id"] == "t1"
