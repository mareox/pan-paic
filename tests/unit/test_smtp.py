"""Unit tests for the SMTP diff alert sender using an in-memory aiosmtpd server."""

from __future__ import annotations

import json
import socket
from datetime import datetime
from email.message import Message
from typing import Any

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.handlers import Message as BaseMessageHandler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from paic.core.smtp_settings import SmtpConfig
from paic.db.base import Base
from paic.db.models import Diff, Tenant
from paic.notifier.smtp import send_diff_email

# ---------------------------------------------------------------------------
# In-memory SMTP server
# ---------------------------------------------------------------------------


class _RecordingHandler(BaseMessageHandler):
    """aiosmtpd handler that stores received Message objects in a list."""

    def __init__(self) -> None:
        super().__init__(message_class=Message)
        self.messages: list[Message] = []

    def handle_message(self, message: Message) -> None:
        self.messages.append(message)


def _free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def smtp_server():
    """Spin up an in-process SMTP server on a random port and yield (handler, port)."""
    port = _free_port()
    handler = _RecordingHandler()
    controller = Controller(handler, hostname="127.0.0.1", port=port)
    controller.start()
    yield handler, port
    controller.stop()


@pytest.fixture()
def smtp_config_factory():
    """Return a factory that builds SmtpConfig pointed at the given port."""

    def _factory(port: int) -> SmtpConfig:
        return SmtpConfig(
            host="127.0.0.1",
            port=port,
            username="",
            password="",
            from_addr="paic@test.local",
            use_tls=False,
            base_link="https://paic.example.com",
        )

    return _factory


