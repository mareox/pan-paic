"""Plain-text renderer — outputs only prefix strings."""

from __future__ import annotations

_SEPARATORS = {
    "comma": ",",
    "space": " ",
    "newline": "\n",
}


def render(records: list, options: dict | None = None) -> bytes:
    """Render records as plain prefix strings.

    Options:
        separator (str): one of ``"comma"``, ``"space"``, ``"newline"`` (default).
    """
    opts = options or {}
    sep_key = opts.get("separator", "newline")
    sep = _SEPARATORS.get(sep_key, "\n")

    prefixes: list[str] = []
    for rec in records:
        prefix = rec.prefix if hasattr(rec, "prefix") else rec["prefix"]
        prefixes.append(prefix)

    return sep.join(prefixes).encode("utf-8")
