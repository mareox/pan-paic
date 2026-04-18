"""Unit tests for notifier.webhook dispatch function."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from paic.core.crypto import seal
from paic.db.base import Base
from paic.db.models import DeliveryAttempt, Tenant, Webhook
from paic.notifier.webhook import _persist_attempt, dispatch


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def webhook(db_session):
    """A Webhook ORM instance with sealed secret."""
    ct, nonce = seal("mysecret")
    tenant_ct, tenant_nonce = seal("apikey")

    tenant = Tenant(
        id="t-1",
        name="test-tenant",
        api_key_ciphertext=tenant_ct,
        api_key_nonce=tenant_nonce,
    )
    db_session.add(tenant)
    db_session.flush()

    wh = Webhook(
        id="wh-1",
        tenant_id="t-1",
        url="https://example.com/hook",
        secret_ciphertext=ct,
        secret_nonce=nonce,
    )
    db_session.add(wh)
    db_session.flush()
    return wh


def _make_payload() -> dict[str, Any]:
    return {
        "ts": int(time.time()),
        "tenant_id": "t-1",
        "diff_summary": "1 added, 0 removed",
        "link": "https://paic.example.com/diffs/1",
    }


@pytest.mark.asyncio
async def test_dispatch_success_first_attempt(db_session, webhook) -> None:
    """A 200 response succeeds on the first attempt."""
    payload = _make_payload()
    mock_response = MagicMock()
    mock_response.status_code = 200

    async_sleep = AsyncMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        attempts = await dispatch(
            webhook, payload, session=db_session, max_attempts=3, sleep_fn=async_sleep
        )

    assert len(attempts) == 1
    assert attempts[0].status_code == 200
    assert attempts[0].error is None
    # First attempt has delay 0, so sleep should not be called
    async_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_non_retryable_error_aborts(db_session, webhook) -> None:
    """A 400 (non-retryable) stops immediately after one attempt."""
    payload = _make_payload()
    mock_response = MagicMock()
    mock_response.status_code = 400

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        attempts = await dispatch(
            webhook, payload, session=db_session, max_attempts=5, sleep_fn=AsyncMock()
        )

    assert len(attempts) == 1
    assert attempts[0].status_code == 400


@pytest.mark.asyncio
async def test_dispatch_retryable_500_retries(db_session, webhook) -> None:
    """A 500 response retries up to max_attempts."""
    payload = _make_payload()
    mock_response = MagicMock()
    mock_response.status_code = 500

    async_sleep = AsyncMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        attempts = await dispatch(
            webhook, payload, session=db_session, max_attempts=3, sleep_fn=async_sleep
        )

    assert len(attempts) == 3
    assert all(a.status_code == 500 for a in attempts)


@pytest.mark.asyncio
async def test_dispatch_transport_error_retries(db_session, webhook) -> None:
    """A network error (TransportError) triggers retry logic."""
    payload = _make_payload()
    async_sleep = AsyncMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TransportError("connection refused"))
        mock_client_cls.return_value = mock_client

        attempts = await dispatch(
            webhook, payload, session=db_session, max_attempts=2, sleep_fn=async_sleep
        )

    assert len(attempts) == 2
    assert all(a.error is not None for a in attempts)
    assert all(a.status_code is None for a in attempts)


@pytest.mark.asyncio
async def test_dispatch_success_after_retry(db_session, webhook) -> None:
    """First attempt fails with 503, second succeeds."""
    payload = _make_payload()
    async_sleep = AsyncMock()

    fail_response = MagicMock()
    fail_response.status_code = 503
    ok_response = MagicMock()
    ok_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=[fail_response, ok_response])
        mock_client_cls.return_value = mock_client

        attempts = await dispatch(
            webhook, payload, session=db_session, max_attempts=3, sleep_fn=async_sleep
        )

    assert len(attempts) == 2
    assert attempts[-1].status_code == 200


def test_persist_attempt_adds_to_session(db_session, webhook) -> None:
    """_persist_attempt creates a DeliveryAttempt and adds it to the session."""
    payload = _make_payload()
    now = datetime.now(tz=UTC)

    da = _persist_attempt(db_session, webhook, payload, 1, now, 200, None)

    assert isinstance(da, DeliveryAttempt)
    assert da.webhook_id == webhook.id
    assert da.attempt_n == 1
    assert da.status_code == 200
    assert da.error is None

    summary = json.loads(da.payload_summary_json)
    assert "tenant_id" in summary
    assert "diff_summary" in summary
