# Wave: 1
# Journey: J2
# Pages: P5 (provider) + 异议响应面
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER / ROLE_ORGAN_MANAGER / ROLE_BUSIAUDIT
# Trace:
#   .twin/e2-j2-journey/plan.yaml F6
#   scripts/customer_demo_j2.py
#   docs/customer-demo-j2.md
"""F6 J2 客户演示集成测试 — 通过 Python driver 跑全链路 + 断言 audit 覆盖 + 时长预算."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
TENANT = "sd-default"


def _seed_ready() -> bool:
    if not SEED_DB.exists():
        return False
    try:
        with sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True) as conn:
            # F6 demo 仅依赖：catalog_entry (≥1000) + resource_asset.resource_kind=table (≥1)
            cat_row = conn.execute(
                "SELECT COUNT(*) FROM catalog_entry WHERE tenant_id=?", (TENANT,)
            ).fetchone()
            if not cat_row or cat_row[0] < 1000:
                return False
            res_row = conn.execute(
                "SELECT COUNT(*) FROM resource_asset WHERE tenant_id=? "
                "AND resource_kind='table' AND owner_org_id IS NOT NULL AND owner_org_id != ''",
                (TENANT,),
            ).fetchone()
            return bool(res_row and res_row[0] >= 1)
    except sqlite3.OperationalError:
        return False


if not _seed_ready():
    pytest.skip(
        "M0 真灌库数据缺位（CI runner 无 .data/zw_brain.db 或 resource_asset.resource_kind='table' 空）",
        allow_module_level=True,
    )


# 把 scripts/ 加入 sys.path 以便 import customer_demo_j2
_SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def test_customer_demo_j2_full_chain_exits_clean(tmp_path):
    """直接 import driver 跑 J2 全链路，断言 result.ok + 14 类 audit 覆盖 + 时长 < 30 分钟."""
    import customer_demo_j2 as demo  # noqa: PLC0415

    shadow = tmp_path / "shadow-full.db"
    result = demo.run_demo(SEED_DB, shadow)
    assert result["ok"] is True
    assert result["catalog_code"].startswith("DEMO-J2-")
    assert result["resource_code"]
    assert result["objection_id"]
    assert result["resource_kind"] == "table"
    # F1+F4 mutate skill 全部触发 — audit_event 类型覆盖 13 类
    # （duplicate.check 是 read-only，落 capability_call 不进 audit_events feed；
    # 用 duplicate_check_triggered + capability_call_core_missing 联合断言 F3）
    assert result["audit_event_types_covered"] >= 13, (
        f"F6 J2 全链路应覆盖 ≥13 类 audit_event 类型；实际 {result['audit_event_types_covered']}"
    )
    assert result["duplicate_check_triggered"] is True, "F3 publish 路径必须自动触发 duplicate.check"
    assert result["elapsed_seconds"] < demo.DEFAULT_BUDGET_SECONDS, (
        f"30 分钟预算超时: {result['elapsed_seconds']}s"
    )


def test_customer_demo_j2_writes_json_report(tmp_path):
    """通过 main() 跑脚本，验证 --report 参数能写 JSON 报告."""
    import customer_demo_j2 as demo  # noqa: PLC0415

    shadow = tmp_path / "shadow-report.db"
    report_path = tmp_path / "demo-test.json"
    argv = sys.argv
    sys.argv = ["customer_demo_j2.py", "--seed-db", str(SEED_DB),
                "--shadow-db", str(shadow), "--report", str(report_path)]
    try:
        rc = demo.main()
    finally:
        sys.argv = argv
    assert rc == 0
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["catalog_code"].startswith("DEMO-J2-")
    assert data["objection_id"]
    # quality_flags：F1+F3+F4 必 true；F2 file/api 当前 false (M0 mapper chip pending)
    qf = data["quality_flags"]
    assert qf["f1_three_layer_review_active"] is True
    assert qf["f3_duplicate_check_auto_triggered"] is True
    assert qf["f4_provider_response_chain_complete"] is True
    assert qf["f2_table_materialization_real_data"] is True
    assert qf["f5_national_ext_elem_deferred"] is True


def test_customer_demo_j2_capability_call_core_coverage(tmp_path):
    """capability_call 持久化 SoT 必须覆盖 F1+F2+F3+F4 9 个核心 skill（core_missing 应为空）."""
    import customer_demo_j2 as demo  # noqa: PLC0415

    shadow = tmp_path / "shadow-cap.db"
    result = demo.run_demo(SEED_DB, shadow)
    assert result["capability_call_total"] > 0
    assert result["capability_call_core_missing"] == [], (
        f"F6 demo 核心 skill capability_call 缺漏：{result['capability_call_core_missing']}"
    )


def test_shell_wrapper_exists_and_executable():
    sh_path = REPO_ROOT / "scripts" / "customer_demo_j2.sh"
    assert sh_path.exists()
    assert os.access(sh_path, os.X_OK), "scripts/customer_demo_j2.sh 必须 chmod +x"


def test_docs_customer_demo_j2_md_exists():
    md_path = REPO_ROOT / "docs" / "customer-demo-j2.md"
    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    # sign-off 流程必须在文档中
    assert "business-signoff" in content
    assert "回滚" in content
    assert "退出码" in content or "exit code" in content.lower()
    # F2 partial 警示必须显式
    assert "f2" in content.lower() or "F2" in content
    assert "partial" in content.lower() or "M0 mapper" in content


def test_30min_budget_constant_aligned_with_plan():
    """plan.yaml F6 evidence_plan 明确 30 分钟时长记录."""
    import customer_demo_j2 as demo  # noqa: PLC0415
    assert demo.DEFAULT_BUDGET_SECONDS == 30 * 60
