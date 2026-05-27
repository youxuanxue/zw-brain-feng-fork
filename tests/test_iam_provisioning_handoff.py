"""scripts/export_iam_provisioning_request.py + ingest_iam_sub_backfill.py 单元测试。

覆盖：
  - export: 缺 dump 时降级为最小列 + note=legacy_dump_missing
  - export: 有 dump 时 phone/email/name mask + 部门区划落库 + 0 PII 泄漏
  - export: --diff 模式只输出 added/changed
  - ingest: classify(empty/missing token/disabled/真实 sub) 分类正确
  - ingest: 幂等（同一份回填跑两次第二次全 unchanged）
  - ingest: 列名大小写不敏感 + 注释行跳过 + not_found_in_manifest 计数
"""
from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@pytest.fixture()
def export_mod():
    return importlib.import_module("export_iam_provisioning_request")


@pytest.fixture()
def ingest_mod():
    return importlib.import_module("ingest_iam_sub_backfill")


@pytest.fixture()
def manifest_blob() -> dict:
    return {
        "manifest_type": "iaf_binding_manifest",
        "tenant_id": "sd-default",
        "manifest_version": "test",
        "description": "test fixture",
        "entries": [
            {
                "legacy_user_id": "U1",
                "legacy_user_code": "U1",
                "account": "alice",
                "iaf_sub": "iaf-sd-placeholder1",
                "preferred_username": "alice",
                "binding_status": "bound",
            },
            {
                "legacy_user_id": "U2",
                "legacy_user_code": "U2",
                "account": "bob",
                "iaf_sub": "iaf-sd-placeholder2",
                "preferred_username": "bob",
                "binding_status": "bound",
            },
        ],
    }


# ---------------------------------------------------------------------------
# export 单元测试
# ---------------------------------------------------------------------------

def test_format_row_without_dump(export_mod) -> None:
    """缺 dump 时 mask 列空 + note=legacy_dump_missing。"""
    entry = {"legacy_user_id": "U1", "account": "alice", "preferred_username": "alice",
             "iaf_sub": "iaf-sd-placeholder1", "binding_status": "bound"}
    row = export_mod._format_row(entry, pub_user_row=None)
    assert row["note"] == "legacy_dump_missing"
    assert row["phone_mask"] == ""
    assert row["email_mask"] == ""
    assert row["org_code"] == ""
    assert row["binding_status"] == "bound"
    assert row["iaf_sub_placeholder"] == "iaf-sd-placeholder1"


def test_format_row_with_dump_masks_pii(export_mod) -> None:
    entry = {"legacy_user_id": "U1", "account": "alice", "preferred_username": "alice",
             "iaf_sub": "iaf-sd-placeholder1", "binding_status": "bound"}
    pub_user = {
        "NAME": "张三",
        "PHONE": "13800138000",
        "MOBILE": "13912345678",
        "EMAIL": "alice@example.com",
        "ORG_CODE": "ORG-001",
        "ORG_NAME": "省大数据局",
        "REGION_CODE": "370000000000",
        "REGION_NAME": "山东省",
        "IS_ADMIN": "1",
        "STATUS": "1",
        "TYPE_CODE": "YWRY",
    }
    row = export_mod._format_row(entry, pub_user_row=pub_user)
    # mask 行为：保留首字 + *
    assert row["display_name_mask"].startswith("张")
    assert row["display_name_mask"] != "张三"
    # phone 前 3 + **** + 后 4
    assert "****" in row["phone_mask"]
    assert "****" in row["mobile_mask"]
    # email level=2 默认是 x***@***（host 也被 mask）
    assert "***" in row["email_mask"]
    assert "alice@example.com" not in row["email_mask"]
    # 部门 / 区划 / 管理员级别原样
    assert row["org_code"] == "ORG-001"
    assert row["region_code"] == "370000000000"
    assert row["is_admin_level"] == "1"
    assert row["note"] == ""


def test_format_row_non_email_email_field_is_masked(export_mod) -> None:
    """旧 dump 的 EMAIL 列偶有 hash 形式（非 email），脚本兜底强 mask 不能原样输出。"""
    entry = {"legacy_user_id": "U1", "account": "alice", "iaf_sub": "x", "binding_status": "bound"}
    pub_user = {"EMAIL": "f4f15bd2e1ef19993095"}  # 无 @ 的 hash
    row = export_mod._format_row(entry, pub_user_row=pub_user)
    assert row["email_mask"] == "***"
    assert "f4f15bd2" not in row["email_mask"]


def test_diff_rows_added_and_unchanged(export_mod) -> None:
    current = [
        {"legacy_user_id": "U1", "account": "alice", "preferred_username": "alice",
         "org_code": "X", "region_code": "Y", "is_admin_level": "0", "status": "1",
         "type_code": "T", "binding_status": "bound", "iaf_sub_placeholder": "",
         "display_name_mask": "", "phone_mask": "", "mobile_mask": "", "email_mask": "",
         "org_name": "", "region_name": "", "note": ""},
        {"legacy_user_id": "U2", "account": "bob", "preferred_username": "bob",
         "org_code": "X", "region_code": "Y", "is_admin_level": "0", "status": "1",
         "type_code": "T", "binding_status": "bound", "iaf_sub_placeholder": "",
         "display_name_mask": "", "phone_mask": "", "mobile_mask": "", "email_mask": "",
         "org_name": "", "region_name": "", "note": ""},
    ]
    previous_by_id = {"U2": current[1].copy()}
    diff, stats = export_mod._diff_rows(current, previous_by_id)
    assert stats["added"] == 1
    assert stats["changed"] == 0
    assert stats["unchanged"] == 1
    assert len(diff) == 1
    assert diff[0]["legacy_user_id"] == "U1"
    assert diff[0]["note"] == "iam_provisioning_pending"


def test_diff_rows_detects_changed_relevant_keys(export_mod) -> None:
    current = [{"legacy_user_id": "U1", "account": "alice2", "preferred_username": "alice",
                "org_code": "X", "region_code": "Y", "is_admin_level": "0", "status": "1",
                "type_code": "T", "binding_status": "bound", "iaf_sub_placeholder": "",
                "display_name_mask": "", "phone_mask": "", "mobile_mask": "", "email_mask": "",
                "org_name": "", "region_name": "", "note": ""}]
    previous = {"U1": current[0] | {"account": "alice"}}  # account changed
    diff, stats = export_mod._diff_rows(current, previous)
    assert stats["changed"] == 1
    assert diff[0]["note"] == "iam_provisioning_changed"


def test_export_csv_end_to_end(export_mod, tmp_path: Path, manifest_blob: dict) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_blob, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out.csv"
    # 不传 dump → 走 fallback 路径
    rc = export_mod.main([
        "--manifest", str(manifest_path),
        "--dump", str(tmp_path / "nonexistent.sql"),
        "--out", str(out),
    ])
    assert rc == 0
    with out.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert len(rows) == 2
    assert {r["legacy_user_id"] for r in rows} == {"U1", "U2"}
    assert all(r["note"] == "legacy_dump_missing" for r in rows)


# ---------------------------------------------------------------------------
# ingest 单元测试
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sub,status,expected", [
    ("", "", ("", "iam_account_missing")),
    ("iam_account_missing", "", ("", "iam_account_missing")),
    ("MISSING", "", ("", "iam_account_missing")),
    ("None", "", ("", "iam_account_missing")),
    ("IAM-PROD-001", "", ("IAM-PROD-001", "bound")),
    ("IAM-PROD-001", "bound", ("IAM-PROD-001", "bound")),
    ("IAM-PROD-001", "disabled", ("IAM-PROD-001", "disabled")),
    ("", "disabled", ("", "disabled")),
])
def test_ingest_classify(ingest_mod, sub: str, status: str, expected: tuple[str, str]) -> None:
    assert ingest_mod._classify(sub, status) == expected


def test_ingest_apply_replace_and_missing(ingest_mod, manifest_blob: dict) -> None:
    backfill = [
        {"legacy_user_id": "U1", "iaf_sub": "IAM-REAL-001", "binding_status": ""},
        {"legacy_user_id": "U2", "iaf_sub": "", "binding_status": ""},  # 触发 missing
        {"legacy_user_id": "U99", "iaf_sub": "IAM-EXTRA", "binding_status": ""},  # extra
    ]
    updated, stats = ingest_mod._apply(manifest_blob, backfill)
    assert stats["replaced"] == 1
    assert stats["marked_missing"] == 1
    assert stats["not_found_in_manifest"] == 1
    assert "U99" in stats["iam_extra_rows"]
    by_id = {e["legacy_user_id"]: e for e in updated["entries"]}
    assert by_id["U1"]["iaf_sub"] == "IAM-REAL-001"
    assert by_id["U1"]["binding_status"] == "bound"
    assert by_id["U2"]["iaf_sub"] == ""
    assert by_id["U2"]["binding_status"] == "iam_account_missing"


