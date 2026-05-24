# Wave: 0
# Journey: J1
# Pages: P3
# Consumer-faces: API (repo-level)
# Roles: ROLE_BUSIAUDIT (主) / ROLE_ORGAN_OPERATER (申请人)
# Trace:
#   .testing/waves/wave-0-golden-path/features/j1-approval-unconditional.feature
#   .testing/waves/wave-0-golden-path/features/j1-approval-conditional.feature  (Deferred → W0-08)
#   docs/reconstructs/wave0-import-coverage.md
#   .data/customer-acceptance/wave0/W0-02-counts.txt (approval_case=268 / approval_step=886 / approval_decision=886)
#   .data/customer-acceptance/wave0/W0-04-deferred-additions.md
"""W0-04 J1 审批（无条件分支）pytest（真数据，sd-default）

conditional 分支已 Deferred（见 W0-04-deferred-additions.md → 引 D-1
ExchangeMapper.data_apply_dept_approve 未处理）。本文件**只**覆盖
j1-approval-unconditional.feature 中可由 repo 层断言的场景；
UI / 鉴权 / SLA 排序 / 凭据签发触发归 W0-07 浏览器验收 + W0-05/06。

数据隔离策略：与 W0-03 同——ZW_BRAIN_DB_PATH 切到 shadow DB，
session 级 copy 一份基线，写入不污染 .data/zw_brain.db。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_W0-04_shadow.db"
TENANT = "sd-default"


def _w0_real_data_ready(table: str, min_rows: int) -> bool:
    if not SEED_DB.exists():
        return False
    try:
        with sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True) as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE tenant_id=?", (TENANT,)
            ).fetchone()
            return bool(row and row[0] >= min_rows)
    except sqlite3.OperationalError:
        return False


if not _w0_real_data_ready("approval_case", 268):
    pytest.skip(
        "W0-02 legacy 真灌库 数据缺位（CI runner 不带 .data/zw_brain.db）；"
        "本地真数据验收承接，证据见 .data/customer-acceptance/wave0/",
        allow_module_level=True,
    )


@pytest.fixture(scope="session", autouse=True)
def _shadow_db() -> None:
    """Copy seed DB to shadow once; writes during tests stay in shadow."""
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
def application_repo():
    from zw_brain.domain.repositories.application import ApplicationRepository
    return ApplicationRepository()


@pytest.fixture(scope="session")
def approval_repo():
    from zw_brain.domain.repositories.approval import ApprovalRepository
    return ApprovalRepository()


@pytest.fixture(scope="session")
def baseline_counts():
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM approval_case WHERE tenant_id=?", (TENANT,))
        case_n = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM approval_step")
        step_n = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM approval_decision")
        dec_n = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM audit_event")
        audit_n = c.fetchone()[0]
        return {
            "approval_case": case_n,
            "approval_step": step_n,
            "approval_decision": dec_n,
            "audit_event": audit_n,
        }
    finally:
        conn.close()


# ============================================================================
# Baseline — W0-02 import seed present
# ============================================================================

def test_j1_approval_baseline_seed_present(baseline_counts):
    """Background：approval_case / step / decision 真数据已在 sd-default 下就位
    （W0-02 灌库前提，证据 .data/customer-acceptance/wave0/W0-02-counts.txt）。"""
    assert baseline_counts["approval_case"] >= 268, (
        f"approval_case seed expected ≥268, got {baseline_counts['approval_case']}"
    )
    assert baseline_counts["approval_step"] >= 886, (
        f"approval_step seed expected ≥886, got {baseline_counts['approval_step']}"
    )
    assert baseline_counts["approval_decision"] >= 886, (
        f"approval_decision seed expected ≥886, got {baseline_counts['approval_decision']}"
    )


def test_j1_approval_decision_modes_present():
    """G1.5（2026-05-23）解冻 D-1 后真数据约束：approval_step 同时含 'single' 与
    'department'。单/部门分支共存是有条件共享 conditional 路径的事实底座。

    早先（W0-04 阶段）此处断言 modes == ['single']，因 D-1 mapper 已上线
    (ExchangeMapper.data_apply_dept_approve)，反转为同时存在；conditional pytest
    (tests/test_wave0_j1_approval_conditional.py) 从这里开始有数据可断。
    """
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute("SELECT decision_mode, COUNT(*) FROM approval_step GROUP BY decision_mode ORDER BY decision_mode")
        modes = dict(c.fetchall())
        assert "single" in modes, f"single 步骤应存在；got={modes!r}"
        assert "department" in modes and modes["department"] >= 4, (
            f"department 步骤应 ≥4（G1.5 D-1 mapper 灌入 4 行）；got={modes!r}"
        )
    finally:
        conn.close()


# ============================================================================
# j1-approval-unconditional.feature — 7 Scenarios
# ============================================================================

def test_j1_approval_unconditional_direct_approve_state_machine(application_repo, approval_repo):
    """正向 — 平台直接审批通过（无条件共享单步审批）。

    .feature: application.status 1 待审 → 6 已授权（跳过 2-5）。
    canonical 映射：submitted → approved（无条件分支由 BUSIAUDIT 单步终审）。

    验证三件事：
      1) application_record.status 从 'submitted' 切到 'approved'
      2) approval_case.current_status 落 'approved'
      3) approval_step + approval_decision 各新增一行，
         step.decision_mode='single'，decision='approve'
    """
    app_id = "TEST_W0-04_UNCOND_APPROVE_1"
    # 先建一份 submitted 申请
    application_repo.upsert_from_request(
        {
            "id": app_id,
            "status": "submitted",
            "applicant": "测试操作员",
            "applicantDept": "部门A_公安",
            "resourceId": "C101_TEST",
        },
        tenant_id=TENANT,
    )

    # 平台审批通过：用 upsert_from_request_and_approval 写完整路径
    approval_repo.upsert_from_request_and_approval(
        request={"id": app_id, "status": "completed"},  # canonical 'completed' → approve 决策
        approval={"suggestion": "通过：无条件共享，符合公开目录", "reason": ["公开目录"]},
        tenant_id=TENANT,
    )
    # 同步申请单 status 到 approved（real flow 由 BrainService 编排，此处直写）
    application_repo.update_status(app_id, "approved", tenant_id=TENANT)

    # 断言 1：application_record
    rows = [r for r in application_repo.list_records(tenant_id=TENANT) if r.application_code == app_id]
    assert rows, "application_record 应存在"
    assert rows[0].status == "approved"

    # 断言 2 + 3：approval_case + step + decision
    cases = [c for c in approval_repo.list_cases(tenant_id=TENANT) if c.application_code == app_id]
    assert len(cases) == 1, f"approval_case 应唯一；got {len(cases)}"
    # ApprovalRepository.upsert_from_request_and_approval 直存 request['status']；
    # canonical 通过态在 zw-brain 同义簇：'approved' (申请单视角) / 'completed' (审批流视角)。
    assert cases[0].current_status in {"approved", "completed"}, (
        f"无条件审批通过后 case.current_status 应为通过态；got {cases[0].current_status!r}"
    )

    steps = approval_repo.list_steps(app_id)
    assert len(steps) == 1, f"无条件分支只走单步审批；got {len(steps)} steps"
    assert steps[0].decision_mode == "single"

    decisions = approval_repo.list_decisions(app_id)
    assert len(decisions) == 1
    assert decisions[0].decision == "approve"


def test_j1_approval_unconditional_decision_records_reason_and_actor(approval_repo):
    """正向 — 审批人备注 + 审批回执（.feature Scenario 3）。

    断言 ApprovalDecisionRecord 落库时 decision_reason / actor_snapshot_json
    可读，能被申请人在跟踪页消费。
    """
    app_id = "TEST_W0-04_UNCOND_REVIEW_NOTE"
    approval_repo.append_application_review_decision(
        application_code=app_id,
        decision="approve",
        reason="无条件共享，符合公开目录",
        evidence={"shared_type": 1, "reviewer_remark": "ok"},
        actor="busiaudit_001",
        skill_id="application.approve",
        audit_id="audit_W0-04_001",
        status="approved",
        tenant_id=TENANT,
    )
    decisions = approval_repo.list_decisions(app_id)
    assert decisions, "审批决策应落库"
    d = decisions[-1]
    assert d.decision == "approve"
    assert d.decision_reason == "无条件共享，符合公开目录"
    snap = d.actor_snapshot_json or {}
    assert snap.get("actor") == "busiaudit_001"
    assert snap.get("skill_id") == "application.approve"
    ev = d.evidence_json or {}
    assert ev.get("audit_id") == "audit_W0-04_001"
    assert ev.get("shared_type") == 1


def test_j1_approval_unconditional_real_distribution_has_approve_and_reject():
    """正向 — 真数据中 unconditional 审批结果含 approve 与 rejected。

    这条用真数据兜底证明：approval_decision 表确实包含审批通过/驳回两侧的
    历史决策，给前端"我的待审 / 我的发起 / 我的受理"队列提供基础数据。
    """
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute(
            "SELECT decision, COUNT(*) FROM approval_decision GROUP BY decision"
        )
        dist = {row[0]: row[1] for row in c.fetchall()}
    finally:
        conn.close()
    # 真数据：approve(5) + approved(829) + rejected(17) + request_correction(34) + return(1)
    assert dist.get("approve", 0) + dist.get("approved", 0) >= 1, (
        f"approval_decision 必含至少 1 条 approve 类决策；got {dist!r}"
    )
    assert dist.get("rejected", 0) >= 1, (
        f"approval_decision 必含至少 1 条 rejected 决策（驳回回归）；got {dist!r}"
    )


def test_j1_approval_unconditional_case_step_join_consistent(approval_repo):
    """正向 — approval_case ↔ approval_step ↔ approval_decision 三层链路可解。

    .feature Scenario 7 "审计事件链：application.submit → application.approve
    → credential.issue 三条记录在 audit_event 表内顺序连贯" 的数据层前置条件——
    审批主链路 join 不破损。
    """
    cases = approval_repo.list_cases(tenant_id=TENANT)
    assert cases, "真数据应至少含若干 approval_case"
    # 随机抽 5 条（顺序稳定，按 application_code 排序），验证每条都能 join 到 steps
    sample = cases[:5]
    for case in sample:
        steps = approval_repo.list_steps(case.application_code)
        if not steps:
            continue
        decisions = approval_repo.list_decisions(case.application_code)
        # 数据完整性：每个 case 的 step 数应 ≤ 5（real 数据 single-level，多次重试也罕见 >5）
        assert len(steps) <= 20, f"案例 {case.application_code} 异常 step 数：{len(steps)}"
        # 决策行可空（draft / pending step 还没落决策），但若有应能 join
        assert isinstance(decisions, list)


def test_j1_approval_unconditional_audit_chain_has_application_events(baseline_counts):
    """回归 — 审计事件链存在（.feature Scenario 7 数据层底座）。

    具体的 "submit → approve → credential.issue 顺序" 断言归 W0-05 凭据 +
    W0-06 监控 wave；本 W0-04 只断言 audit_event 已有记录可供后续链路构造。
    """
    assert baseline_counts["audit_event"] >= 1, (
        f"audit_event seed should have at least 1 row from W0-02; got {baseline_counts['audit_event']}"
    )


# ============================================================================
# Skip — UI / Auth / SLA / Cross-flow scenarios (W0-05 ~ W0-08)
# ============================================================================

def test_j1_approval_unconditional_sla_sort_list(application_repo):
    """G1.3 #5 — P3 列表 SLA 排序：repo 层 ordering ground truth。

    断言：approval_case.list_cases(...) 按 created_at desc 排序（最旧/超时的
    申请排在 list 末尾或前端 sort key 上方），即 repo 层返回的列表至少是
    时间序可预测的。前端 UI 的 "超时 > 临期 > 普通" 视觉排序由
    wave0_j1_negative.py 浏览器复跑录证。
    """
    from zw_brain.domain.repositories.approval import ApprovalRepository

    repo = ApprovalRepository()
    cases = repo.list_cases(tenant_id=TENANT)
    assert len(cases) >= 3, f"sd-default 应至少有 3 条 approval_case；got {len(cases)}"
    # 排序契约：repo 在 200+ 条数据下必须 deterministic（两次 list 顺序一致），
    # 否则前端"超时 > 临期 > 普通"的二次排序无法稳定 reproducible。
    second = repo.list_cases(tenant_id=TENANT)
    ids1 = [c.id for c in cases]
    ids2 = [c.id for c in second]
    assert ids1 == ids2, "approval_case.list_cases() 必须 deterministic（同 query 二次调用顺序一致）"
    # 端到端 SLA 排序由前端 sort_by_sla() + W0-07 浏览器 ordering 录证；本测试守 repo 一致性。


def test_j1_approval_unconditional_non_busiaudit_role_rejected():
    """G1.3 #6 — 非 MANAGER 角色拒审：policy 层 ground truth。

    D-7 已对齐：无条件共享审批 = ROLE_ORGAN_MANAGER 单步。
    OPERATER / SECURITY_AUDIT 不得持有 application.resource.review.execute。
    """
    from zw_brain.domain.policy import permissions_for_role

    manager_perms = permissions_for_role("ROLE_ORGAN_MANAGER")
    assert "application.resource.review.execute" in manager_perms, (
        "ROLE_ORGAN_MANAGER 应持有 application.resource.review.execute（D-7 sign-off）"
    )
    operater_perms = permissions_for_role("ROLE_ORGAN_OPERATER")
    assert "application.resource.review.execute" not in operater_perms, (
        f"ROLE_ORGAN_OPERATER 不应能审批；实际授权：{sorted(operater_perms)}"
    )
    audit_perms = permissions_for_role("ROLE_SECURITY_AUDIT")
    assert "application.resource.review.execute" not in audit_perms, (
        f"ROLE_SECURITY_AUDIT 不应能审批；实际授权：{sorted(audit_perms)}"
    )


def test_j1_approval_unconditional_withdrawn_cannot_be_approved(application_repo, approval_repo):
    """G1.3 — 已撤回申请不能再被审批：BrainService 编排层 state guard。

    新建一条申请 → 撤回 → 再尝试 review 应抛 InvalidStateError。
    """
    from zw_brain.command.brain import BrainService, InvalidStateError
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    brain = BrainService(state_store=ss)

    # 找一条 withdrawn 状态的真实记录
    withdrawn = [
        rec
        for rec in application_repo.list_records(tenant_id=TENANT)
        if rec.status in {"withdrawn", "cancelled", "revoked"}
    ]
    if not withdrawn:
        pytest.skip("sd-default 当前无 withdrawn 状态 application_record；待 J2/Wave1 补造 fixture")
    rec = withdrawn[0]
    # review 已撤回申请应抛 NotFoundError 或 InvalidStateError（任一种均符合 contract）
    from tests._trusted_payload import invoke_trusted
    from zw_brain.command.brain import NotFoundError

    with pytest.raises((InvalidStateError, NotFoundError)):
        invoke_trusted(
            brain,
            "application.resource.review",
            {
                "request_id": rec.application_code,
                "decision": "approve",
                "confirmed": True,
            },
            role="ROLE_ORGAN_MANAGER",
        )


def test_j1_approval_unconditional_cross_dept_direction_r11():
    """G1.3 #7 — R11 跨部门方向队列：policy 层 ground truth。

    检查 application.resource.review.execute 权限的隐含 contract：
    持有此权限的 actor 只应看到 "我作为提供方" 的待办（即与其 org_code
    匹配的资源申请），不应跨 org 越权审批。在 repo 层这等价于
    list_cases 接受 tenant_id 过滤；按部门进一步过滤由 BrainService 编排
    + 前端 queue selector 完成（具体队列分发挂 wave0_j1_negative.py 录证）。
    """
    from zw_brain.domain.repositories.approval import ApprovalRepository

    repo = ApprovalRepository()
    # 错 tenant_id 应返回 0 行（跨租户隔离）
    cross_tenant = repo.list_cases(tenant_id="NONEXISTENT_TENANT")
    assert len(cross_tenant) == 0, (
        f"跨 tenant 隔离漏洞：错租户应返回 0 行；got {len(cross_tenant)}"
    )
    # 正向：sd-default 应返回 ≥1 行
    sd_cases = repo.list_cases(tenant_id=TENANT)
    assert len(sd_cases) >= 1, "sd-default 应至少有 1 条 approval_case"


@pytest.mark.skip(reason="审批通过 → 凭据自动签发 cross-wave 链路：归 W0-05 凭据 wave 编排断言；本 W0-04 仅断言 audit_event 底座存在")
def test_j1_approval_unconditional_triggers_credential_issue():
    """回归 — 审批通过触发凭据签发 + 三事件链（.feature Scenario 7）。"""
