"""Profile CRUD + import/export + render — backed by YAML files on disk.

A *Profile* is a saved bundle of query settings: filter spec, aggregation mode,
optional budget/max_waste, output format. No credentials are persisted.
``/render`` requires ``api_key`` + ``prod`` in the request body, exactly like
``/api/query``.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi import File as FileParam

from paic.api.reports import (
    QueryRequest,
    _build_output_records,
    _fetch_filter_summarize,
)
from paic.api.schemas.profile import Profile, ProfileCreate, ProfileUpdate
from paic.core.filters import FilterSpec
from paic.renderers import render
from paic.storage import ProfileStore, get_profile_store

_CONTENT_TYPES: dict[str, str] = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "xml": "application/xml",
    "edl": "text/plain; charset=utf-8",
    "yaml": "application/yaml",
    "plain": "text/plain; charset=utf-8",
}

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def _store() -> ProfileStore:
    return get_profile_store()


def _validate_filter_spec_json(value: str | None) -> None:
    if value is None:
        return
    try:
        FilterSpec.model_validate_json(value)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"filter_spec_json is not a valid FilterSpec: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=Profile, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ProfileCreate,
    store: ProfileStore = Depends(_store),  # noqa: B008
) -> Profile:
    """Create a new aggregation profile."""
    if any(p.name == body.name for p in store.list()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Profile with name '{body.name}' already exists.",
        )
    _validate_filter_spec_json(body.filter_spec_json)

    profile = Profile(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        mode=body.mode,
        budget=body.budget,
        max_waste=body.max_waste,
        format=body.format,
        filter_spec_json=body.filter_spec_json,
        saved_at=datetime.now(tz=UTC),
    )
    store.save(profile)
    return profile


@router.get("", response_model=list[Profile])
def list_profiles(store: ProfileStore = Depends(_store)) -> list[Profile]:  # noqa: B008
    """Return all profiles."""
    return store.list()


@router.get("/{profile_id}", response_model=Profile)
def get_profile(
    profile_id: str, store: ProfileStore = Depends(_store)  # noqa: B008
) -> Profile:
    """Return a single profile by ID."""
    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return profile


@router.put("/{profile_id}", response_model=Profile)
def update_profile(
    profile_id: str,
    body: ProfileUpdate,
    store: ProfileStore = Depends(_store),  # noqa: B008
) -> Profile:
    """Update mutable profile fields."""
    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

    if body.filter_spec_json is not None:
        _validate_filter_spec_json(body.filter_spec_json)

    update = body.model_dump(exclude_unset=True)
    updated = profile.model_copy(update=update)
    updated.saved_at = datetime.now(tz=UTC)
    store.save(updated)
    return updated


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: str, store: ProfileStore = Depends(_store)  # noqa: B008
) -> None:
    """Delete a profile."""
    if not store.delete(profile_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")


# ---------------------------------------------------------------------------
# Export / Import — YAML payloads for sharing across deployments
# ---------------------------------------------------------------------------


@router.get("/{profile_id}/export")
def export_profile(
    profile_id: str, store: ProfileStore = Depends(_store)  # noqa: B008
) -> Response:
    """Download the profile as a YAML file."""
    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    body = store.export_one(profile_id)
    slug = ProfileStore.slugify(profile.name)
    return Response(
        content=body,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{slug}.yaml"'},
    )


@router.post("/import", response_model=Profile, status_code=status.HTTP_201_CREATED)
async def import_profile(
    file: UploadFile = FileParam(...),  # noqa: B008
    store: ProfileStore = Depends(_store),  # noqa: B008
) -> Profile:
    """Import a profile from an uploaded YAML file."""
    payload = await file.read()
    try:
        return store.import_one(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


# ---------------------------------------------------------------------------
# Render — apply profile settings to live Prisma data
# ---------------------------------------------------------------------------


class ProfileRenderRequest(QueryRequest):
    """Body for /render: caller supplies api_key + prod; profile supplies the rest."""


@router.post("/{profile_id}/render")
async def render_profile(
    profile_id: str,
    body: ProfileRenderRequest,
    store: ProfileStore = Depends(_store),  # noqa: B008
) -> Response:
    """Apply a saved profile to live Prisma data and return rendered bytes."""
    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

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
        mode=profile.mode,
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
