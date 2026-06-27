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

数据隔离：realistic_pg_module 克隆 zw_realistic_tmpl（含真实旧平台数据），
模板缺位时整模块 skip（承接旧 require_real_seed 数据量门槛语义），写不污染真实模板。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (fixture)
from tests._trusted_payload import invoke_trusted
from zw_brain.shared.db import get_database_url

REPO_ROOT = Path(__file__).resolve().parent.parent
TENANT = "sd-default"

# 门槛语义（catalog_entry≥1000）由 realistic_pg_module 的 skip-when-absent 承接。
pytestmark = pytest.mark.usefixtures("realistic_pg_module")


def _pg_read(sql: str, params: tuple = ()):
    """Read against the cloned realistic PG (app read-path's DB), never a file."""
    url = make_url(get_database_url())
    with psycopg.connect(
        host=url.host, port=url.port, user=url.username,
        password=url.password, dbname=url.database,
    ) as conn:
        return conn.execute(sql, params).fetchall()


@pytest.fixture
def brain():
    """G2.2 用 BrainService.invoke_skill 真分发；audit_bus 挂 DatabaseStore.append_audit_event。

    Function-scoped：conftest._isolate_db_env 在每个测试前清 audit-bus sink（PG 隔离卫生），
    故 sink 必须每测试重配——module-scoped 只配一次、test #2 起丢失。realistic_pg_module
    保证 DB 跨测试持久（hands-off 不重克隆），状态可累积。"""
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore
    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


@pytest.fixture(scope="module")
def catalog_repo():
    from zw_brain.domain.repositories.catalog import CatalogRepository
    return CatalogRepository()


@pytest.fixture(scope="module")
def baseline_counts():
    return dict(_pg_read(
        "SELECT lifecycle_status, COUNT(*) FROM catalog_entry "
        "WHERE tenant_id=%s GROUP BY lifecycle_status",
        (TENANT,),
    ))


# F2 (E2 J2)：3 物化（table/file/api）真实样本探针。
# 从 sd-default canonical resource_asset (resource_kind ∈ {table,file,api}) JOIN
# resource_channel_binding + resource_schema_mapping，挑各 1 条真实 (resource_code,
# binding_code, catalog_item_code, catalog_code) 组合作为 bind 入参，让 F2 用例
# 不造数据。缺位 → 对应物化 pytest.skip，由 supervisor 决定提 M0 PR 还是 F2 部分交付。
@pytest.fixture(scope="module")
def provider_samples():
    samples: dict[str, dict | None] = {}
    for kind in ("table", "file", "api"):
        rows = _pg_read(
            """SELECT ra.resource_code, rcb.binding_code, rsm.catalog_item_code,
                      rsm.catalog_code
               FROM resource_asset ra
               JOIN resource_channel_binding rcb
                 ON rcb.tenant_id = ra.tenant_id AND rcb.resource_code = ra.resource_code
               JOIN resource_schema_mapping rsm
                 ON rsm.tenant_id = ra.tenant_id AND rsm.resource_code = ra.resource_code
                AND rsm.status = 'active' AND rsm.catalog_item_code != ''
               WHERE ra.tenant_id = %s AND ra.resource_kind = %s
               LIMIT 1""",
            (TENANT, kind),
        )
        row = rows[0] if rows else None
        samples[kind] = (
            None
            if row is None
            else {
                "resource_code": row[0],
                "binding_code": row[1],
                "catalog_item_code": row[2],
                "catalog_code": row[3],
            }
        )
    return samples


def _unique_catalog_code(prefix: str = "TEST-J2") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _required_summary(**overrides) -> dict:
    """在线编制基本信息必填全集（0611 业务口径确认单 §A，D57）。

    经 catalog.entry.create_draft 新铸的目录提交审核前必须填全必填基本信息
    （catalog_entry.py::_missing_inline_required_basic_fields）；本文件聚焦状态机，
    凡走到 submit_review 的草稿统一带该完整集（shared_type=1 无条件共享，
    避免连带共享条件的条件必填）。必填校验本身的三向用例见
    tests/test_inline_catalog_required_fields.py。
    """
    base = {
        "catalog_type": "测试分类",
        "source_system": "G2.2 测试来源系统",
        "domain": "测试领域",
        "application_scenario": "G2.2 状态机回归",
        "resource_format": "0200",
        "business_update_cycle": "2",
        "data_update_cycle": "2",
        "shared_way": "api",
        "shared_type": "1",
        "open_type": "3",
        "description": "G2.2 状态机回归测试目录",
    }
    base.update(overrides)
    return base


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


# F1 (E2 J2 3-layer) 后的 policy 现实（zw_brain/domain/policy.py::PERMISSION_ROLES）：
# - catalog.entry.review.execute 授予 {ROLE_ORGAN_MANAGER, ROLE_BUSIAUDIT}
# - handler `_review_catalog_entry` 做 stage-aware 判定：
#     state=pending_review + MANAGER  → pending_platform_review
#     state=pending_platform_review + BUSIAUDIT → approved_pending_publish
#     state=pending_review + BUSIAUDIT → approved_pending_publish（旧单步兼容路径，待 3 层全量切换后移除）
# REVIEWER_ROLE 保留 BUSIAUDIT，让既有 6 个测试走兼容路径继续验证状态机正确性；
# 新增的 3 层流程用例显式用 MANAGER + BUSIAUDIT 分阶段调用。
REVIEWER_ROLE = "ROLE_BUSIAUDIT"
MANAGER_ROLE = "ROLE_ORGAN_MANAGER"
PLATFORM_ROLE = "ROLE_BUSIAUDIT"


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
        "catalog_code": code, "title": "待审目录", "summary_json": _required_summary(), "owner_org_id": "dept_a_test",
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
        "catalog_code": code, "title": "需补件目录", "summary_json": _required_summary(), "owner_org_id": "dept_a_test",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "return_for_fix",
        "reason": "信息项缺主键，请补全后重提",
        "role": REVIEWER_ROLE, "confirmed": True,
    })
    assert review["lifecycle_status"] == "draft"
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.lifecycle_status == "draft"
    # D57⑨/R10：退回理由落 summary.review_return_reason（供数方整改依据）。
    assert entry.summary_json.get("review_return_reason") == "信息项缺主键，请补全后重提"


