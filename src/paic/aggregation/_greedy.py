"""Internal greedy merge helpers for prefix aggregation.

The public entry point lives in :mod:`paic.aggregation.engine`.  This module
isolates the heap-based greedy algorithm so the engine remains readable.

Algorithm summary
-----------------
Given a list of CIDR prefixes (already passed through :func:`netaddr.cidr_merge`
so there is no overlap), repeatedly merge an adjacent pair of prefixes whose
combined supernet wastes the fewest IPs.

Cost of merging two adjacent prefixes ``a`` and ``b`` into supernet ``s``::

    cost = s.size - (a.size + b.size)

Tie breaks (lower wins):
    1. cost
    2. delta in supernet prefix length vs. the wider input prefix
    3. starting integer address of the supernet (lexicographic for IPs)

To meet the 500-prefix performance budget we use a min-heap keyed by the cost
tuple.  When a pair is merged we invalidate stale heap entries with a version
counter; rather than removing them we skip them lazily on pop.  Each merge
inserts at most two fresh candidates (left-neighbour + right-neighbour of the
new node), so total work is O(N log N) for the initial heap build plus
O(M log N) where M = (initial_count - target_count).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from netaddr import IPNetwork, spanning_cidr


@dataclass
class _Node:
    """Doubly-linked list node holding a single CIDR prefix.

    ``version`` is bumped whenever the node participates in a merge so that
    stale heap entries pointing at it can be discarded on pop.
    """

    net: IPNetwork
    prev: _Node | None = None
    next: _Node | None = None
    version: int = 0
    alive: bool = True


@dataclass(order=True)
class _Candidate:
    """Heap entry describing a potential merge of two adjacent nodes."""

    cost: int
    prefix_delta: int
    start_addr: int
    seq: int
    left: _Node = field(compare=False)
    right: _Node = field(compare=False)
    left_version: int = field(compare=False, default=0)
    right_version: int = field(compare=False, default=0)


def _merge_cost(a: IPNetwork, b: IPNetwork) -> tuple[int, int, int, IPNetwork]:
    """Return ``(cost, prefix_delta, start_addr, supernet)`` for merging *a* and *b*.

    *a* and *b* must share an IP version.
    """
    super_net = spanning_cidr([a, b])
    cost = int(super_net.size) - (int(a.size) + int(b.size))
    # Wider supernet = smaller prefix length.  We measure how much wider it is
    # than the larger input (= smaller prefix length of the two).
    prefix_delta = min(a.prefixlen, b.prefixlen) - super_net.prefixlen
    start_addr = int(super_net.network)
    return cost, prefix_delta, start_addr, super_net


class _GreedyMerger:
    """Greedy merger over a single IP version's prefix list.

    Inputs must already be deduplicated / non-overlapping (i.e. the output of
    :func:`netaddr.cidr_merge`) and sorted by network address.
    """

    def __init__(self, networks: list[IPNetwork]) -> None:
        self._head: _Node | None = None
        self._count = 0
        self._heap: list[_Candidate] = []
        self._seq = 0  # monotonic counter for stable heap ordering

        # Build doubly-linked list.
        prev: _Node | None = None
        for net in networks:
            node = _Node(net=net, prev=prev)
            if prev is None:
                self._head = node
            else:
                prev.next = node
            prev = node
            self._count += 1

        # Seed heap with all adjacent pair candidates.
        cursor: _Node | None = self._head
        while cursor is not None and cursor.next is not None:
            self._push_candidate(cursor, cursor.next)
            cursor = cursor.next

    # ------------------------------------------------------------------ heap

    def _push_candidate(self, left: _Node, right: _Node) -> None:
        cost, prefix_delta, start_addr, _super = _merge_cost(left.net, right.net)
        self._seq += 1
        cand = _Candidate(
            cost=cost,
            prefix_delta=prefix_delta,
            start_addr=start_addr,
            seq=self._seq,
            left=left,
            right=right,
            left_version=left.version,
            right_version=right.version,
        )
        heapq.heappush(self._heap, cand)

    def _pop_valid(self) -> _Candidate | None:
        """Pop heap entries until a non-stale one is found (or heap empties)."""
        while self._heap:
            cand = heapq.heappop(self._heap)
            if not (cand.left.alive and cand.right.alive):
                continue
            if cand.left_version != cand.left.version:
                continue
            if cand.right_version != cand.right.version:
                continue
            if cand.left.next is not cand.right:
                # Adjacency was broken by a previous merge.
                continue
            return cand
        return None

    def _peek_min_cost(self) -> int | None:
        """Return the cost of the cheapest valid merge without consuming it."""
        # Drain stale entries from the top, but leave the next valid one in place.
        while self._heap:
            cand = self._heap[0]
            if not (cand.left.alive and cand.right.alive):
                heapq.heappop(self._heap)
                continue
            if cand.left_version != cand.left.version:
                heapq.heappop(self._heap)
                continue
            if cand.right_version != cand.right.version:
                heapq.heappop(self._heap)
                continue
            if cand.left.next is not cand.right:
                heapq.heappop(self._heap)
                continue
            return cand.cost
        return None

    # ----------------------------------------------------------------- merge

    def _apply(self, cand: _Candidate) -> None:
        """Merge the pair described by *cand* in place."""
        left = cand.left
        right = cand.right
        super_net = spanning_cidr([left.net, right.net])

        # Replace `left` content with the supernet, drop `right` from the list.
        left.net = super_net
        left.version += 1
        right.alive = False

        new_next = right.next
        left.next = new_next
        if new_next is not None:
            new_next.prev = left

        self._count -= 1

        # Push fresh candidates for the new neighbour pairs.
        if left.prev is not None:
            self._push_candidate(left.prev, left)
        if left.next is not None:
            self._push_candidate(left, left.next)

    # ------------------------------------------------------------------- run

    def run_to_budget(self, budget: int) -> list[IPNetwork]:
        """Merge until the surviving node count is ``<= budget``."""
        while self._count > budget:
            cand = self._pop_valid()
            if cand is None:
                break  # nothing left to merge
            self._apply(cand)
        return self._collect()

    def run_to_waste(
        self,
        announced_ips: int,
        max_waste: float,
    ) -> list[IPNetwork]:
        """Merge while the resulting waste ratio stays ``<= max_waste``.

        ``announced_ips`` is the sum of original (pre-merge) prefix sizes.
        Waste ratio is defined as ``(covered - announced) / covered`` where
        ``covered`` is the sum of supernet sizes after the candidate merge.
        """
        covered = sum(int(node.net.size) for node in self._iter_nodes())

        while self._heap:
            cand = self._pop_valid()
            if cand is None:
                break
            new_covered = covered + cand.cost
            if new_covered <= 0:
                # Defensive: shouldn't happen since cost >= 0 by construction.
                break
            new_ratio = (new_covered - announced_ips) / new_covered
            if new_ratio > max_waste:
                # This merge would breach the budget, and any future merge
                # only widens further, but we still need to consider whether a
                # *different* (more expensive-to-pop, cheaper-to-merge) pair
                # could remain under budget.  Because cost >= 0 and we always
                # pop the cheapest, once the cheapest exceeds the budget we
                # are done.
                break
            self._apply(cand)
            covered = new_covered

        return self._collect()

    # --------------------------------------------------------------- helpers

    def _iter_nodes(self):
        node = self._head
        while node is not None:
            if node.alive:
                yield node
            node = node.next

    def _collect(self) -> list[IPNetwork]:
        return [node.net for node in self._iter_nodes()]


def greedy_merge_to_budget(
    networks: list[IPNetwork], budget: int
) -> list[IPNetwork]:
    """Greedy merge ``networks`` until at most ``budget`` prefixes remain.

    ``networks`` should already be the lossless (cidr_merge) output for a
    single IP version, sorted by network address.
    """
    if budget >= len(networks):
        return list(networks)
    return _GreedyMerger(networks).run_to_budget(budget)


def greedy_merge_to_waste(
    networks: list[IPNetwork],
    announced_ips: int,
    max_waste: float,
) -> list[IPNetwork]:
    """Greedy merge while keeping ``waste_ratio <= max_waste``.

    ``announced_ips`` is the sum of the *pre-aggregation* prefix sizes (after
    dedup); it stays constant across merges.
    """
    if not networks:
        return []
    return _GreedyMerger(networks).run_to_waste(announced_ips, max_waste)
