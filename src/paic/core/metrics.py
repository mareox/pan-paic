"""Prometheus metric definitions and scheduler readiness flag."""

from prometheus_client import Counter, Gauge

# --- Prometheus metrics ---

paic_poll_total = Counter(
    "paic_poll_total",
    "Total poll attempts",
    ["tenant", "status"],
)

paic_poll_failures_total = Counter(
    "paic_poll_failures_total",
    "Total poll failures",
    ["tenant", "error_type"],
)

paic_webhook_delivery_total = Counter(
    "paic_webhook_delivery_total",
    "Total webhook delivery attempts",
    ["status"],
)

paic_prefix_count = Gauge(
    "paic_prefix_count",
    "Current prefix count per tenant and service type",
    ["tenant", "service_type"],
)

# --- Scheduler readiness ---

_scheduler_ready: bool = False


def set_scheduler_ready(value: bool) -> None:
    """Set the scheduler readiness flag (called by the scheduler on start/stop)."""
    global _scheduler_ready
    _scheduler_ready = value


def is_scheduler_ready() -> bool:
    """Return the current scheduler readiness flag."""
    return _scheduler_ready
