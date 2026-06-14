# Wave: 1
# Journey: J1
# Pages: P5 (provider inbox) / B1 (业务运营员工作台督办队列)
# Consumer-faces: API (brain.invoke_skill) + domain projection
# Roles: ROLE_ORGAN_OPERATER (申请方) | ROLE_BUSIAUDIT (业务运营员，督办) | ROLE_ORGAN_MANAGER
# Trace:
#   .testing/waves/wave-1-j1-j2-closed-loop/features/j1-objection-authz.feature:46
#     「O501 升级到 BUSIAUDIT 督查队列（不是改 status 而是新增 escalate 事件）」
#   zw_brain/command/handlers/j1/objection.py (escalate 事件式 / assign 合法目标派生)
#   zw_brain/domain/repositories/objection.py (list_supervised_cases / is_supervised)
#   zw_brain/domain/workbench_backlog_projection.py (业务运营员「待督办」队列)
"""异议升级事件式闭环回归 — escalate 不改 status / 督办事件落库 / 督办队列可见 / assign 合法目标.

事件式升级（对齐已签 j1-objection-authz.feature:46）：escalate 不再 _transition 到
"escalated"（对 5 业务维度必 409，对 generic 维度则污染主 status），改为 emit 一条
escalate 过程事件 + 进 业务运营员（ROLE_BUSIAUDIT）督办队列。assign 不再默认非法的
provider_investigating，按维度+当前态派生合法落点（仿 D57 accept 机械修）。

隔离策略：fresh temp DB（ensure_runtime_schema 建表，无 seed）。本测试验事件机制，
不依赖真实 dump 数据，故不走 require_real_seed。
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.shared import db as db_module

DIMENSIONS = ("catalog", "content", "use", "resource", "authz")

# 维度 → mapper 落库的 evidence_type（与 objection_state.EVIDENCE_TO_DIMENSION_ALIAS 反向一致）。
DIMENSION_TO_EVIDENCE_TYPE = {
    "catalog": "catalog",
    "content": "quality",
    "use": "usage",
    "resource": "resource",
    "authz": "authorization",
}
DIMENSION_TO_KIND = {
    "catalog": "catalog_quality",
    "content": "usage",
    "use": "usage",
    "resource": "resource_quality",
    "authz": "authorization",
}
DIMENSION_TO_TARGET = {
    "catalog": "catalog",
    "content": "delivery",
    "use": "delivery",
    "resource": "resource",
    "authz": "authorization",
}

TENANT = "sd-default"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from zw_brain.shared.migrate import ensure_runtime_schema

    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "objection_escalate.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


@pytest.fixture()
def brain(temp_db: Path):
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


@pytest.fixture()
def repo():
    from zw_brain.domain.repositories.objection import ObjectionRepository

    return ObjectionRepository()


def _create_case(repo, dimension: str, *, status: str = "submitted") -> str:
    """Repo-level 合成 case（含一条该维度 evidence，驱动 dimension_of）。

    repo.create_case 不校验 target 存在性（那是 handler 层校验）；这里直接造合成 case，
    再 transition 到目标起始态，给 escalate / assign 用。
    """
    record = repo.create_case(
        {
            "objection_kind": DIMENSION_TO_KIND[dimension],
            "target_type": DIMENSION_TO_TARGET[dimension],
            "target_id": f"target-{dimension}",
            "title": f"escalate-probe {dimension}",
            "complainant_org_id": "U_PROBE_OP",
            "provider_org_id": "U_PROBE_MGR",
            "basis_text": f"{dimension} 升级督办探针",
            "evidence": [
                {
                    "evidence_type": DIMENSION_TO_EVIDENCE_TYPE[dimension],
                    "content_json": {"probe": True, "dimension": dimension},
                }
            ],
        },
        tenant_id=TENANT,
    )
    oid = record.id
    if status != "draft":
        repo.transition_case(oid, "submitted", action_type="submit", node_name="提交异议")
    if status == "platform_investigating":
        repo.transition_case(
            oid, "platform_investigating", action_type="assign", node_name="平台受理转核查"
        )
    return oid


# ──────────────────────────────────────────────────────────────────────
# D — escalate 事件式：5 维度均不再 409，status 不变，督办事件 + 队列落库
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_escalate_does_not_409_and_keeps_status(brain, repo, dimension):
    """escalate × 5 维度：不抛 409、case.status 原样不变、督办事件落库."""
    oid = _create_case(repo, dimension, status="submitted")
    before = repo.get_case(oid, tenant_id=TENANT)
    assert before is not None
    status_before = before.status

    out = invoke_trusted(
        brain,
        "objection.case.escalate",
        {"confirmed": True, "objection_id": oid, "escalate_reason": "超期未响应自动升级"},
        role="ROLE_BUSIAUDIT",
    )["result"]

    # status 不变（事件式，不走状态机）。
    after = repo.get_case(oid, tenant_id=TENANT)
    assert after is not None
    assert after.status == status_before, f"{dimension}: escalate 不应改 status"
    # 输出携带督办信号。
    assert out.get("supervised") is True
    assert out.get("escalated") is True
    # 督办事件落库（objection_process 一条 action_type=escalate）。
    actions = [p.action_type for p in repo.list_processes(oid)]
    assert "escalate" in actions
    assert repo.is_supervised(oid) is True


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_escalate_puts_case_in_supervised_queue(brain, repo, dimension):
    """escalate 后 case 进 业务运营员督办队列（list_supervised_cases 现算可见）."""
    oid = _create_case(repo, dimension, status="platform_investigating")
    assert repo.is_supervised(oid) is False
    invoke_trusted(
        brain,
        "objection.case.escalate",
        {"confirmed": True, "objection_id": oid},
        role="ROLE_BUSIAUDIT",
    )
    supervised_ids = {c.id for c in repo.list_supervised_cases(tenant_id=TENANT)}
    assert oid in supervised_ids


def test_supervised_queue_excludes_terminal_cases(brain, repo):
    """已 closed/rejected 的 case 即便曾督办也不再回督办队列（督办=待抓办信号）."""
    oid = _create_case(repo, "catalog", status="platform_investigating")
    invoke_trusted(
        brain,
        "objection.case.escalate",
        {"confirmed": True, "objection_id": oid},
        role="ROLE_BUSIAUDIT",
    )
    assert oid in {c.id for c in repo.list_supervised_cases(tenant_id=TENANT)}
    # 推进到 resolved → closed。
    repo.transition_case(oid, "resolved", action_type="review", node_name="复核", resolved_summary="已修正")
    repo.transition_case(oid, "closed", action_type="close", node_name="归档")
    assert oid not in {c.id for c in repo.list_supervised_cases(tenant_id=TENANT)}


def test_escalate_emits_audit_feed_event(brain, repo):
    """escalate 在 audit feed 留一条 objection.case.escalate 事件（事件式闭环可回放）."""
    oid = _create_case(repo, "authz", status="submitted")
    invoke_trusted(
        brain,
        "objection.case.escalate",
        {"confirmed": True, "objection_id": oid},
        role="ROLE_BUSIAUDIT",
    )
    feed = brain.snapshot()["audit_events"]
    types_on_target = [e["type"] for e in feed if e.get("target") == oid]
    assert "objection.case.escalate" in types_on_target


# ──────────────────────────────────────────────────────────────────────
# 业务运营员工作台「待督办」队列投影
# ──────────────────────────────────────────────────────────────────────


def test_busiaudit_backlog_surfaces_supervised_queue(brain, repo):
    """业务运营员（ROLE_BUSIAUDIT）工作台暴露「待督办」待办（深链既有异议收件箱）."""
    from zw_brain.domain.workbench_backlog_projection import enrich_workbench_backlog

    # 零督办时不投该条（无空死链）。
    empty = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    assert not any(t["id"] == "backlog-objection-supervised" for t in empty["todos"])

    oid = _create_case(repo, "catalog", status="platform_investigating")
    invoke_trusted(
        brain,
        "objection.case.escalate",
        {"confirmed": True, "objection_id": oid},
        role="ROLE_BUSIAUDIT",
    )
    enriched = enrich_workbench_backlog({"todos": []}, "ROLE_BUSIAUDIT", tenant_id=TENANT)
    supervised = [t for t in enriched["todos"] if t["id"] == "backlog-objection-supervised"]
    assert supervised, f"督办待办应出现在业务运营员工作台，实测 {[t['id'] for t in enriched['todos']]}"
    assert supervised[0]["href"] == "#/provider/inbox/objection"
    assert "待督办" in supervised[0]["status"]


# ──────────────────────────────────────────────────────────────────────
# D — assign 合法目标派生（仿 D57 accept），不再默认非法 provider_investigating
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_assign_without_target_derives_legal_target_from_submitted(brain, repo, dimension):
    """submitted 态 assign（不传 target_status）派生合法 platform_investigating，不 409.

    旧默认 provider_investigating 从 submitted 是非法跳转（submitted 只允许 →
    platform_investigating / rejected），必 409；机械修后按维度+当前态取合法边。
    """
    oid = _create_case(repo, dimension, status="submitted")
    invoke_trusted(
        brain,
        "objection.case.assign",
        {"confirmed": True, "objection_id": oid},
        role="ROLE_BUSIAUDIT",
    )
    after = repo.get_case(oid, tenant_id=TENANT)
    assert after is not None
    # submitted 维度合法核查落点 = platform_investigating（受理转核查）。
    assert after.status == "platform_investigating", f"{dimension}: assign 应落合法核查态"


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_assign_without_target_derives_provider_from_platform(brain, repo, dimension):
    """platform_investigating 态 assign（不传 target_status）派生 provider_investigating（分发到部门）."""
    oid = _create_case(repo, dimension, status="platform_investigating")
    invoke_trusted(
        brain,
        "objection.case.assign",
        {"confirmed": True, "objection_id": oid},
        role="ROLE_BUSIAUDIT",
    )
    after = repo.get_case(oid, tenant_id=TENANT)
    assert after is not None
    assert after.status == "provider_investigating", f"{dimension}: 分发应落 provider_investigating"


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_assign_honors_explicit_target_status(brain, repo, dimension):
    """显式 target_status 仍优先（既有调用方按段传 platform/provider，行为不变）."""
    oid = _create_case(repo, dimension, status="submitted")
    invoke_trusted(
        brain,
        "objection.case.assign",
        {"confirmed": True, "objection_id": oid, "target_status": "platform_investigating"},
        role="ROLE_BUSIAUDIT",
    )
    after = repo.get_case(oid, tenant_id=TENANT)
    assert after is not None
    assert after.status == "platform_investigating"
