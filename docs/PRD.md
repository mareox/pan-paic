# Prisma Access IP Console (PAIC) — Product Requirements Document

> Mirror of source PRD as of 2026-04-18. This file is the canonical product specification for Phase 1 MVP.

---

## 1. Problem Statement

Palo Alto Networks Prisma Access dynamically allocates egress, loopback, and service IP prefixes across its global backbone. These prefixes change — new regions come online, capacity is added, CIDRs are rotated. Network teams and downstream consumers (firewalls, allowlists, SIEMs, load balancers) need to know the current set of IPs for each service type and react within minutes when the set changes.

Today's options are inadequate:

- **Manual downloads** from the Palo Alto support portal — no automation, no change detection, no history.
- **`curl` scripts** calling `getPrismaAccessIP/v2` directly — single-tenant, no normalization, no diffing, no notifications, no aggregation.
- **Panorama / PAN-OS push** — not universally available and limited to PAN-OS consumers; cannot feed non-PAN infrastructure.

The result is stale allowlists, security gaps, and operational incidents when Prisma rotates IPs without downstream consumers noticing.

---

## 2. Goals

1. **Single source of truth** for Prisma Access egress, loopback, and service IPs across multiple tenants.
2. **Automatic change detection** with fan-out notifications (webhook + SMTP) targeting < 20 minutes P95 from Prisma API update to downstream notification delivery.
3. **Aggregation that fits downstream constraints** — collapse hundreds of prefixes into a vendor-defined ceiling (e.g., ≤ 50) with minimum wasted address space.
4. **Universal output formats** — CSV, JSON, XML, EDL, YAML, plain text — so any downstream consumer can ingest without transformation.
5. **Reusable vendor profiles** — configure "Salesforce: max 60 prefixes, EDL, every Sunday 02:00" once and apply it forever.
6. **Operational simplicity** — one container, one env var (`PAIC_MASTER_KEY`), no external dependencies required beyond a network path to Prisma.

---

## 3. Non-Goals

- **Prisma Access configuration management** — PAIC reads IPs; it does not push policy to Panorama or PAN-OS devices (planned Phase 3+).
- **Multi-user RBAC** — Phase 1 targets single-operator deployments. Authentication is deferred to Phase 2 (OIDC/SSO).
- **SaaS-hosted variant** — Phase 1 is self-hosted only.
- **SIEM forwarder / Grafana bundle** — out of scope for Phase 1.
- **Natural-language query interface** — out of scope for Phase 1.
- **Shareable signed URLs** — out of scope for Phase 1.

---

## 4. Personas

| Persona | Role | Primary Need |
|---|---|---|
| **Network Engineer** | Manages firewall allowlists, EDL feeds, NAT policies | Current Prisma IPs in EDL format on a schedule; immediate alert on change |
| **Security Engineer** | Owns SIEM ingestion rules, threat-hunting queries | Full IP list in JSON/CSV with metadata (service type, region, addr type) |
| **Platform Admin** | Operates PAIC deployment, manages tenants | Simple deploy, key rotation, backup, monitoring |
| **Vendor Integration Owner** | Feeds Salesforce, Zscaler, or other SaaS allowlists | Named profile that auto-exports on schedule in vendor-specific format |

---

## 5. User Stories

| ID | Story | Priority |
|---|---|---|
| US-001 | As a Platform Admin, I can bootstrap the project with all tooling (pyproject, FastAPI skeleton, /healthz, README) so the team can start development. | P0 |
| US-002 | As a Platform Admin, I can add a tenant with a Prisma Access API key, knowing the key is stored AES-GCM encrypted, never returned in API responses. | P0 |
| US-003 | As a Network Engineer, I can retrieve normalized IP prefixes from the Prisma Access API with defensive parsing that never crashes on unknown fields. | P0 |
| US-004 | As a Network Engineer, I can filter prefixes by service type, addr type, region, country, location, IP version, and free text using AND composition. | P0 |
| US-005 | As a Network Engineer, I can export filtered prefixes to CSV, JSON, XML, EDL, YAML, or plain text in one API call. | P0 |
| US-006 | As a Network Engineer, I can summarize prefixes using exact, lossless, budget-driven, or waste-bounded aggregation to meet downstream prefix-count ceilings. | P0 |
| US-007 | As a Vendor Integration Owner, I can define a named profile bundling aggregation mode, format, filter, and schedule, then apply it to any tenant. | P0 |
| US-008 | As a Platform Admin, I can configure per-tenant polling intervals; PAIC automatically diffs each poll against the prior snapshot and persists the result. | P0 |
| US-009 | As a Network Engineer, I receive a signed webhook POST within 20 minutes of a prefix change being detected. | P0 |
| US-010 | As a Network Engineer, I receive an email (HTML + plain text) listing added and removed prefixes grouped by service type when a change is detected. | P1 |
| US-011 | As a Platform Admin, I can monitor PAIC via /healthz, /readyz, and /metrics (Prometheus), with structured JSON logs that never leak API keys. | P0 |
| US-012 | As any user, I can use a React web UI to manage tenants, run reports, manage profiles, and browse diff history without touching the API directly. | P1 |
| US-013 | As a Platform Admin, I can deploy PAIC as a single Docker container, via docker-compose with Postgres, or via pip in three copy-pasteable commands. | P0 |
| US-014 | As a Developer, I have a CI pipeline (GitHub Actions) that enforces lint, type checking, and ≥ 70% line coverage on core modules on every push. | P1 |
| US-015 | As a Developer, I have README, ARCHITECTURE, OPERATIONS, and SECURITY documentation, plus a copy of the PRD in docs/. | P1 |

