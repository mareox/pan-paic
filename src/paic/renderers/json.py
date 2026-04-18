"""JSON renderer for prefix records.

Module is `paic.renderers.json`; the stdlib ``json`` is aliased as ``stdlib_json``
to avoid recursive import shadowing.
"""

from __future__ import annotations

import json as stdlib_json

from paic.renderers._dict import record_to_dict


def render(records: list, options: dict | None = None) -> bytes:
    """Render records as JSON with schema ``{records: [...], summary: {count: N}}``."""
    record_dicts = [record_to_dict(r) for r in records]
    payload = {"records": record_dicts, "summary": {"count": len(record_dicts)}}
    return stdlib_json.dumps(payload, indent=2, default=str).encode("utf-8")
