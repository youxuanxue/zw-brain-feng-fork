"""客户验收脚本契约：身份治理中心步骤与 start-local 默认端口对齐."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "customer_acceptance_checklist.py"

pytestmark = pytest.mark.no_db


def test_customer_acceptance_script_default_port_matches_start_local() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'os.environ.get("ZW_BRAIN_REST_PORT", "8800")' in text
    assert "8830" not in text


def test_customer_acceptance_script_covers_iam_governance_center() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "#/integration-admin/iam-governance" in text
    assert "B1.2 身份治理入口" in text
    assert "B1.2 身份治理页" in text
    assert "B1.2 身份治理岗位守卫" in text
    assert "login-gate-submit" in text
    assert "用户与角色" in text
    assert "谁能访问什么" in text
    assert "旧权限映射审核\" not in t" in text
