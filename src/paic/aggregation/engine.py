"""Prefix summarization / aggregation engine (US-006).

Four modes are supported:

* ``exact``    - return the deduplicated input unchanged.
* ``lossless`` - :func:`netaddr.cidr_merge`; never widens covered range.
* ``budget``   - greedy minimum-waste merging until ``<= budget`` prefixes remain.
* ``waste``    - greedy merging while resulting waste ratio stays ``<= max_waste``.

Both greedy modes treat IPv4 and IPv6 inputs as independent universes (a v4
prefix can never merge with a v6 prefix) and route each universe through the
same heap-based merger living in :mod:`paic.aggregation._greedy`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from netaddr import IPNetwork, cidr_merge
from pydantic import BaseModel, Field

from paic.aggregation._greedy import (
    greedy_merge_to_budget,
    greedy_merge_to_waste,
)

Mode = Literal["exact", "lossless", "budget", "waste"]


class AggregateResult(BaseModel):
    """Result of a :func:`summarize` call.

    Includes both the merged prefix list and statistics that let operators
    judge how much address space is being announced beyond what was originally
    advertised (the *waste*).
    """

    output_prefixes: list[str]
    input_count: int
    output_count: int
    covered_ips: int
    announced_ips: int
    waste_count: int
    waste_ratio: float
    largest_waste_prefix: dict | None = None
    mode: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dedup_preserve_order(prefixes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for p in prefixes:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _parse_prefixes(prefixes: list[str]) -> list[IPNetwork]:
    return [IPNetwork(p) for p in prefixes]


def _split_by_version(networks: list[IPNetwork]) -> tuple[list[IPNetwork], list[IPNetwork]]:
    v4 = [n for n in networks if n.version == 4]
    v6 = [n for n in networks if n.version == 6]
    return v4, v6


def _sorted_by_addr(networks: list[IPNetwork]) -> list[IPNetwork]:
    return sorted(networks, key=lambda n: int(n.network))


def _largest_waste_prefix(
    output_nets: list[IPNetwork], input_nets: list[IPNetwork]
) -> dict | None:
    """Identify the single output prefix with the highest *individual* waste.

    For each output supernet, sum the sizes of input prefixes it covers; the
    waste ratio for that supernet is ``(supernet.size - announced) / supernet.size``.
    The supernet with the highest such ratio (ties broken by raw waste count)
    is returned as a dict, or ``None`` if there are no outputs.
    """
    if not output_nets:
        return None

    # Pair output nets with the announced IPs they cover.  We do this in
    # O(N+M log M) by sorting both lists and walking them with a pointer.
    inputs_sorted = sorted(input_nets, key=lambda n: (n.version, int(n.network)))
    outputs_sorted = sorted(output_nets, key=lambda n: (n.version, int(n.network)))

    # For each output, find inputs whose start address falls inside it.
    # Inputs are non-overlapping (lossless output) so each input maps to one supernet.
    cover_map: dict[int, int] = {id(out): 0 for out in outputs_sorted}
    out_idx = 0
    for inp in inputs_sorted:
        # Advance output pointer until we find one whose range contains this input.
        while out_idx < len(outputs_sorted):
            out = outputs_sorted[out_idx]
            if out.version != inp.version:
                out_idx += 1
                continue
            if int(inp.network) >= int(out.network) and int(inp.broadcast or inp.network) <= int(
                out.broadcast or out.network
            ):
                cover_map[id(out)] += int(inp.size)
                break
            # input lies past this output → next output
            out_idx += 1
        else:
            # Should not happen: every input must fall inside some output.
            continue

    best: tuple[float, int, IPNetwork] | None = None
    for out in outputs_sorted:
        announced = cover_map[id(out)]
        covers = int(out.size)
        if covers == 0:
            ratio = 0.0
        else:
            ratio = (covers - announced) / covers
        waste = covers - announced
        key = (ratio, waste)
        if best is None or key > (best[0], best[1]):
            best = (ratio, waste, out)

    if best is None:
        return None
    ratio, _waste, net = best
    announced = cover_map[id(net)]
    covers = int(net.size)
    return {
        "prefix": str(net.cidr),
        "covers": covers,
        "announces": announced,
        "ratio": ratio,
    }


def _build_result(
    *,
    mode: str,
    input_prefix_strs: list[str],
    input_nets_after_dedup: list[IPNetwork],
    output_nets: list[IPNetwork],
) -> AggregateResult:
    output_prefixes = [str(n.cidr) for n in output_nets]
    covered = sum(int(n.size) for n in output_nets)
    announced = sum(int(n.size) for n in input_nets_after_dedup)
    waste = covered - announced
    ratio = (waste / covered) if covered > 0 else 0.0
    return AggregateResult(
        output_prefixes=output_prefixes,
        input_count=len(input_prefix_strs),
        output_count=len(output_prefixes),
        covered_ips=covered,
        announced_ips=announced,
        waste_count=waste,
        waste_ratio=ratio,
        largest_waste_prefix=_largest_waste_prefix(output_nets, input_nets_after_dedup),
        mode=mode,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def summarize(
    prefixes: list[str],
    mode: Mode,
    *,
    budget: int | None = None,
    max_waste: float | None = None,
) -> AggregateResult:
    """Summarize a list of CIDR ``prefixes`` according to ``mode``.

    Parameters
    ----------
    prefixes:
        List of CIDR strings (IPv4 and/or IPv6).
    mode:
        One of ``"exact"``, ``"lossless"``, ``"budget"``, ``"waste"``.
    budget:
        Required for mode ``"budget"``; the maximum number of output prefixes.
        Must be ``>= 1``.
    max_waste:
        Required for mode ``"waste"``; the maximum allowed waste ratio in the
        closed interval ``[0.0, 1.0]``.

    Raises
    ------
    ValueError
        If a required argument is missing or out of range, or if ``mode`` is
        unknown.
    """
    # ----- validation
    if mode not in ("exact", "lossless", "budget", "waste"):
        raise ValueError(f"unknown mode: {mode!r}")
    if mode == "budget":
        if budget is None:
            raise ValueError("budget is required when mode='budget'")
        if budget < 1:
            raise ValueError("budget must be >= 1")
    if mode == "waste":
        if max_waste is None:
            raise ValueError("max_waste is required when mode='waste'")
        if not (0.0 <= max_waste <= 1.0):
            raise ValueError("max_waste must be in [0.0, 1.0]")

    # ----- empty fast-path: still build a well-formed result
    if not prefixes:
        return AggregateResult(
            output_prefixes=[],
            input_count=0,
            output_count=0,
            covered_ips=0,
            announced_ips=0,
            waste_count=0,
            waste_ratio=0.0,
            largest_waste_prefix=None,
            mode=mode,
        )

    # ----- exact mode: dedup (preserve order) and return
    if mode == "exact":
        deduped_strs = _dedup_preserve_order(prefixes)
        deduped_nets = _parse_prefixes(deduped_strs)
        # output prefixes for exact mode preserve the *input* string form,
        # not the canonical CIDR rewrite, per acceptance criterion 1.
        covered = sum(int(n.size) for n in deduped_nets)
        announced = covered  # exact mode never widens
        return AggregateResult(
            output_prefixes=deduped_strs,
            input_count=len(prefixes),
            output_count=len(deduped_strs),
            covered_ips=covered,
            announced_ips=announced,
            waste_count=0,
            waste_ratio=0.0,
            largest_waste_prefix=None,
            mode=mode,
        )

    # ----- common pre-processing for lossless / budget / waste
    input_nets = _parse_prefixes(prefixes)
    # Lossless baseline: cidr_merge collapses overlap+adjacency without widening.
    lossless = cidr_merge(input_nets)
    # `cidr_merge` returns IPNetwork, but type stubs sometimes say IPNetwork|IPRange.
    lossless_nets: list[IPNetwork] = [IPNetwork(str(n.cidr)) for n in lossless]

    # Compute the post-dedup announced footprint (= sum of lossless sizes).
    # This is the figure used for waste calculations: cidr_merge eliminates
    # overlap so this matches "after dedup" semantics.
    announced_input_nets = lossless_nets

    if mode == "lossless":
        return _build_result(
            mode=mode,
            input_prefix_strs=prefixes,
            input_nets_after_dedup=announced_input_nets,
            output_nets=lossless_nets,
        )

    # Split into v4 / v6 universes; greedy never crosses families.
    v4, v6 = _split_by_version(lossless_nets)
    v4 = _sorted_by_addr(v4)
    v6 = _sorted_by_addr(v6)

    if mode == "budget":
        assert budget is not None  # for mypy
        # Distribute the budget proportionally to family sizes.  When one family
        # is empty the other receives the full budget.
        out_v4, out_v6 = _allocate_budget_per_family(v4, v6, budget)
        merged = out_v4 + out_v6
        return _build_result(
            mode=mode,
            input_prefix_strs=prefixes,
            input_nets_after_dedup=announced_input_nets,
            output_nets=merged,
        )

    # mode == "waste"
    assert max_waste is not None  # for mypy
    if max_waste == 0.0:
        # No widening permitted → identical to lossless.
        return _build_result(
            mode=mode,
            input_prefix_strs=prefixes,
            input_nets_after_dedup=announced_input_nets,
            output_nets=lossless_nets,
        )

    announced_v4 = sum(int(n.size) for n in v4)
    announced_v6 = sum(int(n.size) for n in v6)
    out_v4 = greedy_merge_to_waste(v4, announced_v4, max_waste) if v4 else []
    out_v6 = greedy_merge_to_waste(v6, announced_v6, max_waste) if v6 else []
    merged = out_v4 + out_v6
    return _build_result(
        mode=mode,
        input_prefix_strs=prefixes,
        input_nets_after_dedup=announced_input_nets,
        output_nets=merged,
    )


def _allocate_budget_per_family(
    v4: list[IPNetwork], v6: list[IPNetwork], budget: int
) -> tuple[list[IPNetwork], list[IPNetwork]]:
    """Split the prefix budget between IPv4 and IPv6 lists.

    The split is proportional to the lossless sizes of each family, with at
    least one slot per non-empty family.  The function returns the merged
    per-family prefix lists.
    """
    n_v4 = len(v4)
    n_v6 = len(v6)
    total = n_v4 + n_v6
    if total <= budget:
        # No reduction needed for either family.
        return v4, v6

    if n_v4 == 0:
        return [], greedy_merge_to_budget(v6, budget)
    if n_v6 == 0:
        return greedy_merge_to_budget(v4, budget), []

    # Both families present and over budget.  Allocate at least 1 slot each.
    # Proportional split:
    raw_v4 = max(1, round(budget * n_v4 / total))
    raw_v6 = max(1, budget - raw_v4)
    # Re-balance if rounding overshot.
    while raw_v4 + raw_v6 > budget:
        if raw_v4 > raw_v6:
            raw_v4 -= 1
        else:
            raw_v6 -= 1
    while raw_v4 + raw_v6 < budget:
        # Spend leftover on the larger family.
        if n_v4 - raw_v4 > n_v6 - raw_v6:
            raw_v4 += 1
        else:
            raw_v6 += 1

    out_v4 = greedy_merge_to_budget(v4, raw_v4)
    out_v6 = greedy_merge_to_budget(v6, raw_v6)
    return out_v4, out_v6
