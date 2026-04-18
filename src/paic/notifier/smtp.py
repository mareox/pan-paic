"""Async SMTP sender for diff alert emails."""

from __future__ import annotations

import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from paic.core.smtp_settings import SmtpConfig
from paic.db.models import Diff, Tenant
from paic.notifier._smtp_template import build_email_parts


async def send_diff_email(
    tenant: Tenant,
    diff: Diff,
    recipients: list[str],
    smtp_config: SmtpConfig,
) -> None:
    """Send a multipart/alternative diff alert email to all recipients.

    Args:
        tenant: The Tenant whose prefixes changed.
        diff: The Diff record with added_json / removed_json payloads.
        recipients: List of recipient email addresses.
        smtp_config: SMTP connection and identity configuration.
    """
    if not recipients:
        return

    report_url = smtp_config.base_link
    subject, text_body, html_body = build_email_parts(
        tenant_name=tenant.name,
        added_json=diff.added_json,
        removed_json=diff.removed_json,
        report_url=report_url,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_config.from_addr
    msg["To"] = ", ".join(recipients)
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=smtp_config.host,
        port=smtp_config.port,
        username=smtp_config.username or None,
        password=smtp_config.password or None,
        use_tls=smtp_config.use_tls,
    )
