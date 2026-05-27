"""F2 integration tests — audit.event.query / audit.event.replay capability + 真实
sd-default 审批链 e2e（e4-b1-agentruntime）。

覆盖 supervisor 列的 4 个必备 case：
  (a) 单租户 query by actor / skill / time window
  (b) cross-tenant query 必须被 tenant_scope 拦下
  (c) list_by_request_id 返回完整 phase 序列
  (d) 真实 sd-default fixture multi-phase 审批链端到端 emit → replay 出完整
      phase 序列

不覆盖（F3/E5/M0 范围）：
  - B1.1 panel UI / 调查摘要 AI 助手
  - runtime get_service() 真正拉起；本测试直接用 audit_bus.configure_sink
    + AuditStore 模拟 multiplex sink 的下半（DB 落库部分不需要，handler 不
    读 DB）
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests._handler_call import call_handler
from zw_brain.command.handlers.b1 import audit as audit_handlers
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.audit import store as audit_store_mod
from zw_brain.shared.audit.store import AuditStore, StoredAuditEvent

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROLE_MAPPING_FIXTURE = REPO_ROOT / "tests/fixtures/m0-sd-default/role-mapping-manifest.json"
TENANT = "sd-default"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _store_sink(store: AuditStore):
    """5-tuple sink wired to AuditStore（与 runtime.py multiplex sink 下半同形态）。"""

    def _sink(request_id: str, actor: str, skill_id: str, phase: str, payload: dict[str, Any]) -> None:
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
    """每个测试一个干净的 AuditStore，作为 default store 注入。"""
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


def _seed_chain(*, request_id: str, actor: str, skill_id: str, phases: list[str], audit_class: str = "write-critical", tenant: str = TENANT) -> None:
    for phase in phases:
        audit_bus.emit(
            audit_bus.AuditEvent(
                request_id=request_id,
                actor=actor,
                skill_id=skill_id,
                phase=phase,
                payload={"phase": phase, "skill_id": skill_id, "note": f"e2e {phase}"},
                tenant_id=tenant,
                audit_class=audit_class,
                event_type="capability_call",
            )
        )


# ---------------------------------------------------------------------------
# (a) tenant query by actor / skill / time window
# ---------------------------------------------------------------------------


def test_query_by_actor_skill_and_time_window(store: AuditStore) -> None:
    _seed_chain(
        request_id="REQ-Q-001",
        actor="user:gov:ROLE_SECURITY_AUDIT:安全审计员",
        skill_id="governance.policy_candidate.review",
        phases=["before", "commit", "after"],
        audit_class="write-critical",
    )
    _seed_chain(
        request_id="REQ-Q-002",
        actor="user:gov:ROLE_ORGAN_MANAGER:部门管理员",
        skill_id="application.grant.approve",
        phases=["before", "commit", "after"],
        audit_class="write-critical",
    )

    # by actor
    out = call_handler(audit_handlers.handler_audit_event_query,
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.query",
        payload={
            "actor": "user:gov:ROLE_SECURITY_AUDIT:安全审计员",
            "tenant_id": TENANT,
            "limit": 100,
        },
    )
    assert {ev["request_id"] for ev in out["items"]} == {"REQ-Q-001"}
    assert all(ev["actor"].endswith("安全审计员") for ev in out["items"])
    assert "payload" not in out["items"][0], "F2 query 不应外泄 payload 原文"
    assert out["summary"]["total"] == 3
    assert out["summary"]["by_skill"]["governance.policy_candidate.review"] == 3

    # by skill
    out = call_handler(audit_handlers.handler_audit_event_query,
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.query",
        payload={
            "skill_id": "application.grant.approve",
            "tenant_id": TENANT,
            "limit": 100,
        },
    )
    assert {ev["request_id"] for ev in out["items"]} == {"REQ-Q-002"}

    # time window: future since → empty
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    out = call_handler(audit_handlers.handler_audit_event_query,
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.query",
        payload={"tenant_id": TENANT, "since": later, "limit": 100},
    )
    assert out["items"] == []


def test_query_emits_meta_audit_with_sanitized_payload(store: AuditStore) -> None:
    """F2 contract：handler 自身写一条元审计；payload 只含 param_hash + result_count。"""
    _seed_chain(
        request_id="REQ-META-1",
        actor="user:gov:ROLE_SECURITY_AUDIT:安全审计员",
        skill_id="application.grant.approve",
        phases=["commit"],
        audit_class="write-critical",
    )

    call_handler(audit_handlers.handler_audit_event_query,
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.query",
        payload={
            "actor": "user:gov:ROLE_SECURITY_AUDIT:安全审计员",
            "tenant_id": TENANT,
            "limit": 10,
        },
    )

    meta_events = [
        ev for ev in store.query(skill_id="audit.event.query", limit=10)
    ]
    assert len(meta_events) >= 1
    meta = meta_events[-1]
    assert meta.audit_class == "read-sensitive"
    assert meta.skill_id == "audit.event.query"
    assert meta.event_type == "audit_query"
    assert set(meta.payload.keys()) >= {"param_hash", "result_count", "skill_id"}
    # 不允许把原始查询参数（actor 值）写到元审计里
    payload_text = json.dumps(meta.payload, ensure_ascii=False)
    assert "ROLE_SECURITY_AUDIT" not in payload_text or "安全审计员" not in payload_text


# ---------------------------------------------------------------------------
# (b) cross-tenant query must be rejected
# ---------------------------------------------------------------------------


def test_cross_tenant_query_is_denied(store: AuditStore) -> None:
    with pytest.raises(DomainAccessDeniedError):
        call_handler(audit_handlers.handler_audit_event_query,
        brain=None,  # type: ignore[arg-type]
            skill_id="audit.event.query",
            payload={"tenant_id": "other-tenant"},
        )


def test_cross_tenant_replay_is_denied(store: AuditStore) -> None:
    with pytest.raises(DomainAccessDeniedError):
        call_handler(audit_handlers.handler_audit_event_replay,
        brain=None,  # type: ignore[arg-type]
            skill_id="audit.event.replay",
            payload={"request_id": "REQ-X", "tenant_id": "other-tenant"},
        )


def test_omitted_tenant_id_falls_back_to_runtime_tenant(store: AuditStore) -> None:
    """单租户 sd-default 模式：调用方不传 tenant_id 自动收敛到 runtime tenant。"""
    _seed_chain(
        request_id="REQ-FALLBACK",
        actor="actor-1",
        skill_id="application.grant.approve",
        phases=["commit"],
    )
    out = call_handler(audit_handlers.handler_audit_event_query,
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.query",
        payload={},
    )
    assert len(out["items"]) >= 1
    assert all(ev["tenant_id"] == TENANT for ev in out["items"])


# ---------------------------------------------------------------------------
# (c) list_by_request_id returns full phase sequence
# ---------------------------------------------------------------------------


def test_replay_returns_full_phase_sequence(store: AuditStore) -> None:
    _seed_chain(
        request_id="REQ-CHAIN-001",
        actor="user:gov:ROLE_BUSIAUDIT:平台主管部门",
        skill_id="governance.policy_candidate.review",
        phases=["before", "commit", "after"],
        audit_class="write-critical",
    )

    out = call_handler(audit_handlers.handler_audit_event_replay,
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.replay",
        payload={"request_id": "REQ-CHAIN-001", "tenant_id": TENANT},
    )
    assert out["request_id"] == "REQ-CHAIN-001"
    phases_in_order = [ev["phase"] for ev in out["items"]]
    assert phases_in_order == ["before", "commit", "after"]
    # replay 与 query 不同：必须透传 payload 给 caller（安全审计员需要看原文）
    assert all("payload" in ev for ev in out["items"])
    assert out["items"][0]["payload"]["note"] == "e2e before"
    assert out["summary"]["total"] == 3
    assert out["summary"]["by_audit_class"]["write-critical"] == 3


def test_replay_rejects_empty_request_id(store: AuditStore) -> None:
    with pytest.raises(ValueError):
        call_handler(audit_handlers.handler_audit_event_replay,
        brain=None,  # type: ignore[arg-type]
            skill_id="audit.event.replay",
            payload={"request_id": "   ", "tenant_id": TENANT},
        )


def test_replay_filters_cross_tenant_events_in_chain(store: AuditStore) -> None:
    """若同一 request_id 在不同 tenant 都有事件（攻击场景），replay 只返回本租户的。"""
    _seed_chain(
        request_id="REQ-MIXED",
        actor="actor-a",
        skill_id="application.grant.approve",
        phases=["before", "commit", "after"],
        tenant=TENANT,
    )
    # 伪造另一租户的同 request_id 事件（实际系统不允许，但 store 层不校验）
    store.append(
        StoredAuditEvent(
            request_id="REQ-MIXED",
            actor="attacker",
            skill_id="application.grant.approve",
            tenant_id="other-tenant",
            audit_class="write-critical",
            event_type="capability_call",
            phase="commit",
            occurred_at=datetime.now(UTC),
            payload={"injected": True},
        )
    )

    out = call_handler(audit_handlers.handler_audit_event_replay,
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.replay",
        payload={"request_id": "REQ-MIXED", "tenant_id": TENANT},
    )
    # 攻击者注入的跨租户事件必须被过滤掉
    assert all(ev["tenant_id"] == TENANT for ev in out["items"])
    assert not any(ev["actor"] == "attacker" for ev in out["items"])
    assert len(out["items"]) == 3


# ---------------------------------------------------------------------------
# (d) sd-default 真实 fixture e2e — multi-phase 审批链
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not ROLE_MAPPING_FIXTURE.exists(),
    reason="sd-default role-mapping fixture not present on this checkout",
)
def test_sd_default_real_approval_chain_e2e(store: AuditStore) -> None:
    """以 sd-default 真实 role-mapping-manifest 作为审批源；模拟 governance.
    policy_candidate.review 对前 5 个 legacy_role_ref 做的批量审批：
      每条 legacy_role_ref → 5 phase 序列 (before / validate / commit /
      anchor_enqueued / after)。
    端到端：emit 全部 phase → 通过 audit.event.replay 拉回 → 验证 phase 顺序 +
    内容 + 元审计写入。
    """
    manifest = json.loads(ROLE_MAPPING_FIXTURE.read_text(encoding="utf-8"))
    rows = manifest["rows"]
    assert manifest["tenant_id"] == TENANT
    sample = rows[:5]
    assert len(sample) >= 3, "fixture 至少 3 条才足够 multi-phase 端到端"

    actor = "user:gov:ROLE_BUSIAUDIT:平台主管部门"
    skill_id = "governance.policy_candidate.review"

    request_ids: list[str] = []
    expected_phases = ["before", "validate", "commit", "anchor_enqueued", "after"]
    for i, row in enumerate(sample):
        request_id = f"REQ-SD-GOV-{i:03d}"
        request_ids.append(request_id)
        for phase in expected_phases:
            audit_bus.emit(
                audit_bus.AuditEvent(
                    request_id=request_id,
                    actor=actor,
                    skill_id=skill_id,
                    phase=phase,
                    payload={
                        "legacy_role_ref": row["legacy_role_ref"],
                        "target_role_code": row["target_role_code"],
                        "confidence": row["confidence"],
                        "phase": phase,
                    },
                    tenant_id=TENANT,
                    audit_class="write-critical",
                    event_type="package_lifecycle",
                )
            )

    # 逐条 replay 验证 phase 序列完整
    for rid, row in zip(request_ids, sample, strict=False):
        out = call_handler(audit_handlers.handler_audit_event_replay,
        brain=None,  # type: ignore[arg-type]
            skill_id="audit.event.replay",
            payload={"request_id": rid, "tenant_id": TENANT, "limit": 100},
        )
        assert out["request_id"] == rid
        assert [ev["phase"] for ev in out["items"]] == expected_phases
        assert all(ev["actor"] == actor for ev in out["items"])
        assert all(ev["skill_id"] == skill_id for ev in out["items"])
        assert out["items"][0]["payload"]["legacy_role_ref"] == row["legacy_role_ref"]
        assert out["summary"]["total"] == len(expected_phases)

    # 聚合 query：按 skill 拉所有 commit phase 的事件
    out_query = call_handler(audit_handlers.handler_audit_event_query,
        brain=None,  # type: ignore[arg-type]
        skill_id="audit.event.query",
        payload={
            "skill_id": skill_id,
            "tenant_id": TENANT,
            "audit_class": "write-critical",
            "limit": 1000,
        },
    )
    assert out_query["summary"]["total"] == len(sample) * len(expected_phases)
    assert out_query["summary"]["by_actor"][actor] == len(sample) * len(expected_phases)

    # 元审计：query + 5 次 replay = 6 次 audit.event.* 调用 → 6 条元审计
    meta = store.query(skill_id="audit.event.query", limit=100) + store.query(
        skill_id="audit.event.replay", limit=100
    )
    assert len(meta) >= len(sample) + 1
