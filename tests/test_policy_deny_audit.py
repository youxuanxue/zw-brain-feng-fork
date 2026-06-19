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

import psycopg
import pytest
from sqlalchemy.engine import make_url

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import AccessDeniedError, BrainService
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.db import get_database_url
from zw_brain.shared.state_store import StateStore

# 已知受限只读能力 + 无权角色（同 test_wave0_ops_service_invocation S6 的 deny 事实）：
# ops.service.invocation.query 仅 MANAGER/BUSIAUDIT/SECURITY_AUDIT 可执行；OPERATER 必拒。
_RESTRICTED_SKILL = "ops.service.invocation.query"
_UNAUTHORIZED_ROLE = "ROLE_ORGAN_OPERATER"


@pytest.fixture
def brain():
    """Per-test BrainService，audit sink 接真实 DatabaseStore。

    DB 由 root conftest 的 per-test PG 克隆供给（每测一条干净的 PG 库；
    全盘去 SQLite 后审计落 ``public.audit_event`` 而非 sqlite 文件）。"""
    database_store = DatabaseStore()
    audit_bus.configure_sink(database_store.append_audit_event)
    try:
        yield BrainService(state_store=StateStore(database_store=database_store))
    finally:
        audit_bus.clear_sink()


def _deny_rows() -> list[tuple[str, str, str]]:
    """所有 decision=deny 的 audit_event 行 (skill_id, phase, actor)。

    PG 后端：审计落当前测试 PG 克隆的 ``audit_event`` 表，经 psycopg 直读回放
    （§9.5 裸 SQL 仅限只读测试断言、不在 adapters/legacy 外的业务路径）。"""
    sa_url = make_url(get_database_url())
    rows = []
    with psycopg.connect(
        host=sa_url.host, port=sa_url.port, dbname=sa_url.database,
        user=sa_url.username, password=sa_url.password,
    ) as conn:
        rows = conn.execute(
            "SELECT skill_id, phase, actor, payload_json FROM audit_event"
        ).fetchall()
    out: list[tuple[str, str, str]] = []
    for skill_id, phase, actor, payload_json in rows:
        # PG audit_event.payload_json 是 JSONB —— psycopg 回读已是 dict；
        # 兼容历史 TEXT 列（回读 str）走 json.loads。
        if isinstance(payload_json, dict):
            payload = payload_json
        else:
            try:
                payload = json.loads(payload_json) if payload_json else {}
            except (TypeError, ValueError):
                payload = {}
        if payload.get("decision") == "deny":
            out.append((skill_id, phase, actor))
    return out


def test_policy_deny_emits_decision_deny_audit(brain: BrainService) -> None:
    """越权调用 → AccessDeniedError ∧ 恰好一条 decision=deny 审计行（之前为零）。"""
    with pytest.raises(AccessDeniedError) as exc:
        invoke_trusted(brain, _RESTRICTED_SKILL, {"resource_code": "R-ANY"}, role=_UNAUTHORIZED_ROLE)
    assert _RESTRICTED_SKILL in str(exc.value)

    deny_rows = _deny_rows()
    assert len(deny_rows) == 1, f"deny 必须留恰好一条 decision=deny 审计行，got {deny_rows!r}"
    skill_id, phase, actor = deny_rows[0]
    assert skill_id == _RESTRICTED_SKILL, f"审计行 skill_id 应为被拒能力，got {skill_id!r}"
    assert phase == "error", f"deny 走 error phase（镜像 AuditEmitMiddleware error 形态），got {phase!r}"
    # 拒绝信息不泄漏 projection 数据（actor 是身份非数据）
    assert actor, "deny 审计行须带 actor 身份（谁尝试越权）"


def test_authorized_call_emits_no_deny_audit(brain: BrainService) -> None:
    """对照：授权角色调用 → 无 decision=deny 行（不误报）。"""
    invoke_trusted(brain, _RESTRICTED_SKILL, {"resource_code": "R-ANY"}, role="ROLE_BUSIAUDIT")
    assert _deny_rows() == [], "授权调用不得产生 decision=deny 审计行"
