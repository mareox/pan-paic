"""Observability API router: /healthz, /readyz, /metrics.

PAIC v0.2.1 has no SQL. Readiness verifies the profiles directory is writable.
"""

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from paic.core.settings import Settings

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Unconditional liveness probe."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> JSONResponse:
    """Readiness probe: verifies the profiles directory is writable."""
    reasons: list[str] = []

    try:
        settings = Settings()  # type: ignore[call-arg]
        settings.profiles_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(settings.profiles_dir, os.W_OK):
            reasons.append(f"profiles_dir not writable: {settings.profiles_dir}")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"profiles_dir: {exc}")

    if reasons:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reasons": reasons})
    return JSONResponse(status_code=200, content={"status": "ready"})


@router.get("/metrics")
def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint (text exposition format)."""
    data = generate_latest()
    return PlainTextResponse(content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
