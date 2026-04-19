"""Integration tests for observability endpoints and structured logging."""

import io
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from paic.api.observability import router
from paic.core.logging import RedactionFilter, _JsonFormatter, configure_logging

# ---------------------------------------------------------------------------
# Test app fixture — mounts the observability router without touching main.py
# ---------------------------------------------------------------------------


@pytest.fixture()
def app() -> FastAPI:
    """Minimal FastAPI app that mounts the observability router."""
    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------


def test_healthz_returns_200(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_returns_ok_body(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /readyz — v0.2 only checks DB connectivity (default sqlite is always reachable)
# ---------------------------------------------------------------------------


def test_readyz_200_when_db_reachable(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------


def test_metrics_returns_200(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200


def test_metrics_content_type(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.headers["content-type"].startswith("text/plain")


def test_metrics_contains_query_metric(client: TestClient) -> None:
    # Force-import the metrics module so the counter is registered.
    import paic.core.metrics  # noqa: F401

    response = client.get("/metrics")
    body = response.text
    assert "paic_query_total" in body


# ---------------------------------------------------------------------------
# Logging redaction
# ---------------------------------------------------------------------------


def test_logging_redacts_api_key() -> None:
    """Messages containing api_key=<secret> must have the value redacted."""
    configure_logging(level="DEBUG")

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(RedactionFilter())

    logger = logging.getLogger("test.redact")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    logger.info("connecting with api_key=secret123 to service")

    output = stream.getvalue()
    assert "secret123" not in output
    assert "REDACTED" in output


def test_logging_redacts_bearer_token() -> None:
    """Messages containing 'bearer <token>' must have the token redacted."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(RedactionFilter())

    logger = logging.getLogger("test.redact.bearer")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    logger.warning("header: bearer supersecrettoken")

    output = stream.getvalue()
    assert "supersecrettoken" not in output
    assert "REDACTED" in output


def test_logging_output_is_single_line_json() -> None:
    """Each log record must produce exactly one line of JSON."""
    configure_logging(level="DEBUG")

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(RedactionFilter())

    logger = logging.getLogger("test.json")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    logger.info("hello world")

    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["level"] == "INFO"
    assert record["msg"] == "hello world"
    assert "ts" in record
    assert "logger" in record
