# PAIC

> **Unofficial.** This project is an independent open-source tool. It is NOT affiliated with, endorsed by, or sponsored by Palo Alto Networks Inc. "Palo Alto Networks", "Prisma", "Prisma Access", "Strata", "Strata Cloud Manager", and "Panorama" are trademarks of Palo Alto Networks Inc., used here only for accurate factual reference to the APIs this tool consumes.

A stateless query tool for Prisma Access egress IPs. Fetches the live prefix list from the Prisma Access data-path API, applies filters, **collapses the list to fit downstream allowlist ceilings** with four aggregation modes, and renders to CSV / JSON / XML / EDL / YAML / plain.

## Why this exists

Strata Cloud Manager Insights already alerts you when Prisma Access IPs change. What it doesn't do is **collapse 400 prefixes down to 50** so they fit a SaaS vendor's outbound allowlist. That's the gap this tool fills.

- **Four aggregation modes**: exact, lossless merge, budget-driven (max N prefixes, minimum waste), waste-bounded (max waste ratio)
- **Stateless**: your API key lives in browser sessionStorage and on a single in-flight request. Never written to disk, never logged.
- **Six output formats**: CSV, JSON, XML, EDL, YAML, plain list
- **Vendor profiles**: save "Salesforce: max 60 prefixes, EDL" once, apply forever (settings only, zero credentials)
- **Multi-prod**: built-in selector for `prod`, `prod1`-`prod6`, `china-prod`, plus free-text override for sovereign clouds

## Quick Start

```bash
docker run -d \
  --name eic \
  -p 8080:8080 \
  -v $(pwd)/profiles:/app/profiles \
  ghcr.io/mareox/pan-paic:latest
```

Open `http://localhost:8080`, paste your Prisma Access API key, pick a prod, run a query, download the result.

### docker-compose

```bash
cd deploy/compose && docker compose up -d
```

### pip

```bash
pip install paic
paic serve --port 8080
```

## How to find your prod identifier

Your tenant lives on a specific Prisma Access data-path environment (`prod`, `prod1`, … `prod6`, or `china-prod`). The hostname pattern is `https://api.{prod}.datapath.prismaaccess.com/getPrismaAccessIP/v2`.

You can find your prod in **Strata Cloud Manager → Settings → API Access** (or in the activation email from your Palo Alto Networks SE/PSE/TAC). If unknown, try `prod` first; the API will return 401/404 if your tenant isn't on it.

## Container Image

Pre-built multi-arch images (`linux/amd64`, `linux/arm64`) are published to GitHub Container Registry on every version tag.

```bash
docker pull ghcr.io/mareox/pan-paic:latest
```

### Release workflow (automated)

Pushing a semver tag triggers the GitHub Actions release workflow, which builds and pushes to GHCR automatically:

```bash
git tag v0.2.1 && git push --tags
```

### Manual first-time publish (one-time, before automation)

```bash
gh auth token | docker login ghcr.io -u mareox --password-stdin

docker buildx build --platform=linux/amd64,linux/arm64 \
  -f deploy/docker/Dockerfile \
  -t ghcr.io/mareox/pan-paic:0.2.1 \
  -t ghcr.io/mareox/pan-paic:latest \
  --push .
```

After the first push, set the package to public at:
`https://github.com/users/mareox/packages/container/pan-paic/settings` → "Change visibility" → Public

## Configuration

| Env var | Default | Notes |
|---|---|---|
| `PAIC_PROFILES_DIR` | `./profiles` | Directory for YAML profile files (mount as a volume in Docker). |
| `PAIC_BIND_HOST` | `0.0.0.0` | |
| `PAIC_BIND_PORT` | `8080` | |
| `PAIC_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

No master key. No database. No SMTP. No webhook. The backend is a query proxy plus a YAML-file profile store.

## Profiles

A profile bundles **everything except the API key**: which filter to apply, which aggregation mode and budget to use, and what format to render. Save one per downstream vendor and re-apply whenever you need a fresh export.

### File format

Each profile is one human-readable YAML file in `PAIC_PROFILES_DIR`:

```yaml
# PAIC: Profile
# Apply this in the UI or via the API. Safe to copy/share, contains zero credentials.

id: 8d4aba63-b802-4e54-ab35-a02d0f68c55d
name: Salesforce-50
description: Salesforce upstream allowlist (max 60 prefixes per vendor docs)
saved_at: '2026-04-19T10:06:28+00:00'

# Aggregation: how to collapse the prefix list before rendering.
#   exact     no aggregation
#   lossless  merge adjacent prefixes only (no widening)
#   budget    collapse to at most N prefixes, minimum waste
#   waste     collapse until waste ratio approaches max_waste
mode: budget
budget: 50
max_waste:

# Output format the consumer expects.
format: edl  # csv | json | xml | edl | yaml | plain

# Optional filters applied AFTER fetching from Prisma.
filter_spec_json: '{"service_types":["remote_network"]}'
```

### Sharing profiles between deployments

```bash
# Export: downloads <slug>.yaml
curl -O http://localhost:8080/api/profiles/<id>/export

# Import: upload someone else's YAML
curl -F "file=@salesforce-50.yaml" http://localhost:8080/api/profiles/import
```

Profiles are pure config. Copy the file into another deployment's `profiles/` directory and it's available immediately.

## API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/query` | Stateless query: API key + prod + filter + mode + format → rendered bytes |
| `POST` | `/api/query/preview` | Same body; returns aggregation stats only (no render) |
| `GET` | `/api/known-prods` | List of known data-path prod identifiers |
| `GET/POST/PUT/DELETE` | `/api/profiles` | Profile CRUD |
| `GET` | `/api/profiles/{id}/export` | Download profile YAML |
| `POST` | `/api/profiles/import` | Upload profile YAML |
| `POST` | `/api/profiles/{id}/render` | Apply a saved profile to live Prisma data |
| `GET` | `/healthz` | Liveness |
| `GET` | `/readyz` | Readiness (verifies `PAIC_PROFILES_DIR` is writable) |
| `GET` | `/metrics` | Prometheus exposition |

FastAPI auto-renders OpenAPI/Swagger at `/docs` and ReDoc at `/redoc` for live exploration.

## Development

```bash
uv sync --all-extras
uv run python -m uvicorn paic.api.main:app --reload --port 8080
uv run pytest --cov=src/paic
uv run ruff check src/ tests/
uv run mypy src/paic
```

Frontend (React + Vite + Tailwind):

```bash
cd web && npm install && npm run dev
```

## License

MIT. See [`LICENSE`](LICENSE).
