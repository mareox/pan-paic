"""Profile CRUD endpoints + render action."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from paic.aggregation.engine import summarize
from paic.api.schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate
from paic.core.filters import FilterSpec, apply_filters
from paic.core.types import PrefixRecord
from paic.db.models import Profile, Tenant
from paic.db.session import get_session
from paic.renderers import render

# Content-type map for each supported format.
_CONTENT_TYPES: dict[str, str] = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "xml": "application/xml",
    "edl": "text/plain; charset=utf-8",
    "yaml": "application/yaml",
    "plain": "text/plain; charset=utf-8",
}

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def _to_response(profile: Profile) -> ProfileResponse:
    return ProfileResponse.model_validate(profile)


# ---------------------------------------------------------------------------
# Stub prefix list used until US-008 Snapshot poller is integrated.
# Once the Snapshot table exists, replace this with a DB query keyed by
# tenant_id, ordered by fetch time descending, limit 1.
# ---------------------------------------------------------------------------

_STUB_PREFIXES: list[PrefixRecord] = [
    PrefixRecord(
        prefix="10.0.0.0/24", service_type="remote_network", addr_type="active",
        region="us-west", country="US", location_name="Los Angeles", ip_version=4,
    ),
    PrefixRecord(
        prefix="10.0.1.0/24", service_type="remote_network", addr_type="active",
        region="us-east", country="US", location_name="New York", ip_version=4,
    ),
    PrefixRecord(
        prefix="192.168.0.0/24", service_type="gp_gateway", addr_type="active",
        region="eu-west", country="DE", location_name="Frankfurt", ip_version=4,
    ),
    PrefixRecord(
        prefix="172.16.0.0/24", service_type="gp_gateway", addr_type="active",
        region="apac", country="JP", location_name="Tokyo", ip_version=4,
    ),
    PrefixRecord(
        prefix="2001:db8::/48", service_type="remote_network", addr_type="active",
        region="us-west", country="US", location_name="Seattle", ip_version=6,
    ),
]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ProfileCreate,
    db: Session = Depends(get_session),  # noqa: B008
) -> ProfileResponse:
    """Create a new aggregation profile."""
    existing = db.query(Profile).filter(Profile.name == body.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Profile with name '{body.name}' already exists.",
        )

    # Validate filter_spec_json is a parseable FilterSpec when provided.
    if body.filter_spec_json is not None:
        try:
            FilterSpec.model_validate_json(body.filter_spec_json)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"filter_spec_json is not a valid FilterSpec: {exc}",
            ) from exc

    profile = Profile(
        name=body.name,
        mode=body.mode,
        budget=body.budget,
        max_waste=body.max_waste,
        format=body.format,
        filter_spec_json=body.filter_spec_json,
        schedule_cron=body.schedule_cron,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _to_response(profile)


@router.get("", response_model=list[ProfileResponse])
def list_profiles(db: Session = Depends(get_session)) -> list[ProfileResponse]:  # noqa: B008
    """Return all profiles."""
    profiles = db.query(Profile).order_by(Profile.created_at).all()
    return [_to_response(p) for p in profiles]


@router.get("/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: str, db: Session = Depends(get_session)) -> ProfileResponse:  # noqa: B008
    """Return a single profile by ID."""
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return _to_response(profile)


@router.put("/{profile_id}", response_model=ProfileResponse)
def update_profile(
    profile_id: str,
    body: ProfileUpdate,
    db: Session = Depends(get_session),  # noqa: B008
) -> ProfileResponse:
    """Update mutable profile fields."""
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

    if body.name is not None:
        profile.name = body.name
    if body.mode is not None:
        profile.mode = body.mode
    if body.budget is not None:
        profile.budget = body.budget
    if body.max_waste is not None:
        profile.max_waste = body.max_waste
    if body.format is not None:
        profile.format = body.format
    if body.filter_spec_json is not None:
        try:
            FilterSpec.model_validate_json(body.filter_spec_json)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"filter_spec_json is not a valid FilterSpec: {exc}",
            ) from exc
        profile.filter_spec_json = body.filter_spec_json
    if body.schedule_cron is not None:
        profile.schedule_cron = body.schedule_cron

    db.commit()
    db.refresh(profile)
    return _to_response(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: str, db: Session = Depends(get_session)) -> None:  # noqa: B008
    """Delete a profile."""
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    db.delete(profile)
    db.commit()


# ---------------------------------------------------------------------------
# Render action
# ---------------------------------------------------------------------------


@router.get("/{profile_id}/render")
def render_profile(
    profile_id: str,
    tenant_id: str,
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Apply profile to tenant prefix data and return rendered bytes.

    Until US-008 (Snapshot poller) lands, a small in-memory stub list is used
    when no real snapshot data is in the DB.  Once US-008 is integrated,
    replace _STUB_PREFIXES with a query against the Snapshot table:
        db.query(Snapshot).filter_by(tenant_id=tenant_id).order_by(Snapshot.fetched_at.desc()).first()
    """
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    # TODO(US-008): replace with real snapshot lookup once Snapshot table exists.
    records: list[PrefixRecord] = list(_STUB_PREFIXES)

    if not records:
        # Tenant has no data yet — return empty render.
        content_type = _CONTENT_TYPES.get(profile.format, "application/octet-stream")
        return Response(content=b"", media_type=content_type)

    # Apply filter spec if present.
    if profile.filter_spec_json:
        spec = FilterSpec.model_validate(json.loads(profile.filter_spec_json))
        records = apply_filters(records, spec)

    # Aggregate.
    prefixes = [r.prefix for r in records]
    agg = summarize(
        prefixes,
        profile.mode,  # type: ignore[arg-type]
        budget=profile.budget,
        max_waste=profile.max_waste,
    )

    # Render using aggregated prefix list (as plain dicts for renderer compat).
    rendered_records = [{"prefix": p} for p in agg.output_prefixes]
    content = render(rendered_records, profile.format)

    content_type = _CONTENT_TYPES.get(profile.format, "application/octet-stream")
    return Response(content=content, media_type=content_type)
