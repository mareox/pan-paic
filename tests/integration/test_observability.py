"""Integration tests for observability endpoints and structured logging."""

import io
import json
import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from paic.api.observability import router
from paic.core.logging import RedactionFilter, _JsonFormatter, configure_logging


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("PAIC_PROFILES_DIR", str(tmp_path / "profiles"))
    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_healthz_returns_200(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_returns_ok_body(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_200_when_profiles_dir_writable(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_metrics_returns_200(client: TestClient) -> None:
    assert client.get("/metrics").status_code == 200


def test_metrics_content_type(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.headers["content-type"].startswith("text/plain")


def test_metrics_contains_query_metric(client: TestClient) -> None:
    import paic.core.metrics  # noqa: F401

    body = client.get("/metrics").text
    assert "paic_query_total" in body


def test_logging_redacts_api_key() -> None:
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
