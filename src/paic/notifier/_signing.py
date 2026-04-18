"""Pure HMAC-SHA256 signing helpers for webhook payloads."""

import hashlib
import hmac
import json
import time


def canonical_json(payload: dict) -> str:  # type: ignore[type-arg]
    """Return a deterministic JSON string for *payload*.

    Uses sort_keys=True and compact separators so the byte representation is
    stable regardless of insertion order.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign_payload(secret: bytes, body: str, ts: int) -> str:
    """Compute HMAC-SHA256(secret, body_bytes + str(ts).encode()).

    Returns the hex digest string used as the signature value.
    """
    msg = body.encode("utf-8") + str(ts).encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify_signature(
    secret: bytes,
    body: str,
    ts: int,
    header_value: str,
    max_age_sec: int = 300,
) -> bool:
    """Verify a webhook signature from an inbound request.

    *header_value* is the full ``X-PAIC-Signature`` header, e.g. ``sha256=<hex>``.
    Returns False if the timestamp is older than *max_age_sec*, the prefix is
    wrong, or the HMAC does not match.
    """
    now = int(time.time())
    if abs(now - ts) > max_age_sec:
        return False

    if not header_value.startswith("sha256="):
        return False

    expected = sign_payload(secret, body, ts)
    received = header_value[len("sha256="):]
    return hmac.compare_digest(expected, received)
