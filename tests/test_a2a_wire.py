"""A2A 线级（over-socket）端到端测试 — 补 5 消费面之一零线级覆盖（Wave 3 测试债）。

照 a2a-hardening.feature 核心 4 场景：
1. 线级 discover → invoke + audit 落账；
2. 多轮线级会话 + audit 链可追（source=a2a 贯穿）；
3. trust 旋钮裁剪：untrusted 调责任性写 → 403，verified 清门；
4. 投影一致性：a2a runtime_bindings 与 mcp tools 同源 registry。

诚实口径：trust_level 是 ZW_BRAIN_A2A_CALLER_TRUST_LEVEL **部署级 env 旋钮、非 per-caller
身份裁剪**（A2A daemon 当前无 per-message 外部 Agent 身份）；跨租户隔离(场景5)/anp 门控(场景4)
trigger-deferred 记债，本期不抬全 SPEC 状态（D46.f）。
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select

from tests._iaf_a2a_http import a2a_request, run_a2a_server, stop_a2a_server


@pytest.fixture()
def wire(monkeypatch: pytest.MonkeyPatch):
    """隔离 PG 克隆 + dev bypass + 起线级 A2A daemon；get_service 懒建于克隆库。"""
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    monkeypatch.delenv("ZW_BRAIN_A2A_CALLER_TRUST_LEVEL", raising=False)

    from zw_brain.command import runtime as cmd_runtime
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    cmd_runtime._service = None  # 强制 get_service 在隔离克隆库上重建（含 initialize 种子）

    server, thread, port = run_a2a_server()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        stop_a2a_server(server, thread)
        cmd_runtime._service = None


def _audit_rows(skill_id: str):
    from zw_brain.domain.models import AuditEventRecord
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        return list(
            s.execute(select(AuditEventRecord).where(AuditEventRecord.skill_id == skill_id)).scalars()
        )


# ── 场景1：线级 discover → invoke + audit ────────────────────────────────────

def test_wire_discover_then_invoke_with_audit(wire: str) -> None:
    # discover
    status, skills = a2a_request("GET", f"{wire}/a2a/skills")
    assert status == 200
    assert isinstance(skills, list) and skills
    assert "tool_name" in skills[0]

    # invoke 一个读能力（线级）
    status, body = a2a_request(
        "POST", f"{wire}/a2a/skills/workbench.view/invoke", body={"role": "ROLE_ORGAN_OPERATER"}
    )
    assert status == 200, body
    assert body["skill_id"] == "workbench.view"
    assert "greeting" in body["result"]

    # audit 落账 + source=a2a
    rows = _audit_rows("workbench.view")
    assert rows, "invoke 未落 audit_event"
    assert any((r.payload_json or {}).get("source") == "a2a" for r in rows)


# ── 场景2：多轮线级会话 + audit 链可追 ───────────────────────────────────────

def test_wire_multi_turn_session_audit_chain(wire: str) -> None:
    turns = [
        ("workbench.view", {"role": "ROLE_ORGAN_OPERATER"}),
        ("data.search", {"role": "ROLE_ORGAN_OPERATER", "query": "户籍"}),
        ("system.snapshot", {"role": "ROLE_ORGAN_OPERATER"}),
    ]
    for skill, payload in turns:
        status, body = a2a_request("POST", f"{wire}/a2a/skills/{skill}/invoke", body=payload)
        assert status == 200, (skill, body)
        assert body["skill_id"] == skill
    # 三轮均可经 audit_event 追溯，且 source=a2a 贯穿
    for skill, _ in turns:
        rows = _audit_rows(skill)
        assert rows, f"{skill} 未落 audit"
        assert any((r.payload_json or {}).get("source") == "a2a" for r in rows)


# ── 场景3：trust 旋钮裁剪（部署级，非 per-caller）─────────────────────────────

def test_wire_trust_level_cuts_responsibility_bearing_write(wire: str) -> None:
    write_skill = "resource.mount.table.prepare"  # side_effects → 责任性写
    payload = {"resource_code": "res-a2a-1", "confirmed": True}

    # 默认 untrusted → 403 + reason
    os.environ.pop("ZW_BRAIN_A2A_CALLER_TRUST_LEVEL", None)
    status, body = a2a_request("POST", f"{wire}/a2a/skills/{write_skill}/invoke", body=payload)
    assert status == 403, body
    assert body["reason"] == "trust_level_insufficient"
    assert body["trust_level"] == "untrusted"

    # verified 清 trust 门（不再 403；下游成败与 trust 无关）
    os.environ["ZW_BRAIN_A2A_CALLER_TRUST_LEVEL"] = "verified"
    try:
        status2, body2 = a2a_request("POST", f"{wire}/a2a/skills/{write_skill}/invoke", body=payload)
        assert status2 != 403, body2
    finally:
        os.environ.pop("ZW_BRAIN_A2A_CALLER_TRUST_LEVEL", None)


# ── 场景4：投影一致性（a2a 与 mcp 同源 registry）─────────────────────────────

def test_a2a_mcp_projection_same_registry(wire: str) -> None:
    from zw_brain.entry.a2a.server import get_runtime_bindings
    from zw_brain.entry.mcp.server import list_tools

    a2a_names = {b["tool_name"] for b in get_runtime_bindings()}
    mcp_names = {t["name"] for t in list_tools()}
    assert a2a_names, "a2a 投影为空"
    assert mcp_names, "mcp 投影为空"
    # 同一 registry 派生：两投影应有大量共同 capability（如核心读能力同时暴露）
    common = a2a_names & mcp_names
    assert "data.search" in common
    assert len(common) >= 20
