"""Unit tests for export renderers (US-005)."""

from __future__ import annotations

import csv
import io
import json as stdlib_json
import re
import xml.etree.ElementTree as ET

import yaml

from paic.core.types import PrefixRecord
from paic.renderers import csv as renderer_csv
from paic.renderers import edl as renderer_edl
from paic.renderers import json as renderer_json
from paic.renderers import plain as renderer_plain
from paic.renderers import render
from paic.renderers import xml as renderer_xml
from paic.renderers import yaml as renderer_yaml

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

_IPV4 = PrefixRecord(
    prefix="10.0.0.0/24",
    service_type="gp_gateway",
    addr_type="egress",
    region="us-west",
    country="US",
    location_name="Los Angeles",
    ip_version=4,
)
_IPV6 = PrefixRecord(
    prefix="2001:db8::/32",
    service_type="mobile_users",
    addr_type="egress",
    region="eu-central",
    country="DE",
    location_name="Frankfurt",
    ip_version=6,
)
_NO_REGION = PrefixRecord(
    prefix="203.0.113.0/24",
    service_type="remote_networks",
    addr_type="loopback",
    region=None,
    country=None,
    location_name=None,
    ip_version=4,
)

RECORDS = [_IPV4, _IPV6, _NO_REGION]

# ---------------------------------------------------------------------------
# EDL renderer
# ---------------------------------------------------------------------------

_EDL_LINE_RE = re.compile(r"^[0-9a-fA-F:.]+/\d+$")


class TestEdlRenderer:
    def test_output_lines_match_regex(self):
        body = renderer_edl.render(RECORDS)
        lines = body.decode("utf-8").splitlines()
        assert len(lines) == 3
        for line in lines:
            assert _EDL_LINE_RE.match(line), f"EDL line failed regex: {line!r}"

    def test_no_header_by_default(self):
        body = renderer_edl.render(RECORDS)
        text = body.decode("utf-8")
        assert not text.startswith("#")

    def test_with_header_option(self):
        body = renderer_edl.render(RECORDS, options={"with_header": True})
        lines = body.decode("utf-8").splitlines()
        assert lines[0].startswith("# generated ts=")
        # remaining lines must still match prefix regex
        for line in lines[1:]:
            assert _EDL_LINE_RE.match(line), f"EDL line failed regex: {line!r}"

    def test_prefixes_present(self):
        body = renderer_edl.render(RECORDS)
        text = body.decode("utf-8")
        assert "10.0.0.0/24" in text
        assert "2001:db8::/32" in text
        assert "203.0.113.0/24" in text

    def test_returns_bytes(self):
        assert isinstance(renderer_edl.render(RECORDS), bytes)


# ---------------------------------------------------------------------------
# CSV renderer
# ---------------------------------------------------------------------------

