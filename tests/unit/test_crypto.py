"""Unit tests for AES-GCM seal/unseal."""

import base64
import os

import pytest

from paic.core.crypto import seal, unseal
from paic.core.errors import ConfigError


def test_round_trip_ascii() -> None:
    """seal then unseal returns the original ASCII string."""
    plaintext = "my-secret-api-key-12345"
    ciphertext, nonce = seal(plaintext)
    assert unseal(ciphertext, nonce) == plaintext


def test_round_trip_unicode() -> None:
    """seal then unseal handles arbitrary unicode."""
    plaintext = "pric\u00e9 \u20ac100 \U0001f511"
    ciphertext, nonce = seal(plaintext)
    assert unseal(ciphertext, nonce) == plaintext


def test_different_nonce_each_call() -> None:
    """Each seal call produces a unique nonce."""
    _, nonce1 = seal("same-key")
    _, nonce2 = seal("same-key")
    assert nonce1 != nonce2


def test_ciphertext_differs_per_call() -> None:
    """Each seal call produces different ciphertext (random nonce)."""
    ct1, _ = seal("same-key")
    ct2, _ = seal("same-key")
    assert ct1 != ct2


def test_missing_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing PAIC_MASTER_KEY raises ConfigError with clear message."""
    monkeypatch.delenv("PAIC_MASTER_KEY", raising=False)
    with pytest.raises(ConfigError, match="PAIC_MASTER_KEY"):
        seal("anything")


def test_wrong_length_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key that doesn't decode to 32 bytes raises ConfigError."""
    short_key = base64.b64encode(b"only16byteshere!").decode()
    monkeypatch.setenv("PAIC_MASTER_KEY", short_key)
    with pytest.raises(ConfigError, match="32 bytes"):
        seal("anything")


def test_invalid_base64_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-base64 value raises ConfigError."""
    monkeypatch.setenv("PAIC_MASTER_KEY", "!!!not-base64!!!")
    with pytest.raises(ConfigError, match="not valid base64"):
        seal("anything")


def test_unseal_wrong_nonce_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """unseal with wrong nonce raises an exception (auth tag mismatch)."""
    ciphertext, _ = seal("secret")
    wrong_nonce = os.urandom(12)
    with pytest.raises(Exception):  # noqa: B017
        unseal(ciphertext, wrong_nonce)
