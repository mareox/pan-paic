"""CSV renderer for prefix records."""

from __future__ import annotations

import csv
import io

_HEADER = ["prefix", "service_type", "addr_type", "region", "country", "location_name"]


def render(records: list, options: dict | None = None) -> bytes:
    """Render records as CSV with a fixed header row."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_HEADER)

    for rec in records:
        if hasattr(rec, "prefix"):
            row = [
                rec.prefix,
                rec.service_type,
                rec.addr_type,
                rec.region,
                rec.country,
                rec.location_name,
            ]
        else:
            row = [rec.get(f) for f in _HEADER]
        writer.writerow(row)

    return buf.getvalue().encode("utf-8")