class TestCsvRenderer:
    def test_header_row(self):
        body = renderer_csv.render(RECORDS)
        reader = csv.reader(io.StringIO(body.decode("utf-8")))
        header = next(reader)
        expected = ["prefix", "service_type", "addr_type", "region", "country", "location_name"]
        assert header == expected

    def test_row_count(self):
        body = renderer_csv.render(RECORDS)
        reader = csv.reader(io.StringIO(body.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 4  # header + 3 records

    def test_ipv4_row(self):
        body = renderer_csv.render([_IPV4])
        reader = csv.reader(io.StringIO(body.decode("utf-8")))
        next(reader)  # skip header
        row = next(reader)
        assert row[0] == "10.0.0.0/24"
        assert row[1] == "gp_gateway"

    def test_none_values_allowed(self):
        body = renderer_csv.render([_NO_REGION])
        text = body.decode("utf-8")
        # None renders as empty string in CSV
        assert "203.0.113.0/24" in text

    def test_returns_bytes(self):
        assert isinstance(renderer_csv.render(RECORDS), bytes)


# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------

class TestJsonRenderer:
    def test_schema(self):
        body = renderer_json.render(RECORDS)
        data = stdlib_json.loads(body.decode("utf-8"))
        assert "records" in data
        assert "summary" in data
        assert data["summary"]["count"] == 3

    def test_record_fields(self):
        body = renderer_json.render([_IPV4])
        data = stdlib_json.loads(body.decode("utf-8"))
        rec = data["records"][0]
        assert rec["prefix"] == "10.0.0.0/24"
        assert rec["service_type"] == "gp_gateway"

    def test_indent(self):
        body = renderer_json.render([_IPV4])
        text = body.decode("utf-8")
        assert "\n" in text  # indented

    def test_utf8_encoding(self):
        body = renderer_json.render(RECORDS)
        assert isinstance(body, bytes)
        body.decode("utf-8")  # must not raise

    def test_returns_bytes(self):
        assert isinstance(renderer_json.render(RECORDS), bytes)


# ---------------------------------------------------------------------------
# XML renderer
# ---------------------------------------------------------------------------

class TestXmlRenderer:
    def test_well_formed(self):
        body = renderer_xml.render(RECORDS)
        root = ET.fromstring(body)  # raises if not well-formed
        assert root is not None

    def test_prefix_elements(self):
        body = renderer_xml.render(RECORDS)
        root = ET.fromstring(body)
        prefixes = root.findall("prefix")
        assert len(prefixes) == 3

    def test_count_attribute(self):
        body = renderer_xml.render(RECORDS)
        root = ET.fromstring(body)
        assert root.get("count") == "3"

    def test_returns_bytes(self):
        assert isinstance(renderer_xml.render(RECORDS), bytes)


# ---------------------------------------------------------------------------
# YAML renderer
# ---------------------------------------------------------------------------

class TestYamlRenderer:
    def test_parses_back(self):
        body = renderer_yaml.render(RECORDS)
        data = yaml.safe_load(body.decode("utf-8"))
        assert isinstance(data, dict)
        assert "records" in data
        assert "summary" in data

    def test_count(self):
        body = renderer_yaml.render(RECORDS)
        data = yaml.safe_load(body.decode("utf-8"))
        assert data["summary"]["count"] == 3

    def test_equivalent_to_json_shape(self):
        json_body = renderer_json.render(RECORDS)
        yaml_body = renderer_yaml.render(RECORDS)
        json_data = stdlib_json.loads(json_body)
        yaml_data = yaml.safe_load(yaml_body)
        assert set(json_data.keys()) == set(yaml_data.keys())
        assert json_data["summary"]["count"] == yaml_data["summary"]["count"]

    def test_returns_bytes(self):
        assert isinstance(renderer_yaml.render(RECORDS), bytes)


# ---------------------------------------------------------------------------
# Plain renderer
# ---------------------------------------------------------------------------

class TestPlainRenderer:
    def test_default_newline_separator(self):
        body = renderer_plain.render(RECORDS)
        lines = body.decode("utf-8").split("\n")
        assert len(lines) == 3
        assert lines[0] == "10.0.0.0/24"

    def test_comma_separator(self):
        body = renderer_plain.render(RECORDS, options={"separator": "comma"})
        text = body.decode("utf-8")
        assert "," in text
        assert "\n" not in text
        parts = text.split(",")
        assert len(parts) == 3

    def test_space_separator(self):
        body = renderer_plain.render(RECORDS, options={"separator": "space"})
        text = body.decode("utf-8")
        parts = text.split(" ")
        assert len(parts) == 3

    def test_only_prefix_strings(self):
        body = renderer_plain.render([_IPV4])
        assert body.decode("utf-8").strip() == "10.0.0.0/24"

    def test_returns_bytes(self):
        assert isinstance(renderer_plain.render(RECORDS), bytes)


# ---------------------------------------------------------------------------
# Registry dispatch
# ---------------------------------------------------------------------------

class TestRegistryDispatch:
    def test_dispatch_all_formats(self):
        for fmt in ("csv", "json", "xml", "edl", "yaml", "plain"):
            result = render(RECORDS, fmt)
            assert isinstance(result, bytes), f"format {fmt} did not return bytes"

    def test_unsupported_format_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Unsupported format"):
            render(RECORDS, "pdf")