def test_ingest_apply_idempotent(ingest_mod, manifest_blob: dict) -> None:
    backfill = [{"legacy_user_id": "U1", "iaf_sub": "IAM-REAL-001", "binding_status": ""}]
    _, stats1 = ingest_mod._apply(manifest_blob, backfill)
    assert stats1["replaced"] == 1
    _, stats2 = ingest_mod._apply(manifest_blob, backfill)
    assert stats2["replaced"] == 0
    assert stats2["unchanged"] == 1


def test_ingest_csv_column_case_and_comments(ingest_mod, tmp_path: Path) -> None:
    csv_path = tmp_path / "backfill.csv"
    csv_path.write_text(
        "# 注释行，应该跳过\n"
        "Legacy_User_ID,IAF_SUB,Binding_Status\n"
        "U1,IAM-001,bound\n"
        "U2,,\n",
        encoding="utf-8",
    )
    rows = ingest_mod._read_backfill_csv(csv_path)
    assert len(rows) == 2
    assert rows[0]["legacy_user_id"] == "U1"
    assert rows[0]["iaf_sub"] == "IAM-001"
    assert rows[1]["iaf_sub"] == ""


def test_ingest_csv_missing_required_column(ingest_mod, tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("legacy_user_id,not_sub\nU1,X\n", encoding="utf-8")
    with pytest.raises(ValueError, match="legacy_user_id"):
        ingest_mod._read_backfill_csv(csv_path)


def test_ingest_full_main(ingest_mod, tmp_path: Path, manifest_blob: dict) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_blob, ensure_ascii=False), encoding="utf-8")
    csv_path = tmp_path / "backfill.csv"
    # 同时回填 U1 (real sub) + U2 (missing)，避免 U2 留占位触发 R-001 守卫
    csv_path.write_text("legacy_user_id,iaf_sub\nU1,IAM-REAL-001\nU2,\n", encoding="utf-8")
    rc = ingest_mod.main([str(csv_path), "--manifest", str(manifest_path)])
    assert rc == 0
    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_id = {e["legacy_user_id"]: e for e in updated["entries"]}
    assert by_id["U1"]["iaf_sub"] == "IAM-REAL-001"
    assert "iam-sub backfilled" in updated["description"]


# ---------------------------------------------------------------------------
# R-001 回归：占位前缀守卫
# ---------------------------------------------------------------------------

def test_ingest_scan_residual_placeholders(ingest_mod) -> None:
    blob = {"entries": [
        {"legacy_user_id": "U1", "iaf_sub": "iaf-sd-abc123"},
        {"legacy_user_id": "U2", "iaf_sub": "IAM-REAL-002"},
        {"legacy_user_id": "U3", "iaf_sub": ""},
    ]}
    residual = ingest_mod._scan_residual_placeholders(blob)
    assert residual == ["U1"]


def test_ingest_fail_closed_on_placeholder_residual(ingest_mod, tmp_path: Path) -> None:
    """manifest 全是占位 sub，backfill csv 空 → ingest 必须非零退出（无逃生口）。"""
    manifest_path = tmp_path / "manifest.json"
    original = json.dumps({
        "entries": [{"legacy_user_id": "U1", "account": "a", "iaf_sub": "iaf-sd-placeholder",
                     "preferred_username": "a", "binding_status": "bound"}],
    }, ensure_ascii=False)
    manifest_path.write_text(original, encoding="utf-8")
    csv_path = tmp_path / "backfill.csv"
    csv_path.write_text("legacy_user_id,iaf_sub\n", encoding="utf-8")  # 空回填
    rc = ingest_mod.main([str(csv_path), "--manifest", str(manifest_path)])
    assert rc == 2, "占位 sub 残留必须 fail-closed (exit 2)"
    assert manifest_path.read_text(encoding="utf-8") == original, "fail-closed 不得写盘"


def test_ingest_fail_closed_on_not_found_in_manifest(ingest_mod, tmp_path: Path, manifest_blob: dict) -> None:
    """backfill 含 manifest 不存在的 legacy_user_id → exit 1 且不写盘。"""
    manifest_path = tmp_path / "manifest.json"
    original = json.dumps(manifest_blob, ensure_ascii=False)
    manifest_path.write_text(original, encoding="utf-8")
    csv_path = tmp_path / "backfill.csv"
    csv_path.write_text(
        "legacy_user_id,iaf_sub\nU1,IAM-REAL-001\nU99,IAM-EXTRA\nU2,\n",
        encoding="utf-8",
    )
    rc = ingest_mod.main([str(csv_path), "--manifest", str(manifest_path)])
    assert rc == 1
    assert manifest_path.read_text(encoding="utf-8") == original


def test_ingest_explicit_missing_clears_placeholder(ingest_mod, tmp_path: Path) -> None:
    """残缺用户的合法处理路径：backfill csv 显式标 missing（sub 留空），让 _classify
    把 binding_status 转为 iam_account_missing 同时清空 sub，从而不触发 R-001 守卫。"""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "entries": [{"legacy_user_id": "U1", "account": "a", "iaf_sub": "iaf-sd-placeholder",
                     "preferred_username": "a", "binding_status": "bound"}],
    }, ensure_ascii=False), encoding="utf-8")
    csv_path = tmp_path / "backfill.csv"
    csv_path.write_text("legacy_user_id,iaf_sub\nU1,\n", encoding="utf-8")
    rc = ingest_mod.main([str(csv_path), "--manifest", str(manifest_path)])
    assert rc == 0
    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated["entries"][0]["iaf_sub"] == ""
    assert updated["entries"][0]["binding_status"] == "iam_account_missing"


# ---------------------------------------------------------------------------
# R-002 回归：diff 黑名单（新增 CSV 列默认进 diff，不依赖记忆同步）
# ---------------------------------------------------------------------------

def test_diff_rows_excluded_keys_not_compared(export_mod) -> None:
    """脱敏列变化不应触发 changed（mask level 漂移可能让同源值跨次不同）。"""
    base = {"legacy_user_id": "U1", "account": "a", "preferred_username": "a",
            "org_code": "X", "region_code": "Y", "is_admin_level": "0", "status": "1",
            "type_code": "T", "binding_status": "bound",
            "display_name_mask": "", "phone_mask": "", "mobile_mask": "", "email_mask": "",
            "org_name": "", "region_name": "", "iaf_sub_placeholder": "", "note": ""}
    current = [base.copy()]
    # 模拟脱敏列 + 派生列 + iaf_sub_placeholder + note 都改了，但业务列不变
    previous = {"U1": base | {"phone_mask": "OLD****", "email_mask": "old@***",
                              "org_name": "OLD-NAME", "iaf_sub_placeholder": "iaf-sd-old",
                              "note": "stale", "display_name_mask": "甲*"}}
    diff, stats = export_mod._diff_rows(current, previous)
    assert stats["unchanged"] == 1
    assert stats["changed"] == 0


# ---------------------------------------------------------------------------
# R-003 顺手补的缺口
# ---------------------------------------------------------------------------

def test_diff_rows_previous_only_count(export_mod) -> None:
    """previous 有 current 没的 row → previous_only +1。"""
    current = [{"legacy_user_id": "U1", "account": "a", "preferred_username": "a",
                "org_code": "X", "region_code": "Y", "is_admin_level": "0", "status": "1",
                "type_code": "T", "binding_status": "bound",
                "display_name_mask": "", "phone_mask": "", "mobile_mask": "", "email_mask": "",
                "org_name": "", "region_name": "", "iaf_sub_placeholder": "", "note": ""}]
    previous = {"U1": current[0].copy(), "U2": {"legacy_user_id": "U2"}}
    _, stats = export_mod._diff_rows(current, previous)
    assert stats["previous_only"] == 1


def test_ingest_watermark_added_once(ingest_mod, manifest_blob: dict) -> None:
    backfill = [{"legacy_user_id": "U1", "iaf_sub": "IAM-001", "binding_status": ""}]
    updated1, _ = ingest_mod._apply(manifest_blob, backfill)
    desc1 = updated1["description"]
    updated2, _ = ingest_mod._apply(updated1, backfill)
    desc2 = updated2["description"]
    assert desc1.count("iam-sub backfilled") == 1
    assert desc1 == desc2, "重复跑不应重复加 watermark"


