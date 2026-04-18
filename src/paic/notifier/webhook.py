"""Async webhook dispatcher with HMAC-SHA256 signing, retry, and DB persistence."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from paic.core.crypto import unseal
from paic.core.metrics import paic_webhook_delivery_total
from paic.db.models import DeliveryAttempt, Webhook
from paic.notifier._signing import canonical_json, sign_payload

logger = logging.getLogger(__name__)

# Retry delays in seconds: attempt 1 is immediate (0), then 60, 300, 900, 3600.
_RETRY_DELAYS = [0, 60, 300, 900, 3600]

# HTTP status codes that should trigger a retry.
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


async def dispatch(
    webhook: Webhook,
    payload: dict[str, Any],
    *,
    session: Session,
    max_attempts: int = 5,
    sleep_fn: Callable[[float], Awaitable[None]] | None = None,
) -> list[DeliveryAttempt]:
    """POST *payload* to *webhook.url* with HMAC-SHA256 signature and retry logic.

    Each attempt is persisted as a :class:`DeliveryAttempt` row attached to
    *session*.  The caller is responsible for committing the session.

    Args:
        webhook: The :class:`Webhook` ORM instance to deliver to.
        payload: The dict to serialize and POST.  Must contain ``ts``,
            ``tenant_id``, ``diff_summary``, and ``link`` keys (the caller is
            responsible for populating these before calling dispatch).
        session: SQLAlchemy session used to persist :class:`DeliveryAttempt` rows.
        max_attempts: Maximum number of delivery attempts (default 5).
        sleep_fn: Async sleep callable (default :func:`asyncio.sleep`).  Tests
            can inject a no-op to avoid real delays.

    Returns:
        List of :class:`DeliveryAttempt` rows in attempt order.
    """
    if sleep_fn is None:
        sleep_fn = asyncio.sleep

    secret = unseal(webhook.secret_ciphertext, webhook.secret_nonce)
    secret_bytes = secret.encode("utf-8")

    body_str = canonical_json(payload)
    ts = int(payload.get("ts", time.time()))
    signature = sign_payload(secret_bytes, body_str, ts)

    headers = {
        "Content-Type": "application/json",
        "X-PAIC-Signature": f"sha256={signature}",
        "X-PAIC-Timestamp": str(ts),
    }

    attempts: list[DeliveryAttempt] = []
    delays = _RETRY_DELAYS[:max_attempts]

    async with httpx.AsyncClient() as client:
        for attempt_n, delay in enumerate(delays, start=1):
            if delay > 0:
                await sleep_fn(delay)

            attempt_at = datetime.now(tz=UTC)
            status_code: int | None = None
            error: str | None = None

            try:
                response = await client.post(webhook.url, content=body_str, headers=headers)
                status_code = response.status_code

                if status_code < 400:
                    # Success
                    da = _persist_attempt(
                        session, webhook, payload, attempt_n, attempt_at, status_code, None
                    )
                    attempts.append(da)
                    paic_webhook_delivery_total.labels(status="success").inc()
                    logger.info(
                        "Webhook %s delivered on attempt %d (status=%d)",
                        webhook.id,
                        attempt_n,
                        status_code,
                    )
                    return attempts

                # HTTP error response
                error = f"HTTP {status_code}"
                da = _persist_attempt(
                    session, webhook, payload, attempt_n, attempt_at, status_code, error
                )
                attempts.append(da)

                should_retry = status_code in _RETRYABLE_STATUS
                label = "retry" if (should_retry and attempt_n < max_attempts) else "failure"
                paic_webhook_delivery_total.labels(status=label).inc()

                if not should_retry:
                    logger.warning(
                        "Webhook %s got non-retryable status %d on attempt %d — aborting",
                        webhook.id,
                        status_code,
                        attempt_n,
                    )
                    return attempts

            except httpx.TransportError as exc:
                error = str(exc)
                da = _persist_attempt(
                    session, webhook, payload, attempt_n, attempt_at, None, error
                )
                attempts.append(da)
                paic_webhook_delivery_total.labels(status="retry").inc()
                logger.warning(
                    "Webhook %s network error on attempt %d: %s",
                    webhook.id,
                    attempt_n,
                    error,
                )

            # If this was the last attempt, mark final failure metric
            if attempt_n == max_attempts:
                paic_webhook_delivery_total.labels(status="failure").inc()
                logger.error(
                    "Webhook %s exhausted %d attempts — last error: %s",
                    webhook.id,
                    max_attempts,
                    error,
                )

    return attempts


def _persist_attempt(
    session: Session,
    webhook: Webhook,
    payload: dict[str, Any],
    attempt_n: int,
    attempted_at: datetime,
    status_code: int | None,
    error: str | None,
) -> DeliveryAttempt:
    """Create and add a DeliveryAttempt row to *session* (no commit)."""
    summary = {k: payload[k] for k in ("tenant_id", "diff_summary", "link", "ts") if k in payload}
    import json

    da = DeliveryAttempt(
        webhook_id=webhook.id,
        payload_summary_json=json.dumps(summary),
        status_code=status_code,
        error=error,
        attempt_n=attempt_n,
        attempted_at=attempted_at,
    )
    session.add(da)
    return da
