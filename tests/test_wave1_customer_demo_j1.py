# Wave: 1
# Journey: J1
# Pages: P2 / P3 / P4 / 异议
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_BUSIAUDIT
# Trace:
#   .twin/e1-j1-journey/plan.yaml F9
#   scripts/customer_demo_j1.py
#   docs/customer-demo-j1.md
"""F9 客户演示集成测试 — 通过 Python driver 跑全链路 + 断言 audit 覆盖 + 时长预算."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from tests._seed_guard import require_real_seed

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_wave1_customer_demo_j1_shadow.db"
TENANT = "sd-default"

require_real_seed(
    {"catalog_entry": 100, "application_record": 100, "delivery_task": 50, "objection_case": 20}
)


# 把 scripts/ 加入 sys.path 以便 import customer_demo_j1
_SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def test_customer_demo_j1_full_chain_exits_clean(tmp_path):
    """直接 import driver 跑全链路，断言 result.ok + 全 audit 覆盖 + 时长 < 30 分钟."""
    import customer_demo_j1 as demo  # noqa: PLC0415

    shadow = tmp_path / "shadow-full.db"
    result = demo.run_demo(SEED_DB, shadow)
    assert result["ok"] is True
    assert result["catalog_targets_hit"] == 3, "3 个 core_goal catalog (医疗救助/医保码/异地就医) 必须全命中"
    assert result["audit_event_types_covered"] >= 13, "P2/P3/P4 + 异议 7 步 cap 类型必须全覆盖"
    assert result["elapsed_seconds"] < demo.DEFAULT_BUDGET_SECONDS, f"30 分钟预算超时: {result['elapsed_seconds']}s"
    assert result["primary_catalog"]["title"] in ("医疗救助信息", "医保码信息", "异地就医统筹区开通信息")


def test_customer_demo_j1_writes_json_report(tmp_path):
    """通过 main() 跑脚本，验证 --report 参数能写 JSON 报告."""
    import customer_demo_j1 as demo  # noqa: PLC0415

    shadow = tmp_path / "shadow-report.db"
    report_path = tmp_path / "demo-test.json"
    argv = sys.argv
    sys.argv = ["customer_demo_j1.py", "--seed-db", str(SEED_DB),
                "--shadow-db", str(shadow), "--report", str(report_path)]
    try:
        rc = demo.main()
    finally:
        sys.argv = argv
    assert rc == 0
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["catalog_targets_hit"] == 3
    assert data["objection_id"]
    assert data["request_id"] == "REQ-DEMO-F9-MEDICAL-AID"


def test_customer_demo_j1_audit_chain_contains_all_steps(tmp_path):
    """全链路 audit_event 类型必须包含 13 个关键 cap."""
    import customer_demo_j1 as demo  # noqa: PLC0415

    shadow = tmp_path / "shadow-audit.db"
    result = demo.run_demo(SEED_DB, shadow)
    assert result["audit_event_types_covered"] >= 13
    assert result["audit_event_total"] > result["audit_event_types_covered"], (
        "同 cap 多步骤应产生多 audit_event（如 objection.case.assign 出现 2 次）"
    )


def test_shell_wrapper_exists_and_executable():
    sh_path = REPO_ROOT / "scripts" / "customer_demo_j1.sh"
    assert sh_path.exists()
    assert os.access(sh_path, os.X_OK), "scripts/customer_demo_j1.sh 必须 chmod +x"


def test_docs_customer_demo_j1_md_exists():
    md_path = REPO_ROOT / "docs" / "customer-demo-j1.md"
    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    # 关键 sign-off 流程必须在文档中
    assert "business-signoff" in content
    assert "回滚" in content
    assert "退出码" in content or "exit code" in content.lower()


def test_30min_budget_constant_aligned_with_plan():
    """plan.yaml F9 evidence_plan 明确 30 分钟时长记录."""
    import customer_demo_j1 as demo  # noqa: PLC0415
    assert demo.DEFAULT_BUDGET_SECONDS == 30 * 60
