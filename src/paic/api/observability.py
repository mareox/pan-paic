"""Observability API router: /healthz, /readyz, /metrics."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from paic.core.metrics import is_scheduler_ready

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Unconditional liveness probe — returns 200 if the process is up."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> JSONResponse:
    """Readiness probe — checks DB connectivity and scheduler state."""
    reasons: list[str] = []

    # --- DB check ---
    try:
        from paic.db.base import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"db: {exc}")

    # --- Scheduler check ---
    if not is_scheduler_ready():
        reasons.append("scheduler: not started")

    if reasons:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reasons": reasons},
        )

    return JSONResponse(status_code=200, content={"status": "ready"})


@router.get("/metrics")
def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint (text exposition format)."""
    data = generate_latest()
    return PlainTextResponse(
        content=data.decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )
