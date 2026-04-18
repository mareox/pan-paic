"""HTML and plain-text email body builders for diff alert emails."""

from __future__ import annotations

import json
from typing import Any


def _parse_grouped(json_str: str) -> dict[str, list[str]]:
    """Parse a diff JSON string into {service_type: [prefix, ...]} mapping."""
    try:
        data: Any = json.loads(json_str)
    except (ValueError, TypeError):
        return {}
    if isinstance(data, dict):
        return {k: list(v) for k, v in data.items() if isinstance(v, list)}
    if isinstance(data, list):
        return {"default": [str(x) for x in data]}
    return {}


def build_subject(tenant_name: str, added_count: int, removed_count: int) -> str:
    """Return the email subject line."""
    return f"[PAIC] {tenant_name} prefix change: +{added_count} / -{removed_count}"


def _count_prefixes(grouped: dict[str, list[str]]) -> int:
    return sum(len(v) for v in grouped.values())


def build_text_body(
    tenant_name: str,
    added_grouped: dict[str, list[str]],
    removed_grouped: dict[str, list[str]],
    report_url: str,
) -> str:
    """Build a plain-text email body."""
    lines: list[str] = [
        f"PAIC Prefix Change Report — {tenant_name}",
        "=" * 60,
        "",
    ]

    added_count = _count_prefixes(added_grouped)
    removed_count = _count_prefixes(removed_grouped)

    if added_count == 0 and removed_count == 0:
        lines.append("No prefix changes detected.")
    else:
        if added_count:
            lines.append(f"ADDED ({added_count} total):")
            for svc, prefixes in sorted(added_grouped.items()):
                lines.append(f"  [{svc}]")
                for p in sorted(prefixes):
                    lines.append(f"    + {p}")
            lines.append("")

        if removed_count:
            lines.append(f"REMOVED ({removed_count} total):")
            for svc, prefixes in sorted(removed_grouped.items()):
                lines.append(f"  [{svc}]")
                for p in sorted(prefixes):
                    lines.append(f"    - {p}")
            lines.append("")

    if report_url:
        lines.append(f"Full report: {report_url}")

    return "\n".join(lines)


def build_html_body(
    tenant_name: str,
    added_grouped: dict[str, list[str]],
    removed_grouped: dict[str, list[str]],
    report_url: str,
) -> str:
    """Build an HTML email body."""
    added_count = _count_prefixes(added_grouped)
    removed_count = _count_prefixes(removed_grouped)

    parts: list[str] = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'></head><body>",
        f"<h2>PAIC Prefix Change Report &mdash; {tenant_name}</h2>",
    ]

    if added_count == 0 and removed_count == 0:
        parts.append("<p>No prefix changes detected.</p>")
    else:
        if added_count:
            parts.append(f"<h3>Added ({added_count} total)</h3>")
            for svc, prefixes in sorted(added_grouped.items()):
                parts.append(f"<h4>{svc}</h4><ul>")
                for p in sorted(prefixes):
                    parts.append(f"<li style='color:green'>+ {p}</li>")
                parts.append("</ul>")

        if removed_count:
            parts.append(f"<h3>Removed ({removed_count} total)</h3>")
            for svc, prefixes in sorted(removed_grouped.items()):
                parts.append(f"<h4>{svc}</h4><ul>")
                for p in sorted(prefixes):
                    parts.append(f"<li style='color:red'>- {p}</li>")
                parts.append("</ul>")

    if report_url:
        parts.append(f"<p><a href='{report_url}'>View full report</a></p>")

    parts.append("</body></html>")
    return "\n".join(parts)


def build_email_parts(
    tenant_name: str,
    added_json: str,
    removed_json: str,
    report_url: str,
) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for a diff email.

    Args:
        tenant_name: Display name of the tenant.
        added_json: JSON string of added prefixes (grouped by service_type).
        removed_json: JSON string of removed prefixes (grouped by service_type).
        report_url: URL to the full diff report.

    Returns:
        Tuple of (subject, plain_text_body, html_body).
    """
    added_grouped = _parse_grouped(added_json)
    removed_grouped = _parse_grouped(removed_json)
    added_count = _count_prefixes(added_grouped)
    removed_count = _count_prefixes(removed_grouped)

    subject = build_subject(tenant_name, added_count, removed_count)
    text_body = build_text_body(tenant_name, added_grouped, removed_grouped, report_url)
    html_body = build_html_body(tenant_name, added_grouped, removed_grouped, report_url)

    return subject, text_body, html_body