---

## 6. Requirements

### P0 — Must Ship in Phase 1 MVP

| # | Requirement |
|---|---|
| R-01 | Tenant CRUD API with AES-256-GCM field-level encryption of API keys. Master key from `PAIC_MASTER_KEY` env var. |
| R-02 | Async httpx client for `POST /getPrismaAccessIP/v2`. Discovers `serviceType` and `addrType` enum values dynamically. |
| R-03 | Pure-function filter engine: `service_type`, `addr_type`, `region`, `country`, `location_name`, `ip_version` (4/6), free-text. AND composition. |
| R-04 | Six export renderers: CSV, JSON, XML, EDL, YAML, plain. EDL lines match `^[0-9a-fA-F:.]+/\d+$`. |
| R-05 | Summarization engine: exact (no-op), lossless (`cidr_merge`), budget-driven (greedy merge to N prefixes), waste-bounded (greedy merge up to W waste ratio). |
| R-06 | APScheduler per-tenant interval job (min 300 s, default 900 s, max 86 400 s). |
| R-07 | Diff engine: per-poll added/removed/unchanged sets by service type. Snapshot + Diff rows persisted to DB. |
| R-08 | Webhook dispatcher: HMAC-SHA256 signed, payload includes `ts`, retry schedule 0/60/300/900/3600 s (5 attempts max). |
| R-09 | `/healthz` (liveness), `/readyz` (DB + scheduler), `/metrics` (Prometheus: poll_total, poll_failures, webhook_delivery, prefix_count). |
| R-10 | Structured JSON logs. API keys, secrets, passwords redacted to `[REDACTED]` in all log output. |
| R-11 | Dockerfile (SQLite default) + docker-compose (Postgres) + pip-installable package with `paic serve` CLI entry point. |

### P1 — Target Phase 1, Defer if Necessary

| # | Requirement |
|---|---|
| R-12 | SMTP alerter: `multipart/alternative` email (text/plain + text/html) per diff. Subject: `[PAIC] {name} prefix change: +{added} / -{removed}`. |
| R-13 | Vendor aggregation profiles: named, DB-persisted, CRUD API, `GET /api/profiles/{id}/render?tenant_id=X`. |
| R-14 | React + Vite + Tailwind web UI: Tenants, Reports, Profiles, Diffs pages. Static bundle served by FastAPI at `/`. |
| R-15 | GitHub Actions CI: ruff, mypy, pytest with ≥ 70% coverage on `core`, `aggregation`, `clients`, `renderers`, `notifier`. |
| R-16 | Documentation: README, ARCHITECTURE.md (sequence diagram), OPERATIONS.md (deploy/backup/key-rotation), SECURITY.md (threat model, AES-GCM, HMAC, redaction). |

### P2 — Phase 2 Backlog

| # | Requirement |
|---|---|
| R-17 | OIDC/SSO authentication (Okta, Entra, Google). |
| R-18 | RBAC (admin / read-only / tenant-scoped). |
| R-19 | Persistent audit log (actor, resource, change, timestamp, source IP). |
| R-20 | Scheduler leader election for multi-replica deployments. |
| R-21 | Automated master-key rotation command. |
| R-22 | Snapshot retention policy and automated pruning. |

---

## 7. Architecture Sketch

