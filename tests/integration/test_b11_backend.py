"""F3-backend integration tests — B1.1 4 panel 后端 capability + 调查摘要助手
(e4-b1-agentruntime)。

覆盖 supervisor 列的 6 个 case：
  (a) statistics 时间桶聚合（hour / day / week / month 四档）
  (b) anomaly Top-N 异常事件含跨租户读 + 高频失败 + repeated-denied 三类规则
  (c) accountability 按 actor 拉 denied 链 + 敏感字段 hash 化
  (d) investigation_summary 走 shared/inference/client mock 返回脱敏摘要
      （摘要 input 不含原始 actor/skill_id 字面值）
  (e) tenant_scope 越权 statistics/anomaly/accountability/summary 全部拦下
  (f) sd-default 真实 fixture e2e：statistics + anomaly + accountability +
      summary 端到端串一遍

不覆盖（F5 / E5 / E6 范围）：
  - B1.1 UI panel 截图
  - 真实集团推理平台 chat()（用 monkeypatch mock 拦截）
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from zw_brain.command.handlers.b1 import audit as audit_handlers
from zw_brain.command.handlers.b1 import investigation as inv_handlers
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.audit import store as audit_store_mod
from zw_brain.shared.audit.store import AuditStore, StoredAuditEvent

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROLE_MAPPING_FIXTURE = REPO_ROOT / "tests/fixtures/m0-sd-default/role-mapping-manifest.json"
TENANT = "sd-default"


def _store_sink(store: AuditStore):
    def _sink(request_id, actor, skill_id, phase, payload):
        store.append(
            StoredAuditEvent(
                request_id=request_id,
                actor=actor,
                skill_id=skill_id,
                tenant_id=str(payload.get("tenant_id") or TENANT),
                audit_class=str(payload.get("audit_class") or "read-sensitive"),
                event_type=str(payload.get("event_type") or "capability_call"),
                phase=phase,
                occurred_at=datetime.now(UTC),
                payload=payload,
            )
        )

    return _sink


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "audit.db"
    s = AuditStore(path=db)
    audit_store_mod.set_default_store(s)
    audit_bus.clear_sink()
    audit_bus.drain()
    audit_bus.configure_sink(_store_sink(s))
    yield s
    audit_bus.clear_sink()
    audit_bus.drain()
    audit_store_mod.set_default_store(None)


def _emit(*, request_id, actor, skill_id, phase, audit_class="write-normal", tenant=TENANT, payload=None):
    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id=request_id,
            actor=actor,
            skill_id=skill_id,
            phase=phase,
            payload=payload or {},
            tenant_id=tenant,
            audit_class=audit_class,
            event_type="capability_call",
        )
    )


# ---------------------------------------------------------------------------
# (a) statistics 时间桶聚合（4 档）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bucket", ["hour", "day", "week", "month"])
def test_statistics_time_bucket(store: AuditStore, bucket: str) -> None:
    for i in range(5):
        _emit(
            request_id=f"REQ-STAT-{i}",
            actor=f"actor-{i % 2}",
            skill_id="application.grant.approve",
            phase="commit",
            audit_class="write-critical",
        )

    out = audit_handlers.handler_audit_event_statistics(
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.statistics",
        payload={"bucket": bucket, "dimension": "audit_class", "tenant_id": TENANT, "limit": 1000},
    )
    assert out["bucket"] == bucket
    assert out["dimension"] == "audit_class"
    assert out["scanned"] == 5
    assert "write-critical" in out["totals"]
    assert out["totals"]["write-critical"] == 5
    assert len(out["buckets"]) >= 1
    assert sum(b["total"] for b in out["buckets"]) == 5


def test_statistics_dimension_actor(store: AuditStore) -> None:
    _emit(request_id="R-1", actor="alice", skill_id="application.grant.approve", phase="commit")
    _emit(request_id="R-2", actor="alice", skill_id="application.grant.approve", phase="commit")
    _emit(request_id="R-3", actor="bob", skill_id="application.grant.approve", phase="commit")

    out = audit_handlers.handler_audit_event_statistics(
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.statistics",
        payload={"dimension": "actor", "tenant_id": TENANT},
    )
    assert out["totals"] == {"alice": 2, "bob": 1}


# ---------------------------------------------------------------------------
# (b) anomaly: cross-tenant-read / high-failure-rate / repeated-denied
# ---------------------------------------------------------------------------


def test_anomaly_high_failure_rate(store: AuditStore) -> None:
    for i in range(4):
        _emit(
            request_id=f"REQ-FAIL-{i}",
            actor="user:gov:ROLE_ORGAN_OPERATER:attacker",
            skill_id="application.resource.review",
            phase="error",
            audit_class="write-critical",
            payload={"error": "DomainAccessDeniedError"},
        )

    out = audit_handlers.handler_audit_event_anomaly(
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.anomaly",
        payload={"tenant_id": TENANT, "min_failure_count": 3, "top_n": 20},
    )
    rules = [a["rule"] for a in out["anomalies"]]
    assert "high-failure-rate" in rules
    hit = next(a for a in out["anomalies"] if a["rule"] == "high-failure-rate")
    assert hit["occurrence_count"] == 4
    assert len(hit["evidence_request_ids"]) <= 5


def test_anomaly_repeated_denied(store: AuditStore) -> None:
    for i in range(3):
        _emit(
            request_id="REQ-DENY-LOOP",
            actor="actor-x",
            skill_id="application.grant.approve",
            phase="error",
            payload={"outcome": "denied", "attempt": i},
        )

    out = audit_handlers.handler_audit_event_anomaly(
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.anomaly",
        payload={"tenant_id": TENANT},
    )
    rules = [a["rule"] for a in out["anomalies"]]
    assert "repeated-denied" in rules
    hit = next(a for a in out["anomalies"] if a["rule"] == "repeated-denied")
    assert "REQ-DENY-LOOP" in hit["evidence_request_ids"]
    assert hit["occurrence_count"] == 3


def test_anomaly_cross_tenant_read(store: AuditStore) -> None:
    """同一 actor 在两个 tenant 上都有 read-sensitive 事件 → 触发跨租户读异常。"""
    _emit(
        request_id="R-CT-1",
        actor="actor-cross",
        skill_id="audit.event.query",
        phase="commit",
        audit_class="read-sensitive",
        tenant=TENANT,
    )
    # 直接写入 store（绕过 emit 的 tenant_scope 校验），模拟其他租户事件残留
    store.append(
        StoredAuditEvent(
            request_id="R-CT-2",
            actor="actor-cross",
            skill_id="audit.event.query",
            tenant_id="other-tenant",
            audit_class="read-sensitive",
            event_type="capability_call",
            phase="commit",
            occurred_at=datetime.now(UTC),
            payload={},
        )
    )

    out = audit_handlers.handler_audit_event_anomaly(
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.anomaly",
        payload={"tenant_id": TENANT},
    )
    rules = [a["rule"] for a in out["anomalies"]]
    assert "cross-tenant-read" in rules
    hit = next(a for a in out["anomalies"] if a["rule"] == "cross-tenant-read")
    assert hit["actor"] == "actor-cross"
    assert "sd-default" in hit["tenant_id"] and "other-tenant" in hit["tenant_id"]


# ---------------------------------------------------------------------------
# (c) accountability 按 actor 拉 denied 链 + 敏感字段 hash 化
# ---------------------------------------------------------------------------


def test_accountability_returns_denied_chains_sanitized(store: AuditStore) -> None:
    actor = "user:gov:ROLE_ORGAN_OPERATER:bad_user"
    secret_value = "AKIA-SUPER-SECRET-KEY-12345"
    _emit(
        request_id="REQ-DENY-A",
        actor=actor,
        skill_id="application.grant.approve",
        phase="before",
        payload={"step": "before", "credential": secret_value},
    )
    _emit(
        request_id="REQ-DENY-A",
        actor=actor,
        skill_id="application.grant.approve",
        phase="error",
        payload={"outcome": "denied", "reason": "rbac", "credential": secret_value},
    )
    _emit(
        request_id="REQ-DENY-B",
        actor=actor,
        skill_id="application.grant.revoke",
        phase="error",
        payload={"outcome": "denied", "api_key": secret_value},
    )

    out = audit_handlers.handler_audit_event_accountability(
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.accountability",
        payload={"actor": actor, "tenant_id": TENANT, "limit": 50},
    )
    assert out["actor"] == actor
    assert out["total"] == 2
    rids = {c["request_id"] for c in out["denied_chains"]}
    assert rids == {"REQ-DENY-A", "REQ-DENY-B"}

    # 敏感字段必须 hash 化
    flat = json.dumps(out, ensure_ascii=False)
    assert secret_value not in flat, "accountability 不允许外泄 credential / api_key 原文"
    chain_a = next(c for c in out["denied_chains"] if c["request_id"] == "REQ-DENY-A")
    payloads = [ev["sanitized_payload"] for ev in chain_a["events"]]
    cred_values = [p.get("credential") for p in payloads if "credential" in p]
    assert all(v and v.startswith("sha1:") for v in cred_values)


# ---------------------------------------------------------------------------
# (d) investigation_summary 走 inference mock，输出脱敏
# ---------------------------------------------------------------------------


def test_investigation_summary_uses_inference_client_and_sanitizes(monkeypatch, store: AuditStore) -> None:
    captured_messages: list[Any] = []

    def _mock_chat(messages, *, model, request_id, **kwargs):
        captured_messages.extend(messages)
        from zw_brain.shared.inference.client import ChatResult

        return ChatResult(
            text="安全审计员摘要：本窗口共观察到 1 项 high-severity 异常",
            model="claude-sonnet-4-7-mock",
            usage={"prompt_tokens": 64, "completion_tokens": 32, "total_tokens": 96},
            finish_reason="stop",
        )

    monkeypatch.setattr(inv_handlers.inference_client, "chat", _mock_chat)

    panel_payload = {
        "anomalies": [
            {
                "actor": "user:gov:ROLE_ORGAN_OPERATER:bad_user",
                "skill_id": "application.grant.approve",
                "tenant_id": TENANT,
                "rule": "high-failure-rate",
                "occurrence_count": 5,
                "evidence_request_ids": ["REQ-1", "REQ-2"],
            }
        ]
    }

    out = inv_handlers.handler_assistant_investigation_summary(
        brain=None,  # type: ignore[arg-type]
        skill_id="assistant.investigation_summary",
        payload={
            "request_id": "REQ-INV-001",
            "panel": "anomaly",
            "panel_payload": panel_payload,
            "tenant_id": TENANT,
        },
    )
    assert "high-severity" in out["summary"]
    assert out["model"] == "claude-sonnet-4-7-mock"
    assert re.fullmatch(r"[0-9a-f]{40}", out["sanitized_input_digest"])

    # 推送给推理平台的 user message 不能含原始敏感字面值
    user_msg = next(m for m in captured_messages if m.role == "user")
    assert "bad_user" not in user_msg.content
    assert "application.grant.approve" not in user_msg.content
    assert "REQ-1" not in user_msg.content
    assert "sha1:" in user_msg.content, "脱敏后应保留 sha1: 占位符"


# ---------------------------------------------------------------------------
# (e) tenant_scope 越权全 panel 拦下
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn,kwargs",
    [
        (audit_handlers.handler_audit_event_statistics, {"skill_id": "audit.event.statistics", "payload": {"tenant_id": "other"}}),
        (audit_handlers.handler_audit_event_anomaly, {"skill_id": "audit.event.anomaly", "payload": {"tenant_id": "other"}}),
        (audit_handlers.handler_audit_event_accountability, {"skill_id": "audit.event.accountability", "payload": {"actor": "x", "tenant_id": "other"}}),
        (inv_handlers.handler_assistant_investigation_summary, {"skill_id": "assistant.investigation_summary", "payload": {"request_id": "R", "panel": "anomaly", "panel_payload": {}, "tenant_id": "other"}}),
    ],
)
def test_cross_tenant_access_is_denied_across_all_b11_handlers(store: AuditStore, fn, kwargs) -> None:
    with pytest.raises(DomainAccessDeniedError):
        fn(brain=None, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# (f) sd-default fixture e2e — statistics + anomaly + accountability + summary
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not ROLE_MAPPING_FIXTURE.exists(),
    reason="sd-default role-mapping fixture not present",
)
def test_sd_default_e2e_b11_full_panel_chain(monkeypatch, store: AuditStore) -> None:
    manifest = json.loads(ROLE_MAPPING_FIXTURE.read_text(encoding="utf-8"))
    rows = manifest["rows"][:6]
    assert manifest["tenant_id"] == TENANT

    review_actor = "user:gov:ROLE_BUSIAUDIT:平台主管部门"
    operator_actor = "user:gov:ROLE_ORGAN_OPERATER:申请人"
    skill = "governance.policy_candidate.review"

    # 半数 row 成功 → write-critical commit；另一半 → denied error，制造 high-failure-rate
    for i, row in enumerate(rows):
        rid = f"REQ-SD-E2E-{i:03d}"
        _emit(
            request_id=rid,
            actor=review_actor if i % 2 == 0 else operator_actor,
            skill_id=skill,
            phase="commit" if i % 2 == 0 else "error",
            audit_class="write-critical",
            payload={
                "legacy_role_ref": row["legacy_role_ref"],
                "target_role_code": row["target_role_code"],
                "outcome": "approved" if i % 2 == 0 else "denied",
            },
        )

    # statistics by skill
    stats = audit_handlers.handler_audit_event_statistics(
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.statistics",
        payload={"bucket": "day", "dimension": "skill_id", "tenant_id": TENANT},
    )
    assert stats["totals"].get(skill) == len(rows)

    # anomaly: should detect high-failure-rate（operator 3 次 denied 达阈值）
    anomaly = audit_handlers.handler_audit_event_anomaly(
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.anomaly",
        payload={"tenant_id": TENANT, "min_failure_count": 3, "top_n": 10},
    )
    high_failure = [a for a in anomaly["anomalies"] if a["rule"] == "high-failure-rate"]
    assert len(high_failure) >= 1
    assert any(operator_actor in a["actor"] for a in high_failure)

    # accountability: denied 链
    account = audit_handlers.handler_audit_event_accountability(
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.accountability",
        payload={"actor": operator_actor, "tenant_id": TENANT},
    )
    assert account["total"] >= 1
    assert all(c["request_id"].startswith("REQ-SD-E2E-") for c in account["denied_chains"])

    # summary: mock inference, 验证 panel 输入脱敏 + 摘要回流
    def _mock_chat(messages, *, model, request_id, **kwargs):
        from zw_brain.shared.inference.client import ChatResult

        return ChatResult(
            text="sd-default 窗口摘要：发现一类 high-failure-rate 异常 + 多条 denied 链",
            model="claude-sonnet-4-7-mock",
            usage={"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
        )

    monkeypatch.setattr(inv_handlers.inference_client, "chat", _mock_chat)
    summary = inv_handlers.handler_assistant_investigation_summary(
        brain=None,  # type: ignore[arg-type]
        skill_id="assistant.investigation_summary",
        payload={
            "request_id": "REQ-SD-INV-001",
            "panel": "anomaly",
            "panel_payload": anomaly,
            "tenant_id": TENANT,
        },
    )
    assert "sd-default" in summary["summary"]

    # 验证 4 个 handler 都写了 meta-audit
    meta_skills = {
        "audit.event.statistics",
        "audit.event.anomaly",
        "audit.event.accountability",
        "assistant.investigation_summary",
    }
    written = {ev.skill_id for ev in store.query(limit=1000) if ev.skill_id in meta_skills}
    assert written == meta_skills
