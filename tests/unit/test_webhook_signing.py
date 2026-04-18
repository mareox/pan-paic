"""Unit tests for HMAC-SHA256 signing helpers."""

import time

from paic.notifier._signing import canonical_json, sign_payload, verify_signature

SECRET = b"test-secret-key-bytes"
SECRET_ALT = b"different-secret"


# ---------------------------------------------------------------------------
# canonical_json
# ---------------------------------------------------------------------------


def test_canonical_json_is_deterministic() -> None:
    payload = {"z": 1, "a": 2, "m": 3}
    assert canonical_json(payload) == canonical_json(payload)


def test_canonical_json_sorted_keys() -> None:
    out = canonical_json({"z": 1, "a": 2})
    assert out == '{"a":2,"z":1}'


def test_canonical_json_compact_separators() -> None:
    out = canonical_json({"key": "value"})
    assert " " not in out


# ---------------------------------------------------------------------------
# sign_payload
# ---------------------------------------------------------------------------


def test_sign_payload_deterministic() -> None:
    body = '{"a":1}'
    ts = 1700000000
    assert sign_payload(SECRET, body, ts) == sign_payload(SECRET, body, ts)


def test_sign_payload_differs_for_different_secrets() -> None:
    body = '{"a":1}'
    ts = 1700000000
    assert sign_payload(SECRET, body, ts) != sign_payload(SECRET_ALT, body, ts)


def test_sign_payload_differs_for_different_body() -> None:
    ts = 1700000000
    assert sign_payload(SECRET, '{"a":1}', ts) != sign_payload(SECRET, '{"a":2}', ts)


def test_sign_payload_differs_for_different_ts() -> None:
    body = '{"a":1}'
    assert sign_payload(SECRET, body, 100) != sign_payload(SECRET, body, 200)


def test_sign_payload_returns_hex_string() -> None:
    sig = sign_payload(SECRET, '{"a":1}', 0)
    assert len(sig) == 64
    assert all(c in "0123456789abcdef" for c in sig)


# ---------------------------------------------------------------------------
# verify_signature
# ---------------------------------------------------------------------------


def test_verify_signature_valid() -> None:
    body = canonical_json({"a": 1})
    ts = int(time.time())
    sig = sign_payload(SECRET, body, ts)
    assert verify_signature(SECRET, body, ts, f"sha256={sig}") is True


def test_verify_signature_tampered_body() -> None:
    body = canonical_json({"a": 1})
    ts = int(time.time())
    sig = sign_payload(SECRET, body, ts)
    # Tamper the body after signing
    tampered = canonical_json({"a": 2})
    assert verify_signature(SECRET, tampered, ts, f"sha256={sig}") is False


def test_verify_signature_wrong_secret() -> None:
    body = canonical_json({"a": 1})
    ts = int(time.time())
    sig = sign_payload(SECRET, body, ts)
    assert verify_signature(SECRET_ALT, body, ts, f"sha256={sig}") is False


def test_verify_signature_expired_ts() -> None:
    body = canonical_json({"a": 1})
    ts = int(time.time()) - 400  # 400 seconds old — beyond max_age_sec=300
    sig = sign_payload(SECRET, body, ts)
    assert verify_signature(SECRET, body, ts, f"sha256={sig}", max_age_sec=300) is False


def test_verify_signature_wrong_prefix() -> None:
    body = canonical_json({"a": 1})
    ts = int(time.time())
    sig = sign_payload(SECRET, body, ts)
    # Header without "sha256=" prefix
    assert verify_signature(SECRET, body, ts, sig) is False


def test_verify_signature_within_max_age() -> None:
    body = canonical_json({"a": 1})
    ts = int(time.time()) - 100  # 100 seconds old — within max_age_sec=300
    sig = sign_payload(SECRET, body, ts)
    assert verify_signature(SECRET, body, ts, f"sha256={sig}", max_age_sec=300) is True
