"""Regression tests for user provisioning helper scripts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import import_loggedin_users, provision_iam_users, update_user_roles
from zw_brain.domain.role_codes import BUSINESS_ROLE_CODES

pytestmark = pytest.mark.no_db


def test_provision_failure_records_strip_passwords(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    csv_path = tmp_path / "users.csv"
    csv_path.write_text(
        "account,phone,email,password\n"
        "zhangsan,13800138000,zhangsan@example.com,PlainSecret123!\n",
        encoding="utf-8",
    )
    fail_path = tmp_path / "fail.jsonl"
    success_path = tmp_path / "success.jsonl"

    monkeypatch.setattr(
        provision_iam_users,
        "call_iam_create_user",
        lambda *_args, **_kwargs: (None, "simulated IAM failure"),
    )

    rc = provision_iam_users.main(
        [
            "--csv",
            str(csv_path),
            "--token",
            "test-token",
            "--iam-url",
            "https://iam.example",
            "--fail-out",
            str(fail_path),
            "--success-out",
            str(success_path),
        ]
    )

    assert rc == 1
    record = json.loads(fail_path.read_text(encoding="utf-8"))
    assert record["payload"] == {"name": "zhangsan", "email": "zhangsan@example.com", "phone": "13800138000"}
    assert "PlainSecret123!" not in fail_path.read_text(encoding="utf-8")


def test_update_user_roles_uses_canonical_role_codes() -> None:
    assert update_user_roles.PRODUCT_ROLES == frozenset(BUSINESS_ROLE_CODES)
    legacy_role = next(iter(update_user_roles.LEGACY_ROLE_CODES))
    assert update_user_roles.normalize_role(legacy_role, {}) is None
    assert update_user_roles.normalize_role(
        "ROLE_DATA_LEADER",
        {
            "ROLE_DATA_LEADER": {
                "target_type": "tag",
                "target_role_code": "ROLE_ORGAN_MANAGER",
                "target_tag": "tag_lead_dept",
            }
        },
    ) == {"role_code": "ROLE_ORGAN_MANAGER", "tags_json": {"tag_lead_dept": True}}


def test_import_loggedin_users_scopes_org_lookup_by_tenant() -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    class Cursor:
        def execute(self, sql: str, params: tuple[str, ...]) -> None:
            calls.append((sql, params))

        def fetchone(self) -> None:
            return None

        def close(self) -> None:
            return None

    class Conn:
        def cursor(self) -> Cursor:
            return Cursor()

    import_loggedin_users.ensure_org(
        Conn(),
        "tenant-b",
        {"org_code": "ORG-1", "org_name": "Org One", "status": "active"},
    )

    assert calls[0][1] == ("tenant-b", "ORG-1")
    assert "tenant_id = %s AND org_code = %s" in calls[0][0]
