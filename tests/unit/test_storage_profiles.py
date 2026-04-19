"""Unit tests for the YAML-file ProfileStore."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from paic.api.schemas.profile import Profile
from paic.storage.profiles import ProfileStore, _slugify


def _make(name: str = "Salesforce-50", **overrides) -> Profile:
    base = {
        "id": str(uuid.uuid4()),
        "name": name,
        "description": "Salesforce upstream allowlist (max 60 prefixes)",
        "mode": "budget",
        "budget": 50,
        "max_waste": None,
        "format": "edl",
        "filter_spec_json": None,
        "saved_at": datetime.now(tz=UTC),
    }
    base.update(overrides)
    return Profile(**base)


@pytest.fixture()
def store(tmp_path: Path) -> ProfileStore:
    return ProfileStore(tmp_path / "profiles")


def test_save_creates_yaml_file(store: ProfileStore) -> None:
    p = _make()
    path = store.save(p)
    assert path.exists()
    assert path.suffix == ".yaml"
    assert path.name == "salesforce-50.yaml"


def test_saved_file_contains_header_block(store: ProfileStore) -> None:
    p = _make()
    path = store.save(p)
    text = path.read_text()
    assert "# Egress IP Condenser — Profile" in text
    assert "Safe to copy/share" in text


def test_saved_file_contains_section_comments(store: ProfileStore) -> None:
    p = _make()
    text = store.save(p).read_text()
    assert "Aggregation:" in text
    assert "exact     — no aggregation" in text
    assert "Output format the consumer expects." in text
    assert "csv | json | xml | edl | yaml | plain" in text
    assert "Optional filters applied AFTER fetching from Prisma." in text


def test_round_trip_preserves_data(store: ProfileStore) -> None:
    original = _make()
    store.save(original)
    loaded = store.get(original.id)
    assert loaded is not None
    assert loaded.id == original.id
    assert loaded.name == original.name
    assert loaded.mode == original.mode
    assert loaded.budget == original.budget
    assert loaded.format == original.format


def test_round_trip_preserves_header_after_rewrite(store: ProfileStore) -> None:
    """A subsequent save must not strip the header comment block."""
    p = _make()
    store.save(p)
    loaded = store.get(p.id)
    assert loaded is not None
    store.save(loaded)
    text = (store.dir / "salesforce-50.yaml").read_text()
    assert "# Egress IP Condenser — Profile" in text


def test_list_returns_all_profiles(store: ProfileStore) -> None:
    store.save(_make("alpha"))
    store.save(_make("beta"))
    store.save(_make("gamma"))
    assert {p.name for p in store.list()} == {"alpha", "beta", "gamma"}


def test_get_returns_none_for_missing_id(store: ProfileStore) -> None:
    assert store.get("nonexistent") is None


def test_delete_removes_file(store: ProfileStore) -> None:
    p = _make()
    path = store.save(p)
    assert store.delete(p.id) is True
    assert not path.exists()
    assert store.get(p.id) is None


def test_delete_returns_false_for_missing_id(store: ProfileStore) -> None:
    assert store.delete("nonexistent") is False


def test_export_returns_raw_yaml_bytes(store: ProfileStore) -> None:
    p = _make()
    store.save(p)
    body = store.export_one(p.id)
    assert b"# Egress IP Condenser" in body
    assert p.name.encode() in body


def test_export_missing_raises(store: ProfileStore) -> None:
    with pytest.raises(KeyError):
        store.export_one("nope")


def test_import_round_trips(store: ProfileStore) -> None:
    p = _make("Imported-Profile")
    store.save(p)
    body = store.export_one(p.id)
    store.delete(p.id)
    imported = store.import_one(body)
    assert imported.name == "Imported-Profile"
    assert store.get(imported.id) is not None


def test_import_rejects_duplicate_id(store: ProfileStore) -> None:
    p = _make()
    store.save(p)
    body = store.export_one(p.id)
    with pytest.raises(ValueError, match="already exists"):
        store.import_one(body)


def test_save_replaces_existing_with_same_id(store: ProfileStore) -> None:
    p = _make("Original")
    store.save(p)
    updated = p.model_copy(update={"name": "Renamed", "budget": 99})
    store.save(updated)
    loaded = store.get(p.id)
    assert loaded is not None
    assert loaded.name == "Renamed"
    assert loaded.budget == 99
    files = list(store.dir.glob("*.yaml"))
    assert len(files) == 1


def test_two_profiles_with_same_name_get_unique_filenames(store: ProfileStore) -> None:
    a = _make("Salesforce")
    b = _make("Salesforce", id=str(uuid.uuid4()))
    store.save(a)
    store.save(b)
    files = sorted(p.name for p in store.dir.glob("*.yaml"))
    assert files == ["salesforce-1.yaml", "salesforce.yaml"]


def test_slugify_basic() -> None:
    assert _slugify("Salesforce 50") == "salesforce-50"
    assert _slugify("Okta-25") == "okta-25"
    assert _slugify("  weird   spaces  ") == "weird-spaces"
    assert _slugify("Special!@# chars$%") == "special-chars"
    assert _slugify("") == "profile"
    assert _slugify("---") == "profile"


def test_dir_auto_created(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "profiles"
    assert not target.exists()
    ProfileStore(target)
    assert target.exists()
