"""Per-tenant polling service using APScheduler."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from paic.clients.models import PrismaResponse
from paic.clients.prisma import (
    PrismaAuthError,
    PrismaRateLimitError,
    PrismaSchemaError,
    PrismaUpstreamError,
    fetch_prisma_ips,
)
from paic.core.crypto import unseal
from paic.core.metrics import (
    paic_poll_failures_total,
    paic_poll_total,
    paic_prefix_count,
    set_scheduler_ready,
)
from paic.db.base import _get_session_local
from paic.db.models import Diff, Snapshot, Tenant
from paic.scheduler.diff import compute_diff

logger = logging.getLogger(__name__)

_MIN_INTERVAL = 300
_DEFAULT_INTERVAL = 900
_MAX_INTERVAL = 86400


def _clamp_interval(interval: int) -> int:
    """Clamp poll interval to [MIN, MAX]."""
    return max(_MIN_INTERVAL, min(_MAX_INTERVAL, interval))


def _normalize_payload(prisma_response: PrismaResponse) -> dict[str, list[str]]:
    """Convert a PrismaResponse into {service_type: sorted([prefix, ...])}."""
    payload: dict[str, set[str]] = {}
    for entry in prisma_response.result:
        svc = entry.serviceType
        if svc not in payload:
            payload[svc] = set()
        for detail in entry.addressDetails:
            payload[svc].add(detail.address)
    return {svc: sorted(addrs) for svc, addrs in payload.items()}


class PollerService:
    """Manages per-tenant APScheduler jobs and drives Snapshot/Diff persistence."""

    def __init__(self, scheduler: AsyncIOScheduler | None = None) -> None:
        self._scheduler = scheduler or AsyncIOScheduler()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler and register all active tenants."""
        session: Session = _get_session_local()()
        try:
            tenants = session.query(Tenant).all()
        finally:
            session.close()

        for tenant in tenants:
            self.register_tenant(tenant)

        if not self._scheduler.running:
            self._scheduler.start()
        set_scheduler_ready(True)
        logger.info("PollerService started with %d tenant(s)", len(tenants))

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        set_scheduler_ready(False)
        logger.info("PollerService stopped")

    # ------------------------------------------------------------------
    # Tenant registration
    # ------------------------------------------------------------------

    def register_tenant(self, tenant: Tenant) -> None:
        """Add or replace a job for *tenant* at its poll_interval_sec."""
        interval = _clamp_interval(tenant.poll_interval_sec)
        job_id = f"poll_tenant_{tenant.id}"

        # Remove existing job for this tenant (idempotent re-register)
        existing = self._scheduler.get_job(job_id)
        if existing:
            existing.remove()

        self._scheduler.add_job(
            self._poll_job,
            trigger="interval",
            seconds=interval,
            id=job_id,
            args=[tenant.id],
            replace_existing=True,
        )
        logger.debug("Registered poll job for tenant %s (interval=%ds)", tenant.name, interval)

    # ------------------------------------------------------------------
    # Internal APScheduler callback (sync wrapper)
    # ------------------------------------------------------------------

    def _poll_job(self, tenant_id: str) -> None:
        """Synchronous APScheduler callback — loads tenant and delegates."""
        import asyncio

        session: Session = _get_session_local()()
        try:
            tenant = session.get(Tenant, tenant_id)
            if not tenant:
                logger.warning("Poll job fired for unknown tenant_id=%s — skipping", tenant_id)
                return
            asyncio.run(self.run_once_for_tenant(tenant))
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Core poll logic
    # ------------------------------------------------------------------

    async def run_once_for_tenant(self, tenant: Tenant) -> None:
        """Fetch IPs, persist Snapshot/Diff, update tenant status + metrics."""
        session: Session = _get_session_local()()
        try:
            # Re-fetch tenant in this session to ensure it's bound
            live_tenant = session.get(Tenant, tenant.id)
            if not live_tenant:
                logger.warning("Tenant %s not found in DB during poll", tenant.id)
                return
            await self._do_poll(live_tenant, session)
        finally:
            session.close()

    async def _do_poll(self, tenant: Tenant, session: Session) -> None:
        """Inner poll: fetch → snapshot → diff → persist → update status."""
        api_key = unseal(tenant.api_key_ciphertext, tenant.api_key_nonce)

        try:
            response = await fetch_prisma_ips(api_key, base_url=tenant.base_url)
        except PrismaAuthError:
            self._record_failure(session, tenant, "auth_error")
            paic_poll_failures_total.labels(tenant=tenant.name, error_type="auth_error").inc()
            paic_poll_total.labels(tenant=tenant.name, status="auth_error").inc()
            return
        except PrismaRateLimitError:
            self._record_failure(session, tenant, "rate_limited")
            paic_poll_failures_total.labels(tenant=tenant.name, error_type="rate_limited").inc()
            paic_poll_total.labels(tenant=tenant.name, status="rate_limited").inc()
            return
        except PrismaUpstreamError:
            status = "upstream_error"
            self._record_failure(session, tenant, status)
            paic_poll_failures_total.labels(tenant=tenant.name, error_type=status).inc()
            paic_poll_total.labels(tenant=tenant.name, status=status).inc()
            return
        except PrismaSchemaError:
            self._record_failure(session, tenant, "schema_error")
            paic_poll_failures_total.labels(tenant=tenant.name, error_type="schema_error").inc()
            paic_poll_total.labels(tenant=tenant.name, status="schema_error").inc()
            return

        # Normalize and persist snapshot
        new_payload = _normalize_payload(response)
        now = datetime.now(tz=UTC)

        snapshot = Snapshot(
            tenant_id=tenant.id,
            fetched_at=now,
            payload_json=json.dumps(new_payload),
        )
        session.add(snapshot)
        session.flush()  # get snapshot.id without committing yet

        # Find prior snapshot (most recent before the one we just created)
        prior_snapshot = (
            session.query(Snapshot)
            .filter(
                Snapshot.tenant_id == tenant.id,
                Snapshot.id != snapshot.id,
            )
            .order_by(Snapshot.fetched_at.desc())
            .first()
        )

        if prior_snapshot:
            prior_payload: dict[str, list[str]] = json.loads(prior_snapshot.payload_json)
            diff_data = compute_diff(prior_payload, new_payload)

            # Extract per-service added/removed; unchanged_count is top-level
            unchanged_count = int(diff_data.pop("unchanged_count", 0))  # type: ignore[call-overload]
            added_by_svc = {svc: v["added"] for svc, v in diff_data.items()}  # type: ignore[index]
            removed_by_svc = {svc: v["removed"] for svc, v in diff_data.items()}  # type: ignore[index]

            diff = Diff(
                tenant_id=tenant.id,
                computed_at=now,
                added_json=json.dumps(added_by_svc),
                removed_json=json.dumps(removed_by_svc),
                unchanged_count=unchanged_count,
            )
            session.add(diff)

        # Update tenant status
        tenant.last_fetch_at = now
        tenant.last_fetch_status = "ok"
        session.commit()

        # Update metrics
        paic_poll_total.labels(tenant=tenant.name, status="ok").inc()
        for svc, prefixes in new_payload.items():
            paic_prefix_count.labels(tenant=tenant.name, service_type=svc).set(len(prefixes))

        logger.info(
            "Polled tenant %s: %d service types, prior_snapshot=%s",
            tenant.name,
            len(new_payload),
            prior_snapshot.id if prior_snapshot else None,
        )

    def _record_failure(self, session: Session, tenant: Tenant, status: str) -> None:
        """Update tenant.last_fetch_status and commit."""
        tenant.last_fetch_at = datetime.now(tz=UTC)
        tenant.last_fetch_status = status
        session.commit()
        logger.warning("Poll failed for tenant %s: %s", tenant.name, status)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_poller: PollerService | None = None


def get_poller() -> PollerService:
    """Return the module-level PollerService singleton."""
    global _poller
    if _poller is None:
        _poller = PollerService()
    return _poller


async def on_app_startup() -> None:
    """FastAPI lifespan hook — start the scheduler on app startup."""
    get_poller().start()


async def on_app_shutdown() -> None:
    """FastAPI lifespan hook — stop the scheduler on app shutdown."""
    get_poller().stop()
