"""Diffs API — paginated list of computed diffs per tenant."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from paic.db.models import Diff, Tenant
from paic.db.session import get_session

router = APIRouter()


class DiffResponse(BaseModel):
    """Serialised representation of a single Diff row."""

    id: str
    tenant_id: str
    computed_at: str
    added: dict[str, list[str]]
    removed: dict[str, list[str]]
    unchanged_count: int


def _to_response(diff: Diff) -> DiffResponse:
    added: dict[str, list[str]] = json.loads(diff.added_json)
    removed: dict[str, list[str]] = json.loads(diff.removed_json)
    return DiffResponse(
        id=diff.id,
        tenant_id=diff.tenant_id,
        computed_at=diff.computed_at.isoformat(),
        added=added,
        removed=removed,
        unchanged_count=diff.unchanged_count,
    )


@router.get(
    "/api/tenants/{tenant_id}/diffs",
    response_model=list[DiffResponse],
    tags=["diffs"],
)
def list_diffs(
    tenant_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_session),  # noqa: B008
) -> list[Any]:
    """Return paginated diffs for *tenant_id*, most-recent first."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    diffs = (
        db.query(Diff)
        .filter(Diff.tenant_id == tenant_id)
        .order_by(Diff.computed_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_response(d) for d in diffs]
