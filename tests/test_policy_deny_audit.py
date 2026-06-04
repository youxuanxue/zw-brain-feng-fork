"""ops-deny-audit guard — 越权 deny 必须留审计痕（decision=deny），不再 traceless.

背景（D4 审计脊柱 / debt ops-deny-audit）：在此 PR 之前，policy 门 deny 在
``PolicyMiddleware`` 最外层抛 ``AccessDeniedError``，而审计发射在更内层的
``AuditEmitMiddleware``，故 deny **零审计事件**——越权尝试无痕。本 PR 在
``BrainService._enforce_manifest_policy``（读/写两路策略门的唯一收口点）统一发一条
``phase="error" / decision="deny"`` 审计事件，覆盖 5 消费面。

本测试是**跨切行为护栏**，刻意不绑任何 .feature（不进 feature 指纹轴），用一个已知的
受限只读能力 + 无权角色坐实：deny 仍抛 AccessDeniedError ∧ 恰好落一条 decision=deny 审计行。

非阻塞语义：deny 审计写失败仅告警、不改 deny→403 契约（「写失败是否熔断」是状态机决策，
待业务方 sign-off，本期不实现）——见 _enforce_manifest_policy 注释 + debt ops-deny-audit。
"""
from __future__ import annotations

import json
import os
import sqlite3
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import AccessDeniedError, BrainService
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.db import _CACHE_LOCK, _ENGINE_CACHE
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

# 已知受限只读能力 + 无权角色（同 test_wave0_ops_service_invocation S6 的 deny 事实）：
# ops.service.invocation.query 仅 MANAGER/BUSIAUDIT/SECURITY_AUDIT 可执行；OPERATER 必拒。
_RESTRICTED_SKILL = "ops.service.invocation.query"
_UNAUTHORIZED_ROLE = "ROLE_ORGAN_OPERATER"


@pytest.fixture
def brain():
    """Per-test BrainService bound to a fresh DB，audit sink 接真实 DatabaseStore。"""
    with TemporaryDirectory() as tmp:
        prev_path = os.environ.get("ZW_BRAIN_DB_PATH")
        prev_url = os.environ.get("ZW_BRAIN_DATABASE_URL")
        os.environ["ZW_BRAIN_DB_PATH"] = os.path.join(tmp, "deny_audit_brain.db")
        os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
        with _CACHE_LOCK:
            _ENGINE_CACHE.clear()
        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        try:
            yield BrainService(state_store=StateStore(database_store=database_store))
        finally:
            audit_bus.clear_sink()
            with _CACHE_LOCK:
                _ENGINE_CACHE.clear()
            if prev_path is None:
                os.environ.pop("ZW_BRAIN_DB_PATH", None)
            else:
                os.environ["ZW_BRAIN_DB_PATH"] = prev_path
            if prev_url is not None:
                os.environ["ZW_BRAIN_DATABASE_URL"] = prev_url


def _deny_rows(db_path: str) -> list[tuple[str, str, str]]:
    """所有 decision=deny 的 audit_event 行 (skill_id, phase, actor)。"""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT skill_id, phase, actor, payload_json FROM audit_event"
        ).fetchall()
    finally:
        conn.close()
    out: list[tuple[str, str, str]] = []
    for skill_id, phase, actor, payload_json in rows:
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except (TypeError, ValueError):
            payload = {}
        if payload.get("decision") == "deny":
            out.append((skill_id, phase, actor))
    return out


def test_policy_deny_emits_decision_deny_audit(brain: BrainService) -> None:
    """越权调用 → AccessDeniedError ∧ 恰好一条 decision=deny 审计行（之前为零）。"""
    db_path = os.environ["ZW_BRAIN_DB_PATH"]

    with pytest.raises(AccessDeniedError) as exc:
        invoke_trusted(brain, _RESTRICTED_SKILL, {"resource_code": "R-ANY"}, role=_UNAUTHORIZED_ROLE)
    assert _RESTRICTED_SKILL in str(exc.value)

    deny_rows = _deny_rows(db_path)
    assert len(deny_rows) == 1, f"deny 必须留恰好一条 decision=deny 审计行，got {deny_rows!r}"
    skill_id, phase, actor = deny_rows[0]
    assert skill_id == _RESTRICTED_SKILL, f"审计行 skill_id 应为被拒能力，got {skill_id!r}"
    assert phase == "error", f"deny 走 error phase（镜像 AuditEmitMiddleware error 形态），got {phase!r}"
    # 拒绝信息不泄漏 projection 数据（actor 是身份非数据）
    assert actor, "deny 审计行须带 actor 身份（谁尝试越权）"


def test_authorized_call_emits_no_deny_audit(brain: BrainService) -> None:
    """对照：授权角色调用 → 无 decision=deny 行（不误报）。"""
    db_path = os.environ["ZW_BRAIN_DB_PATH"]
    invoke_trusted(brain, _RESTRICTED_SKILL, {"resource_code": "R-ANY"}, role="ROLE_BUSIAUDIT")
    assert _deny_rows(db_path) == [], "授权调用不得产生 decision=deny 审计行"
