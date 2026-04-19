"""Renderer registry: dispatch render(records, fmt, options) -> bytes."""

from __future__ import annotations

from typing import Any

from paic.renderers import csv as _csv
from paic.renderers import edl as _edl
from paic.renderers import json as _json
from paic.renderers import plain as _plain
from paic.renderers import xml as _xml
from paic.renderers import yaml as _yaml
from paic.renderers._dict import record_to_dict

_REGISTRY: dict[str, Any] = {
    "csv": _csv,
    "json": _json,
    "xml": _xml,
    "edl": _edl,
    "yaml": _yaml,
    "plain": _plain,
}

SUPPORTED_FORMATS: list[str] = list(_REGISTRY.keys())

__all__ = ["SUPPORTED_FORMATS", "record_to_dict", "render"]


def render(records: list, fmt: str, options: dict | None = None) -> bytes:
    """Dispatch to the appropriate renderer module."""
    mod = _REGISTRY.get(fmt)
    if mod is None:
        raise ValueError(f"Unsupported format {fmt!r}. Choose from: {SUPPORTED_FORMATS}")
    return mod.render(records, options)
