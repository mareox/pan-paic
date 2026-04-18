"""AES-GCM field-level encryption for sensitive values."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from paic.core.errors import ConfigError

_NONCE_SIZE = 12  # 96-bit nonce recommended for AES-GCM


def _load_master_key() -> bytes:
    """Load and validate the master key from PAIC_MASTER_KEY env var."""
    raw = os.environ.get("PAIC_MASTER_KEY", "")
    if not raw:
        raise ConfigError(
            "PAIC_MASTER_KEY is not set. "
            "Generate: python -c 'import secrets,base64; "
            "print(base64.b64encode(secrets.token_bytes(32)).decode())'"
        )
    try:
        key_bytes = base64.b64decode(raw)
    except Exception as exc:
        raise ConfigError(
            f"PAIC_MASTER_KEY is not valid base64: {exc}"
        ) from exc
    if len(key_bytes) != 32:
        raise ConfigError(
            f"PAIC_MASTER_KEY must decode to exactly 32 bytes (got {len(key_bytes)}). "
            "AES-256-GCM requires a 256-bit key."
        )
    return key_bytes


def seal(plaintext: str) -> tuple[bytes, bytes]:
    """Encrypt *plaintext* with AES-256-GCM.

    Returns (ciphertext, nonce).  Both must be stored to unseal later.
    A fresh random nonce is generated for every call.
    """
    key = _load_master_key()
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def unseal(ciphertext: bytes, nonce: bytes) -> str:
    """Decrypt *ciphertext* produced by :func:`seal`.

    Returns the original plaintext string.
    """
    key = _load_master_key()
    aesgcm = AESGCM(key)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext_bytes.decode("utf-8")