# ---------------------------------------------------------------------------
# Fixtures: ORM objects via in-memory SQLite session
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    """Provide a transient SQLAlchemy session backed by in-memory SQLite."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def tenant(db_session) -> Tenant:
    t = Tenant(
        name="ACME Corp",
        api_key_ciphertext=b"x",
        api_key_nonce=b"x",
        base_url="https://api.example.com",
        poll_interval_sec=900,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture()
def diff_with_changes(db_session, tenant) -> Diff:
    d = Diff(
        tenant_id=tenant.id,
        computed_at=datetime.utcnow(),
        added_json=json.dumps({"mobile_users": ["10.0.0.0/8", "10.1.0.0/16"]}),
        removed_json=json.dumps({"sdwan": ["192.168.1.0/24"]}),
        unchanged_count=50,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


@pytest.fixture()
def diff_empty(db_session, tenant) -> Diff:
    d = Diff(
        tenant_id=tenant.id,
        computed_at=datetime.utcnow(),
        added_json=json.dumps({}),
        removed_json=json.dumps({}),
        unchanged_count=100,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_diff_email_delivers_message(
    smtp_server: tuple[_RecordingHandler, int],
    smtp_config_factory: Any,
    tenant: Tenant,
    diff_with_changes: Diff,
) -> None:
    handler, port = smtp_server
    cfg = smtp_config_factory(port)
    recipients = ["alice@example.com", "bob@example.com"]

    await send_diff_email(tenant, diff_with_changes, recipients, cfg)

    assert len(handler.messages) == 1


@pytest.mark.asyncio
async def test_message_from_address(
    smtp_server: tuple[_RecordingHandler, int],
    smtp_config_factory: Any,
    tenant: Tenant,
    diff_with_changes: Diff,
) -> None:
    handler, port = smtp_server
    cfg = smtp_config_factory(port)
    await send_diff_email(tenant, diff_with_changes, ["alice@example.com"], cfg)

    msg = handler.messages[0]
    assert "paic@test.local" in msg["From"]


@pytest.mark.asyncio
async def test_message_to_address(
    smtp_server: tuple[_RecordingHandler, int],
    smtp_config_factory: Any,
    tenant: Tenant,
    diff_with_changes: Diff,
) -> None:
    handler, port = smtp_server
    cfg = smtp_config_factory(port)
    await send_diff_email(tenant, diff_with_changes, ["alice@example.com"], cfg)

    msg = handler.messages[0]
    assert "alice@example.com" in msg["To"]


@pytest.mark.asyncio
async def test_subject_format(
    smtp_server: tuple[_RecordingHandler, int],
    smtp_config_factory: Any,
    tenant: Tenant,
    diff_with_changes: Diff,
) -> None:
    handler, port = smtp_server
    cfg = smtp_config_factory(port)
    await send_diff_email(tenant, diff_with_changes, ["alice@example.com"], cfg)

    msg = handler.messages[0]
    assert "[PAIC]" in msg["Subject"]
    assert "ACME Corp" in msg["Subject"]
    assert "+2" in msg["Subject"]
    assert "-1" in msg["Subject"]


@pytest.mark.asyncio
async def test_message_is_multipart(
    smtp_server: tuple[_RecordingHandler, int],
    smtp_config_factory: Any,
    tenant: Tenant,
    diff_with_changes: Diff,
) -> None:
    handler, port = smtp_server
    cfg = smtp_config_factory(port)
    await send_diff_email(tenant, diff_with_changes, ["alice@example.com"], cfg)

    msg = handler.messages[0]
    assert msg.is_multipart()


@pytest.mark.asyncio
async def test_message_has_text_and_html_parts(
    smtp_server: tuple[_RecordingHandler, int],
    smtp_config_factory: Any,
    tenant: Tenant,
    diff_with_changes: Diff,
) -> None:
    handler, port = smtp_server
    cfg = smtp_config_factory(port)
    await send_diff_email(tenant, diff_with_changes, ["alice@example.com"], cfg)

    msg = handler.messages[0]
    content_types = [part.get_content_type() for part in msg.walk()]
    assert "text/plain" in content_types
    assert "text/html" in content_types


@pytest.mark.asyncio
async def test_text_part_contains_prefix(
    smtp_server: tuple[_RecordingHandler, int],
    smtp_config_factory: Any,
    tenant: Tenant,
    diff_with_changes: Diff,
) -> None:
    handler, port = smtp_server
    cfg = smtp_config_factory(port)
    await send_diff_email(tenant, diff_with_changes, ["alice@example.com"], cfg)

    msg = handler.messages[0]
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            body = part.get_payload(decode=True)
            assert body is not None
            decoded = body.decode("utf-8", errors="replace")
            assert "10.0.0.0/8" in decoded
            break
    else:
        pytest.fail("No text/plain part found")


@pytest.mark.asyncio
async def test_html_part_contains_prefix(
    smtp_server: tuple[_RecordingHandler, int],
    smtp_config_factory: Any,
    tenant: Tenant,
    diff_with_changes: Diff,
) -> None:
    handler, port = smtp_server
    cfg = smtp_config_factory(port)
    await send_diff_email(tenant, diff_with_changes, ["alice@example.com"], cfg)

    msg = handler.messages[0]
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            body = part.get_payload(decode=True)
            assert body is not None
            decoded = body.decode("utf-8", errors="replace")
            assert "10.0.0.0/8" in decoded
            break
    else:
        pytest.fail("No text/html part found")


@pytest.mark.asyncio
async def test_no_message_when_no_recipients(
    smtp_server: tuple[_RecordingHandler, int],
    smtp_config_factory: Any,
    tenant: Tenant,
    diff_with_changes: Diff,
) -> None:
    handler, port = smtp_server
    cfg = smtp_config_factory(port)
    await send_diff_email(tenant, diff_with_changes, [], cfg)

    assert len(handler.messages) == 0


@pytest.mark.asyncio
async def test_empty_diff_sends_valid_email(
    smtp_server: tuple[_RecordingHandler, int],
    smtp_config_factory: Any,
    tenant: Tenant,
    diff_empty: Diff,
) -> None:
    handler, port = smtp_server
    cfg = smtp_config_factory(port)
    await send_diff_email(tenant, diff_empty, ["alice@example.com"], cfg)

    assert len(handler.messages) == 1
    msg = handler.messages[0]
    assert "+0 / -0" in msg["Subject"]
