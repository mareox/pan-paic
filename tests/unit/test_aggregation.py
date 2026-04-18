"""Unit tests for the prefix summarization engine (US-006)."""

from __future__ import annotations

import random
import time

import pytest
from netaddr import IPNetwork

from paic.aggregation import AggregateResult, summarize

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_unknown_mode(self):
        with pytest.raises(ValueError, match="unknown mode"):
            summarize(["1.1.1.0/24"], "bogus")  # type: ignore[arg-type]

    def test_budget_requires_budget_arg(self):
        with pytest.raises(ValueError, match="budget is required"):
            summarize(["1.1.1.0/24"], "budget")

    def test_budget_must_be_positive(self):
        with pytest.raises(ValueError, match="budget must be >= 1"):
            summarize(["1.1.1.0/24"], "budget", budget=0)

    def test_budget_must_be_positive_negative(self):
        with pytest.raises(ValueError, match="budget must be >= 1"):
            summarize(["1.1.1.0/24"], "budget", budget=-3)

    def test_waste_requires_max_waste_arg(self):
        with pytest.raises(ValueError, match="max_waste is required"):
            summarize(["1.1.1.0/24"], "waste")

    def test_waste_below_zero(self):
        with pytest.raises(ValueError, match=r"max_waste must be in"):
            summarize(["1.1.1.0/24"], "waste", max_waste=-0.01)

    def test_waste_above_one(self):
        with pytest.raises(ValueError, match=r"max_waste must be in"):
            summarize(["1.1.1.0/24"], "waste", max_waste=1.5)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEmpty:
    @pytest.mark.parametrize("mode", ["exact", "lossless", "budget", "waste"])
    def test_empty_returns_zero_result(self, mode: str):
        kwargs: dict = {}
        if mode == "budget":
            kwargs["budget"] = 5
        if mode == "waste":
            kwargs["max_waste"] = 0.5
        r = summarize([], mode, **kwargs)  # type: ignore[arg-type]
        assert isinstance(r, AggregateResult)
        assert r.output_count == 0
        assert r.input_count == 0
        assert r.output_prefixes == []
        assert r.waste_ratio == 0.0
        assert r.largest_waste_prefix is None
        assert r.mode == mode


class TestSingleSlash32:
    @pytest.mark.parametrize(
        "mode,kwargs",
        [
            ("exact", {}),
            ("lossless", {}),
            ("budget", {"budget": 1}),
            ("budget", {"budget": 50}),
            ("waste", {"max_waste": 0.0}),
            ("waste", {"max_waste": 0.99}),
        ],
    )
    def test_single_prefix_unchanged(self, mode: str, kwargs: dict):
        r = summarize(["192.0.2.5/32"], mode, **kwargs)  # type: ignore[arg-type]
        assert r.output_count == 1
        assert r.output_prefixes == ["192.0.2.5/32"]
        assert r.waste_count == 0


# ---------------------------------------------------------------------------
# Mode: exact
# ---------------------------------------------------------------------------


class TestExactMode:
    def test_returns_input_unchanged(self):
        inp = ["1.1.1.0/24", "2.2.2.0/24", "3.3.3.0/24"]
        r = summarize(inp, "exact")
        assert r.output_prefixes == inp
        assert r.output_count == 3
        assert r.input_count == 3
        assert r.waste_count == 0
        assert r.waste_ratio == 0.0
        assert r.mode == "exact"

    def test_dedup_first_seen_order(self):
        inp = ["1.1.1.0/24", "2.2.2.0/24", "1.1.1.0/24", "3.3.3.0/24", "2.2.2.0/24"]
        r = summarize(inp, "exact")
        assert r.output_prefixes == ["1.1.1.0/24", "2.2.2.0/24", "3.3.3.0/24"]
        assert r.input_count == 5
        assert r.output_count == 3


# ---------------------------------------------------------------------------
# Mode: lossless
# ---------------------------------------------------------------------------


class TestLosslessMode:
    def test_collapses_adjacent(self):
        r = summarize(["1.1.1.0/32", "1.1.1.1/32"], "lossless")
        assert r.output_prefixes == ["1.1.1.0/31"]
        assert r.waste_count == 0

    def test_no_widening(self):
        r = summarize(["1.1.1.0/32", "1.1.1.100/32"], "lossless")
        # Not adjacent → must NOT collapse to a wider supernet.
        assert set(r.output_prefixes) == {"1.1.1.0/32", "1.1.1.100/32"}
        assert r.waste_count == 0
        assert r.waste_ratio == 0.0

    def test_overlap_dedup(self):
        r = summarize(["1.1.1.0/24", "1.1.1.128/25"], "lossless")
        # /25 is contained in /24 → result is just /24.
        assert r.output_prefixes == ["1.1.1.0/24"]
        assert r.waste_count == 0


# ---------------------------------------------------------------------------
# Mode: budget
# ---------------------------------------------------------------------------