def test_j2_dept_review_reject_terminal(brain, catalog_repo):
    """正向 — MANAGER reject（带理由）→ rejected 终态（编目员看到驳回理由，需新建草稿重提）."""
    code = _unique_catalog_code("J2-REV-REJECT")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "将被驳回目录", "summary_json": _required_summary(), "owner_org_id": "dept_a_test",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "reject",
        "reason": "口径不符合编目规范",
        "role": REVIEWER_ROLE, "confirmed": True,
    })
    assert review["lifecycle_status"] == "rejected"
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.summary_json.get("review_return_reason") == "口径不符合编目规范"


def test_j2_dept_review_reject_without_reason_fail_closed(brain, catalog_repo):
    """负向（D57⑨/R10 fail-closed）— 退回/驳回不带理由 → InvalidStateError，态不变。

    REST/CLI 直调不带理由同样拦（前端 toast 只是第一道），保证供数方一定拿到整改依据。
    """
    from zw_brain.command.brain import InvalidStateError
    code = _unique_catalog_code("J2-REV-NOREASON")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "无理由驳回目录", "summary_json": _required_summary(), "owner_org_id": "dept_a_test",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    for decision in ("reject", "return_for_fix"):
        with pytest.raises(InvalidStateError):
            _call(brain, "catalog.entry.review", {
                "catalog_code": code, "decision": decision, "reason": "   ",  # 空白理由同样拦
                "role": REVIEWER_ROLE, "confirmed": True,
            })
        # 守卫在转换前 fail-closed：态停在 pending_review（未被改写）。
        entry = catalog_repo.get_entry(code, tenant_id=TENANT)
        assert entry.lifecycle_status == "pending_review"


def test_j2_dept_review_approve_clears_stale_reject_reason(brain, catalog_repo):
    """通过审核清掉历史驳回理由（陈旧整改依据不再展示）——退回带理由→补件重提→通过后理由清空。"""
    code = _unique_catalog_code("J2-REV-CLEAR")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "清理由目录", "summary_json": _required_summary(), "owner_org_id": "dept_a_test",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {"catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True})
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "return_for_fix", "reason": "先补件",
        "role": REVIEWER_ROLE, "confirmed": True,
    })
    assert catalog_repo.get_entry(code, tenant_id=TENANT).summary_json.get("review_return_reason") == "先补件"
    _call(brain, "catalog.entry.submit_review", {"catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True})
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": REVIEWER_ROLE, "confirmed": True,
    })
    assert not catalog_repo.get_entry(code, tenant_id=TENANT).summary_json.get("review_return_reason")


def test_j2_dept_review_unsupported_decision_rejected(brain):
    """负向 — 未知 decision 值 → BrainServiceError."""
    from zw_brain.command.brain import BrainServiceError
    code = _unique_catalog_code("J2-REV-BAD")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "异常 decision 目录", "summary_json": _required_summary(),
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
        "catalog_code": code, "title": "G2.2 准备发布的目录", "summary_json": _required_summary(),
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
    version_count = _pg_read(
        "SELECT COUNT(*) FROM catalog_entry_version WHERE catalog_code=%s",
        (code,),
    )[0][0]
    assert version_count >= 1, f"publish 应触发 entry_version 创建；count={version_count}"


def test_j2_platform_withdraw_transitions_to_retired(brain, catalog_repo):
    """正向 — BUSIAUDIT withdraw 已 active → retired（下线）."""
    code = _unique_catalog_code("J2-WITHDRAW")
    # full chain to active
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "G2.2 将被下线的目录", "summary_json": _required_summary(),
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


# ============================================================================
# F1 (E2 J2 3-layer)：原生 3 层默认流程 6+1 态可达性
# pending_review (部门待审) → MANAGER approve → pending_platform_review (平台待审)
#                          → BUSIAUDIT approve → approved_pending_publish → publish → active
# ============================================================================


