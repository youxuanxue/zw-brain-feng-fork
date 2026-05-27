# Wave: 1
# Journey: J1
# Pages: P3 / P5 (UI 嵌入 — 本项后端 + 集成测试骨架；UI 实装 blocked-on E5 P3 异议响应面设计)
# Consumer-faces: API (repo + brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER (申请方) | ROLE_ORGAN_MANAGER (部门) | ROLE_BUSIAUDIT | ROLE_SECURITY_AUDIT
# Trace:
#   .testing/waves/wave-1-j1-j2-closed-loop/features/j1-objection-{catalog,authz,content,resource,use}.feature
#   .twin/e1-j1-journey/plan.yaml F3
#   zw_brain/domain/repositories/objection.py:evaluate_case + add_process
#   zw_brain/command/handlers/j1/objection.py
"""F3: 异议 evaluate/process 辅助流程闭环 — 5 维度完整 lifecycle + audit chain.

覆盖 ObjectionRepository + brain.invoke_skill 两层：
  - repo 层：8 步 lifecycle (create→submit→assign→assign→reply→reply→review→evaluate→close)
    × 5 维度，断言 process records 链 + evaluation 表 + 状态机联动
  - brain 层：1 条 brain.invoke_skill 端到端 (catalog), 断言 _snapshot["audit_events"] 链

数据隔离：与 W0 / F1 / F2 一致的 shadow DB 模式。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tests._seed_guard import require_real_seed
from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_wave1_objection_lifecycle_shadow.db"
TENANT = "sd-default"

require_real_seed({"objection_case": 20})


@pytest.fixture(scope="module", autouse=True)
def _shadow_db() -> None:
    if SHADOW_DB.exists():
        SHADOW_DB.unlink()
    shutil.copy(SEED_DB, SHADOW_DB)
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as _db
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()
    yield


@pytest.fixture(scope="module")
def repo():
    from zw_brain.domain.repositories.objection import ObjectionRepository
    return ObjectionRepository()


# ──────────────────────────────────────────────────────────────────────
# Per-dimension synthetic case factory (复用 F2 套路)
# ──────────────────────────────────────────────────────────────────────

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


def _create_case(repo, dimension: str, *, title_suffix: str) -> str:
    record = repo.create_case(
        {
            "objection_kind": DIMENSION_TO_KIND[dimension],
            "target_type": DIMENSION_TO_TARGET[dimension],
            "target_id": f"target-{dimension}",
            "title": f"F3 {dimension} lifecycle — {title_suffix}",
            "complainant_org_id": "U_LIFECYCLE_OP",
            "provider_org_id": "U_LIFECYCLE_MGR",
            "basis_text": f"{dimension} 维度 lifecycle 探针",
            "evidence": [
                {
                    "evidence_type": DIMENSION_TO_EVIDENCE_TYPE[dimension],
                    "content_json": {"probe": True, "stage": "create"},
                }
            ],
        },
        tenant_id=TENANT,
    )
    return record.id


# ──────────────────────────────────────────────────────────────────────
# 5 维度 lifecycle (8 步) 参数化
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "dimension", ["catalog", "content", "use", "resource", "authz"]
)
def test_full_lifecycle_with_reply_evaluate_close(repo, dimension):
    """5 维度 × 完整 lifecycle:
        create → submit → assign(platform) → assign(provider)
        → reply(provider) → reply(complainant) → review(resolved)
        → evaluate → close

    断言：
        - 终态 status=closed
        - process records 包含每步对应 action_type
        - evaluation 记录写入且字段完整
        - 评分回写 + evaluator snapshot 保留
    """
    objection_id = _create_case(repo, dimension, title_suffix="full-cycle")

    # 1) submit
    repo.transition_case(
        objection_id, "submitted",
        action_type="submit", node_name="提交异议",
        handler_snapshot_json={"actor": "U_LIFECYCLE_OP", "role": "ROLE_ORGAN_OPERATER"},
    )
    # 2) platform_investigating
    repo.transition_case(
        objection_id, "platform_investigating",
        action_type="assign", node_name="平台受理转核查",
        handler_snapshot_json={"actor": "U_PLATFORM_AUDIT", "role": "ROLE_BUSIAUDIT"},
    )
    # 3) provider_investigating
    repo.transition_case(
        objection_id, "provider_investigating",
        action_type="assign", node_name="分发到部门",
        handler_snapshot_json={"actor": "U_PLATFORM_AUDIT", "role": "ROLE_BUSIAUDIT"},
    )

    # 4) reply by provider — does not change status
    repo.add_process(
        objection_id,
        node_name="部门核查回复",
        action_type="reply",
        action_result="submitted",
        handler_snapshot_json={"actor": "U_LIFECYCLE_MGR", "role": "ROLE_ORGAN_MANAGER"},
        opinion="已核实，准备修正",
    )
    # 5) reply by complainant — does not change status
    repo.add_process(
        objection_id,
        node_name="申请人补充材料",
        action_type="reply",
        action_result="submitted",
        handler_snapshot_json={"actor": "U_LIFECYCLE_OP", "role": "ROLE_ORGAN_OPERATER"},
        opinion="补充证据：截图 3 张",
    )

    # mid-state assertion: status unchanged after replies
    mid = repo.get_case(objection_id, tenant_id=TENANT)
    assert mid is not None
    assert mid.status == "provider_investigating"

    # 6) review → resolved with summary
    repo.transition_case(
        objection_id, "resolved",
        action_type="review", node_name="部门修正闭环",
        resolved_summary=f"{dimension} 维度修正完成",
        handler_snapshot_json={"actor": "U_LIFECYCLE_MGR", "role": "ROLE_ORGAN_MANAGER"},
    )

    # 7) evaluate (forced status=resolved)
    evaluation = repo.evaluate_case(
        objection_id,
        {
            "evaluator_snapshot_json": {"actor": "U_LIFECYCLE_OP", "role": "ROLE_ORGAN_OPERATER"},
            "solved_flag": True,
            "overall_score": 5,
            "timeliness_score": 4,
            "result_score": 5,
            "comment": f"处理及时，{dimension} 问题已彻底修复",
        },
    )
    assert evaluation.solved_flag is True
    assert evaluation.overall_score == 5
    assert evaluation.timeliness_score == 4
    assert evaluation.result_score == 5
    assert evaluation.comment is not None
    assert dimension in evaluation.comment
    assert evaluation.evaluator_snapshot_json.get("actor") == "U_LIFECYCLE_OP"

    # 8) close (resolved → closed)
    repo.transition_case(
        objection_id, "closed",
        action_type="close", node_name="异议归档",
        handler_snapshot_json={"actor": "U_LIFECYCLE_OP", "role": "ROLE_ORGAN_OPERATER"},
    )

    final = repo.get_case(objection_id, tenant_id=TENANT)
    assert final is not None
    assert final.status == "closed"
    assert final.closed_at is not None
    assert final.resolved_summary is not None
    assert dimension in final.resolved_summary

    # process chain：至少包含 8 步对应的 action_type
    processes = repo.list_processes(objection_id)
    action_types = [p.action_type for p in processes]
    # create writes node "创建异议" action_type="create"; transition_case/add_process append rest
    for required in ("create", "submit", "assign", "reply", "review", "evaluate", "close"):
        assert required in action_types, f"missing process action_type={required} in {action_types}"
    # assign appears twice (platform + provider)
    assert action_types.count("assign") == 2
    # reply appears twice (provider + complainant)
    assert action_types.count("reply") == 2


# ──────────────────────────────────────────────────────────────────────
# evaluate 边界 — 非 resolved 状态拒绝评价
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "dimension", ["catalog", "content", "use", "resource", "authz"]
)
def test_evaluate_rejects_when_status_not_resolved(repo, dimension):
    from zw_brain.domain.repositories.objection import ObjectionStateError

    objection_id = _create_case(repo, dimension, title_suffix="early-eval")
    # only submit
    repo.transition_case(
        objection_id, "submitted",
        action_type="submit", node_name="提交",
        handler_snapshot_json={"actor": "U_OP"},
    )
    with pytest.raises(ObjectionStateError, match="resolved"):
        repo.evaluate_case(
            objection_id,
            {"evaluator_snapshot_json": {"actor": "U_OP"}, "solved_flag": False, "overall_score": 1, "comment": "未结案不应能评价"},
        )


@pytest.mark.parametrize(
    "dimension", ["catalog", "content", "use", "resource", "authz"]
)
def test_evaluate_after_rejected_terminal_disallowed(repo, dimension):
    """rejected 终态既不能再 transition 也不应该被 evaluate（status != resolved）."""
    from zw_brain.domain.repositories.objection import ObjectionStateError

    objection_id = _create_case(repo, dimension, title_suffix="rejected-eval")
    repo.transition_case(
        objection_id, "submitted",
        action_type="submit", node_name="提交",
        handler_snapshot_json={"actor": "U_OP"},
    )
    repo.transition_case(
        objection_id, "rejected",
        action_type="reject", node_name="平台拒绝",
        handler_snapshot_json={"actor": "U_PLATFORM"},
    )
    with pytest.raises(ObjectionStateError, match="resolved"):
        repo.evaluate_case(
            objection_id,
            {"evaluator_snapshot_json": {"actor": "U_OP"}, "solved_flag": False, "overall_score": 1, "comment": "rejected 不应被评价"},
        )


# ──────────────────────────────────────────────────────────────────────
# evaluate 幂等 + 重复评价覆盖
# ──────────────────────────────────────────────────────────────────────


def test_evaluate_is_upsert(repo):
    """同一 objection 二次 evaluate 走 UPDATE 路径，覆盖字段；不会写两条 evaluation."""
    objection_id = _create_case(repo, "catalog", title_suffix="upsert-eval")
    # walk to resolved
    repo.transition_case(objection_id, "submitted", action_type="submit", node_name="提交", handler_snapshot_json={"actor": "U_OP"})
    repo.transition_case(objection_id, "platform_investigating", action_type="assign", node_name="平台核查", handler_snapshot_json={"actor": "U_PLATFORM"})
    repo.transition_case(objection_id, "resolved", action_type="review", node_name="平台直接结案", resolved_summary="不重要", handler_snapshot_json={"actor": "U_PLATFORM"})

    repo.evaluate_case(
        objection_id,
        {"evaluator_snapshot_json": {"actor": "U_OP"}, "solved_flag": False, "overall_score": 1, "comment": "first"},
    )
    repo.evaluate_case(
        objection_id,
        {"evaluator_snapshot_json": {"actor": "U_OP"}, "solved_flag": True, "overall_score": 5, "comment": "second"},
    )
    final = repo.get_evaluation(objection_id)
    assert final is not None
    assert final.overall_score == 5
    assert final.solved_flag is True
    assert final.comment == "second"

    # process chain 增长：两次 evaluate 都各自追加 process 节点
    evaluate_steps = [p for p in repo.list_processes(objection_id) if p.action_type == "evaluate"]
    assert len(evaluate_steps) == 2


# ──────────────────────────────────────────────────────────────────────
# reply 边界 — 不改变 status，只追加 process 节点
# ──────────────────────────────────────────────────────────────────────


def test_reply_does_not_change_status_and_records_process(repo):
    """reply 是中间过程节点：不进入状态机校验，但写 process record + 不动 status."""
    objection_id = _create_case(repo, "catalog", title_suffix="reply-no-status")
    repo.transition_case(objection_id, "submitted", action_type="submit", node_name="提交", handler_snapshot_json={"actor": "U_OP"})
    repo.transition_case(objection_id, "platform_investigating", action_type="assign", node_name="平台", handler_snapshot_json={"actor": "U_PLATFORM"})

    before_processes = len(repo.list_processes(objection_id))
    repo.add_process(
        objection_id,
        node_name="平台补充意见",
        action_type="reply",
        action_result="submitted",
        handler_snapshot_json={"actor": "U_PLATFORM"},
        opinion="附加证据 3 件",
    )
    after = repo.get_case(objection_id, tenant_id=TENANT)
    assert after is not None
    assert after.status == "platform_investigating"  # unchanged
    after_processes = repo.list_processes(objection_id)
    assert len(after_processes) == before_processes + 1
    assert after_processes[-1].action_type == "reply"
    assert after_processes[-1].opinion == "附加证据 3 件"


# ──────────────────────────────────────────────────────────────────────
# Brain.invoke_skill 端到端 — audit_events feed 链路
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def brain():
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore
    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


def _invoke(brain, skill_id: str, payload: dict) -> dict:
    role = payload.pop("role", "ROLE_ORGAN_MANAGER")
    return invoke_trusted(brain, skill_id, payload, role=role)["result"]


def test_brain_dispatch_catalog_lifecycle_audit_chain(repo, brain):
    """通过 brain.invoke_skill 跑 catalog 维度 lifecycle，断言 snapshot audit_events 链含 7 节点.

    target_id 必须取 SHADOW_DB 内真实 catalog_code — handler `_create_objection_case`
    新校验拒绝凭空 ID（PR #134 R-002 修），避免回潮到 "C-LIFE" 类 fake fixture。
    """
    from zw_brain.domain.models import CatalogEntryRecord
    from zw_brain.shared.db import create_session_factory
    with create_session_factory()() as session:
        from sqlalchemy import select
        real_catalog = session.execute(
            select(CatalogEntryRecord.catalog_code).where(
                CatalogEntryRecord.tenant_id == "sd-default"
            ).limit(1)
        ).scalar_one()
    create_payload = {
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
        "objection_kind": "catalog_quality",
        "target_type": "catalog",
        "target_id": real_catalog,
        "title": "F3 brain-dispatch lifecycle",
        "complainant_org_id": "U_LIFECYCLE_OP",
        "provider_org_id": "U_LIFECYCLE_MGR",
        "basis_text": "brain dispatch e2e",
        "evidence": [{"evidence_type": "catalog", "content_json": {"probe": True}}],
    }
    case = _invoke(brain, "objection.case.create", create_payload)
    objection_id = case["id"]
    assert case["status"] == "draft"

    common = {"role": "ROLE_BUSIAUDIT", "confirmed": True, "objection_id": objection_id}
    _invoke(brain, "objection.case.submit", common)
    _invoke(brain, "objection.case.assign", {**common, "target_status": "platform_investigating"})
    _invoke(brain, "objection.case.assign", {**common, "target_status": "provider_investigating"})
    _invoke(brain, "objection.case.reply", {**common, "node_name": "部门核查回复", "opinion": "已核实", "action_result": "submitted"})
    _invoke(brain, "objection.case.review", {**common, "decision": "resolve", "resolved_summary": "已修正"})
    _invoke(brain, "objection.case.evaluate", {**common, "role": "ROLE_ORGAN_OPERATER",
            "solved_flag": True, "overall_score": 5, "comment": "处理及时"})
    _invoke(brain, "objection.case.close", common)

    # audit feed 链路：至少包含上述 7 个 event_type (create + submit + 2*assign + reply + review + evaluate + close)
    feed_events = brain.snapshot()["audit_events"]
    types_on_target = [e["type"] for e in feed_events if e.get("target") == objection_id]
    for required in ("objection.case.create", "objection.case.submit", "objection.case.assign",
                     "objection.case.reply", "objection.case.review", "objection.case.evaluate",
                     "objection.case.close"):
        assert required in types_on_target, f"missing audit type {required} in {types_on_target}"
    # assign appears at least 2 次
    assert types_on_target.count("objection.case.assign") >= 2

    # 最终状态归档
    final = repo.get_case(objection_id, tenant_id=TENANT)
    assert final is not None
    assert final.status == "closed"
    assert final.closed_at is not None
    assert final.resolved_summary == "已修正"
    # evaluation 写入
    evaluation = repo.get_evaluation(objection_id)
    assert evaluation is not None
    assert evaluation.overall_score == 5
    assert evaluation.solved_flag is True
