# PAIC Security Model

This document describes the threat model, cryptographic design, webhook signing scheme, log redaction contract, and audit trail for Prisma Access IP Console.

---

## Threat Model

### What PAIC Protects

| Asset | Sensitivity | Why |
|---|---|---|
| Prisma Access API keys | Critical | A leaked key allows any caller to enumerate all Prisma egress IPs for your tenants and — depending on tenant permissions — make API mutations. |
| Webhook HMAC secrets | High | A leaked secret allows an attacker to forge webhook payloads that downstream consumers will accept as authentic. |
| SMTP credentials | High | Leaked credentials enable spam relay and inbox access. |
| Prefix data | Medium | The full list of Prisma egress IPs is operationally sensitive; exposure assists network reconnaissance. |

### Actors

| Actor | Trust Level | Notes |
|---|---|---|
| PAIC admin (operator) | Full trust | Configures tenants, webhooks, profiles. Has access to the host environment including `PAIC_MASTER_KEY`. |
| Network-adjacent attacker | No trust | Can observe traffic on the same network segment if TLS is not terminated before PAIC. |
| Webhook receiver | Partial trust | Receives signed payloads; must verify the HMAC before acting. |
| Prisma Access API | External authority | PAIC calls out to Prisma; responses are defensively parsed and never executed. |
| Database (Postgres/SQLite) | Storage trust | PAIC assumes the DB is not directly accessible to untrusted actors. If the DB is compromised, ciphertexts are safe only as long as the master key is not also compromised. |

### Out of Scope (Phase 1)

- Multi-user RBAC — Phase 1 is single-operator; there is no user authentication layer within PAIC itself. Deploy behind a reverse proxy (Caddy, nginx) with HTTP Basic Auth or network-level access control.
- SSO / OIDC — deferred to Phase 2.
- Audit log — a persistent audit trail of all admin actions is a Phase 2 feature. See placeholder section below.

---

## AES-GCM Key Sourcing

PAIC uses AES-256-GCM for all field-level encryption of secrets stored in the database.

### Master Key

The master key is a 256-bit (32-byte) random value, base64-encoded, supplied at runtime via the `PAIC_MASTER_KEY` environment variable.

```bash
# Generate a new master key
openssl rand -base64 32
```

The application loads the key at startup via `paic.core.crypto`:

```python
import os, base64
raw = os.environ["PAIC_MASTER_KEY"]
key_bytes = base64.b64decode(raw)
assert len(key_bytes) == 32, "PAIC_MASTER_KEY must decode to exactly 32 bytes"
```

A missing or wrong-length key causes a hard startup failure with a clear error message — the application will not start in a degraded state.

### Seal / Unseal Interface

```python
# src/paic/core/crypto.py

def seal(plaintext: str) -> tuple[bytes, bytes]:
    """
    Encrypt plaintext under the master key using AES-256-GCM.
    Returns (ciphertext, nonce).  Both must be stored; nonce is 12 random bytes.
    """

def unseal(ciphertext: bytes, nonce: bytes) -> str:
    """
    Decrypt ciphertext using the master key and nonce.
    Raises InvalidTag if the ciphertext was tampered with.
    """
```

Each call to `seal()` generates a fresh 12-byte random nonce (via `os.urandom(12)`). GCM provides both confidentiality and integrity — any bit-flip in the stored ciphertext causes `unseal()` to raise `cryptography.exceptions.InvalidTag` rather than returning corrupt plaintext.

### Key Sourcing Alternatives

| Source | Configuration | Notes |
|---|---|---|
| Environment variable | `PAIC_MASTER_KEY=<base64>` | Default. Suitable for single-host deployments. Avoid process-environment exposure by using Docker secrets or Kubernetes Secrets with `envFrom`. |
| HashiCorp Vault | Read secret at startup, populate env | Use the Vault Agent sidecar or `vault kv get` in an init container. PAIC itself has no Vault SDK dependency in Phase 1. |
| AWS Secrets Manager | Read secret at startup | Use an init script: `aws secretsmanager get-secret-value --secret-id paic/master-key --query SecretString --output text`. |
| Azure Key Vault | Read secret at startup | Use `az keyvault secret show`. |

For external secret stores, the recommended pattern is to inject the key into the container environment at start time rather than requiring PAIC to have SDK dependencies on a specific secrets manager.

---

## Webhook HMAC Signing

Every webhook delivery is signed so that receivers can verify the payload originated from PAIC and was not tampered with in transit.

### Signing Algorithm

```
signature = HMAC-SHA256(webhook_secret, canonical_body + "." + str(ts))
header: X-PAIC-Signature: sha256=<hex_digest>
```

