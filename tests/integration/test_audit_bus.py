"""F1 integration tests — audit bus production event stream (e4-b1-agentruntime).

覆盖：
  - 3 级 audit_class（write-critical / write-normal / read-sensitive）写后可按
    actor / skill_id / tenant_id / audit_class 回查
  - 历史 audit_class enum 映射规范化 + 原值留底
  - store 写失败硬熔断（D4「审计写入失败必须熔断」）
  - sd-default 真实角色映射 fixture 端到端 emit → store → query

不覆盖（F2 / F3 / E6 范围，本测试不预拉时序）：
  - audit.event.query / audit.event.replay capability
  - B1.1 panel UI / 调查摘要助手
  - 区块链锚定真实链路
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from zw_brain.shared import audit as audit_bus
from zw_brain.shared.audit import index as audit_index
from zw_brain.shared.audit.store import (
    CANONICAL_AUDIT_CLASSES,
    AuditStore,
    AuditWriteError,
    StoredAuditEvent,
    normalize_audit_class,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROLE_MAPPING_FIXTURE = REPO_ROOT / "tests/fixtures/m0-sd-default/role-mapping-manifest.json"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _store_sink(store: AuditStore):
    """Return a 5-tuple sink callable that forwards to AuditStore.append.

    与 runtime.configure_sink(database_store.append_audit_event) 同形态。"""

    def _sink(request_id: str, actor: str, skill_id: str, phase: str, payload: dict[str, Any]) -> None:
        store.append(
            StoredAuditEvent(
                request_id=request_id,
                actor=actor,
                skill_id=skill_id,
                tenant_id=str(payload.get("tenant_id") or "sd-default"),
                audit_class=str(payload.get("audit_class") or "read-sensitive"),
                event_type=str(payload.get("event_type") or "capability_call"),
                phase=phase,
                occurred_at=datetime.now(UTC),
                payload=payload,
            )
        )

    return _sink


@pytest.fixture
def store(tmp_path) -> AuditStore:
    """每个测试一个干净的 SQLite 文件 store。"""
    db = tmp_path / "audit.db"
    s = AuditStore(path=db)
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _reset_audit_bus():
    audit_bus.clear_sink()
    audit_bus.drain()
    yield
    audit_bus.clear_sink()
    audit_bus.drain()


# ---------------------------------------------------------------------------
# (a) 3 级各写一条 + index.query 按多维度回查
# ---------------------------------------------------------------------------


def test_three_level_roundtrip_by_actor_skill_tenant(store: AuditStore) -> None:
    audit_bus.configure_sink(_store_sink(store))

    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id="REQ-WC-001",
            actor="ROLE_ORGAN_MANAGER",
            skill_id="application.grant.approve",
            phase="commit",
            payload={"decision": "approved"},
            tenant_id="sd-default",
            audit_class="write-critical",
            event_type="capability_call",
        )
    )
    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id="REQ-WN-002",
            actor="ROLE_ORGAN_OPERATER",
            skill_id="adapter.health.probe",
            phase="commit",
            payload={"endpoint": "iaf"},
            tenant_id="sd-default",
            audit_class="write-normal",
            event_type="capability_call",
        )
    )
    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id="REQ-RS-003",
            actor="ROLE_SECURITY_AUDIT",
            skill_id="audit.list",
            phase="commit",
            payload={"page": 1},
            tenant_id="sd-default",
            audit_class="read-sensitive",
            event_type="capability_call",
        )
    )

    assert store.count() == 3

    by_actor = audit_index.query(store=store, actor="ROLE_SECURITY_AUDIT")
    assert len(by_actor) == 1
    assert by_actor[0].request_id == "REQ-RS-003"
    assert by_actor[0].audit_class == "read-sensitive"

    by_skill = audit_index.query(store=store, skill_id="adapter.health.probe")
    assert len(by_skill) == 1
    assert by_skill[0].actor == "ROLE_ORGAN_OPERATER"

    by_tenant = audit_index.query(store=store, tenant_id="sd-default")
    assert len(by_tenant) == 3

    by_class = audit_index.query(store=store, audit_class="write-critical")
    assert len(by_class) == 1
    assert by_class[0].request_id == "REQ-WC-001"

    # 三级 enum 完整覆盖
    seen_classes = {ev.audit_class for ev in audit_index.query(store=store, tenant_id="sd-default")}
    assert seen_classes == set(CANONICAL_AUDIT_CLASSES)


def test_query_time_range_and_limit(store: AuditStore) -> None:
    audit_bus.configure_sink(_store_sink(store))
    base = datetime.now(UTC)

    for i in range(5):
        audit_bus.emit(
            audit_bus.AuditEvent(
                request_id=f"REQ-T-{i}",
                actor="actor-1",
                skill_id="audit.list",
                phase="commit",
                payload={"i": i},
                tenant_id="sd-default",
                audit_class="read-sensitive",
            )
        )

    all_events = audit_index.query(store=store, actor="actor-1")
    assert len(all_events) == 5

    limited = audit_index.query(store=store, actor="actor-1", limit=2)
    assert len(limited) == 2

    one_hour_later = base + timedelta(hours=1)
    in_future = audit_index.query(store=store, since=one_hour_later)
    assert in_future == []


def test_summarize_aggregates(store: AuditStore) -> None:
    audit_bus.configure_sink(_store_sink(store))
    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id="R-1", actor="a", skill_id="s1", phase="commit",
            tenant_id="sd-default", audit_class="write-critical",
        )
    )
    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id="R-2", actor="a", skill_id="s1", phase="commit",
            tenant_id="sd-default", audit_class="write-critical",
        )
    )
    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id="R-3", actor="b", skill_id="s2", phase="commit",
            tenant_id="sd-default", audit_class="read-sensitive",
        )
    )

    summary = audit_index.summarize(audit_index.query(store=store))
    assert summary["total"] == 3
    assert summary["by_audit_class"]["write-critical"] == 2
    assert summary["by_audit_class"]["read-sensitive"] == 1
    assert summary["by_skill"]["s1"] == 2
    assert summary["by_actor"]["a"] == 2
    assert summary["first_occurred_at"] is not None
    assert summary["last_occurred_at"] is not None


# ---------------------------------------------------------------------------
# (b) store 写失败硬熔断（D4）
# ---------------------------------------------------------------------------


def test_store_write_failure_circuit_breaks(tmp_path) -> None:
    """sqlite IntegrityError / OperationalError / DiskFull 都必须升级为 AuditWriteError 上抛。"""

    class _BrokenStore(AuditStore):
        def append(self, event):  # type: ignore[override]
            raise sqlite3.OperationalError("disk full")

    broken = _BrokenStore(path=tmp_path / "broken.db")

    def _sink_via_broken(rid, actor, sid, phase, payload):
        broken.append(
            StoredAuditEvent(
                request_id=rid, actor=actor, skill_id=sid,
                tenant_id="sd-default", audit_class="write-critical",
                event_type="capability_call", phase=phase,
                occurred_at=datetime.now(UTC), payload=payload,
            )
        )

    audit_bus.configure_sink(_sink_via_broken)
    with pytest.raises(AuditWriteError):
        audit_bus.emit(
            audit_bus.AuditEvent(
                request_id="REQ-BREAK", actor="actor-1", skill_id="application.grant.approve",
                phase="commit", audit_class="write-critical", tenant_id="sd-default",
            )
        )
    broken.close()


def test_store_missing_fields_raises(store: AuditStore) -> None:
    with pytest.raises(AuditWriteError):
        store.append(
            StoredAuditEvent(
                request_id="", actor="a", skill_id="s",
                tenant_id="sd-default", audit_class="read-sensitive",
                event_type="capability_call", phase="commit",
                occurred_at=datetime.now(UTC), payload={},
            )
        )


def test_store_non_serializable_payload_raises(store: AuditStore) -> None:
    # 循环引用：json.dumps 会 raise ValueError；store 必须升级为 AuditWriteError
    cycle: dict[str, Any] = {}
    cycle["self"] = cycle
    with pytest.raises(AuditWriteError):
        store.append(
            StoredAuditEvent(
                request_id="REQ-CYCLE", actor="a", skill_id="s",
                tenant_id="sd-default", audit_class="read-sensitive",
                event_type="capability_call", phase="commit",
                occurred_at=datetime.now(UTC), payload=cycle,
            )
        )


# ---------------------------------------------------------------------------
# (c) 历史 audit_class enum 映射规范化
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("write-critical", "write-critical"),
        ("adapter-write", "write-critical"),
        ("external-execution", "write-critical"),
        ("write-normal", "write-normal"),
        ("write-default", "write-normal"),
        ("read-sensitive", "read-sensitive"),
        ("read-default", "read-sensitive"),
        ("read-normal", "read-sensitive"),
        ("read-trace", "read-sensitive"),
        ("read", "read-sensitive"),
        ("totally-unknown-class", "read-sensitive"),
        ("", "read-sensitive"),
        (None, "read-sensitive"),
    ],
)
def test_normalize_audit_class_mapping(raw, expected) -> None:
    assert normalize_audit_class(raw) == expected


def test_emit_normalizes_and_preserves_original(store: AuditStore) -> None:
    """当 audit_class=read-trace（历史值）入 emit 时：
      - sink 收到的 payload[audit_class] = "read-sensitive"
      - sink 收到的 payload[original_audit_class] = "read-trace"
      - store 里查到的 audit_class 是 read-sensitive
    """
    audit_bus.configure_sink(_store_sink(store))
    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id="REQ-NORM-1",
            actor="actor-x",
            skill_id="audit.list",
            phase="commit",
            payload={},
            tenant_id="sd-default",
            audit_class="read-trace",
        )
    )

    events = audit_index.query(store=store, request_id="REQ-NORM-1")
    assert len(events) == 1
    ev = events[0]
    assert ev.audit_class == "read-sensitive"
    assert ev.payload["original_audit_class"] == "read-trace"


def test_store_append_normalizes_when_called_directly(store: AuditStore) -> None:
    """store.append 不经过 emit 时也必须自己 normalize（防御层）。"""
    store.append(
        StoredAuditEvent(
            request_id="REQ-DIRECT-1", actor="actor-y", skill_id="audit.list",
            tenant_id="sd-default", audit_class="adapter-write",
            event_type="capability_call", phase="commit",
            occurred_at=datetime.now(UTC), payload={"raw": "x"},
        )
    )
    events = store.query(request_id="REQ-DIRECT-1")
    assert len(events) == 1
    assert events[0].audit_class == "write-critical"
    assert events[0].payload["original_audit_class"] == "adapter-write"


# ---------------------------------------------------------------------------
# (d) sd-default 真实角色映射 fixture e2e
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not ROLE_MAPPING_FIXTURE.exists(),
    reason="sd-default role mapping fixture not present on this checkout",
)
def test_sd_default_real_role_mapping_audit_roundtrip(store: AuditStore) -> None:
    """以 sd-default 真实 role-mapping-manifest（73 legacy ROLE_* → 6 产品角色）作为
    审计事件源；模拟一次 governance.policy_candidate.review 批量审批，每条
    legacy_role_ref 一条审计事件，端到端 emit → store → query 回放。

    选择该 fixture 是因为它就是 sd-default 现场实际下发的 manifest 内容
    （tenant_id=sd-default, manifest_version=m0-sd-default-v1），与 AC1
    「真实 sd-default 审计事件回放」要求一致。
    """
    manifest = json.loads(ROLE_MAPPING_FIXTURE.read_text(encoding="utf-8"))
    rows = manifest["rows"]
    assert manifest["tenant_id"] == "sd-default"
    assert len(rows) > 0, "fixture must contain at least one role mapping row"

    audit_bus.configure_sink(_store_sink(store))
    request_id = "REQ-GOV-REVIEW-001"
    actor = "ROLE_SECURITY_AUDIT"
    skill_id = "governance.policy_candidate.review"

    for i, row in enumerate(rows):
        audit_bus.emit(
            audit_bus.AuditEvent(
                request_id=request_id,
                actor=actor,
                skill_id=skill_id,
                phase=f"row-{i}",
                payload={
                    "legacy_role_ref": row["legacy_role_ref"],
                    "target_role_code": row["target_role_code"],
                    "confidence": row["confidence"],
                    "decision": "approve_and_apply",
                },
                tenant_id="sd-default",
                audit_class="write-critical",
                event_type="package_lifecycle",
            )
        )

    chain = audit_index.list_by_request_id(request_id, store=store, limit=10_000)
    assert len(chain) == len(rows)
    assert all(ev.audit_class == "write-critical" for ev in chain)
    assert all(ev.tenant_id == "sd-default" for ev in chain)
    assert all(ev.skill_id == skill_id for ev in chain)
    # 真实回放：第一条 legacy_role_ref 还原
    assert chain[0].payload["legacy_role_ref"] == rows[0]["legacy_role_ref"]
    # 端到端聚合 stats（B1.1 panel 预聚合形态）
    summary = audit_index.summarize(chain)
    assert summary["total"] == len(rows)
    assert summary["by_actor"][actor] == len(rows)
    assert summary["by_audit_class"]["write-critical"] == len(rows)


# ---------------------------------------------------------------------------
# default store singleton helpers
# ---------------------------------------------------------------------------


def test_default_store_lazy_init(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_AUDIT_DB_PATH", str(tmp_path / "default.db"))
    from zw_brain.shared.audit import store as audit_store_mod

    # 强制重新初始化 default store
    audit_store_mod.set_default_store(None)
    s = audit_store_mod.get_default_store()
    assert Path(s.path) == tmp_path / "default.db"
    assert (tmp_path / "default.db").exists()
    audit_store_mod.set_default_store(None)
