"""Unit tests for notifier._signing (HMAC-SHA256 helpers)."""

import time

from paic.notifier._signing import canonical_json, sign_payload, verify_signature


def test_canonical_json_sorts_keys() -> None:
    payload = {"z": 1, "a": 2, "m": 3}
    result = canonical_json(payload)
    assert result == '{"a":2,"m":3,"z":1}'


def test_canonical_json_compact_separators() -> None:
    result = canonical_json({"k": "v"})
    assert " " not in result


def test_canonical_json_nested() -> None:
    result = canonical_json({"b": {"x": 1}, "a": 2})
    assert result.startswith('{"a"')


def test_sign_payload_returns_hex_string() -> None:
    secret = b"a" * 32
    sig = sign_payload(secret, "body", 12345)
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA-256 hex digest


def test_sign_payload_deterministic() -> None:
    secret = b"b" * 32
    sig1 = sign_payload(secret, "body", 9999)
    sig2 = sign_payload(secret, "body", 9999)
    assert sig1 == sig2


def test_sign_payload_different_body_differs() -> None:
    secret = b"c" * 32
    ts = 1000
    assert sign_payload(secret, "aaa", ts) != sign_payload(secret, "bbb", ts)


def test_sign_payload_different_ts_differs() -> None:
    secret = b"d" * 32
    assert sign_payload(secret, "body", 1) != sign_payload(secret, "body", 2)


def test_verify_signature_valid() -> None:
    secret = b"e" * 32
    body = '{"key":"value"}'
    ts = int(time.time())
    sig = sign_payload(secret, body, ts)
    assert verify_signature(secret, body, ts, f"sha256={sig}") is True


def test_verify_signature_wrong_secret() -> None:
    secret = b"f" * 32
    wrong_secret = b"g" * 32
    body = "payload"
    ts = int(time.time())
    sig = sign_payload(secret, body, ts)
    assert verify_signature(wrong_secret, body, ts, f"sha256={sig}") is False


def test_verify_signature_expired_timestamp() -> None:
    secret = b"h" * 32
    body = "payload"
    ts = int(time.time()) - 400  # older than default 300s
    sig = sign_payload(secret, body, ts)
    assert verify_signature(secret, body, ts, f"sha256={sig}") is False


def test_verify_signature_wrong_prefix() -> None:
    secret = b"i" * 32
    body = "payload"
    ts = int(time.time())
    sig = sign_payload(secret, body, ts)
    assert verify_signature(secret, body, ts, f"md5={sig}") is False


def test_verify_signature_tampered_body() -> None:
    secret = b"j" * 32
    body = "original"
    ts = int(time.time())
    sig = sign_payload(secret, body, ts)
    assert verify_signature(secret, "tampered", ts, f"sha256={sig}") is False


def test_verify_signature_custom_max_age() -> None:
    """max_age_sec=0 rejects any non-current timestamp."""
    secret = b"k" * 32
    body = "payload"
    ts = int(time.time()) - 5
    sig = sign_payload(secret, body, ts)
    assert verify_signature(secret, body, ts, f"sha256={sig}", max_age_sec=0) is False