```
Browser / API client
        │
        ▼
  FastAPI (port 8080)       ← REST API + React SPA
        │
  SQLAlchemy (async)
  ├── Postgres 15            (docker-compose / managed DB)
  └── SQLite 3.40+           (single-container default)

APScheduler (in-process)
  └── per-tenant IntervalJob (poll_interval_sec)
        ├── httpx → Prisma Access API  (outbound HTTPS)
        ├── Diff Engine
        └── Notifier
              ├── httpx → Webhook URLs (outbound HTTPS, HMAC-signed)
              └── aiosmtp → SMTP relay  (outbound)
```

Full layer description and Mermaid sequence diagram: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 8. Summarization Algorithm Detail

The aggregation engine (`src/paic/aggregation/engine.py`) exposes four modes:

### 8.1 Exact

Returns the input prefix list unchanged. No merging, no widening.

### 8.2 Lossless

Calls `netaddr.cidr_merge()` on the input list. Merges adjacent and contained prefixes into the smallest set of CIDRs that covers exactly the same address space. Guaranteed: no address outside the input set is covered by the output.

### 8.3 Budget-Driven (greedy merge, minimum waste)

Target: reduce the prefix count to at most `budget` entries.

Algorithm:

1. Start from the lossless result.
2. If `len(output) <= budget`, return immediately.
3. Compute all candidate supernet merges. For each adjacent pair that shares a supernet, calculate the waste introduced (addresses in the supernet not covered by either prefix).
4. Merge the pair with the lowest waste cost. Re-run `cidr_merge` on the updated list.
5. Repeat until `len(output) <= budget` or no further merges are possible.

The result is the smallest set of CIDRs ≤ `budget` that covers the input with minimum introduced waste.

### 8.4 Waste-Bounded (greedy merge, maximum waste ratio)

Target: merge as aggressively as possible while keeping `waste_count / announced_ips <= max_waste`.

Algorithm: same greedy loop as budget-driven, but the stopping condition is the waste ratio ceiling rather than a count ceiling. With `max_waste = 0.0`, the result is identical to lossless.

### 8.5 Output Fields

```
AggregateResult:
  output_prefixes: list[str]
  input_count: int
  output_count: int
  covered_ips: int        # addresses in input prefixes
  announced_ips: int      # addresses in output prefixes (>= covered_ips)
  waste_count: int        # announced_ips - covered_ips
  waste_ratio: float      # waste_count / announced_ips
  largest_waste_prefix: str | None
  mode: Literal["exact","lossless","budget","waste"]
  generated_at: datetime
```

---

## 9. Security and Privacy

- All tenant API keys, webhook secrets, and SMTP passwords are stored AES-256-GCM encrypted. The master key never touches the database.
- Webhook payloads are HMAC-SHA256 signed with a per-webhook secret. Receivers must verify the signature and reject payloads older than 5 minutes.
- Logs never contain plaintext secrets. A test asserts redaction in CI.
- TLS termination is the responsibility of a front-end reverse proxy. PAIC binds HTTP.
- Phase 1 has no authentication layer within PAIC. Deploy behind a reverse proxy with access control.

Full threat model, key sourcing options, and verifier sample code: [`docs/SECURITY.md`](SECURITY.md).

---

## 10. Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| P95 notification latency | < 20 minutes from Prisma API update to webhook delivery | `paic_webhook_delivery_total` + timestamp delta in Diff rows |
| Poll success rate | > 99% over 7-day rolling window | `paic_poll_failures_total / paic_poll_total` |
| Test coverage | ≥ 70% line coverage on `core`, `aggregation`, `clients`, `renderers`, `notifier` | `pytest --cov` in CI |
| Time-to-first-export | < 5 minutes from `docker run` to first EDL export | Manual onboarding test |
| Budget aggregation correctness | `len(output) <= budget` for all valid inputs | Unit test in `test_aggregation.py` |

---

## 11. Open Questions

| Question | Blocking | Owner | Notes |
|---|---|---|---|
| What is the rate limit on `getPrismaAccessIP/v2`? | Yes | Engineering + TAC | Current design assumes 429 handling is sufficient; actual limit unknown. |
| Does the API response distinguish dedicated vs shared IPs? | No | Engineering + TAC | Relevant for waste calculations — shared IPs should not be widened. |
| IPv6 parity day-1 or v4-only acceptable for Phase 1? | Yes | Engineering | Filtering, aggregation, and EDL must handle IPv6 CIDRs correctly. |
| Target OIDC provider for Phase 2 auth? | No | Platform admin | Okta, Entra ID, and Google Workspace are all candidates. |
| Self-hosted only or SaaS-hosted variant in roadmap? | No | Product | SaaS hosting would require multi-tenancy isolation beyond current design. |

