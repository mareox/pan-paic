"""YAML-file-backed profile storage.

Each profile lives at ``<profiles_dir>/<slug>.yaml`` where ``<slug>`` is a
kebab-case form of the profile name. Files are written with comment-preserving
``ruamel.yaml`` so a round-trip keeps the human-readable header block.
"""

from __future__ import annotations

import io
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from paic.api.schemas.profile import Profile
from paic.core.settings import Settings

_HEADER = """\
# Egress IP Condenser — Profile
# Apply this in the UI or via the API. Safe to copy/share — contains zero credentials.
"""

_AGGREGATION_COMMENT = """\
Aggregation: how to collapse the prefix list before rendering.
  exact     — no aggregation
  lossless  — merge adjacent prefixes only (no widening)
  budget    — collapse to at most N prefixes, minimum waste
  waste     — collapse until waste ratio approaches max_waste"""

_FORMAT_COMMENT = "Output format the consumer expects."
_FILTER_COMMENT = "Optional filters applied AFTER fetching from Prisma."
_FORMAT_HINT = "csv | json | xml | edl | yaml | plain"


def _yaml() -> YAML:
    """ruamel.yaml instance configured for comment-preserving round trips."""
    y = YAML()
    y.indent(mapping=2, sequence=4, offset=2)
    y.preserve_quotes = True
    y.default_flow_style = False
    return y


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Kebab-case ascii slug, max 64 chars."""
    s = name.strip().lower()
    s = _SLUG_RE.sub("-", s)
    s = s.strip("-")
    return s[:64] or "profile"


class ProfileStore:
    """File-backed profile repository — one YAML file per profile."""

    def __init__(self, profiles_dir: Path) -> None:
        self.dir = Path(profiles_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list(self) -> list[Profile]:
        """Return all profiles, sorted by saved_at."""
        profiles: list[Profile] = []
        for path in sorted(self.dir.glob("*.yaml")):
            try:
                profiles.append(self._read(path))
            except Exception:
                continue
        return sorted(profiles, key=lambda p: p.saved_at)

    def get(self, profile_id: str) -> Profile | None:
        for path in self.dir.glob("*.yaml"):
            try:
                p = self._read(path)
            except Exception:
                continue
            if p.id == profile_id:
                return p
        return None

    def export_one(self, profile_id: str) -> bytes:
        path = self._path_for_id(profile_id)
        if path is None:
            raise KeyError(profile_id)
        return path.read_bytes()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, profile: Profile) -> Path:
        """Write profile to <slug>.yaml; replaces existing file with same id."""
        existing_path = self._path_for_id(profile.id)
        if existing_path is not None and existing_path.exists():
            existing_path.unlink()

        slug = _slugify(profile.name)
        target = self.dir / f"{slug}.yaml"
        suffix = 1
        while target.exists():
            target = self.dir / f"{slug}-{suffix}.yaml"
            suffix += 1

        self._write(target, profile)
        return target

    def delete(self, profile_id: str) -> bool:
        path = self._path_for_id(profile_id)
        if path is None:
            return False
        path.unlink(missing_ok=True)
        return True

    def import_one(self, yaml_bytes: bytes) -> Profile:
        """Parse a YAML payload and persist it. Auto-generates id if missing."""
        data = _yaml().load(io.BytesIO(yaml_bytes)) or {}
        if not isinstance(data, dict):
            raise ValueError("imported file does not contain a YAML mapping")
        if "id" not in data or not data["id"]:
            data["id"] = str(uuid.uuid4())
        if "saved_at" not in data:
            data["saved_at"] = datetime.now(tz=UTC)
        profile = Profile.model_validate(_unwrap(data))
        if self.get(profile.id) is not None:
            raise ValueError(f"profile id {profile.id} already exists")
        self.save(profile)
        return profile

    @staticmethod
    def slugify(name: str) -> str:
        return _slugify(name)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _path_for_id(self, profile_id: str) -> Path | None:
        for path in self.dir.glob("*.yaml"):
            try:
                p = self._read(path)
            except Exception:
                continue
            if p.id == profile_id:
                return path
        return None

    def _read(self, path: Path) -> Profile:
        data = _yaml().load(path) or {}
        return Profile.model_validate(_unwrap(data))

    def _write(self, path: Path, profile: Profile) -> None:
        y = _yaml()
        doc = _build_doc(profile)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(_HEADER)
            fh.write("\n")
            y.dump(doc, fh)


def _unwrap(data: Any) -> dict[str, Any]:
    """Convert ruamel CommentedMap → plain dict for pydantic validation."""
    if hasattr(data, "items"):
        return {k: _unwrap_value(v) for k, v in data.items()}
    raise ValueError(f"expected mapping, got {type(data).__name__}")


def _unwrap_value(v: Any) -> Any:
    if hasattr(v, "items"):
        return {k: _unwrap_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_unwrap_value(x) for x in v]
    return v


def _build_doc(profile: Profile) -> Any:
    """Build a CommentedMap with section comments for a polished round-trip."""
    from ruamel.yaml.comments import CommentedMap

    doc = CommentedMap()
    doc["id"] = profile.id
    doc["name"] = profile.name
    if profile.description is not None:
        doc["description"] = profile.description
    doc["saved_at"] = profile.saved_at.isoformat()

    doc["mode"] = profile.mode
    doc.yaml_set_comment_before_after_key("mode", before="\n" + _AGGREGATION_COMMENT)
    doc["budget"] = profile.budget
    doc["max_waste"] = profile.max_waste

    doc["format"] = profile.format
    doc.yaml_set_comment_before_after_key("format", before="\n" + _FORMAT_COMMENT)
    doc.yaml_add_eol_comment(_FORMAT_HINT, "format")

    doc["filter_spec_json"] = profile.filter_spec_json
    doc.yaml_set_comment_before_after_key("filter_spec_json", before="\n" + _FILTER_COMMENT)

    return doc


def get_profile_store(settings: Settings | None = None) -> ProfileStore:
    """FastAPI dependency — return a singleton-ish ProfileStore for the active settings."""
    s = settings or Settings()  # type: ignore[call-arg]
    return ProfileStore(s.profiles_dir)
