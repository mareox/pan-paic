# PAIC Operations Runbook

This runbook covers initial deployment, master-key management, database backup, and scaling considerations for Prisma Access IP Console.

---

## Initial Deployment

### Option 1: Single Container (SQLite, simplest)

Generate a master key and start the container:

```bash
export PAIC_MASTER_KEY="$(openssl rand -base64 32)"

docker run -d \
  --name paic \
  --restart unless-stopped \
  -e PAIC_MASTER_KEY="${PAIC_MASTER_KEY}" \
  -p 8080:8080 \
  -v paic-data:/app/data \
  paic:latest
```

Verify liveness:

```bash
curl -sf http://localhost:8080/healthz
# {"status":"ok"}
```

Verify readiness (DB reachable + scheduler started):

```bash
curl -sf http://localhost:8080/readyz
# {"status":"ok"}
```

The SQLite database is written to `/app/data/paic.db` inside the container. The volume `paic-data` persists it across restarts.

### Option 2: docker-compose (Postgres-backed)

```bash
cd deploy/compose

# Copy and edit the environment file
cp .env.example .env
# Set PAIC_MASTER_KEY, POSTGRES_PASSWORD, etc.

docker compose up -d
```

Services started:

| Service | Port | Notes |
|---|---|---|
| `paic` | 8080 | FastAPI + React UI + APScheduler |
| `postgres` | 5432 (internal) | Postgres 15, named volume |

Check status:

```bash
docker compose ps
docker compose logs -f paic
```

### Option 3: pip (air-gapped or development)

```bash
pip install paic

export PAIC_MASTER_KEY="$(openssl rand -base64 32)"
export PAIC_DATABASE_URL="sqlite:///./paic.db"   # or postgresql+psycopg://...

paic serve --host 0.0.0.0 --port 8080
```

Or with uv from the source tree:

```bash
uv sync
uv run uvicorn paic.api.main:app --host 0.0.0.0 --port 8080
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PAIC_MASTER_KEY` | **yes** | (required) | Base64-encoded 32 bytes. AES-GCM master key for sealing API keys, webhook secrets, SMTP credentials. |
| `PAIC_DATABASE_URL` | no | `sqlite:///./paic.db` | SQLAlchemy URL. Postgres: `postgresql+psycopg://user:pass@host/paic` |
| `PAIC_BIND_HOST` | no | `0.0.0.0` | Listen address. |
| `PAIC_BIND_PORT` | no | `8080` | Listen port. |
| `PAIC_LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `PAIC_PRISMA_BASE_URL` | no | `https://api.prod.datapath.prismaaccess.com` | Override for sovereign cloud endpoints. |

---

## Master Key Generation

Generate a cryptographically random 32-byte key encoded as base64:

```bash
openssl rand -base64 32
```

Example output (do not use this value):

```
kZ3mN9pQrT2uV5wX8yA1bC4dE7fG0hI=
```

Store the key in:
- A secrets manager (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault): recommended for production.
- A `.env` file excluded from version control: acceptable for single-operator deployments.
- A Docker secret or Kubernetes Secret: acceptable for container deployments.

Never commit the master key to git. Verify `.gitignore` covers `.env` before proceeding.

### Key Rotation Procedure

Rotating the master key requires re-encrypting every ciphertext in the database. Phase 1 does not ship an automated rotation command; use the following manual procedure:

1. Export all tenant API keys while the old key is still active:

   ```bash
   # Using the PAIC admin API: retrieve decrypted keys via a one-off script
   # or directly via psql/sqlite3 with the old master key loaded
   PAIC_MASTER_KEY=<old_key> python -c "
   from paic.core.crypto import unseal
   from paic.db.models import Tenant
   # ... iterate tenants and write api_keys to a temp file (chmod 600)
   "
   ```

2. Stop PAIC:

   ```bash
   docker compose stop paic
   # or: docker stop paic
   ```

3. Set the new master key in your secrets store / `.env`.

4. Re-encrypt and update tenant records with the new key:

   ```bash
   PAIC_MASTER_KEY=<new_key> python -c "
   from paic.core.crypto import seal
   # ... read saved api_keys, seal with new key, UPDATE tenant rows
   "
   ```

5. Restart PAIC with the new key:

   ```bash
   docker compose up -d paic
   ```

6. Verify `/readyz` returns 200 and confirm the first scheduled poll succeeds in the logs.

7. Securely delete the temp file from step 1.

---

## Database Backup

### SQLite

The database is a single file. Back it up with an online-safe copy:

```bash
# While PAIC is running: SQLite online backup
sqlite3 /path/to/paic.db ".backup /backup/paic-$(date +%Y%m%d-%H%M%S).db"

# Or stop PAIC first, then copy
docker compose stop paic
cp /var/lib/docker/volumes/paic-data/_data/paic.db /backup/paic-$(date +%Y%m%d-%H%M%S).db
docker compose start paic
```

