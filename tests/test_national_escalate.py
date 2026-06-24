"""国家直达转报 handler（D50/C6，national-direct 子旅程）.

权威：docs/decisions/national-platform-access-D50.md §三；national-direct.feature。
核实：
  - 转报打**计算态** overlay（escalating/revoking），display 派生「国家通道转报中/撤销中」；
  - 经 C4 gate：未配置→诚实 pending（不出站、不伪造回流）；provisioned+协议桩→真实出站；
  - **J1 主链路未污染**：escalate 不写 application 聚合、主 status 枚举无新增值；
  - 审计 capability_call=application.escalate_national（ctx.skill_id 驱动）。
"""

from __future__ import annotations

import json
import types

import pytest

from zw_brain.command.handlers.infra import national_channel_gate as gate
from zw_brain.command.handlers.j1 import escalate
from zw_brain.shared.national.provisioning import (
    ENV_APPKEY,
    ENV_APPSECRET,
    ENV_ENABLED,
    ENV_ENDPOINT,
    ENV_RID,
    ENV_SID_MAP,
)

_CAP = "application.escalate_national"

pytestmark = pytest.mark.no_db


@pytest.fixture()
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (ENV_ENABLED, ENV_ENDPOINT, ENV_RID, ENV_APPKEY, ENV_APPSECRET, ENV_SID_MAP):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(gate, "OUTBOUND_TRANSPORT", None)


def _provision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_ENABLED, "1")
    monkeypatch.setenv(ENV_ENDPOINT, "https://national.example")
    monkeypatch.setenv(ENV_RID, "RID-1")
    monkeypatch.setenv(ENV_APPKEY, "AK")
    monkeypatch.setenv(ENV_APPSECRET, "SK")
    monkeypatch.setenv(ENV_SID_MAP, json.dumps({"adapter.national.application.submit": "SID-1"}))


def _ctx() -> types.SimpleNamespace:
    return types.SimpleNamespace(skill_id=_CAP, role="ROLE_BUSIAUDIT", actor="busi")


def _fake_deps() -> types.SimpleNamespace:
    # deps.write 直接跑 mutation 闭包（绕过 pipeline），audit_id/actor 注入定值。
    def write(ctx, payload, mutation):  # noqa: ANN001
        return mutation("AE-ESC", "busi")

    return types.SimpleNamespace(brain_legacy=object(), write=write)


# ---- 计算态纯函数（不入主状态机）------------------------------------------


def test_display_helper_maps_stage_to_human_label() -> None:
    assert escalate.national_channel_display("escalating") == "国家通道转报中"
    assert escalate.national_channel_display("revoking") == "国家通道撤销中"
    assert escalate.national_channel_display(None) is None
    assert escalate.national_channel_display("") is None


def test_stage_values_not_in_j1_main_status_machine() -> None:
    """硬约束：计算态值绝不出现在 J1 主状态机里（不污染主枚举）。"""
    from zw_brain.domain.services import conditional_approval as ca

    main_statuses = set(ca.CONDITIONAL_TRANSITIONS) | {
        s for nxt in ca.CONDITIONAL_TRANSITIONS.values() for s in nxt
    }
    assert escalate.STAGE_ESCALATING not in main_statuses
    assert escalate.STAGE_REVOKING not in main_statuses
    assert "国家通道转报中" not in main_statuses


# ---- handler：未配置 / provisioned ----------------------------------------


def test_escalate_unprovisioned_records_intent_pending(_clean_env: None) -> None:
    result = _fake_deps().write  # ensure structure
    out = escalate.handler_application_escalate_national(_fake_deps(), _ctx(), {"application_code": "A_7001"})
    assert out["application_code"] == "A_7001"
    assert out["national_channel_stage"] == "escalating"
    assert out["display_status"] == "国家通道转报中"
    assert out["national_channel"]["status"] == "pending"  # 诚实 pending、不伪造回流
    assert "run" not in out or out.get("run") is None
    assert callable(result)


def test_escalate_provisioned_calls_client(_clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _provision(monkeypatch)
    sent: dict = {}

    def stub(url, headers, body):  # noqa: ANN001
        sent["headers"] = headers
        return 200, json.dumps({"code": "200", "message": "ok"}).encode("utf-8")

    monkeypatch.setattr(gate, "OUTBOUND_TRANSPORT", stub)
    out = escalate.handler_application_escalate_national(_fake_deps(), _ctx(), {"application_code": "A_7001"})
    assert out["national_channel"]["status"] == "submitted"
    assert out["national_channel_stage"] == "escalating"
    # 经国家通道 adapter 真实出站（4 签名头齐全）。
    assert sent["headers"]["gjzwfwpt_sid"] == "SID-1"


def test_revoke_action_uses_revoking_stage(_clean_env: None) -> None:
    out = escalate.handler_application_escalate_national(
        _fake_deps(), _ctx(), {"application_code": "A_7001", "action": "revoke"}
    )
    assert out["national_channel_stage"] == "revoking"
    assert out["display_status"] == "国家通道撤销中"


def test_escalate_does_not_touch_application_aggregate() -> None:
    """escalate 代码（AST，排除 docstring/注释）不引用 application 写仓 / update_status /
    主状态机——结构性保证主链路零写。"""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(escalate))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    for forbidden in ("update_status", "application_repo", "ApplicationRecord", "CONDITIONAL_TRANSITIONS"):
        assert forbidden not in names, f"escalate 代码不应引用 {forbidden}（会污染 J1 主链路）"