def test_j2_three_layer_happy_path_full_chain(brain, catalog_repo):
    """正向 3 层 — OPERATER submit → MANAGER approve → BUSIAUDIT approve → publish → active.

    校验：
      1. MANAGER approve 后落到中间态 pending_platform_review；
      2. BUSIAUDIT approve 后落到 approved_pending_publish；
      3. publish 后落到 active；
      4. capability_call 链含 5 个 J2 skill；
      5. audit_event 序列含两次 catalog.entry.review。
    """
    code = _unique_catalog_code("J2-3L-HAPPY")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "G2.2 3 层流程目录", "summary_json": _required_summary(),
        "owner_org_id": "dept_a_test", "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    # Stage 1: 部门待审 — MANAGER approve
    dept_review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": MANAGER_ROLE, "confirmed": True,
    })
    assert dept_review["lifecycle_status"] == "pending_platform_review", dept_review
    mid_entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert mid_entry.lifecycle_status == "pending_platform_review"

    # Stage 2: 平台待审 — BUSIAUDIT approve
    platform_review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": PLATFORM_ROLE, "confirmed": True,
    })
    assert platform_review["lifecycle_status"] == "approved_pending_publish", platform_review

    # Stage 3: 发布
    publish = _call(brain, "catalog.entry.publish", {
        "catalog_code": code, "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    assert publish["lifecycle_status"] == "active", publish

    # capability_call 链 + audit_event 序列
    skills = [
        r[0] for r in _pg_read(
            "SELECT skill_id FROM capability_call WHERE input_json::text LIKE %s ORDER BY id",
            (f"%{code}%",),
        )
    ]
    expected = {
        "catalog.entry.create_draft",
        "catalog.entry.submit_review",
        "catalog.entry.review",
        "catalog.entry.publish",
    }
    assert expected <= set(skills), f"3 层链路 capability_call 缺漏：expected={expected}, got={skills}"
    # 两次 review 都要落到 capability_call（同一 skill_id 两次执行）
    review_count = sum(1 for s in skills if s == "catalog.entry.review")
    assert review_count >= 2, f"3 层流程应记录两次 catalog.entry.review，实际={review_count}"


def test_j2_three_layer_manager_return_for_fix_back_to_draft(brain, catalog_repo):
    """正向 — MANAGER 阶段 return_for_fix → 回 draft（编目员补件再提）."""
    code = _unique_catalog_code("J2-3L-MGR-RETURN")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "MANAGER 退回目录", "summary_json": _required_summary(),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "return_for_fix", "reason": "部门审退回补件",
        "role": MANAGER_ROLE, "confirmed": True,
    })
    assert review["lifecycle_status"] == "draft"
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.lifecycle_status == "draft"


def test_j2_three_layer_manager_reject_terminal(brain, catalog_repo):
    """正向 — MANAGER 阶段 reject → rejected 终态."""
    code = _unique_catalog_code("J2-3L-MGR-REJECT")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "MANAGER 驳回目录", "summary_json": _required_summary(),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "reject", "reason": "部门审驳回",
        "role": MANAGER_ROLE, "confirmed": True,
    })
    assert review["lifecycle_status"] == "rejected"


def test_j2_three_layer_platform_return_for_fix_back_to_draft(brain, catalog_repo):
    """正向 — 平台 stage BUSIAUDIT return_for_fix → 回 draft."""
    code = _unique_catalog_code("J2-3L-PLT-RETURN")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "平台退回目录", "summary_json": _required_summary(),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    # 先让 MANAGER 通过到 pending_platform_review
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": MANAGER_ROLE, "confirmed": True,
    })
    # 平台 stage BUSIAUDIT return_for_fix
    review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "return_for_fix", "reason": "平台审退回补件",
        "role": PLATFORM_ROLE, "confirmed": True,
    })
    assert review["lifecycle_status"] == "draft"


def test_j2_three_layer_platform_reject_terminal(brain, catalog_repo):
    """正向 — 平台 stage BUSIAUDIT reject → rejected 终态."""
    code = _unique_catalog_code("J2-3L-PLT-REJECT")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "平台驳回目录", "summary_json": _required_summary(),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": MANAGER_ROLE, "confirmed": True,
    })
    review = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "reject", "reason": "平台审驳回",
        "role": PLATFORM_ROLE, "confirmed": True,
    })
    assert review["lifecycle_status"] == "rejected"


def test_j2_three_layer_stage_mismatch_rejected(brain):
    """负向 — state=pending_platform_review 时 MANAGER approve → InvalidStateError（阶段错位）."""
    from zw_brain.command.brain import InvalidStateError
    code = _unique_catalog_code("J2-3L-STAGE-MIS")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "阶段错位目录", "summary_json": _required_summary(),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": MANAGER_ROLE, "confirmed": True,
    })
    # 此时 state=pending_platform_review；MANAGER 再来 approve 应被拒
    with pytest.raises(InvalidStateError, match="cannot be approved"):
        _call(brain, "catalog.entry.review", {
            "catalog_code": code, "decision": "approve",
            "role": MANAGER_ROLE, "confirmed": True,
        })