Verify the backup is not corrupt:

```bash
sqlite3 /backup/paic-<timestamp>.db "PRAGMA integrity_check;"
# Should output: ok
```

### Postgres

Use `pg_dump` for a logical backup:

```bash
pg_dump \
  --host=localhost \
  --port=5432 \
  --username=paic \
  --no-password \
  --format=custom \
  --file=/backup/paic-$(date +%Y%m%d-%H%M%S).pgdump \
  paic
```

To restore:

```bash
pg_restore \
  --host=localhost \
  --port=5432 \
  --username=paic \
  --dbname=paic \
  --no-password \
  /backup/paic-<timestamp>.pgdump
```

For docker-compose deployments, run `pg_dump` inside the container:

```bash
docker compose exec postgres pg_dump \
  -U paic \
  --format=custom \
  paic > /backup/paic-$(date +%Y%m%d-%H%M%S).pgdump
```

Automate with a daily cron job:

```cron
0 3 * * * docker compose -f /opt/paic/docker-compose.yml exec -T postgres pg_dump -U paic --format=custom paic > /backup/paic-$(date +\%Y\%m\%d).pgdump
```

---

## Upgrade Procedure

1. Pull the new image:

   ```bash
   docker pull paic:latest
   # or for a pinned version:
   docker pull paic:0.2.0
   ```

2. Back up the database (see above).

3. Apply the upgrade:

   ```bash
   docker compose pull paic
   docker compose up -d paic
   ```

   PAIC runs Alembic migrations automatically on startup before binding the port.

4. Verify `/readyz` and check logs for migration output.

---

## Scaling Notes

### Phase 1 (current): Single Replica + DB

The supported topology is **one PAIC process** backed by either SQLite or Postgres. The APScheduler instance runs in-process. There is no external job queue.

This topology handles:
- Tens of tenants polling every 15 minutes.
- Low-volume webhook fan-out (< 100 endpoints per tenant).

### Multi-Replica Considerations (Phase 2 concern)

Running more than one PAIC replica against the same database will cause duplicate scheduler ticks. Each replica starts its own APScheduler and independently polls Prisma for each tenant.

**Do not run multiple replicas in Phase 1** unless you accept duplicate polls, duplicate diffs, and duplicate notifications.

Phase 2 will introduce scheduler leader election (APScheduler `SQLAlchemyJobStore` with row-level locking, or an external lock via Redis/Postgres advisory locks) to allow safe horizontal scaling.

### Load Balancing (stateless API tier only)

The FastAPI request-handling tier is stateless: it reads/writes the DB and holds no in-memory tenant state. If you need to scale API throughput independently of the scheduler, you can run multiple PAIC processes with the environment variable `PAIC_SCHEDULER_ENABLED=false` (Phase 2 feature) to disable the scheduler in all but one designated leader process.

### Resource Sizing

| Component | Minimum | Recommended |
|---|---|---|
| PAIC process | 256 MB RAM, 0.25 vCPU | 512 MB RAM, 0.5 vCPU |
| Postgres | 512 MB RAM | 1 GB RAM + SSD storage |
| SQLite | (none) | Not recommended beyond 10 tenants / low write rate |

Disk growth: each `Snapshot` row stores the full JSON payload (~10-100 KB per tenant per poll). At 900 s intervals, one tenant generates ~96 snapshots/day. Plan for ~10-100 MB/day per active tenant and implement a retention policy (automated snapshot pruning is a Phase 2 feature).

---

## Log Management

PAIC writes structured JSON logs to stdout. Capture and ship with your preferred collector:

```bash
# Tail recent logs
docker compose logs -f --tail=100 paic

# Example log line
# {"ts":"2026-04-18T10:00:01Z","level":"INFO","logger":"paic.scheduler.poller",
#  "msg":"poll complete","tenant_id":"t-abc123","added":3,"removed":0,"elapsed_ms":412}
```

Sensitive values (API keys, webhook secrets, SMTP passwords) are redacted to `[REDACTED]` before any log line is written. See `docs/SECURITY.md` for the redaction contract.

---

## Prometheus Metrics

Scrape `GET /metrics` for the following time series:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `paic_poll_total` | Counter | `tenant_id`, `status` | Total poll attempts |
| `paic_poll_failures_total` | Counter | `tenant_id`, `reason` | Failed polls |
| `paic_webhook_delivery_total` | Counter | `status` | Webhook delivery outcomes |
| `paic_prefix_count` | Gauge | `tenant_id`, `service_type` | Current prefix count |

Example Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: paic
    static_configs:
      - targets: ["paic:8080"]
```
