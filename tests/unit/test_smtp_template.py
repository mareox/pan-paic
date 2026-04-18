"""Unit tests for SMTP email body builders."""

import json

from paic.notifier._smtp_template import (
    build_email_parts,
    build_html_body,
    build_subject,
    build_text_body,
)

# ---------------------------------------------------------------------------
# Subject
# ---------------------------------------------------------------------------


def test_subject_format() -> None:
    subject = build_subject("ACME Corp", 5, 3)
    assert subject == "[PAIC] ACME Corp prefix change: +5 / -3"


def test_subject_zero_counts() -> None:
    subject = build_subject("My Tenant", 0, 0)
    assert subject == "[PAIC] My Tenant prefix change: +0 / -0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _grouped_json(data: dict[str, list[str]]) -> str:
    return json.dumps(data)


# ---------------------------------------------------------------------------
# Text body
# ---------------------------------------------------------------------------


def test_text_body_contains_added_prefix() -> None:
    text = build_text_body("Tenant A", {"mobile_users": ["10.0.0.0/8"]}, {}, "")
    assert "10.0.0.0/8" in text
    assert "ADDED" in text


def test_text_body_contains_removed_prefix() -> None:
    text = build_text_body("Tenant A", {}, {"sdwan": ["192.168.1.0/24"]}, "")
    assert "192.168.1.0/24" in text
    assert "REMOVED" in text


def test_text_body_contains_tenant_name() -> None:
    text = build_text_body("MyTenant", {}, {}, "")
    assert "MyTenant" in text


def test_text_body_contains_report_url() -> None:
    text = build_text_body("T", {}, {}, "https://paic.example.com/report/123")
    assert "https://paic.example.com/report/123" in text


def test_text_body_groups_by_service_type() -> None:
    added = {"gp_gateway": ["1.2.3.0/24"], "mobile_users": ["10.0.0.0/8"]}
    text = build_text_body("T", added, {}, "")
    assert "gp_gateway" in text
    assert "mobile_users" in text
    assert "1.2.3.0/24" in text
    assert "10.0.0.0/8" in text


def test_text_body_empty_diff_no_crash() -> None:
    text = build_text_body("Tenant X", {}, {}, "")
    assert "Tenant X" in text
    assert "No prefix changes detected" in text


# ---------------------------------------------------------------------------
# HTML body
# ---------------------------------------------------------------------------


def test_html_body_contains_added_prefix() -> None:
    html = build_html_body("Tenant B", {"mobile_users": ["10.0.0.0/8"]}, {}, "")
    assert "10.0.0.0/8" in html
    assert "Added" in html


def test_html_body_contains_removed_prefix() -> None:
    html = build_html_body("Tenant B", {}, {"sdwan": ["172.16.0.0/12"]}, "")
    assert "172.16.0.0/12" in html
    assert "Removed" in html


def test_html_body_contains_tenant_name() -> None:
    html = build_html_body("Corp X", {}, {}, "")
    assert "Corp X" in html


def test_html_body_contains_report_link() -> None:
    html = build_html_body("T", {}, {}, "https://paic.example.com/report/42")
    assert "https://paic.example.com/report/42" in html
    assert "<a href=" in html


def test_html_body_groups_by_service_type() -> None:
    added = {"gp_gateway": ["1.2.3.0/24"]}
    removed = {"mobile_users": ["10.0.0.0/8"]}
    html = build_html_body("T", added, removed, "")
    assert "gp_gateway" in html
    assert "mobile_users" in html
    assert "1.2.3.0/24" in html
    assert "10.0.0.0/8" in html


def test_html_body_empty_diff_no_crash() -> None:
    html = build_html_body("Tenant Y", {}, {}, "")
    assert "Tenant Y" in html
    assert "No prefix changes detected" in html


def test_html_body_is_valid_html_fragment() -> None:
    html = build_html_body("T", {"svc": ["1.0.0.0/8"]}, {}, "")
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html


# ---------------------------------------------------------------------------
# build_email_parts (integration)
# ---------------------------------------------------------------------------


def test_build_email_parts_returns_tuple() -> None:
    added_json = json.dumps({"mu": ["10.0.0.0/8"]})
    removed_json = json.dumps({"sdwan": ["192.168.0.0/16"]})
    subject, text, html = build_email_parts("Acme", added_json, removed_json, "")
    assert "[PAIC]" in subject
    assert "Acme" in subject
    assert "+1" in subject
    assert "-1" in subject
    assert "10.0.0.0/8" in text
    assert "192.168.0.0/16" in html


def test_build_email_parts_empty_diff() -> None:
    subject, text, html = build_email_parts("T", "{}", "{}", "")
    assert "+0 / -0" in subject
    assert "No prefix changes detected" in text
    assert "No prefix changes detected" in html


def test_build_email_parts_malformed_json_no_crash() -> None:
    subject, text, html = build_email_parts("T", "not-json", "[]", "")
    assert "[PAIC]" in subject
