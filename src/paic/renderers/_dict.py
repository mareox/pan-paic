"""Shared helper for renderers — coerce a record-like object to a plain dict."""

from __future__ import annotations

from typing import Any


def record_to_dict(rec: object) -> dict[str, Any]:
    """Coerce a PrefixRecord (or compatible object) to a plain dict."""
    if hasattr(rec, "model_dump"):
        return rec.model_dump()
    if hasattr(rec, "__dict__"):
        return dict(rec.__dict__)
    return dict(rec)  # type: ignore[call-overload]
