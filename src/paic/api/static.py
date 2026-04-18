"""Static file router — mounts the built Vite bundle at '/' if present."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

router = APIRouter()

_STATIC_DIR = Path(__file__).parent.parent / "static"


def mount_static(app: object) -> None:  # app: FastAPI
    """Mount the built SPA bundle onto *app* if the static directory exists.

    Called by the application factory after all API routers are registered so
    that API routes always take precedence over the catch-all SPA handler.
    """
    if not _STATIC_DIR.exists():
        logger.info("Static bundle directory %s not found — skipping SPA mount", _STATIC_DIR)
        return

    # Mount assets directory separately so it is served with cache headers.
    assets_dir = _STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount(  # type: ignore[attr-defined]
            "/assets",
            StaticFiles(directory=str(assets_dir)),
            name="assets",
        )

    # Mount the root — html=True enables SPA fallback to index.html.
    app.mount(  # type: ignore[attr-defined]
        "/",
        StaticFiles(directory=str(_STATIC_DIR), html=True),
        name="static",
    )
    logger.info("SPA bundle mounted from %s", _STATIC_DIR)