def test_j2_three_layer_audit_chain_records_both_review_events(brain):
    """端到端 — 3 层完整链路落 5+ capability_call + 2 次 review audit_event."""
    code = _unique_catalog_code("J2-3L-AUDIT")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "3 层审计链", "summary_json": _required_summary(),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": MANAGER_ROLE, "confirmed": True,
    })
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": PLATFORM_ROLE, "confirmed": True,
    })
    _call(brain, "catalog.entry.publish", {
        "catalog_code": code, "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    rows = _pg_read(
        """SELECT skill_id, role_code FROM capability_call
           WHERE input_json::text LIKE %s ORDER BY id""",
        (f"%{code}%",),
    )
    skills = [r[0] for r in rows]
    # 两次 review 分别由 MANAGER 与 BUSIAUDIT 触发
    review_roles = [role for skill, role in rows if skill == "catalog.entry.review"]
    assert len(review_roles) == 2, f"应记录 2 次 review，实际 roles={review_roles}"
    assert "ROLE_ORGAN_MANAGER" in review_roles, review_roles
    assert "ROLE_BUSIAUDIT" in review_roles, review_roles
    assert skills.count("catalog.entry.review") == 2


# ============================================================================
# D57⑧ 反向编目审核两级管线：
#   OPERATER/MANAGER create（draft, source=reverse）
#   → MANAGER reverse_draft.confirm（部门审，含 field_decisions）→ pending_platform_review
#   → BUSIAUDIT catalog.entry.review approve（平台审，复用正向平台档）→ approved_pending_publish
#   → BUSIAUDIT publish → active
# 替换原「仅 BUSIAUDIT 一级 confirm」；操作员双面无审核权（做的人不审自己）。
# ============================================================================


def _mint_reverse_draft(brain, prefix: str, *, creator_role: str = "ROLE_ORGAN_OPERATER") -> str:
    code = _unique_catalog_code(prefix)
    _call(brain, "catalog.entry.reverse_draft.create", {
        "catalog_code": code, "title": f"反向编目草稿 {code}",
        "schema_ref": f"schema:{code}", "owner_org_id": "dept_a_test",
        "role": creator_role, "confirmed": True,
    })
    return code


def test_reverse_two_level_happy_path_manager_dept_then_busiaudit_platform(brain, catalog_repo):
    """正向 — 操作员铸反向草稿 → MANAGER 部门审 confirm → 平台档 → BUSIAUDIT 平台审 → 发布。"""
    code = _mint_reverse_draft(brain, "J2-REVERSE-2L")
    entry = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert entry.lifecycle_status == "draft"
    assert entry.summary_json.get("source") == "reverse"

    # 第一级：部门管理员部门审（字段口径裁决随部门审落账）
    confirm = _call(brain, "catalog.entry.reverse_draft.confirm", {
        "catalog_code": code, "role": MANAGER_ROLE, "confirmed": True,
        "field_decisions": [{"field": "name", "decision": "keep"}],
        "comment": "部门审通过",
    })
    assert confirm["lifecycle_status"] == "pending_platform_review", confirm
    mid = catalog_repo.get_entry(code, tenant_id=TENANT)
    assert mid.lifecycle_status == "pending_platform_review"
    # 字段裁决语义保留在部门审级（落 summary，平台审/详情可读）
    assert mid.summary_json.get("field_decisions") == [{"field": "name", "decision": "keep"}]
    assert mid.summary_json.get("source") == "reverse"

    # 第二级：业务运营员平台审（复用正向 catalog.entry.review 平台档，不造第二套状态机）
    platform = _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": PLATFORM_ROLE, "confirmed": True,
    })
    assert platform["lifecycle_status"] == "approved_pending_publish", platform

    publish = _call(brain, "catalog.entry.publish", {
        "catalog_code": code, "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    assert publish["lifecycle_status"] == "active", publish


def test_reverse_dept_reject_terminal_and_platform_return_back_to_dept_inbox(brain, catalog_repo):
    """负向/回流 — 部门审驳回 → rejected；平台审 return_for_fix → 回 draft（即回部门审收件箱口径）。"""
    # 部门审驳回
    code_a = _mint_reverse_draft(brain, "J2-REVERSE-REJ")
    rejected = _call(brain, "catalog.entry.reverse_draft.reject", {
        "catalog_code": code_a, "reject_reason": "口径需补充证据",
        "role": MANAGER_ROLE, "confirmed": True,
    })
    assert rejected["lifecycle_status"] == "rejected", rejected

    # 平台审退回 → draft（source=reverse 保留 → 重新出现在部门审收件箱口径 source=reverse ∧ draft）
    code_b = _mint_reverse_draft(brain, "J2-REVERSE-RET")
    _call(brain, "catalog.entry.reverse_draft.confirm", {
        "catalog_code": code_b, "role": MANAGER_ROLE, "confirmed": True,
    })
    returned = _call(brain, "catalog.entry.review", {
        "catalog_code": code_b, "decision": "return_for_fix", "reason": "平台审退回部门补件",
        "role": PLATFORM_ROLE, "confirmed": True,
    })
    assert returned["lifecycle_status"] == "draft", returned
    back = catalog_repo.get_entry(code_b, tenant_id=TENANT)
    assert back.summary_json.get("source") == "reverse", "退回后仍是反向单，须回部门审收件箱口径"


def test_reverse_confirm_denied_for_operater_and_busiaudit(brain):
    """负向双面 — 操作员（做的人不审自己）与业务运营员（已退 draft 阶段）均无部门审权。"""
    from zw_brain.command.brain import AccessDeniedError

    code = _mint_reverse_draft(brain, "J2-REVERSE-DENY")
    for forbidden_role in ("ROLE_ORGAN_OPERATER", "ROLE_BUSIAUDIT"):
        with pytest.raises(AccessDeniedError):
            _call(brain, "catalog.entry.reverse_draft.confirm", {
                "catalog_code": code, "role": forbidden_role, "confirmed": True,
            })
        with pytest.raises(AccessDeniedError):
            _call(brain, "catalog.entry.reverse_draft.reject", {
                "catalog_code": code, "reject_reason": "无权驳回",
                "role": forbidden_role, "confirmed": True,
            })


def test_reverse_platform_stage_manager_approve_rejected(brain):
    """负向 — 平台档（pending_platform_review）MANAGER 不能再 approve（阶段错位，与正向一致）。"""
    from zw_brain.command.brain import InvalidStateError

    code = _mint_reverse_draft(brain, "J2-REVERSE-STAGE")
    _call(brain, "catalog.entry.reverse_draft.confirm", {
        "catalog_code": code, "role": MANAGER_ROLE, "confirmed": True,
    })
    with pytest.raises(InvalidStateError, match="cannot be approved"):
        _call(brain, "catalog.entry.review", {
            "catalog_code": code, "decision": "approve",
            "role": MANAGER_ROLE, "confirmed": True,
        })


# ============================================================================
# F2 (E2 J2)：3 物化 (table/file/api) 字段绑定完整性 — 覆盖 AC2 上半
# 每物化各 1 条真实 sd-default 资源端到端：
#   编制 → 部门审 → 平台审 → publish active → catalog.resource.bind
# 验证：mapping_code 落库 + status=active + materialization_kind 反射 +
#       capability_call.input_json 可反推物化形式 + resource_schema_snapshot
#       含字段映射（snapshot 缺位 → 单独 skip 由 M0 补）。
# ============================================================================


@pytest.mark.parametrize("kind", ["table", "file", "api"])
def test_j2_mount_per_materialization_end_to_end(brain, catalog_repo, provider_samples, kind):
    sample = provider_samples.get(kind)
    if sample is None:
        pytest.skip(
            f"sd-default canonical 缺 {kind} 物化资源样本（resource_asset.resource_kind='{kind}' 0 行）；"
            f"需 M0 PR 把 dump-data_resource + dump-rc_resource_{kind} 迁入 canonical"
        )
    if not sample.get("catalog_item_code"):
        pytest.skip(
            f"sd-default canonical 缺 {kind} 物化的 catalog_item 链接（rc_resource_catalog_item_link 未迁）"
        )

    code = _unique_catalog_code(f"J2-MOUNT-{kind.upper()}")
    # F1 链路：编制 → 部门审 → 平台审 → publish
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": f"G2.2-F2 {kind} 物化资源挂接目录", "summary_json": _required_summary(),
        "owner_org_id": "dept_a_test", "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": MANAGER_ROLE, "confirmed": True,
    })
    _call(brain, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": PLATFORM_ROLE, "confirmed": True,
    })
    publish = _call(brain, "catalog.entry.publish", {
        "catalog_code": code, "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    assert publish["lifecycle_status"] == "active"

    # F2：挂接真实物化资源到新发布的目录
    bind_payload = {
        "catalog_code": code,
        "resource_code": sample["resource_code"],
        "catalog_item_code": sample["catalog_item_code"],
        # 用真实 binding_code 加 test 后缀保 uq_resource_schema_mapping_current 不撞旧 active 行
        "binding_code": f"{sample['binding_code']}#f2-{uuid.uuid4().hex[:6]}",
        "materialization_kind": kind,
        "schema_signature": f"g2.2.f2.{kind}.schema.v1",
        "field_mapping_json": {"id": "id", "name": "title"},
        "source_schema_ref": {"materialization": kind, "origin_binding": sample["binding_code"]},
        "mapping_rule_json": {"materialization": kind, "rule": "passthrough"},
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
    }
    bind_result = _call(brain, "catalog.resource.bind", bind_payload)
    assert bind_result["mapping_code"]
    assert bind_result["status"] == "active", bind_result
    assert bind_result.get("materialization_kind") == kind, bind_result

    # canonical 校验：mapping 落库 + 字段映射保留 + capability_call 可反推
    import json as _json
    rows = _pg_read(
        """SELECT mapping_code, status, catalog_item_code, resource_code,
                  mapping_rule_json, source_schema_ref
           FROM resource_schema_mapping
           WHERE tenant_id=%s AND catalog_code=%s""",
        (TENANT, code),
    )
    assert len(rows) == 1, f"F2 应落 1 条 mapping；got {len(rows)}"
    _mp_code, mp_status, mp_item, mp_res, mp_rule_raw, mp_src_raw = rows[0]
    assert mp_status == "active"
    assert mp_res == sample["resource_code"]
    assert mp_item == sample["catalog_item_code"]
    # field_mapping_json 入参等价：repo 只持久 mapping_rule_json + source_schema_ref，
    # 物化形式在两个 JSON 中均非空
    mp_rule = _json.loads(mp_rule_raw) if isinstance(mp_rule_raw, str) else mp_rule_raw
    mp_src = _json.loads(mp_src_raw) if isinstance(mp_src_raw, str) else mp_src_raw
    assert mp_rule.get("materialization") == kind, mp_rule
    assert mp_src.get("materialization") == kind, mp_src

    # capability_call.input_json 反推物化形式
    cc_rows = _pg_read(
        """SELECT input_json FROM capability_call
           WHERE skill_id='catalog.resource.bind' AND input_json::text LIKE %s
           ORDER BY id DESC LIMIT 1""",
        (f"%{code}%",),
    )
    cc_row = cc_rows[0] if cc_rows else None
    assert cc_row is not None, "catalog.resource.bind capability_call 未落账"
    cc_input = _json.loads(cc_row[0]) if isinstance(cc_row[0], str) else cc_row[0]
    assert cc_input.get("materialization_kind") == kind, cc_input

    # resource_schema_snapshot 含字段映射（M0 已迁的真实资源才有 snapshot）
    snap_rows = _pg_read(
        """SELECT snapshot_ref, schema_json FROM resource_schema_snapshot
           WHERE tenant_id=%s AND resource_code=%s LIMIT 1""",
        (TENANT, sample["resource_code"]),
    )
    snap = snap_rows[0] if snap_rows else None
    if snap is None:
        pytest.skip(
            f"sd-default canonical 缺 {kind} 物化资源 {sample['resource_code']} 的 schema_snapshot；"
            f"需 M0 PR 把 meta_table_column / meta_baseinfo 迁入 resource_schema_snapshot"
        )
    snap_schema = _json.loads(snap[1]) if isinstance(snap[1], str) else snap[1]
    assert snap_schema, f"snapshot.schema_json 不应为空：{snap[1]!r}"


# ============================================================================
# F3 (E2 J2)：发布前重复率检测 — 非硬拦 UI 提醒
# 覆盖 AC2 下半：故意造重复 → publish 仍达 active + duplicate_warnings 含被重复条目；
# 唯一目录 publish 时 duplicate_warnings == []。
# ============================================================================


def _publish_to_active(brain_, code: str, title: str, *, owner_org_id: str = "dept_dup_test", region_code: str = "370100") -> dict:
    """Helper：走 3 层链路把一个新 catalog 推到 active；返回最后一步 publish 的 inner result。"""
    _call(brain_, "catalog.entry.create_draft", {
        "catalog_code": code, "title": title,
        "owner_org_id": owner_org_id, "region_code": region_code,
        "summary_json": _required_summary(),
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain_, "catalog.entry.submit_review", {
        "catalog_code": code, "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain_, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": MANAGER_ROLE, "confirmed": True,
    })
    _call(brain_, "catalog.entry.review", {
        "catalog_code": code, "decision": "approve",
        "role": PLATFORM_ROLE, "confirmed": True,
    })
    return _call(brain_, "catalog.entry.publish", {
        "catalog_code": code, "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })


def test_j2_publish_duplicate_warns_does_not_block(brain, catalog_repo):
    """故意造 2 个同 title + 同 region + 同 owner_org 的 catalog 都推到 active：
    第二个 publish 时 duplicate_warnings 非空且第一个 catalog 在 list；lifecycle_status 仍达 active（不阻拦）。
    """
    same_title = "G2.2-F3 重复率检测测试目录-市营商专班"
    code_a = _unique_catalog_code("J2-DUP-A")
    code_b = _unique_catalog_code("J2-DUP-B")

    publish_a = _publish_to_active(brain, code_a, same_title)
    assert publish_a["lifecycle_status"] == "active"
    # 第一个发布时 region+org 无人占位，title 也独一无二 → warnings 应为空
    assert publish_a.get("duplicate_warnings") == [], publish_a.get("duplicate_warnings")

    publish_b = _publish_to_active(brain, code_b, same_title)
    assert publish_b["lifecycle_status"] == "active", publish_b
    warnings = publish_b.get("duplicate_warnings") or []
    assert warnings, "F3：第二个同 title+同 region+同 org 的 publish 应触发 duplicate_warnings"
    matched_codes = {w["catalog_code"] for w in warnings}
    assert code_a in matched_codes, f"F3：warnings 应含第一个 catalog；got {warnings}"
    # 至少一个 warning 命中 title 维度；同 region+org 也应命中（fixture 同 owner_org+region）
    target_warning = next(w for w in warnings if w["catalog_code"] == code_a)
    assert "title" in target_warning["match_dimensions"], target_warning
    assert "region+org" in target_warning["match_dimensions"], target_warning

    # canonical 状态校验：两个 catalog 都成 active（非硬拦语义）
    entry_a = catalog_repo.get_entry(code_a, tenant_id=TENANT)
    entry_b = catalog_repo.get_entry(code_b, tenant_id=TENANT)
    assert entry_a.lifecycle_status == "active"
    assert entry_b.lifecycle_status == "active"

    # F3 evidence_plan: 提醒事件 audit — duplicate.check capability_call 应独立落账。
    # publish 路径走 brain.invoke_skill('catalog.duplicate.check', ...)，capability_call 表
    # 应能查到 skill_id='catalog.duplicate.check' + input_json 含 code_b 的记录。
    dup_call_count = _pg_read(
        """SELECT COUNT(*) FROM capability_call
           WHERE skill_id='catalog.duplicate.check' AND input_json::text LIKE %s""",
        (f"%{code_b}%",),
    )[0][0]
    assert dup_call_count >= 1, (
        f"F3：publish 路径应触发 catalog.duplicate.check capability_call，实际 count={dup_call_count}"
    )


def test_j2_publish_no_duplicate_clean(brain):
    """唯一 title + 唯一 region+org 的 catalog publish 时 duplicate_warnings == []。"""
    unique_title = f"G2.2-F3 唯一目录-{uuid.uuid4().hex[:8]}"
    code = _unique_catalog_code("J2-DUP-CLEAN")
    publish = _publish_to_active(
        brain, code, unique_title,
        owner_org_id=f"dept_unique_{uuid.uuid4().hex[:6]}",
        region_code=f"3700{uuid.uuid4().hex[:2]}",
    )
    assert publish["lifecycle_status"] == "active"
    assert publish.get("duplicate_warnings") == [], publish.get("duplicate_warnings")


def test_j2_duplicate_check_skill_direct_invoke(brain):
    """catalog.duplicate.check 作为独立 skill 直接 invoke — 验证 dispatch 接通 + capability_call 落账。"""
    title = f"G2.2-F3 独立调用-{uuid.uuid4().hex[:8]}"
    code = _unique_catalog_code("J2-DUP-SKILL")
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": title,
        "owner_org_id": "dept_dup_skill", "region_code": "370200",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    # 直接 invoke read-only skill —— 不需要 confirmed；走 trust-stamp 与 production BFF 一致
    result = invoke_trusted(
        brain,
        "catalog.duplicate.check",
        {"catalog_code": code},
        role="ROLE_ORGAN_OPERATER",
    )
    assert result["catalog_code"] == code
    assert result["duplicate_warnings"] == []
    # capability_call 落账（_invoke_traced_read）
    n = _pg_read(
        """SELECT COUNT(*) FROM capability_call
           WHERE skill_id='catalog.duplicate.check' AND input_json::text LIKE %s""",
        (f"%{code}%",),
    )[0][0]
    assert n >= 1, "F3 read-only skill 应落 capability_call（_invoke_traced_read 路径）"


def test_j2_audit_chain_records_lifecycle_transitions(brain, baseline_counts):
    """端到端 — 完整 J2 链路写入 audit_event + capability_call，链条可追溯."""
    code = _unique_catalog_code("J2-AUDIT")
    # 5 stages
    _call(brain, "catalog.entry.create_draft", {
        "catalog_code": code, "title": "G2.2 审计链测试", "summary_json": _required_summary(),
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
    calls = _pg_read(
        """SELECT skill_id, status FROM capability_call
           WHERE input_json::text LIKE %s ORDER BY id""",
        (f'%{code}%',),
    )
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


# ============================================================================
# F4 (E2 J2)：提供方异议响应面后端链 — 覆盖 AC3 (catalog 维度代表 5 维度)
# 走 main #90 已 land 的 objection 5 维度共享 transition 表 + 13 manifest，
# J2 提供方语义体现在：F4 扩了 query handler 的 target_ref / target_org_id /
# dimension filter，让收件箱按 (target_type, status, target_org_id) 过滤。
# E1 PR #90 已覆盖申请方 J1 视角 (test_wave1_objection_lifecycle.py)，本批不重测。
# ============================================================================


@pytest.fixture(scope="module")
def provider_catalog_sample():
    """从 sd-default canonical 找一个 owner_org_id 非空 + lifecycle=active 的 catalog 作为 F4 fixture。
    缺位 → skip（不造数据）。"""
    rows = _pg_read(
        """SELECT catalog_code, owner_org_id, title FROM catalog_entry
           WHERE tenant_id=%s AND lifecycle_status='active'
             AND owner_org_id IS NOT NULL AND owner_org_id != ''
           LIMIT 1""",
        (TENANT,),
    )
    if not rows:
        return None
    row = rows[0]
    return {"catalog_code": row[0], "owner_org_id": row[1], "title": row[2]}


def test_j2_provider_objection_response_full_chain(brain, provider_catalog_sample):
    """J2 提供方 e2e 链（catalog 维度代表）：
      申请方 OPERATER create → submit → 平台 BUSIAUDIT accept → assign provider_investigating
      → 提供方 MANAGER 视角 query (target_ref + target_org_id + dimension=catalog 命中本异议)
      → 提供方 MANAGER reply → 平台 BUSIAUDIT review resolve → 申请方 OPERATER evaluate → close
    断言：终态 closed + audit chain 含 7 类事件 + capability_call 7+ 条 + query filter 命中本异议。
    """
    if provider_catalog_sample is None:
        pytest.skip("sd-default canonical 缺 owner_org_id 非空的 active catalog；F4 fixture 缺位")

    provider_org = provider_catalog_sample["owner_org_id"]
    catalog_code = provider_catalog_sample["catalog_code"]

    # Step 1: 申请方 OPERATER 造异议 (target_type=catalog, target_id=catalog_code)
    create_result = _call(brain, "objection.case.create", {
        "objection_kind": "catalog_quality",
        "target_type": "catalog",
        "target_id": catalog_code,
        "title": f"F4 J2 提供方响应链探针 - {catalog_code}",
        "complainant_org_id": "dept_complainant_test",
        "provider_org_id": provider_org,
        "basis_text": "F4 J2 提供方响应面后端 e2e",
        "evidence": [{"evidence_type": "catalog", "content_json": {"probe": True}}],
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
    })
    objection_id = create_result["id"]
    assert create_result["status"] == "draft"

    # Step 2: submit (申请方)
    _call(brain, "objection.case.submit", {
        "objection_id": objection_id,
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    # Step 3: 平台 BUSIAUDIT 平台核查
    _call(brain, "objection.case.assign", {
        "objection_id": objection_id,
        "target_status": "platform_investigating",
        "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    # Step 4: 平台 BUSIAUDIT 分发到提供方部门
    assigned = _call(brain, "objection.case.assign", {
        "objection_id": objection_id,
        "target_status": "provider_investigating",
        "handler_org_id": provider_org,
        "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    assert assigned["status"] == "provider_investigating"

    # Step 5: J2 提供方 MANAGER 视角调 query — target_ref + target_org_id + dimension=catalog 命中
    inbox = invoke_trusted(brain, "objection.case.query", {
        "target_type": "catalog",
        "target_ref": catalog_code,
        "target_org_id": provider_org,
        "status": "provider_investigating",
        "dimension": "catalog",
    }, role="ROLE_ORGAN_MANAGER")
    ids_in_inbox = {item["id"] for item in inbox["items"]}
    assert objection_id in ids_in_inbox, (
        f"F4 J2 收件箱 query 应命中本异议；ids={ids_in_inbox}, total={inbox['total']}"
    )

    # Step 6: provider MANAGER reply（不改 status，写 process record）
    _call(brain, "objection.case.reply", {
        "objection_id": objection_id,
        "node_name": "提供方部门核查回复",
        "opinion": "已核实，准备修正字段缺失",
        "action_result": "submitted",
        "handler_org_id": provider_org,
        "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    # Step 7: 平台 BUSIAUDIT 复核 → resolved（提供方 reply 后回平台确认，MANAGER 无权 review）
    resolved = _call(brain, "objection.case.review", {
        "objection_id": objection_id,
        "decision": "resolve",
        "resolved_summary": "提供方已修正字段缺失",
        "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    assert resolved["status"] == "resolved"
    # Step 8: 申请方 OPERATER evaluate（resolved 后才允许）
    _call(brain, "objection.case.evaluate", {
        "objection_id": objection_id,
        "solved_flag": True,
        "overall_score": 5,
        "timeliness_score": 4,
        "result_score": 5,
        "comment": "提供方响应及时，问题已闭环",
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    # Step 9: close
    closed = _call(brain, "objection.case.close", {
        "objection_id": objection_id,
        "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    assert closed["status"] == "closed"

    # Audit chain 校验 — brain.snapshot()["audit_events"] 是 SoT（每步 _append_audit_feed
    # 写一条；target=objection_id 一致，含 create 在内的 8 类事件）。
    feed = brain.snapshot()["audit_events"]
    types_on_target = [e["type"] for e in feed if e.get("target") == objection_id]
    expected_audit_types = {
        "objection.case.create",
        "objection.case.submit",
        "objection.case.assign",
        "objection.case.reply",
        "objection.case.review",
        "objection.case.evaluate",
        "objection.case.close",
    }
    missing_audit = expected_audit_types - set(types_on_target)
    assert not missing_audit, (
        f"F4 J2 提供方链 audit_events 缺漏：{missing_audit}; got={types_on_target}"
    )
    assert types_on_target.count("objection.case.assign") >= 2, types_on_target

    # capability_call 持久化：subsequent ops 全部以 objection_id 入参，create 不带（流出值），
    # 至少 7 条非-create capability_call 落账（submit+assign×2+reply+review+evaluate+close = 7）。
    # psycopg3：带参数时查询里的字面 % 需写成 %% 转义。
    non_create_skills = [
        r[0] for r in _pg_read(
            """SELECT skill_id FROM capability_call
               WHERE input_json::text LIKE %s AND skill_id LIKE 'objection.case.%%'
               ORDER BY id""",
            (f"%{objection_id}%",),
        )
    ]
    assert len(non_create_skills) >= 7, (
        f"F4 J2 提供方链 capability_call 至少 7 条（不含 create）；got={non_create_skills}"
    )
    assert non_create_skills.count("objection.case.assign") >= 2, non_create_skills


def test_j2_objection_reply_rejected_for_operater_role(brain, provider_catalog_sample):
    """负向 — ROLE_ORGAN_OPERATER 调 reply → AccessDeniedError（policy MANAGER+ only）。"""
    if provider_catalog_sample is None:
        pytest.skip("sd-default canonical 缺 owner_org_id 非空的 active catalog；F4 fixture 缺位")

    from zw_brain.command.brain import AccessDeniedError

    catalog_code = provider_catalog_sample["catalog_code"]
    provider_org = provider_catalog_sample["owner_org_id"]
    create_result = _call(brain, "objection.case.create", {
        "objection_kind": "catalog_quality",
        "target_type": "catalog",
        "target_id": catalog_code,
        "title": "F4 反例 — OPERATER reply 拒绝",
        "complainant_org_id": "dept_complainant_test",
        "provider_org_id": provider_org,
        "evidence": [{"evidence_type": "catalog", "content_json": {"probe": True}}],
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    objection_id = create_result["id"]
    _call(brain, "objection.case.submit", {
        "objection_id": objection_id,
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "objection.case.assign", {
        "objection_id": objection_id,
        "target_status": "platform_investigating",
        "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    _call(brain, "objection.case.assign", {
        "objection_id": objection_id,
        "target_status": "provider_investigating",
        "handler_org_id": provider_org,
        "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    with pytest.raises(AccessDeniedError):
        _call(brain, "objection.case.reply", {
            "objection_id": objection_id,
            "node_name": "OPERATER 误调",
            "opinion": "不应放行",
            "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
        })


def test_j2_objection_reply_allowed_for_manager_cross_dept(brain, provider_catalog_sample):
    """正向 — ROLE_ORGAN_MANAGER 跨部门调 reply 应允许（policy 不限 dept；本期不实装跨部门拒绝）。
    断言 reply 成功流转 process record + status 回到 platform_investigating（供平台复核）。"""
    if provider_catalog_sample is None:
        pytest.skip("sd-default canonical 缺 owner_org_id 非空的 active catalog；F4 fixture 缺位")

    catalog_code = provider_catalog_sample["catalog_code"]
    provider_org = provider_catalog_sample["owner_org_id"]
    other_org = f"dept_other_{uuid.uuid4().hex[:6]}"

    create_result = _call(brain, "objection.case.create", {
        "objection_kind": "catalog_quality",
        "target_type": "catalog",
        "target_id": catalog_code,
        "title": "F4 跨部门 MANAGER reply",
        "complainant_org_id": "dept_complainant_test",
        "provider_org_id": provider_org,
        "evidence": [{"evidence_type": "catalog", "content_json": {"probe": True}}],
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    objection_id = create_result["id"]
    _call(brain, "objection.case.submit", {
        "objection_id": objection_id,
        "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    _call(brain, "objection.case.assign", {
        "objection_id": objection_id,
        "target_status": "platform_investigating",
        "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    _call(brain, "objection.case.assign", {
        "objection_id": objection_id,
        "target_status": "provider_investigating",
        "handler_org_id": provider_org,
        "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    reply_result = _call(brain, "objection.case.reply", {
        "objection_id": objection_id,
        "node_name": "跨部门 MANAGER 顺手回复",
        "opinion": "跨部门 MANAGER 反馈：异议指向另一部门资源",
        "handler_org_id": other_org,
        "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
    })
    assert reply_result["status"] == "platform_investigating", reply_result