Where:
- `webhook_secret` is the per-webhook HMAC secret (stored AES-GCM encrypted in `webhook.secret_ciphertext`).
- `canonical_body` is `json.dumps(payload, separators=(",", ":"), sort_keys=True)` — deterministic serialization.
- `ts` is the Unix epoch timestamp (integer seconds) included as `payload["ts"]`.
- The hex digest is lowercase.

### Payload Structure

```json
{
  "ts": 1745020800,
  "tenant_id": "t-abc123",
  "diff_summary": {
    "added": 3,
    "removed": 0,
    "unchanged": 417,
    "service_types_affected": ["gp_gateway", "gp_portal"]
  },
  "link": "https://paic.example.com/tenants/t-abc123/diffs/d-xyz789"
}
```

### Receiver Verification (Python sample)

```python
import hashlib
import hmac
import json
import time

TOLERANCE_SECONDS = 300  # reject payloads older than 5 minutes

def verify_paic_webhook(
    raw_body: bytes,
    signature_header: str,
    secret: str,
    received_at: float | None = None,
) -> bool:
    """
    Returns True if the HMAC signature is valid and the timestamp is fresh.
    Raises ValueError with a reason string on failure.
    """
    if not signature_header.startswith("sha256="):
        raise ValueError("X-PAIC-Signature header missing or malformed")

    received_hex = signature_header.removeprefix("sha256=")

    payload = json.loads(raw_body)
    ts = payload.get("ts")
    if ts is None:
        raise ValueError("Payload missing 'ts' field")

    now = received_at or time.time()
    if abs(now - ts) > TOLERANCE_SECONDS:
        raise ValueError(f"Payload timestamp too old or too far in future: ts={ts}")

    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    message = canonical + "." + str(ts)
    expected = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hex):
        raise ValueError("HMAC signature mismatch")

    return True
```

Note: use `hmac.compare_digest` (constant-time comparison) to prevent timing attacks.

### Replay Protection

The `ts` field in every payload is the Unix timestamp at dispatch time. Receivers that reject payloads where `abs(now - ts) > 300` (5 minutes) are protected against replay attacks where an attacker captures a valid signed payload and re-submits it.

PAIC sets `ts` immediately before computing the signature; the signature therefore binds the payload to its dispatch time.

---

## Log Redaction

No secret value ever appears in a PAIC log line. The following values are redacted before any log entry is written:

| Value | Replacement |
|---|---|
| `PAIC_MASTER_KEY` env value | `[REDACTED]` |
| Tenant API key (plaintext) | `[REDACTED]` |
| Webhook HMAC secret (plaintext) | `[REDACTED]` |
| SMTP password (plaintext) | `[REDACTED]` |

Ciphertexts (the AES-GCM encrypted bytes stored in the DB) are not logged either — they are binary blobs with no log value.

The log redaction test in `tests/integration/test_observability.py` asserts that a simulated poll cycle producing a tenant API key in memory does not result in the plaintext key appearing in any log output captured during the test.

Example safe log line (all sensitive fields absent):

```json
{
  "ts": "2026-04-18T10:00:01Z",
  "level": "INFO",
  "logger": "paic.scheduler.poller",
  "msg": "poll complete",
  "tenant_id": "t-abc123",
  "tenant_name": "Acme Corp",
  "added": 3,
  "removed": 0,
  "unchanged": 417,
  "elapsed_ms": 412
}
```

---

## Transport Security

PAIC binds on HTTP. TLS termination must be provided by a front-end reverse proxy (Caddy, nginx, AWS ALB, etc.). Deploy PAIC behind TLS in any environment where the network path between the client and PAIC is not fully trusted.

Recommended Caddy snippet:

```
paic.example.com {
    reverse_proxy localhost:8080
}
```

Caddy provisions and auto-renews a Let's Encrypt certificate automatically.

---

## Audit Trail

**Phase 2 placeholder.** A persistent audit log of all admin actions (tenant create/edit/delete, profile changes, webhook add/remove, key rotation events) is planned for Phase 2. The audit log will record:

- Who performed the action (user identity after OIDC/SSO is added).
- What resource was affected (tenant ID, webhook ID, etc.).
- What change was made (old value hashes, new value hashes — never plaintext secrets).
- When (ISO-8601 timestamp with timezone).
- Source IP.

In Phase 1, the Postgres/SQLite `updated_at` column on each model provides a last-modified timestamp but no change history or actor attribution.

---

## Dependency Security

Keep dependencies up to date. The `cryptography` library is the most security-critical dependency; subscribe to Python Security Advisories and update promptly on CVE disclosure.

```bash
# Audit installed packages for known vulnerabilities
uv run pip-audit
```

The `.github/workflows/ci.yml` CI pipeline runs `pip-audit` (Phase 2 addition) on every push.
