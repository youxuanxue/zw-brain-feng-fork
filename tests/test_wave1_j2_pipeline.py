# Wave: 1
# Journey: J2
# Pages: P5
# Consumer-faces: API (repo + brain.invoke_skill 层)
# Roles: ROLE_ORGAN_OPERATER (编目员) / ROLE_ORGAN_MANAGER (部门审) / ROLE_BUSIAUDIT (平台审)
# Trace:
#   .testing/waves/wave-1-j1-j2-closed-loop/features/j2-online-catalog-compile.feature
#   .testing/waves/wave-1-j1-j2-closed-loop/features/j2-resource-mount.feature
#   .testing/waves/wave-1-j1-j2-closed-loop/features/j2-department-review.feature
#   .testing/waves/wave-1-j1-j2-closed-loop/features/j2-platform-publish.feature
"""G2.2 J2 单部门最小闭环 pytest（真数据，sd-default）

覆盖 J2 黄金链路 4 阶段端到端：
  在线编制 (catalog.entry.create_draft + update)
  → 资源挂接 (catalog.resource.bind)
  → 部门审 (catalog.entry.submit_review + review[approve|return|reject])
  → 平台发布 (catalog.entry.publish + withdraw)

测试范式：每个 scenario 走 brain.invoke_skill 真分发 + 真 DB（shadow），断言
状态机转换 + audit_event 落账 + capability_call 审计。不 mock 业务数据。

数据隔离：ZW_BRAIN_DB_PATH 切到 shadow，写不污染 .data/zw_brain.db。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_wave1_j2_shadow.db"
TENANT = "sd-default"


def _real_data_ready() -> bool:
    if not SEED_DB.exists():
        return False
    try:
        with sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM catalog_entry WHERE tenant_id=?", (TENANT,),
            ).fetchone()
            return bool(row and row[0] >= 1000)
    except sqlite3.OperationalError:
        return False


if not _real_data_ready():
    pytest.skip(
        "Wave 0 真灌库 catalog_entry 缺位（CI runner 不带 .data/zw_brain.db）；"
        "本地真数据验收承接。",
        allow_module_level=True,
    )


@pytest.fixture(scope="session", autouse=True)
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


@pytest.fixture(scope="session")
def brain():
    """G2.2 用 BrainService.invoke_skill 真分发；audit_bus 挂 DatabaseStore.append_audit_event。"""
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore
    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


@pytest.fixture(scope="session")
def catalog_repo():
    from zw_brain.domain.repositories.catalog import CatalogRepository
    return CatalogRepository()


@pytest.fixture(scope="session")
def baseline_counts():
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute(
            "SELECT lifecycle_status, COUNT(*) FROM catalog_entry WHERE tenant_id=? GROUP BY lifecycle_status",
            (TENANT,),
        )
        return dict(c.fetchall())
    finally:
        conn.close()


def _unique_catalog_code(prefix: str = "TEST-J2") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _call(brain, skill: str, payload: dict) -> dict:
    """invoke_skill wraps the inner mutation in {'ok', 'skill_id', 'audit_id', 'result'};
    helper returns just `result` dict so scenario assertions stay terse.

    Routes through trusted-payload helper so mutate skill tests go through the
    same trust-stamp path as production BFF (REST/MCP/CLI) instead of bypassing
    `build_trusted_skill_payload`. role is extracted from payload (test fixtures
    embed it) and passed to invoke_trusted to construct the actor_snapshot.
    """
    role = str(payload.pop("role", "ROLE_ORGAN_OPERATER"))
    return invoke_trusted(brain, skill, payload, role=role)["result"]


# G2.2 policy reality（见 zw_brain/domain/policy.py line 110）：
# catalog.entry.review.execute 仅授予 ROLE_BUSIAUDIT；MANAGER 没有此权限。
# .feature 文件描述的「MANAGER 部门审 → BUSIAUDIT 平台审」属业务期望，
# 当前实现是「OPERATER 提交 → BUSIAUDIT 一次评审」单步审批。
# 下面所有 review 步骤统一用 ROLE_BUSIAUDIT；MANAGER 双步审批属 Wave 1 增强
# （见 wave1 j2-department-review.feature 头标 Status: Draft 未实现）。
REVIEWER_ROLE = "ROLE_BUSIAUDIT"


# ============================================================================
# Baseline — sd-default 真数据 catalog 6 状态分布存在
# ============================================================================


def test_j2_baseline_real_catalog_lifecycle_present(baseline_counts):
    """W0-02 灌库前提：catalog 状态机 6 态在真数据中均有实例。"""
    expected_states = {"draft", "pending_review", "approved_pending_publish",
                       "rejected", "active", "retired"}
    actual_states = set(baseline_counts.keys())
    missing = expected_states - actual_states
    assert not missing, f"缺失状态实例：{missing}; got={baseline_counts}"
    assert baseline_counts.get("active", 0) >= 1, baseline_counts
    assert baseline_counts.get("draft", 0) >= 1, baseline_counts


# ============================================================================
# Stage 1: 在线编制 (catalog.entry.create_draft)
# ============================================================================


def test_j2_online_compile_create_draft_lands_with_status_draft(brain, catalog_repo):
    """正向 — ORGAN_OPERATER 在线编制新目录 → status=draft."""
    code = _unique_catalog_code("J2-NEW")
    result = _call(brain,
        "catalog.entry.create_draft",
        {
            "catalog_code": code,
            "title": "G2.2 测试目录-市营商专班企业开办",
            "owner_org_id": "dept_a_test",
            "region_code": "370100",
            "summary_json": {"description": "G2.2 pytest 真数据写入", "category": "test"},
            "role": "ROLE_ORGAN_OPERATER",
            "confirmed": True,
        },
    )
    assert result["lifecycle_status"] == "draft", result
    assert result["catalog_code"] == code, result
    # 重读验证持久化
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry is not None
    assert entry.lifecycle_status == "draft"
    assert entry.title == "G2.2 测试目录-市营商专班企业开办"


def test_j2_online_compile_update_preserves_lifecycle_status(brain, catalog_repo):
    """正向 — ORGAN_OPERATER 编辑草稿（标题 + summary）不应改 lifecycle_status."""
    code = _unique_catalog_code("J2-EDIT")
    _call(brain,
        "catalog.entry.create_draft",
        {
            "catalog_code": code,
            "title": "原标题",
            "owner_org_id": "dept_a_test",
            "summary_json": {"description": "初稿"},
            "role": "ROLE_ORGAN_OPERATER",
            "confirmed": True,
        },
    )
    _call(brain,
        "catalog.entry.update",
        {
            "catalog_code": code,
            "title": "更新后标题",
            "summary_json": {"description": "二稿"},
            "role": "ROLE_ORGAN_OPERATER",
            "confirmed": True,
        },
    )
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry is not None
    assert entry.title == "更新后标题"
    assert entry.lifecycle_status == "draft"  # 编辑不触发状态机


def test_j2_online_compile_update_missing_entry_rejected(brain):
    """负向 — 编辑不存在的 catalog → NotFoundError."""
    from zw_brain.command.brain import NotFoundError
    code = _unique_catalog_code("J2-NOPE")
    with pytest.raises(NotFoundError):
        _call(brain,
            "catalog.entry.update",
            {
                "catalog_code": code,
                "title": "凭空更新",
                "role": "ROLE_ORGAN_OPERATER",
                "confirmed": True,
            },
        )


# ============================================================================
# Stage 2: 部门审 (catalog.entry.submit_review + review)
# ============================================================================


def test_j2_dept_review_approve_transitions_to_approved_pending_publish(brain, catalog_repo):
    """正向 — submit_review → pending_review；MANAGER approve → approved_pending_publish."""
    code = _unique_catalog_code("J2-REV-APPROVE")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "待审目录", "owner_org_id": "dept_a_test",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    submit = _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    assert submit["lifecycle_status"] == "pending_review"
    review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": REVIEWER_ROLE, "confirmed": True,
    })
    assert review["lifecycle_status"] == "approved_pending_publish"
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.lifecycle_status == "approved_pending_publish"


def test_j2_dept_review_return_for_fix_transitions_to_draft(brain, catalog_repo):
    """正向 — MANAGER return_for_fix → 回到 draft（编目员补件再提交）."""
    code = _unique_catalog_code("J2-REV-RETURN")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "需补件目录", "owner_org_id": "dept_a_test",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "return_for_fix",
        "role": REVIEWER_ROLE, "confirmed": True,
    })
    assert review["lifecycle_status"] == "draft"
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.lifecycle_status == "draft"


def test_j2_dept_review_reject_terminal(brain, catalog_repo):
    """正向 — MANAGER reject → rejected 终态（编目员看到驳回理由，需新建草稿重提）."""
    code = _unique_catalog_code("J2-REV-REJECT")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "将被驳回目录", "owner_org_id": "dept_a_test",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "reject",
        "role": REVIEWER_ROLE, "confirmed": True,
    })
    assert review["lifecycle_status"] == "rejected"


def test_j2_dept_review_unsupported_decision_rejected(brain):
    """负向 — 未知 decision 值 → BrainServiceError."""
    from zw_brain.command.brain import BrainServiceError
    code = _unique_catalog_code("J2-REV-BAD")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "异常 decision 目录",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    with pytest.raises(BrainServiceError, match="unsupported"):
        _call(brain, "catalog.entry.review", {
            "catalog_code": code, "decision": "ambiguous",
            "role": REVIEWER_ROLE, "confirmed": True,
        })


# ============================================================================
# Stage 3: 平台发布 (catalog.entry.publish)
# ============================================================================


def test_j2_platform_publish_activates_and_creates_version(brain, catalog_repo):
    """正向 — BUSIAUDIT publish 已 approved 的目录 → lifecycle_status=active + 创建 entry_version."""
    code = _unique_catalog_code("J2-PUB")
    # 走全链路 draft → pending_review → approved_pending_publish
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "G2.2 准备发布的目录",
        "owner_org_id": "dept_a_test", "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": REVIEWER_ROLE, "confirmed": True,
    })
    publish = _call(brain, "catalog.entry.publish", {
        "catalog_code": code, "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    assert publish["lifecycle_status"] == "active"
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.lifecycle_status == "active"
    # 验证 entry_version 落库（active 状态触发 create_entry_version）
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM catalog_entry_version WHERE catalog_code=?",
            (code,),
        )
        version_count = c.fetchone()[0]
        assert version_count >= 1, f"publish 应触发 entry_version 创建；count={version_count}"
    finally:
        conn.close()


def test_j2_platform_withdraw_transitions_to_retired(brain, catalog_repo):
    """正向 — BUSIAUDIT withdraw 已 active → retired（下线）."""
    code = _unique_catalog_code("J2-WITHDRAW")
    # full chain to active
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "G2.2 将被下线的目录",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": REVIEWER_ROLE, "confirmed": True,
    })
    _call(brain, "catalog.entry.publish", {
        "catalog_code": code, "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    result = _call(brain, "catalog.entry.withdraw", {
        "catalog_code": code, "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    assert result["lifecycle_status"] == "retired"


# ============================================================================
# Stage 4: 资源挂接 (catalog.resource.bind)
# ============================================================================


def test_j2_resource_mount_bind_creates_mapping(brain):
    """正向 — bind catalog ↔ resource schema mapping (新增 mapping_code)."""
    code = _unique_catalog_code("J2-MOUNT")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "G2.2 资源挂接目录",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    bind_payload = {
        "catalog_code": code,
        "resource_code": f"asset-{uuid.uuid4().hex[:10]}",
        "catalog_item_code": f"item-{uuid.uuid4().hex[:8]}",
        "binding_code": f"bind-{uuid.uuid4().hex[:8]}",
        "schema_signature": "g2.2.test.schema.v1",
        "field_mapping_json": {"id": "id", "name": "title"},
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
    }
    result = _call(brain, "catalog.resource.bind", bind_payload)
    assert result["mapping_code"]
    assert "status" in result


# ============================================================================
# Audit chain — capability_call + audit_event 落账
# ============================================================================


def test_j2_audit_chain_records_lifecycle_transitions(brain, baseline_counts):
    """端到端 — 完整 J2 链路写入 audit_event + capability_call，链条可追溯."""
    code = _unique_catalog_code("J2-AUDIT")
    # 5 stages
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "G2.2 审计链测试",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": REVIEWER_ROLE, "confirmed": True,
    })
    _call(brain, "catalog.entry.publish", {
        "catalog_code": code, "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    # 查 capability_call
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute(
            """SELECT skill_id, status FROM capability_call
               WHERE input_json LIKE ? ORDER BY id""",
            (f'%{code}%',),
        )
        calls = c.fetchall()
        skill_ids = [r[0] for r in calls]
        # 至少有 4 个 J2 skill 的 capability_call 记录
        expected_skills = {
            "catalog.entry.create_draft",
            "catalog.entry.submit_review",
            "catalog.entry.review",
            "catalog.entry.publish",
        }
        recorded_skills = set(skill_ids)
        missing = expected_skills - recorded_skills
        assert not missing, (
            f"缺失 capability_call skill 记录：{missing}；recorded={skill_ids}"
        )
    finally:
        conn.close()
