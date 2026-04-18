# Prisma Access IP Console (PAIC)

Multi-tenant control plane for Palo Alto Networks Prisma Access egress, loopback, and service IPs. Polls upstream, normalizes, summarizes (exact / lossless / budget-driven / waste-bounded), renders to every format engineers actually request, and notifies downstream consumers on diff.

> **Status:** Phase 1 MVP under active development. See [`docs/PRD.md`](docs/PRD.md) for the full product spec and [`../.omc/prd.json`](../.omc/prd.json) for the trackable user-story plan.

## Why

Existing Palo Alto IP API clients are single-tenant CLIs. PAIC adds:

- **Single source of truth** across multiple Prisma Access tenants
- **Change detection** with webhook + SMTP fan-out (target < 20 min P95)
- **Aggregation that fits downstream allowlist ceilings** (e.g., collapse 420 prefixes into ≤ 50 with minimum waste)
- **Universal output** — CSV, JSON, XML, EDL, YAML, plain — one click each
- **Vendor profiles** — "Salesforce: max 60 prefixes, EDL, weekly" once, apply forever

## Quick Start

### Docker (single container, SQLite)

```bash
docker run -d \
  --name paic \
  -e PAIC_MASTER_KEY="$(openssl rand -base64 32)" \
  -p 8080:8080 \
  paic:latest
```

Open `http://localhost:8080`, add a tenant with your Prisma Access API key, done.

### docker-compose (Postgres-backed)

```bash
cd deploy/compose && docker compose up -d
```

### pip (air-gapped)

```bash
pip install paic
export PAIC_MASTER_KEY="$(openssl rand -base64 32)"
paic serve --port 8080
```

## Architecture

```
┌─────────────┐  ┌─────────────┐  ┌───────────────────┐
│  Web / API  │  │   Poller    │  │    Notifier       │
│  (FastAPI)  │  │ (APScheduler│  │ (webhook + SMTP)  │
│   + React)  │  │  per-tenant)│  │                   │
└──────┬──────┘  └──────┬──────┘  └────────┬──────────┘
       │                │                  │
       └────────┬───────┴──────────────────┘
                │
        ┌───────▼───────┐
        │  Postgres /   │
        │   SQLite      │
        └───────────────┘
                │
                ▼ outbound
   Prisma Access API, downstream webhooks, SMTP relay
```

Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Configuration

| Env var | Required | Default | Notes |
|---|---|---|---|
| `PAIC_MASTER_KEY` | yes | — | Base64-encoded 32 bytes. Used for AES-GCM seal of API keys, webhook secrets, SMTP creds. |
| `PAIC_DATABASE_URL` | no | `sqlite:///./paic.db` | Postgres example: `postgresql+psycopg://user:pass@host/paic` |
| `PAIC_BIND_HOST` | no | `0.0.0.0` | |
| `PAIC_BIND_PORT` | no | `8080` | |
| `PAIC_LOG_LEVEL` | no | `INFO` | |
| `PAIC_PRISMA_BASE_URL` | no | `https://api.prod.datapath.prismaaccess.com` | Override for sovereign clouds. |

## Development

```bash
uv sync
uv run uvicorn paic.api.main:app --reload --port 8080
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/paic
```

Frontend:

```bash
cd web && npm install && npm run dev
```

## License

MIT. See [`LICENSE`](LICENSE).
