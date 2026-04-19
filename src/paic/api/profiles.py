"""Profile CRUD endpoints + render action.

A *Profile* is a saved bundle of query settings: filter spec, aggregation mode,
optional budget/max_waste, output format.  No credentials are persisted —
``/render`` requires ``api_key`` + ``prod`` in the request body, exactly like
``/api/query``.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from paic.api.reports import (
    QueryRequest,
    _build_output_records,
    _fetch_filter_summarize,
)
from paic.api.schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate
from paic.core.filters import FilterSpec
from paic.db.models import Profile
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
# Render action — applies a profile's saved settings on top of caller-supplied
# api_key + prod.  No credentials live in the DB.
# ---------------------------------------------------------------------------


class ProfileRenderRequest(QueryRequest):
    """Body for /render: same as QueryRequest but profile fields are ignored.

    The profile's ``mode``, ``budget``, ``max_waste``, ``format``, and
    ``filter`` always win.  The caller supplies only the auth fields
    (``api_key``, ``prod``, ``base_url_override``) and the upstream
    ``service_type`` / ``addr_type`` filters that go to Prisma.
    """


@router.post("/{profile_id}/render")
async def render_profile(
    profile_id: str,
    body: ProfileRenderRequest,
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Apply a saved profile to live Prisma data and return rendered bytes."""
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

    # Build a QueryRequest from caller's auth fields + profile's settings.
    if profile.filter_spec_json:
        filter_spec = FilterSpec.model_validate(json.loads(profile.filter_spec_json))
    else:
        filter_spec = FilterSpec()

    req = QueryRequest(
        api_key=body.api_key,
        prod=body.prod,
        base_url_override=body.base_url_override,
        service_type=body.service_type,
        addr_type=body.addr_type,
        filter=filter_spec,
        mode=profile.mode,  # type: ignore[arg-type]
        budget=profile.budget,
        max_waste=profile.max_waste,
        format=profile.format,
    )

    filtered, agg = await _fetch_filter_summarize(req)
    output_records = _build_output_records(filtered, agg.output_prefixes)
    content = render(output_records, profile.format)

    return Response(
        content=content,
        media_type=_CONTENT_TYPES.get(profile.format, "application/octet-stream"),
        headers={
            "X-Input-Count": str(agg.input_count),
            "X-Output-Count": str(agg.output_count),
            "X-Waste-Ratio": f"{agg.waste_ratio:.6f}",
            "X-Source-Prod": req.prod,
        },
    )