class TestBudgetMode:
    def test_acceptance_criterion_3(self):
        """budget=2 on the canonical input must yield exactly 2 prefixes."""
        inp = ["1.1.3.2/32", "1.1.3.3/32", "1.1.3.9/32", "1.1.3.14/32"]
        r = summarize(inp, "budget", budget=2)
        assert r.output_count == 2
        # Sanity: every input must be covered by some output supernet.
        outs = [IPNetwork(p) for p in r.output_prefixes]
        for ip in inp:
            net = IPNetwork(ip)
            assert any(net in out for out in outs), f"{ip} not covered by {r.output_prefixes}"

    def test_budget_above_lossless_returns_lossless(self):
        """When budget >= lossless count, no widening should occur."""
        inp = ["1.1.1.0/32", "1.1.1.1/32", "1.1.1.100/32"]
        # lossless: 1.1.1.0/31 + 1.1.1.100/32  → 2 prefixes
        r = summarize(inp, "budget", budget=10)
        assert r.output_count == 2
        assert set(r.output_prefixes) == {"1.1.1.0/31", "1.1.1.100/32"}
        assert r.waste_count == 0

    def test_acceptance_criterion_6_greedy_correctness(self):
        """budget=2 must prefer the cheap adjacent merge over a wide supernet.

        Input: 1.1.1.0/32, 1.1.1.1/32, 1.1.1.100/32 → 3 lossless prefixes,
        and we want 2.  The cheap merge collapses .0+.1 into .0/31 (cost 0).
        Lifting to a wide supernet (.0/25) would have cost 125.
        """
        inp = ["1.1.1.0/32", "1.1.1.1/32", "1.1.1.100/32"]
        r = summarize(inp, "budget", budget=2)
        assert r.output_count == 2
        assert set(r.output_prefixes) == {"1.1.1.0/31", "1.1.1.100/32"}
        assert r.waste_count == 0  # the cheap merge is lossless

    def test_budget_one_collapses_to_single_supernet(self):
        inp = ["1.1.1.0/32", "1.1.1.1/32", "1.1.1.100/32"]
        r = summarize(inp, "budget", budget=1)
        assert r.output_count == 1
        # The single supernet must contain every input.
        out = IPNetwork(r.output_prefixes[0])
        for ip in inp:
            assert IPNetwork(ip) in out

    def test_largest_waste_prefix_present(self):
        inp = ["1.1.1.0/32", "1.1.1.1/32", "1.1.1.100/32"]
        r = summarize(inp, "budget", budget=1)
        assert r.largest_waste_prefix is not None
        assert "prefix" in r.largest_waste_prefix
        assert r.largest_waste_prefix["covers"] >= r.largest_waste_prefix["announces"]


# ---------------------------------------------------------------------------
# Mode: waste
# ---------------------------------------------------------------------------


class TestWasteMode:
    def test_max_waste_zero_returns_lossless(self):
        inp = ["1.1.1.0/32", "1.1.1.1/32", "1.1.1.100/32"]
        r = summarize(inp, "waste", max_waste=0.0)
        assert r.waste_count == 0
        assert set(r.output_prefixes) == {"1.1.1.0/31", "1.1.1.100/32"}

    def test_high_max_waste_allows_aggressive_merge(self):
        inp = ["1.1.1.0/32", "1.1.1.1/32", "1.1.1.100/32"]
        # Allow up to 99% waste — should collapse everything.
        r = summarize(inp, "waste", max_waste=0.99)
        assert r.output_count <= 2
        # Waste ratio respects the cap.
        assert r.waste_ratio <= 0.99 + 1e-9

    def test_waste_ratio_does_not_exceed_cap(self):
        # Pick prefixes that allow some, but not arbitrary, merging.
        inp = [f"10.0.0.{i}/32" for i in (0, 1, 2, 3)] + ["10.0.5.0/32"]
        cap = 0.5
        r = summarize(inp, "waste", max_waste=cap)
        assert r.waste_ratio <= cap + 1e-9


# ---------------------------------------------------------------------------
# IPv6 support
# ---------------------------------------------------------------------------


class TestIPv6:
    def test_lossless_ipv6_collapses_adjacent(self):
        r = summarize(["2001:db8::/33", "2001:db8:8000::/33"], "lossless")
        assert r.output_prefixes == ["2001:db8::/32"]
        assert r.waste_count == 0

    def test_budget_ipv6(self):
        inp = ["2001:db8::/128", "2001:db8::1/128", "2001:db8::100/128"]
        r = summarize(inp, "budget", budget=2)
        assert r.output_count == 2

    def test_mixed_ipv4_ipv6_no_cross_family_merge(self):
        inp = ["1.1.1.0/32", "1.1.1.1/32", "2001:db8::/128", "2001:db8::1/128"]
        r = summarize(inp, "lossless")
        # Each family collapses to one /31 or /127 respectively.
        assert set(r.output_prefixes) == {"1.1.1.0/31", "2001:db8::/127"}

    def test_mixed_family_budget_keeps_at_least_one_each(self):
        inp = [
            "1.1.1.0/32",
            "1.1.1.1/32",
            "1.1.1.5/32",
            "2001:db8::/128",
            "2001:db8::1/128",
            "2001:db8::5/128",
        ]
        r = summarize(inp, "budget", budget=2)
        assert r.output_count == 2
        outs = [IPNetwork(p) for p in r.output_prefixes]
        assert any(o.version == 4 for o in outs)
        assert any(o.version == 6 for o in outs)


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


class TestPerformance:
    def test_500_random_ipv4_slash32_budget_50_under_1s(self):
        """Acceptance criterion 7: must complete under 1.0s."""
        random.seed(20260418)
        # Spread across a /16 to keep them mostly non-adjacent.
        seen: set[str] = set()
        prefixes: list[str] = []
        while len(prefixes) < 500:
            o3 = random.randint(0, 255)
            o4 = random.randint(0, 255)
            p = f"10.0.{o3}.{o4}/32"
            if p in seen:
                continue
            seen.add(p)
            prefixes.append(p)

        start = time.perf_counter()
        r = summarize(prefixes, "budget", budget=50)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"perf budget exceeded: {elapsed:.3f}s"
        assert r.output_count <= 50
        assert r.input_count == 500
