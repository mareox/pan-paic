"""EDL (External Dynamic List) renderer: one prefix per line, no extra tokens."""

from __future__ import annotations

from datetime import UTC, datetime


def render(records: list, options: dict | None = None) -> bytes:
    """Render records as an EDL: one prefix per line.

    Options:
        with_header (bool): prepend a single ``# generated ts=<iso>`` comment line.
    """
    opts = options or {}
    lines: list[str] = []

    if opts.get("with_header"):
        ts = datetime.now(tz=UTC).isoformat()
        lines.append(f"# generated ts={ts}")

    for rec in records:
        prefix = rec.prefix if hasattr(rec, "prefix") else rec["prefix"]
        lines.append(prefix)

    return "\n".join(lines).encode("utf-8")
