# syntax=docker/dockerfile:1
# Stage 1: builder — installs deps into a venv using uv
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files needed for install
COPY pyproject.toml uv.lock LICENSE README.md ./
COPY src/ ./src/

# Sync deps (no dev extras) into project venv
RUN uv sync --no-dev --frozen

# Stage 2: runtime — lean image with only the venv and source
FROM python:3.13-slim AS runtime

WORKDIR /app

# Non-root user (UID 1000)
RUN groupadd --gid 1000 paic && \
    useradd --uid 1000 --gid 1000 --no-create-home paic

# Copy installed venv + source from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Make venv the active Python
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root
USER paic

EXPOSE 8080

# Profiles live here — operators mount a host dir or named volume to persist them.
VOLUME ["/app/profiles"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c 'import urllib.request; urllib.request.urlopen("http://localhost:8080/healthz")'

CMD ["uvicorn", "paic.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