---

## 12. Timeline and Phasing

### Phase 1 MVP — Current

Scope: US-001 through US-015 (P0 mandatory, P1 targeted).

Excluded from Phase 1: SSO/OIDC (US-010 equivalent), full RBAC, audit log, pip package with optional `[web]` extra.

### Phase 2

- OIDC/SSO authentication.
- RBAC (admin / read-only / tenant-scoped).
- Persistent audit log.
- Scheduler leader election (multi-replica safe).
- Automated master-key rotation.
- Snapshot retention policy.

### Phase 3+

- Shareable signed export URLs.
- SAML support.
- Webhook replay UI.
- SIEM forwarder (syslog, Splunk HEC, Elastic).
- Grafana dashboard bundle.
- PAN-OS / Panorama push integration.
- Natural-language query interface.

---

## 13. Prior Art and Gaps

| Tool | What it does | Gap |
|---|---|---|
| `pan-python` | General-purpose PAN-OS/Panorama Python SDK | No Prisma Access IP API support, no diff/notify, single-call |
| Palo Alto IP feed (support portal) | Manual CSV download of current IPs | Not automated, no history, no notification |
| Terraform provider for PAN-OS | Manages PAN-OS config declaratively | Reads IPs only as data source; no independent export or notification |
| Custom `curl` scripts | Direct calls to `getPrismaAccessIP/v2` | Single-tenant, no persistence, no diff, no aggregation, no notification |
| Prisma Access EDL built-in feed | PAN-OS can consume a URL EDL | PAN-OS-only; not available to non-PAN consumers; no aggregation |

PAIC fills the gap for multi-tenant, multi-consumer, aggregation-aware IP management with change notification.

---

## 14. Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Prisma Access API rate limit causes missed polls | Medium | High | 429 backoff with `last_fetch_status` tracking; alerting via `paic_poll_failures_total`; Phase 2 — adaptive interval. |
| Master key lost | Low | Critical | Document key backup procedure in OPERATIONS.md; require operator to store in a secrets manager. |
| Single-process scheduler fails silently | Medium | High | `/readyz` returns 503 if scheduler has not ticked; `paic_poll_failures_total` alert. |
| IPv6 CIDR merge produces incorrect waste calculation | Low | Medium | Unit tests with IPv6 fixtures; `netaddr` handles IPv6 natively. |
| Large tenant (500+ prefixes) budget merge exceeds 1 s | Low | Low | Performance test in `test_aggregation.py` asserts < 1 s on 500-prefix synthetic input. |
| Webhook secret leaked via log | Low | High | Redaction contract tested in CI; no plaintext secret in any log path. |

---

## Appendix A — Prisma Access API Reference

### Endpoint

```
POST https://api.prod.datapath.prismaaccess.com/getPrismaAccessIP/v2
```

### Request Headers

| Header | Value |
|---|---|
| `header-api-key` | Prisma Access tenant API key |
| `Content-Type` | `application/json` |

### Request Body

```json
{
  "serviceType": "all",
  "addrType": "all",
  "location": "all"
}
```

Known `serviceType` values (discovered dynamically, not hardcoded): `gp_gateway`, `gp_portal`, `remote_network`, `clean_pipe`, `swg_proxy`, `all`.

Known `addrType` values: `active`, `reserve`, `all`.

### Response Structure (abbreviated)

```json
{
  "status": "success",
  "result": {
    "gp_gateway": {
      "addresses": [
        {
          "serviceType": "gp_gateway",
          "addressType": "active",
          "zone": "us-east-1",
          "region": "americas",
          "create_time": "...",
          "address": "198.51.100.0/24"
        }
      ]
    }
  }
}
```

PAIC normalizes each address entry into a `PrefixRecord` with fields: `prefix`, `service_type`, `addr_type`, `region`, `country`, `location_name`. Unknown keys in the response are accepted without error (`Extra.allow` on the Pydantic model).

### Error Classes

| HTTP Status | PAIC Exception |
|---|---|
| 401, 403 | `PrismaAuthError` |
| 429 | `PrismaRateLimitError` (handled: skip poll, set `rate_limited` status) |
| 5xx, network failure | `PrismaUpstreamError` |
| Malformed JSON body | `PrismaSchemaError` |

### Sovereign Cloud Override

For tenants on non-production or sovereign-cloud endpoints, set `PAIC_PRISMA_BASE_URL` or supply `base_url` per-tenant in the API:

```
https://api.eu.datapath.prismaaccess.com
```
