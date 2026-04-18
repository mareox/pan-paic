"""Export API — GET /api/reports/export."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from paic.core.filters import FilterSpec, apply_filters
from paic.core.types import PrefixRecord
from paic.db.models import Snapshot
from paic.db.session import get_session
from paic.renderers import SUPPORTED_FORMATS, render

router = APIRouter(prefix="/api/reports", tags=["reports"])

_CONTENT_TYPES: dict[str, str] = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "xml": "application/xml",
    "edl": "text/plain; charset=utf-8",
    "yaml": "text/yaml; charset=utf-8",
    "plain": "text/plain; charset=utf-8",
}


def _ip_version(prefix: str) -> Literal[4, 6]:
    return 6 if ":" in prefix else 4


def _records_from_latest_snapshot(session: Session, tenant_id: str | None) -> list[PrefixRecord]:
    """Pull the most recent Snapshot (optionally for a specific tenant) and unpack to records."""
    stmt = select(Snapshot).order_by(Snapshot.fetched_at.desc())
    if tenant_id:
        stmt = stmt.where(Snapshot.tenant_id == tenant_id)
    snapshot = session.execute(stmt.limit(1)).scalar_one_or_none()
    if snapshot is None:
        return []

    payload: dict[str, list[str]] = json.loads(snapshot.payload_json)
    return [
        PrefixRecord(
            prefix=prefix,
            service_type=svc,
            addr_type="active",
            region=None,
            country=None,
            location_name=None,
            ip_version=_ip_version(prefix),
        )
        for svc, prefixes in payload.items()
        for prefix in prefixes
    ]


@router.get("/export")
def export_prefixes(
    fmt: str = Query(default="json", alias="format", description=f"One of {SUPPORTED_FORMATS}"),
    tenant_id: str | None = Query(default=None, description="Limit to one tenant"),
    service_type: str | None = Query(default=None),
    addr_type: str | None = Query(default=None),
    region: str | None = Query(default=None),
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Export prefix records from the most recent snapshot."""
    if fmt not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format {fmt!r}. Choose from: {SUPPORTED_FORMATS}",
        )

    records = _records_from_latest_snapshot(db, tenant_id)
    spec = FilterSpec(
        service_types={service_type} if service_type else None,
        addr_types={addr_type} if addr_type else None,
        regions={region} if region else None,
    )
    filtered = apply_filters(records, spec)

    body = render(filtered, fmt)
    return Response(content=body, media_type=_CONTENT_TYPES[fmt])