def test_ingest_csv_missing_legacy_user_id_column(ingest_mod, tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("foo,iaf_sub\nU1,X\n", encoding="utf-8")
    with pytest.raises(ValueError, match="legacy_user_id"):
        ingest_mod._read_backfill_csv(csv_path)


# ---------------------------------------------------------------------------
# P0-C 回归：import --unmapped-csv 落表
# ---------------------------------------------------------------------------

@pytest.fixture()
def import_legacy_mod():
    return importlib.import_module("import_legacy_dumps")


def test_import_filter_issues_default_types(import_legacy_mod) -> None:
    issues = [
        {"type": "unmapped_permission", "table": "pub_resource", "legacy_ref": "RA1", "detail": {}},
        {"type": "missing_role_mapping", "table": "pub_user", "legacy_ref": "U1", "detail": {}},
        {"type": "iam_account_missing", "table": "pub_user", "legacy_ref": "U2", "detail": {}},
        {"type": "missing_actor_ref", "table": "sys_user", "legacy_ref": "U3", "detail": {}},  # 默认不在范围
        {"type": "error", "table": "pub_user", "legacy_ref": "U4", "detail": {}},  # 默认不在范围
    ]
    filtered = import_legacy_mod._filter_issues(issues, set(import_legacy_mod._DEFAULT_UNMAPPED_ISSUE_TYPES))
    types = {i["type"] for i in filtered}
    assert "unmapped_permission" in types
    assert "missing_role_mapping" in types
    assert "iam_account_missing" in types
    assert "missing_actor_ref" not in types
    assert "error" not in types


def test_import_filter_issues_all(import_legacy_mod) -> None:
    issues = [{"type": "x", "table": "t", "legacy_ref": "1", "detail": {}},
              {"type": "y", "table": "t", "legacy_ref": "2", "detail": {}}]
    assert len(import_legacy_mod._filter_issues(issues, {"all"})) == 2


def test_import_write_unmapped_csv_sorted(import_legacy_mod, tmp_path: Path) -> None:
    out = tmp_path / "unmapped.csv"
    issues = [
        {"type": "unmapped_permission", "table": "pub_resource", "legacy_ref": "Z9", "detail": {"path": "/foo"}},
        {"type": "unmapped_permission", "table": "pub_resource", "legacy_ref": "A1", "detail": {"path": "/bar"}},
        {"type": "iam_account_missing", "table": "pub_user", "legacy_ref": "U1", "detail": {}},
    ]
    n = import_legacy_mod._write_unmapped_csv(out, issues)
    assert n == 3
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    # 排序 by (type, table, legacy_ref)：iam_account_missing 在前；同 type 内按 legacy_ref 升序
    assert [r["legacy_ref"] for r in rows] == ["U1", "A1", "Z9"]
    # detail_json 序列化（中文不转 ascii）
    assert rows[1]["detail_json"] == '{"path": "/bar"}'


# ---------------------------------------------------------------------------
# P0-D 回归：role-mapping diff
# ---------------------------------------------------------------------------

@pytest.fixture()
def diff_role_mod():
    return importlib.import_module("diff_role_mapping_against_dump")


def test_diff_roles_uncovered(diff_role_mod) -> None:
    from collections import Counter
    dump_counters = {
        "pub_role": Counter({"ROLE_KNOWN": 1, "ROLE_NEW": 1}),
        "pub_user_role": Counter({"ROLE_KNOWN": 10, "ROLE_NEW": 5, "ROLE_RARE": 1}),
        "pub_user_organ_role": Counter({"ROLE_NEW": 3}),
    }
    manifest_refs = {"ROLE_KNOWN"}
    rows = diff_role_mod.diff_roles(dump_counters, manifest_refs)
    # ROLE_KNOWN 已覆盖 → 不出现
    refs = [r["legacy_role_ref"] for r in rows]
    assert "ROLE_KNOWN" not in refs
    # 按 total_occurrences 降序：ROLE_NEW (1+5+3=9) > ROLE_RARE (0+1+0=1)
    assert refs == ["ROLE_NEW", "ROLE_RARE"]
    assert rows[0]["total_occurrences"] == 9
    assert rows[0]["occurrence_pub_user_organ_role"] == 3
    assert rows[1]["total_occurrences"] == 1


def test_diff_roles_all_covered(diff_role_mod) -> None:
    from collections import Counter
    dump_counters = {
        "pub_role": Counter({"RA1": 1}),
        "pub_user_role": Counter({"RA1": 5}),
        "pub_user_organ_role": Counter(),
    }
    rows = diff_role_mod.diff_roles(dump_counters, {"RA1"})
    assert rows == []


def test_diff_role_load_manifest_refs(diff_role_mod, tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "rows": [
            {"legacy_role_ref": "ROLE_A", "target_role_code": "X"},
            {"legacy_role_ref": "ROLE_B", "target_role_code": "Y"},
            {"legacy_role_ref": "", "target_role_code": "Z"},  # 空 ref 跳过
        ]
    }), encoding="utf-8")
    refs = diff_role_mod._load_manifest_role_refs(manifest)
    assert refs == {"ROLE_A", "ROLE_B"}
