"""Unit tests for core.smtp_settings."""

import pytest

from paic.core.smtp_settings import SmtpConfig


def test_smtp_defaults() -> None:
    cfg = SmtpConfig()
    assert cfg.host == "localhost"
    assert cfg.port == 587
    assert cfg.username == ""
    assert cfg.password == ""
    assert cfg.from_addr == "paic@localhost"
    assert cfg.use_tls is False
    assert cfg.base_link == ""


def test_smtp_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAIC_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("PAIC_SMTP_PORT", "465")
    monkeypatch.setenv("PAIC_SMTP_USERNAME", "user@example.com")
    monkeypatch.setenv("PAIC_SMTP_PASSWORD", "s3cret")
    monkeypatch.setenv("PAIC_SMTP_FROM_ADDR", "noreply@example.com")
    monkeypatch.setenv("PAIC_SMTP_USE_TLS", "true")
    monkeypatch.setenv("PAIC_SMTP_BASE_LINK", "https://paic.example.com")

    cfg = SmtpConfig()
    assert cfg.host == "smtp.example.com"
    assert cfg.port == 465
    assert cfg.username == "user@example.com"
    assert cfg.password == "s3cret"
    assert cfg.from_addr == "noreply@example.com"
    assert cfg.use_tls is True
    assert cfg.base_link == "https://paic.example.com"


def test_smtp_partial_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAIC_SMTP_HOST", "mail.internal")
    cfg = SmtpConfig()
    assert cfg.host == "mail.internal"
    assert cfg.port == 587  # default
