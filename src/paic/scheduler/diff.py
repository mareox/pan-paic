"""Pure-function diff computation for Prisma Access prefix snapshots."""

from __future__ import annotations


def compute_diff(
    prior_payload: dict[str, list[str]],
    new_payload: dict[str, list[str]],
) -> dict[str, object]:
    """Compute added/removed prefixes per service_type between two payloads.

    Args:
        prior_payload: Normalized payload from the previous Snapshot.
                       Shape: {service_type: sorted([prefix_str, ...])}
        new_payload:   Normalized payload from the new Snapshot.
                       Same shape.

    Returns:
        Dict with per-service_type diffs and a top-level ``unchanged_count``::

            {
                "service_type_A": {"added": [...], "removed": [...]},
                ...,
                "unchanged_count": N,
            }
    """
    all_service_types = set(prior_payload.keys()) | set(new_payload.keys())
    result: dict[str, object] = {}
    unchanged_count = 0

    for svc in sorted(all_service_types):
        prior_set = set(prior_payload.get(svc, []))
        new_set = set(new_payload.get(svc, []))

        added = sorted(new_set - prior_set)
        removed = sorted(prior_set - new_set)
        unchanged_count += len(prior_set & new_set)

        result[svc] = {"added": added, "removed": removed}

    result["unchanged_count"] = unchanged_count
    return result
