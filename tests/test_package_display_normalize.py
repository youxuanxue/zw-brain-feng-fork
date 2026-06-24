"""B12 能力包行投影回归：与 zw-brain-web/src/lib/packageDisplay.ts 保持语义一致。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_db

TRUST_LEVELS = ("baseline", "reviewed", "restricted", "revoked")


def _normalize_trust_level(raw: object) -> str:
    v = str(raw or "baseline").strip()
    return v if v in TRUST_LEVELS else "baseline"


def _normalize_package_row(raw: dict) -> dict:
    slug = str(raw.get("slug") or "")
    return {
        "trust_level": _normalize_trust_level(raw.get("trust_level") or raw.get("trustLevel")),
        "version": str(raw.get("version") or raw.get("registeredVersion") or "—"),
        "rollback_target": str(raw.get("rollback_target") or raw.get("rollbackTarget") or ""),
        "name": str(raw.get("name") or raw.get("desc") or slug),
    }


def test_trust_level_from_camel_case_field() -> None:
    row = _normalize_package_row({"slug": "demo", "trustLevel": "reviewed"})
    assert row["trust_level"] == "reviewed"


def test_trust_level_defaults_when_missing() -> None:
    row = _normalize_package_row({"slug": "demo"})
    assert row["trust_level"] == "baseline"


def test_version_reads_registered_version() -> None:
    row = _normalize_package_row({"slug": "demo", "registeredVersion": "v1.2.0"})
    assert row["version"] == "v1.2.0"
