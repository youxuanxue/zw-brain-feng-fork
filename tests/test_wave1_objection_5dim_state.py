# Wave: 1
# Journey: J1
# Pages: P2 / P3 / P4 / P5
# Consumer-faces: API (repo-level) — UI 嵌入归 F3
# Roles: ROLE_ORGAN_OPERATER (申请方) | ROLE_ORGAN_MANAGER (部门) | ROLE_BUSIAUDIT | ROLE_SECURITY_AUDIT
# Trace:
#   .testing/waves/wave-1-j1-j2-closed-loop/features/j1-objection-{catalog,authz,content,resource,use}.feature
#   .twin/e1-j1-journey/plan.yaml F1 (catalog) + F2 (content/use/resource/authz)
#   zw_brain/domain/objection_state.py
"""F1 + F2: 异议 5 维度状态机闭环 — 真实数据可达性 + sd-default e2e + 跨维度路由.

数据隔离策略 (与 W0 系列一致): .data/zw_brain.db -> shadow copy, ZW_BRAIN_DB_PATH
设到 shadow，writes 不污染 W0 / F1 基线。

5 维度共享同一 transition 形状（catalog 真实派生 + 4 维度真实数据子集校验，详见
objection_state.py 头注释）。当业务方提供 content/resource 真实异议样本或 F3
evaluate/process 引入分化需求时，由 objection_state.py split。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_wave1_objection_shadow.db"
TENANT = "sd-default"


def _seed_has_objections(min_total: int = 20) -> bool:
    if not SEED_DB.exists():
        return False
    try:
        with sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM objection_case WHERE tenant_id = ?",
                (TENANT,),
            ).fetchone()
            return bool(row and row[0] >= min_total)
    except sqlite3.OperationalError:
        return False


if not _seed_has_objections():
    pytest.skip(
        "M0 真灌库 异议数据缺位（CI runner 无 .data/zw_brain.db 或 objection 迁移未跑）",
        allow_module_level=True,
    )


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
# Per-dimension synthetic case factory
# ──────────────────────────────────────────────────────────────────────

# Maps 业务维度名 → mapper 写入的 evidence_type 串（与
# objection_state.EVIDENCE_TO_DIMENSION_ALIAS 反向一致）
DIMENSION_TO_EVIDENCE_TYPE = {
    "catalog": "catalog",
    "content": "quality",
    "use": "usage",
    "resource": "resource",
    "authz": "authorization",
}

DIMENSION_TO_KIND = {
    "catalog": "catalog_quality",
    "content": "usage",  # mapper has no `content` kind; falls back to evidence-first
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


def _create_case_for_dimension(repo, dimension: str, *, title_suffix: str) -> str:
    record = repo.create_case(
        {
            "objection_kind": DIMENSION_TO_KIND[dimension],
            "target_type": DIMENSION_TO_TARGET[dimension],
            "target_id": f"target-{dimension}",
            "title": f"F2 {dimension} probe — {title_suffix}",
            "complainant_org_id": "U_PROBE_OP",
            "provider_org_id": "U_PROBE_MGR",
            "basis_text": f"{dimension} 维度状态机探针",
            "evidence": [
                {
                    "evidence_type": DIMENSION_TO_EVIDENCE_TYPE[dimension],
                    "content_json": {"probe": True, "dimension": dimension},
                }
            ],
        },
        tenant_id=TENANT,
    )
    return record.id


# Reachability paths — 复用 F1 catalog 路径（5 维度共享形状）
REACHABILITY_PATHS: dict[str, list[tuple[str, str, str]]] = {
    "draft": [],
    "submitted": [
        ("submitted", "submit", "提交异议"),
    ],
    "platform_investigating": [
        ("submitted", "submit", "提交异议"),
        ("platform_investigating", "assign", "平台受理转核查"),
    ],
    "provider_investigating": [
        ("submitted", "submit", "提交异议"),
        ("platform_investigating", "assign", "平台受理转核查"),
        ("provider_investigating", "assign", "分发到部门"),
    ],
    "resolved": [
        ("submitted", "submit", "提交异议"),
        ("platform_investigating", "assign", "平台受理转核查"),
        ("provider_investigating", "assign", "分发到部门"),
        ("resolved", "review", "部门修正闭环"),
    ],
    "rejected": [
        ("submitted", "submit", "提交异议"),
        ("rejected", "reject", "平台拒绝"),
    ],
}


def _walk(repo, objection_id: str, target_status: str) -> None:
    for next_status, action_type, node_name in REACHABILITY_PATHS[target_status]:
        repo.transition_case(
            objection_id,
            next_status,
            action_type=action_type,
            node_name=node_name,
            handler_snapshot_json={"actor": "f2-probe", "role": "ROLE_BUSIAUDIT"},
        )


# ──────────────────────────────────────────────────────────────────────
# 5 维度可达性参数化（F1 stop condition for catalog + F2 for 4 维度）
# ──────────────────────────────────────────────────────────────────────

REACHABLE_STATES = (
    "draft",
    "submitted",
    "platform_investigating",
    "provider_investigating",
    "resolved",
    "rejected",
)


@pytest.mark.parametrize("dimension", ["catalog", "content", "use", "resource", "authz"])
@pytest.mark.parametrize("target_status", REACHABLE_STATES)
def test_dimension_state_reachability(repo, dimension, target_status):
    """5 维度 × 6 状态 = 30 用例，每个状态从初始 draft 可达."""
    objection_id = _create_case_for_dimension(
        repo, dimension, title_suffix=f"reach-{target_status}"
    )
    _walk(repo, objection_id, target_status)
    case = repo.get_case(objection_id, tenant_id=TENANT)
    assert case is not None
    assert case.status == target_status


@pytest.mark.parametrize("dimension", ["catalog", "content", "use", "resource", "authz"])
def test_dimension_rejects_illegal_jump(repo, dimension):
    """5 维度均拒绝 draft 直接跳 resolved（验证维度路由生效）."""
    from zw_brain.domain.repositories.objection import ObjectionStateError

    objection_id = _create_case_for_dimension(repo, dimension, title_suffix="illegal")
    with pytest.raises(ObjectionStateError, match=dimension):
        repo.transition_case(
            objection_id,
            "resolved",
            action_type="review",
            node_name="非法跳转",
        )


@pytest.mark.parametrize("dimension", ["catalog", "content", "use", "resource", "authz"])
def test_dimension_submitted_rejects_accepted(repo, dimension):
    """5 维度 submitted → accepted 必须被拒（real flow 直进 platform_investigating，
    不经 accepted 中间态）。验证 generic TRANSITIONS 不再泄漏到 5 业务维度。
    """
    from zw_brain.domain.repositories.objection import ObjectionStateError

    objection_id = _create_case_for_dimension(repo, dimension, title_suffix="no-accepted")
    repo.transition_case(
        objection_id, "submitted", action_type="submit", node_name="提交"
    )
    with pytest.raises(ObjectionStateError, match=dimension):
        repo.transition_case(
            objection_id, "accepted", action_type="accept", node_name="平台受理"
        )


@pytest.mark.parametrize("dimension", ["catalog", "content", "use", "resource", "authz"])
def test_dimension_rejected_is_terminal(repo, dimension):
    """5 维度 rejected 是终态 — 不能再跳任何状态."""
    from zw_brain.domain.repositories.objection import ObjectionStateError

    objection_id = _create_case_for_dimension(repo, dimension, title_suffix="rejected-term")
    _walk(repo, objection_id, "rejected")
    for next_status in ("resolved", "submitted", "platform_investigating"):
        with pytest.raises(ObjectionStateError, match=dimension):
            repo.transition_case(
                objection_id,
                next_status,
                action_type="probe",
                node_name=f"非法跳转 {next_status}",
            )


# ──────────────────────────────────────────────────────────────────────
# sd-default 真数据 e2e
# ──────────────────────────────────────────────────────────────────────


def _pick_real_case(evidence_type: str, status: str) -> str | None:
    """Return a real sd-default objection_case.id matching (evidence_type, status), or None."""
    with sqlite3.connect(f"file:{SHADOW_DB}?mode=rw", uri=True) as conn:
        row = conn.execute(
            "SELECT c.id FROM objection_case c "
            "JOIN objection_evidence e ON e.objection_id = c.id "
            "WHERE c.tenant_id = ? AND e.evidence_type = ? AND c.status = ? "
            "LIMIT 1",
            (TENANT, evidence_type, status),
        ).fetchone()
    return row[0] if row else None


def test_catalog_real_dump_e2e_close_resolved(repo):
    """catalog: 真实 resolved case → closed，断言 audit 链."""
    objection_id = _pick_real_case("catalog", "resolved")
    assert objection_id is not None, "M0 dump expected to contain a resolved catalog objection"
    repo.transition_case(
        objection_id,
        "closed",
        action_type="close",
        node_name="归档异议",
        resolved_summary="目录已修正",
        handler_snapshot_json={"actor": "f1-e2e", "role": "ROLE_BUSIAUDIT"},
    )
    case = repo.get_case(objection_id, tenant_id=TENANT)
    assert case is not None
    assert case.status == "closed"
    assert case.closed_at is not None
    actions = [p.action_type for p in repo.list_processes(objection_id)]
    assert "close" in actions


def test_catalog_real_dump_e2e_reject_terminal(repo):
    """catalog: 真实 rejected case → 任何跳变拒绝."""
    from zw_brain.domain.repositories.objection import ObjectionStateError

    objection_id = _pick_real_case("catalog", "rejected")
    assert objection_id is not None
    for next_status in ("resolved", "submitted", "platform_investigating"):
        with pytest.raises(ObjectionStateError, match="catalog"):
            repo.transition_case(
                objection_id,
                next_status,
                action_type="probe",
                node_name=f"非法跳转 {next_status}",
            )


def test_authz_real_dump_e2e_close_resolved(repo):
    """authz: 真实 resolved case (kind=authorization 或 resource_quality 跨打标) → closed."""
    objection_id = _pick_real_case("authorization", "resolved")
    assert objection_id is not None, "M0 dump expected to contain a resolved authz-evidence objection"
    repo.transition_case(
        objection_id,
        "closed",
        action_type="close",
        node_name="授权异议归档",
        resolved_summary="授权决策已重新审批",
        handler_snapshot_json={"actor": "f2-e2e", "role": "ROLE_ORGAN_MANAGER"},
    )
    case = repo.get_case(objection_id, tenant_id=TENANT)
    assert case is not None
    assert case.status == "closed"
    assert case.closed_at is not None


def test_authz_real_dump_e2e_advance_from_investigating(repo):
    """authz: 真实 provider_investigating 推进到 resolved，断言维度路由走 authz."""
    objection_id = _pick_real_case("authorization", "provider_investigating")
    assert objection_id is not None
    repo.transition_case(
        objection_id,
        "resolved",
        action_type="review",
        node_name="部门重新审批闭环",
        resolved_summary="重新审批后同意授权",
        handler_snapshot_json={"actor": "f2-e2e", "role": "ROLE_ORGAN_MANAGER"},
    )
    case = repo.get_case(objection_id, tenant_id=TENANT)
    assert case is not None
    assert case.status == "resolved"


def test_use_real_dump_e2e_advance(repo):
    """use: 真实 1 条 platform_investigating case → resolved → closed."""
    objection_id = _pick_real_case("usage", "platform_investigating")
    assert objection_id is not None, "M0 dump expected to contain the single usage-evidence objection"
    repo.transition_case(
        objection_id,
        "resolved",
        action_type="review",
        node_name="合规处置",
        resolved_summary="警告 + 通知使用方",
        handler_snapshot_json={"actor": "f2-e2e", "role": "ROLE_BUSIAUDIT"},
    )
    repo.transition_case(
        objection_id,
        "closed",
        action_type="close",
        node_name="使用异议归档",
        handler_snapshot_json={"actor": "f2-e2e", "role": "ROLE_BUSIAUDIT"},
    )
    case = repo.get_case(objection_id, tenant_id=TENANT)
    assert case is not None
    assert case.status == "closed"


def test_content_resource_no_real_dump_data():
    """content/resource: 真实 sd-default `dump-dsp_handling` 中 0 条 — 状态机用合成数据覆盖.

    Why: data_objection_content 表与 data_objection_resource 表在真实 dump 中无数据；
    M0 mapper 字段映射齐全（参见 zw_brain/adapters/legacy/mappers/objection.py:281），
    属于业务场景未触发而非映射缺位，不需要提 M0 PR。合成数据 e2e 由
    `test_dimension_state_reachability` 与 `test_dimension_rejects_illegal_jump`
    覆盖（参数化已含 content/resource）。
    """
    # Inspect SEED_DB (raw M0 dump), not SHADOW (polluted by synthetic probes above)
    with sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True) as conn:
        for evidence_type in ("quality", "resource"):
            cnt = conn.execute(
                "SELECT COUNT(*) FROM objection_evidence e "
                "JOIN objection_case c ON c.id = e.objection_id "
                "WHERE c.tenant_id = ? AND e.evidence_type = ?",
                (TENANT, evidence_type),
            ).fetchone()[0]
            assert cnt == 0, f"unexpected {evidence_type} evidence in raw dump: {cnt}"


# ──────────────────────────────────────────────────────────────────────
# 跨维度路由 / dimension_of 单元检验
# ──────────────────────────────────────────────────────────────────────


def test_dimension_of_evidence_first():
    """dimension_of 优先看 evidence_type，回落 objection_kind / target_type."""
    from zw_brain.domain.objection_state import dimension_of

    class _Case:
        objection_kind = "catalog_quality"
        target_type = "catalog"

    class _Ev:
        def __init__(self, t):
            self.evidence_type = t

    # evidence-first：authorization evidence 即使 kind=catalog_quality 也被归 authz
    case = _Case()
    assert dimension_of(case, [_Ev("authorization")]) == "authz"
    # catalog evidence 短路：含 catalog evidence 直接归 catalog
    assert dimension_of(case, [_Ev("authorization"), _Ev("catalog")]) == "catalog"
    # 无 evidence：回落 kind
    assert dimension_of(case, []) == "catalog"
    # kind 不在表内：回落 target_type
    class _NoKind:
        objection_kind = "unknown"
        target_type = "resource"
    assert dimension_of(_NoKind(), []) == "resource"
    # 全部 unknown → generic
    class _Unknown:
        objection_kind = "x"
        target_type = "delivery"
    assert dimension_of(_Unknown(), []) == "generic"


def test_evidence_alias_table_covers_5_mapper_types():
    """objection_state.EVIDENCE_TO_DIMENSION_ALIAS 必须覆盖 mapper 落库的 5 个 evidence_type."""
    from zw_brain.adapters.legacy.mappers.objection import ObjectionMapper  # noqa: F401
    from zw_brain.domain.objection_state import EVIDENCE_TO_DIMENSION_ALIAS

    # 与 zw_brain/adapters/legacy/mappers/objection.py:281 的 evidence_table_to_type 反向同步
    expected = {"authorization", "catalog", "quality", "resource", "usage"}
    assert set(EVIDENCE_TO_DIMENSION_ALIAS.keys()) == expected


def test_allowed_transitions_by_dimension_covers_all_5():
    from zw_brain.domain.objection_state import (
        ALL_DIMENSIONS,
        ALLOWED_TRANSITIONS_BY_DIMENSION,
    )

    assert set(ALLOWED_TRANSITIONS_BY_DIMENSION.keys()) == set(ALL_DIMENSIONS)
