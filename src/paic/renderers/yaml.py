"""YAML renderer for prefix records."""

from __future__ import annotations

import yaml  # type: ignore[import-untyped]

from paic.renderers._dict import record_to_dict


def render(records: list, options: dict | None = None) -> bytes:
    """Render records as YAML; round-trips via yaml.safe_load to the JSON dict shape."""
    record_dicts = [record_to_dict(r) for r in records]
    payload = {"records": record_dicts, "summary": {"count": len(record_dicts)}}
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).encode("utf-8")
