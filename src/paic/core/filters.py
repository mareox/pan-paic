"""Filter engine for PrefixRecord collections."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from paic.core.types import PrefixRecord


class FilterSpec(BaseModel):
    """Specification for filtering a list of PrefixRecords.

    All fields are optional. Unspecified fields impose no constraint.
    Multiple fields are combined with AND logic.
    """

    service_types: set[str] | None = None
    addr_types: set[str] | None = None
    regions: set[str] | None = None
    countries: set[str] | None = None
    location_names: set[str] | None = None
    ip_version: Literal[4, 6] | None = None
    text: str | None = None


def apply_filters(records: list[PrefixRecord], spec: FilterSpec) -> list[PrefixRecord]:
    """Return only the records that match every specified filter in *spec*.

    An unspecified filter (None) passes all records.  Multiple filters are
    combined with AND: a record must satisfy all active filters to be included.

    The ``text`` filter performs a case-insensitive substring search across
    ``prefix``, ``region``, ``country``, and ``location_name``.
    """
    result: list[PrefixRecord] = []

    for record in records:
        if spec.service_types is not None and record.service_type not in spec.service_types:
            continue
        if spec.addr_types is not None and record.addr_type not in spec.addr_types:
            continue
        if spec.regions is not None and record.region not in spec.regions:
            continue
        if spec.countries is not None and record.country not in spec.countries:
            continue
        if spec.location_names is not None and record.location_name not in spec.location_names:
            continue
        if spec.ip_version is not None and record.ip_version != spec.ip_version:
            continue
        if spec.text is not None:
            needle = spec.text.lower()
            haystack = " ".join(
                v
                for v in (
                    record.prefix,
                    record.region or "",
                    record.country or "",
                    record.location_name or "",
                )
            ).lower()
            if needle not in haystack:
                continue
        result.append(record)

    return result
