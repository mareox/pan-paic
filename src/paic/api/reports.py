"""Stateless query endpoints.

Endpoints:
    GET  /api/known-prods         - list known Prisma cloud selectors
    POST /api/query               - fetch live, filter, summarize, render
    POST /api/query/preview       - same as /api/query but returns the
                                    AggregateResult JSON instead of bytes
                                    (so the UI can preview output size /
                                    waste before downloading).

These endpoints never persist the caller's API key.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from paic.aggregation import AggregateResult, summarize
from paic.clients.prisma import (
    PrismaAuthError,
    PrismaError,
    PrismaRateLimitError,
    PrismaSchemaError,
    PrismaUpstreamError,
    fetch_prisma_ips,
    known_prods,
)
from paic.core.filters import FilterSpec, apply_filters
from paic.core.types import PrefixRecord
from paic.renderers import SUPPORTED_FORMATS, render

router = APIRouter(tags=["query"])

_CONTENT_TYPES: dict[str, str] = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "xml": "application/xml",
    "edl": "text/plain; charset=utf-8",
    "yaml": "application/yaml",
    "plain": "text/plain; charset=utf-8",
}

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """Request body for /api/query and /api/query/preview."""

    api_key: str = Field(
        ..., min_length=1, description="Plaintext Prisma API key (never persisted)."
    )
    prod: str = Field(default="prod", min_length=1, max_length=64)
    base_url_override: str | None = Field(default=None, max_length=512)
    service_type: str = "all"
    addr_type: str = "all"
    filter: FilterSpec = Field(default_factory=FilterSpec)
    mode: Literal["exact", "lossless", "budget", "waste"] = "exact"
    budget: int | None = Field(default=None, ge=1)
    max_waste: float | None = Field(default=None, ge=0.0, le=1.0)
    format: str = Field(default="json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ip_version(prefix: str) -> Literal[4, 6]:
    return 6 if ":" in prefix else 4


def _records_from_response(resp: object) -> list[PrefixRecord]:
    """Flatten a PrismaResponse into a list[PrefixRecord]."""
    records: list[PrefixRecord] = []
    for entry in getattr(resp, "result", []):
        for detail in getattr(entry, "addressDetails", []):
            extra = getattr(detail, "model_extra", {}) or {}
            zone = getattr(entry, "zone", None) or extra.get("zone")
            country = extra.get("country")
            location_name = None
            node_names = extra.get("node_name")
            if isinstance(node_names, list) and node_names:
                location_name = str(node_names[0])
            elif isinstance(node_names, str):
                location_name = node_names

            records.append(
                PrefixRecord(
                    prefix=detail.address,
                    service_type=detail.serviceType,
                    addr_type=detail.addressType,
                    region=zone,
                    country=country,
                    location_name=location_name,
                    ip_version=_ip_version(detail.address),
                )
            )
    return records


def _summarize(records: list[PrefixRecord], req: QueryRequest) -> AggregateResult:
    """Run the aggregation engine, surfacing validation errors as HTTP 400."""
    try:
        return summarize(
            [r.prefix for r in records],
            req.mode,
            budget=req.budget,
            max_waste=req.max_waste,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _build_output_records(
    inputs: list[PrefixRecord], output_prefixes: list[str]
) -> list[PrefixRecord]:
    """Map each output prefix back to a PrefixRecord with metadata.

    For aggregated supernets there can be multiple input records that collapse
    into one output: we keep the *first* matching input's metadata fields.
    Inputs with identical prefix to the output trivially match; for supernets
    we look for any input contained by the output.
    """
    if not inputs:
        return [
            PrefixRecord(
                prefix=p,
                service_type="aggregated",
                addr_type="aggregated",
                region=None,
                country=None,
                location_name=None,
                ip_version=_ip_version(p),
            )
            for p in output_prefixes
        ]

    # Build a lookup: exact prefix → first input record with that prefix.
    by_prefix: dict[str, PrefixRecord] = {}
    for r in inputs:
        by_prefix.setdefault(r.prefix, r)

    # For aggregated supernets we walk inputs once via netaddr and pick the
    # first input contained by each output; only used when no exact match.
    from netaddr import IPNetwork  # local import keeps cold-start lean

    parsed_inputs: list[tuple[IPNetwork, PrefixRecord]] | None = None

    out: list[PrefixRecord] = []
    for prefix in output_prefixes:
        match = by_prefix.get(prefix)
        if match is None:
            if parsed_inputs is None:
                parsed_inputs = [(IPNetwork(r.prefix), r) for r in inputs]
            net = IPNetwork(prefix)
            match = next(
                (rec for inp_net, rec in parsed_inputs if inp_net in net),
                None,
            )

        if match is None:
            out.append(
                PrefixRecord(
                    prefix=prefix,
                    service_type="aggregated",
                    addr_type="aggregated",
                    region=None,
                    country=None,
                    location_name=None,
                    ip_version=_ip_version(prefix),
                )
            )
        else:
            out.append(
                PrefixRecord(
                    prefix=prefix,
                    service_type=match.service_type,
                    addr_type=match.addr_type,
                    region=match.region,
                    country=match.country,
                    location_name=match.location_name,
                    ip_version=_ip_version(prefix),
                )
            )
    return out


async def _fetch_filter_summarize(
    req: QueryRequest,
) -> tuple[list[PrefixRecord], AggregateResult]:
    """Common pipeline used by both /api/query and /api/query/preview."""
    if req.format not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format {req.format!r}. Choose from: {SUPPORTED_FORMATS}",
        )
    if req.mode == "budget" and req.budget is None:
        raise HTTPException(status_code=400, detail="budget is required when mode='budget'")
    if req.mode == "waste" and req.max_waste is None:
        raise HTTPException(status_code=400, detail="max_waste is required when mode='waste'")

    try:
        response = await fetch_prisma_ips(
            req.api_key,
            prod=req.prod,
            base_url_override=req.base_url_override,
            service_type=req.service_type,
            addr_type=req.addr_type,
        )
    except PrismaAuthError as exc:
        raise HTTPException(status_code=401, detail=f"Prisma auth failed: {exc}") from exc
    except PrismaRateLimitError as exc:
        raise HTTPException(status_code=429, detail=f"Prisma rate limited: {exc}") from exc
    except PrismaSchemaError as exc:
        raise HTTPException(status_code=502, detail=f"Prisma schema error: {exc}") from exc
    except PrismaUpstreamError as exc:
        raise HTTPException(status_code=502, detail=f"Prisma upstream error: {exc}") from exc
    except PrismaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        # Bad prod selector
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    records = _records_from_response(response)
    filtered = apply_filters(records, req.filter)
    agg = _summarize(filtered, req)
    return filtered, agg


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/known-prods")
def list_known_prods() -> dict[str, list[str]]:
    """Return the registry of well-known Prisma cloud selectors."""
    return {"prods": known_prods()}


@router.post("/api/query")
async def query(req: QueryRequest) -> Response:
    """Fetch from Prisma live, filter, summarize, and render."""
    filtered, agg = await _fetch_filter_summarize(req)

    output_records = _build_output_records(filtered, agg.output_prefixes)
    body = render(output_records, req.format)

    headers = {
        "X-Input-Count": str(agg.input_count),
        "X-Output-Count": str(agg.output_count),
        "X-Waste-Ratio": f"{agg.waste_ratio:.6f}",
        "X-Source-Prod": req.prod,
    }
    return Response(
        content=body,
        media_type=_CONTENT_TYPES.get(req.format, "application/octet-stream"),
        headers=headers,
    )


@router.post("/api/query/preview")
async def query_preview(req: QueryRequest) -> JSONResponse:
    """Same as /api/query but returns the AggregateResult JSON (no rendering)."""
    _filtered, agg = await _fetch_filter_summarize(req)
    return JSONResponse(content=agg.model_dump(mode="json"))
