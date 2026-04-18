"""Unit tests for scheduler.poller (PollerService, helpers)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from paic.clients.models import PrismaResponse
from paic.clients.prisma import PrismaAuthError, PrismaSchemaError, PrismaUpstreamError
from paic.scheduler.poller import (
    PollerService,
    _clamp_interval,
    _normalize_payload,
    get_poller,
    on_app_shutdown,
    on_app_startup,
)

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_clamp_interval_below_min() -> None:
    assert _clamp_interval(10) == 300


def test_clamp_interval_above_max() -> None:
    assert _clamp_interval(999999) == 86400


def test_clamp_interval_within_range() -> None:
    assert _clamp_interval(600) == 600


def test_clamp_interval_exactly_min() -> None:
    assert _clamp_interval(300) == 300


def test_clamp_interval_exactly_max() -> None:
    assert _clamp_interval(86400) == 86400


def _make_prisma_response(entries: list[dict]) -> PrismaResponse:
    """Build a PrismaResponse from a list of {serviceType, addresses} dicts."""
    from paic.clients.models import AddressDetail, ResultEntry

    result_entries = []
    for e in entries:
        details = [
            AddressDetail(address=a, serviceType=e["serviceType"], addressType="")
            for a in e["addresses"]
        ]
        result_entries.append(
            ResultEntry(serviceType=e["serviceType"], addrType="", addressDetails=details)
        )
    return PrismaResponse(status="success", result=result_entries)


def test_normalize_payload_groups_by_service_type() -> None:
    resp = _make_prisma_response([
        {"serviceType": "gp_gateway", "addresses": ["1.1.1.1", "2.2.2.2"]},
        {"serviceType": "gp_portal", "addresses": ["3.3.3.3"]},
    ])
    result = _normalize_payload(resp)
    assert set(result.keys()) == {"gp_gateway", "gp_portal"}
    assert result["gp_gateway"] == ["1.1.1.1", "2.2.2.2"]
    assert result["gp_portal"] == ["3.3.3.3"]


def test_normalize_payload_deduplicates_addresses() -> None:
    resp = _make_prisma_response([
        {"serviceType": "svc", "addresses": ["10.0.0.1", "10.0.0.1", "10.0.0.2"]},
    ])
    result = _normalize_payload(resp)
    assert result["svc"] == ["10.0.0.1", "10.0.0.2"]


def test_normalize_payload_sorts_addresses() -> None:
    resp = _make_prisma_response([
        {"serviceType": "svc", "addresses": ["10.0.0.3", "10.0.0.1", "10.0.0.2"]},
    ])
    result = _normalize_payload(resp)
    assert result["svc"] == sorted(result["svc"])


def test_normalize_payload_empty() -> None:
    resp = _make_prisma_response([])
    assert _normalize_payload(resp) == {}


# ---------------------------------------------------------------------------
# PollerService.register_tenant
# ---------------------------------------------------------------------------

def _make_tenant(interval: int = 900) -> MagicMock:
    t = MagicMock()
    t.id = "t-abc"
    t.name = "acme"
    t.poll_interval_sec = interval
    return t


def test_register_tenant_adds_job() -> None:
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = None
    svc = PollerService(scheduler=mock_scheduler)
    svc.register_tenant(_make_tenant())
    mock_scheduler.add_job.assert_called_once()


def test_register_tenant_removes_existing_job() -> None:
    mock_scheduler = MagicMock()
    existing_job = MagicMock()
    mock_scheduler.get_job.return_value = existing_job
    svc = PollerService(scheduler=mock_scheduler)
    svc.register_tenant(_make_tenant())
    existing_job.remove.assert_called_once()


def test_register_tenant_clamps_interval() -> None:
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = None
    svc = PollerService(scheduler=mock_scheduler)
    svc.register_tenant(_make_tenant(interval=60))  # below min
    call_kwargs = mock_scheduler.add_job.call_args[1]
    assert call_kwargs["seconds"] == 300


# ---------------------------------------------------------------------------
# PollerService.stop
# ---------------------------------------------------------------------------

def test_stop_shuts_down_running_scheduler() -> None:
    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    svc = PollerService(scheduler=mock_scheduler)
    svc.stop()
    mock_scheduler.shutdown.assert_called_once_with(wait=False)


def test_stop_skips_shutdown_if_not_running() -> None:
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    svc = PollerService(scheduler=mock_scheduler)
    svc.stop()
    mock_scheduler.shutdown.assert_not_called()


# ---------------------------------------------------------------------------
# PollerService._do_poll — auth/upstream/schema errors
# ---------------------------------------------------------------------------

def _make_live_tenant() -> MagicMock:
    from paic.core.crypto import seal
    ct, nonce = seal("fake-api-key")
    t = MagicMock()
    t.id = "t-live"
    t.name = "live-tenant"
    t.api_key_ciphertext = ct
    t.api_key_nonce = nonce
    t.base_url = "https://api.prismaaccess.example.com"
    return t


@pytest.mark.asyncio
async def test_do_poll_auth_error_records_failure() -> None:
    mock_scheduler = MagicMock()
    svc = PollerService(scheduler=mock_scheduler)
    tenant = _make_live_tenant()
    mock_session = MagicMock()

    exc = PrismaAuthError("unauthorized")
    with patch("paic.scheduler.poller.fetch_prisma_ips", side_effect=exc):
        await svc._do_poll(tenant, mock_session)

    mock_session.commit.assert_called()
    assert tenant.last_fetch_status == "auth_error"


@pytest.mark.asyncio
async def test_do_poll_upstream_error_rate_limited() -> None:
    mock_scheduler = MagicMock()
    svc = PollerService(scheduler=mock_scheduler)
    tenant = _make_live_tenant()
    mock_session = MagicMock()

    from paic.clients.prisma import PrismaRateLimitError
    exc = PrismaRateLimitError("429 rate limited")
    with patch("paic.scheduler.poller.fetch_prisma_ips", side_effect=exc):
        await svc._do_poll(tenant, mock_session)

    assert tenant.last_fetch_status == "rate_limited"


@pytest.mark.asyncio
async def test_do_poll_upstream_error_generic() -> None:
    mock_scheduler = MagicMock()
    svc = PollerService(scheduler=mock_scheduler)
    tenant = _make_live_tenant()
    mock_session = MagicMock()

    exc = PrismaUpstreamError("503 service unavailable")
    with patch("paic.scheduler.poller.fetch_prisma_ips", side_effect=exc):
        await svc._do_poll(tenant, mock_session)

    assert tenant.last_fetch_status == "upstream_error"


@pytest.mark.asyncio
async def test_do_poll_schema_error() -> None:
    mock_scheduler = MagicMock()
    svc = PollerService(scheduler=mock_scheduler)
    tenant = _make_live_tenant()
    mock_session = MagicMock()

    exc = PrismaSchemaError("bad schema")
    with patch("paic.scheduler.poller.fetch_prisma_ips", side_effect=exc):
        await svc._do_poll(tenant, mock_session)

    assert tenant.last_fetch_status == "schema_error"


@pytest.mark.asyncio
async def test_do_poll_success_no_prior_snapshot() -> None:
    """Successful poll with no prior snapshot creates a Snapshot but no Diff."""
    mock_scheduler = MagicMock()
    svc = PollerService(scheduler=mock_scheduler)
    tenant = _make_live_tenant()
    mock_session = MagicMock()

    prisma_resp = _make_prisma_response([
        {"serviceType": "gp_gateway", "addresses": ["1.1.1.0"]},
    ])
    # No prior snapshot
    first_mock = mock_session.query.return_value.filter.return_value.order_by.return_value.first
    first_mock.return_value = None

    with patch("paic.scheduler.poller.fetch_prisma_ips", return_value=prisma_resp):
        await svc._do_poll(tenant, mock_session)

    mock_session.add.assert_called()
    mock_session.commit.assert_called()
    assert tenant.last_fetch_status == "ok"


@pytest.mark.asyncio
async def test_do_poll_success_with_prior_snapshot() -> None:
    """Successful poll with a prior snapshot creates both Snapshot and Diff."""
    mock_scheduler = MagicMock()
    svc = PollerService(scheduler=mock_scheduler)
    tenant = _make_live_tenant()
    mock_session = MagicMock()

    prisma_resp = _make_prisma_response([
        {"serviceType": "gp_gateway", "addresses": ["1.1.1.1", "2.2.2.2"]},
    ])
    prior = MagicMock()
    prior.id = "snap-prior"
    prior.payload_json = json.dumps({"gp_gateway": ["1.1.1.1"]})
    first_mock = mock_session.query.return_value.filter.return_value.order_by.return_value.first
    first_mock.return_value = prior

    with patch("paic.scheduler.poller.fetch_prisma_ips", return_value=prisma_resp):
        await svc._do_poll(tenant, mock_session)

    # session.add should be called at least twice (Snapshot + Diff)
    assert mock_session.add.call_count >= 2
    assert tenant.last_fetch_status == "ok"


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

def test_get_poller_returns_singleton() -> None:
    import paic.scheduler.poller as poller_mod
    poller_mod._poller = None  # reset
    p1 = get_poller()
    p2 = get_poller()
    assert p1 is p2
    poller_mod._poller = None  # cleanup


@pytest.mark.asyncio
async def test_on_app_startup_calls_start() -> None:
    import paic.scheduler.poller as poller_mod
    mock_svc = MagicMock()
    poller_mod._poller = mock_svc
    await on_app_startup()
    mock_svc.start.assert_called_once()
    poller_mod._poller = None


@pytest.mark.asyncio
async def test_on_app_shutdown_calls_stop() -> None:
    import paic.scheduler.poller as poller_mod
    mock_svc = MagicMock()
    poller_mod._poller = mock_svc
    await on_app_shutdown()
    mock_svc.stop.assert_called_once()
    poller_mod._poller = None
