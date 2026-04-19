"""Prometheus metric definitions.

PAIC v0.2 has no scheduler / poller / webhooks; metrics are pared down to a
single counter for ad-hoc query traffic so /metrics still has signal.
"""

from prometheus_client import Counter

paic_query_total = Counter(
    "paic_query_total",
    "Total /api/query requests",
    ["status"],
)
