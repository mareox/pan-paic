"""Unit tests for the filter engine (US-004)."""

from __future__ import annotations

from paic.core.filters import FilterSpec, apply_filters  # noqa: E402
from paic.core.types import PrefixRecord  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _rec(**kwargs) -> PrefixRecord:
    defaults = dict(
        prefix="1.2.3.0/24",
        service_type="prisma-access",
        addr_type="egress",
        region="us-west",
        country="US",
        location_name="Los Angeles",
        ip_version=4,
    )
    defaults.update(kwargs)
    return PrefixRecord(**defaults)


IPV4 = _rec(prefix="10.0.0.0/24", ip_version=4)
IPV6 = _rec(prefix="2001:db8::/32", ip_version=6)
EMEA = _rec(
    prefix="5.5.5.0/24",
    service_type="mobile-users",
    region="eu-central",
    country="DE",
    location_name="Frankfurt",
)
APAC = _rec(
    prefix="203.0.113.0/24",
    service_type="remote-networks",
    addr_type="loopback",
    region="ap-southeast",
    country="SG",
    location_name="Singapore",
)


# ---------------------------------------------------------------------------
# Individual filter tests
# ---------------------------------------------------------------------------

class TestServiceTypeFilter:
    def test_matching(self):
        records = [IPV4, EMEA, APAC]
        result = apply_filters(records, FilterSpec(service_types={"prisma-access"}))
        assert result == [IPV4]

    def test_multiple_values(self):
        records = [IPV4, EMEA, APAC]
        result = apply_filters(records, FilterSpec(service_types={"prisma-access", "mobile-users"}))
        assert sorted(r.prefix for r in result) == sorted([IPV4.prefix, EMEA.prefix])

    def test_no_match(self):
        result = apply_filters([IPV4], FilterSpec(service_types={"nonexistent"}))
        assert result == []


class TestAddrTypeFilter:
    def test_matching(self):
        result = apply_filters([IPV4, APAC], FilterSpec(addr_types={"loopback"}))
        assert result == [APAC]

    def test_no_match(self):
        result = apply_filters([IPV4], FilterSpec(addr_types={"loopback"}))
        assert result == []


class TestRegionFilter:
    def test_matching(self):
        result = apply_filters([IPV4, EMEA, APAC], FilterSpec(regions={"eu-central"}))
        assert result == [EMEA]

    def test_none_region_excluded(self):
        rec = _rec(region=None)
        result = apply_filters([rec], FilterSpec(regions={"us-west"}))
        assert result == []


class TestCountryFilter:
    def test_matching(self):
        result = apply_filters([IPV4, EMEA, APAC], FilterSpec(countries={"DE"}))
        assert result == [EMEA]


class TestLocationNameFilter:
    def test_matching(self):
        result = apply_filters([IPV4, EMEA, APAC], FilterSpec(location_names={"Singapore"}))
        assert result == [APAC]


class TestIpVersionFilter:
    def test_ipv4_only(self):
        result = apply_filters([IPV4, IPV6], FilterSpec(ip_version=4))
        assert result == [IPV4]

    def test_ipv6_only(self):
        result = apply_filters([IPV4, IPV6], FilterSpec(ip_version=6))
        assert result == [IPV6]

    def test_ipv6_excluded_from_ipv4_filter(self):
        result = apply_filters([IPV6], FilterSpec(ip_version=4))
        assert result == []


class TestTextFilter:
    def test_exact_prefix_match(self):
        result = apply_filters([IPV4, EMEA], FilterSpec(text="10.0.0.0"))
        assert result == [IPV4]

    def test_location_name_substring(self):
        result = apply_filters([IPV4, EMEA, APAC], FilterSpec(text="frank"))
        assert result == [EMEA]

    def test_case_insensitive(self):
        result = apply_filters([APAC], FilterSpec(text="SINGAPORE"))
        assert result == [APAC]

    def test_country_match(self):
        result = apply_filters([EMEA, APAC], FilterSpec(text="sg"))
        assert result == [APAC]

    def test_region_match(self):
        result = apply_filters([IPV4, EMEA], FilterSpec(text="eu-central"))
        assert result == [EMEA]

    def test_no_text_match(self):
        result = apply_filters([IPV4], FilterSpec(text="zzznomatch"))
        assert result == []


# ---------------------------------------------------------------------------
# Empty filter
# ---------------------------------------------------------------------------

class TestEmptyFilter:
    def test_empty_spec_returns_all(self):
        records = [IPV4, IPV6, EMEA, APAC]
        result = apply_filters(records, FilterSpec())
        assert result == records

    def test_empty_list_returns_empty(self):
        assert apply_filters([], FilterSpec()) == []


# ---------------------------------------------------------------------------
# AND composition (multi-filter)
# ---------------------------------------------------------------------------

class TestAndComposition:
    def test_service_and_region(self):
        """Only EMEA matches mobile-users AND eu-central."""
        records = [IPV4, EMEA, APAC]
        result = apply_filters(
            records,
            FilterSpec(service_types={"mobile-users"}, regions={"eu-central"}),
        )
        assert result == [EMEA]

    def test_ip_version_and_text(self):
        """ipv4 AND substring 'angeles' → only the LA record."""
        la = _rec(location_name="Los Angeles", ip_version=4)
        other = _rec(location_name="Los Angeles", ip_version=6)
        result = apply_filters([la, other], FilterSpec(ip_version=4, text="angeles"))
        assert result == [la]

    def test_all_filters_combined(self):
        rec = _rec(
            prefix="192.168.1.0/24",
            service_type="prisma-access",
            addr_type="egress",
            region="us-east",
            country="US",
            location_name="New York",
            ip_version=4,
        )
        noise = _rec(service_type="mobile-users", region="ap-southeast")
        result = apply_filters(
            [rec, noise],
            FilterSpec(
                service_types={"prisma-access"},
                addr_types={"egress"},
                regions={"us-east"},
                countries={"US"},
                location_names={"New York"},
                ip_version=4,
                text="new york",
            ),
        )
        assert result == [rec]

    def test_one_filter_mismatch_excludes_record(self):
        """Even if 5 out of 6 filters match, a single mismatch excludes the record."""
        rec = _rec(service_type="mobile-users")
        result = apply_filters(
            [rec],
            FilterSpec(
                service_types={"prisma-access"},  # mismatch
                addr_types={"egress"},
                regions={"us-west"},
                countries={"US"},
                ip_version=4,
            ),
        )
        assert result == []
