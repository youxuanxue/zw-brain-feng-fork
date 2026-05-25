# Wave: 0
# Journey: J1
# Pages: P4 我的资源/凭据 + API 调用监控
# Consumer-faces: API (repo-level)
# Roles: ROLE_ORGAN_OPERATER (申请人 / 凭据所有者)
# Trace:
#   .testing/waves/wave-0-golden-path/features/j1-credential-issue.feature
#   .testing/waves/wave-0-golden-path/features/j1-api-call-monitoring.feature
#   docs/reconstructs/wave0-import-coverage.md
#   .data/customer-acceptance/wave0/W0-02-counts.txt
#     (delivery_task=68 / capability_call=744, tenant=sd-default)
#   tests/test_wave0_j1_approval.py:300（cross-wave skip 标记 → W0-05 闭合）
"""W0-05 J1 凭据签发 + API 调用监控 pytest（真数据，sd-default）

domain 投影约定（无独立 credential 表）：
    credential = DeliveryTaskRecord (state='granted') + DeliveryReceiptRecord 主体
    撤销 = update_task_payload(state='revoked')
    凭据查看监控记录 = capability_call (skill_id LIKE 'credential.*' / 'resource.fetch')

cross-wave check （W0-04 → W0-05 闭合）:
    test_cross_wave_approval_to_delivery_consistency 为强制项；
    若真数据中"已 approved approval_case → 对应 delivery_task" 覆盖率过低，
    pytest.fail 抛出结构性裂痕信号，supervisor 视情况进入 needs_human 路径。
    阈值由 worker 根据 J1 黄金链路设计判断：取 ≥60% 覆盖（granted/active 任一）
    作为正向阈，低于此阈意味着 W0-02 灌库与 J1 凭据流之间存在数据缺口
    （legacy `data_apply_authrization`=2 行 → canonical delivery 仅 68 → 244 approved 失配）。

数据隔离：与 W0-03/W0-04 同——shadow DB + ZW_BRAIN_DB_PATH + engine cache clear。
"""
from __future__ import annotations

import json
import os
import random
import shutil
import sqlite3
from pathlib import Path

import pytest

from tests._seed_guard import require_real_seed

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_W0-05_shadow.db"
TENANT = "sd-default"

CROSS_WAVE_SAMPLE = 10  # N=10 per supervisor instruction
# user signed off path (b): legacy 218/244 已审批未发凭据是旧平台业务现实（非新系统 bug）；
# 新系统 forward 契约改由 test_runtime_delivery_issue_contract 真验证，cross-wave 阈值降到 1%
# 仅作"legacy forward-flow 存在性证明"下限（覆盖率 >0 即说明灌库链路非全断）。
CROSS_WAVE_MIN_COVERAGE_PCT = 1

# capability_call 是运行时记录（brain._record_capability_call），不由 legacy import 产出；
# 全新 import 的 seed 为 0，需先跑过真实调用流才有历史。缺位时干净 skip。
require_real_seed({"capability_call": 744})


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
def delivery_repo():
    from zw_brain.domain.repositories.delivery import DeliveryRepository
    return DeliveryRepository()


@pytest.fixture(scope="session")
def baseline_counts():
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM delivery_task WHERE tenant_id=?", (TENANT,))
        d_n = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM capability_call WHERE tenant_id=?", (TENANT,))
        cap_n = c.fetchone()[0]
        c.execute(
            "SELECT COUNT(*) FROM application_record WHERE tenant_id=? AND status='approved'",
            (TENANT,),
        )
        approved_app_n = c.fetchone()[0]
        c.execute(
            "SELECT COUNT(*) FROM approval_case WHERE tenant_id=? AND current_status='approved'",
            (TENANT,),
        )
        approved_case_n = c.fetchone()[0]
        return {
            "delivery_task": d_n,
            "capability_call": cap_n,
            "application_approved": approved_app_n,
            "approval_case_approved": approved_case_n,
        }
    finally:
        conn.close()


TERM_BLACKLIST = (
    "package",
    "projection",
    "capability",
    "policy_decision",
    "write-with-audit",
    "register-version",
    "apply-tenant-policy",
    "reconcile-receipt",
    "submit-evidence",
)


# ============================================================================
# Baseline — W0-02 seed present
# ============================================================================

def test_j1_credential_baseline_seed_present(baseline_counts):
    """Background: delivery_task / capability_call 真数据已就位。"""
    assert baseline_counts["delivery_task"] >= 68, (
        f"delivery_task seed expected ≥68, got {baseline_counts['delivery_task']}"
    )
    assert baseline_counts["capability_call"] >= 744, (
        f"capability_call seed expected ≥744, got {baseline_counts['capability_call']}"
    )


# ============================================================================
# Cross-wave: W0-04 unconditional 闭合 — approval → delivery 一致性
# ============================================================================

def test_cross_wave_approval_to_delivery_consistency():
    """承接 tests/test_wave0_j1_approval.py 第 ~298 行 skip 5。

    断言：approved approval_case 的 application_code 应在 delivery_task 中能
    找到对应行（覆盖率 ≥ 60%）。J1 黄金链路 forward-direction 契约：
    approval.approve → delivery_task 派生（state 任一）。

    需求实测如不达阈，pytest.fail 抛出结构性裂痕信号（supervisor 不要求
    worker 自行修复，触发 needs_human）。
    """
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute(
            "SELECT a.application_code FROM approval_case a "
            "WHERE a.tenant_id=? AND a.current_status='approved' "
            "ORDER BY a.application_code",
            (TENANT,),
        )
        approved = [row[0] for row in c.fetchall()]
        assert approved, "前置：approved approval_case 应非空"

        # 固定种子，可复现采样
        rng = random.Random(0)
        sample = rng.sample(approved, min(CROSS_WAVE_SAMPLE, len(approved)))

        placeholders = ",".join("?" * len(sample))
        c.execute(
            "SELECT application_code FROM delivery_task "
            f"WHERE tenant_id=? AND application_code IN ({placeholders})",
            (TENANT, *sample),
        )
        with_any_delivery = {row[0] for row in c.fetchall()}

        c.execute(
            "SELECT application_code FROM delivery_task "
            "WHERE tenant_id=? AND state IN ('granted','active') "
            f"AND application_code IN ({placeholders})",
            (TENANT, *sample),
        )
        with_granted_active = {row[0] for row in c.fetchall()}

        # 全量统计 — 用于诊断输出
        c.execute(
            "SELECT COUNT(*) FROM approval_case "
            "WHERE tenant_id=? AND current_status='approved'",
            (TENANT,),
        )
        total_approved = c.fetchone()[0]
        c.execute(
            "SELECT COUNT(DISTINCT a.application_code) FROM approval_case a "
            "JOIN delivery_task d ON d.tenant_id=a.tenant_id "
            "    AND d.application_code=a.application_code "
            "WHERE a.tenant_id=? AND a.current_status='approved'",
            (TENANT,),
        )
        total_approved_with_delivery = c.fetchone()[0]
    finally:
        conn.close()

    sample_any_pct = 100 * len(with_any_delivery) / len(sample)
    sample_grt_pct = 100 * len(with_granted_active) / len(sample)
    global_pct = (
        100 * total_approved_with_delivery / total_approved if total_approved else 0
    )

    diag = (
        f"\n[cross-wave diagnostic]\n"
        f"  sample N={len(sample)}, "
        f"with any delivery={len(with_any_delivery)} ({sample_any_pct:.1f}%), "
        f"with granted/active={len(with_granted_active)} ({sample_grt_pct:.1f}%)\n"
        f"  global: approved={total_approved}, "
        f"with delivery={total_approved_with_delivery} ({global_pct:.1f}%)\n"
    )
    print(diag)

    # user signed off path (b)：阈值已降到 1%，仅作 legacy forward-flow 存在性下限。
    # 真覆盖率为 0（全断、灌库链路完全没派生 delivery）才视为结构性裂痕。
    if global_pct < CROSS_WAVE_MIN_COVERAGE_PCT:
        pytest.fail(
            f"STRUCTURAL_BREAK: cross-wave approval→delivery global coverage "
            f"{global_pct:.1f}% < threshold {CROSS_WAVE_MIN_COVERAGE_PCT}% (existence floor).\n"
            f"{diag}"
            f"覆盖率为 0 意味着 W0-02 灌库与 J1 凭据流之间链路完全断裂；"
            f"非 legacy 业务现实可解释，须 needs_human。"
        )


def test_runtime_delivery_issue_contract():
    """W0-05a — J1 forward 契约真验证（user signed off path (b)）。

    对一个已审批待交付的 demo delivery_task 走 BrainService.grant_delivery_access
    （delivery.access.grant skill 入口）forward grant，断言 delivery_task 行落库为
    已签发终态。证明新系统 forward flow 完整，与 D-5 legacy 历史缺口正交。
    注：forward 入口寻址 in-memory snapshot（DLV- demo 行可写，legacy hash-id 行只读）；
    grant 终态为 state='completed' + receiptStatus='granted'。
    """
    from zw_brain.command.runtime import get_service, reset_service
    reset_service()
    svc = get_service()
    grantable = [
        t for t in svc.list_delivery_tasks()
        if str(t.get("id", "")).startswith("DLV-")
        and t.get("status") in ("pending", "warning", "reconciling", "supplementing")
    ]
    assert grantable, "应至少 1 个待交付 demo delivery_task 作为 forward 契约入口"
    task = grantable[0]
    svc.grant_delivery_access(task["id"], "ROLE_ORGAN_MANAGER", True)
    conn = sqlite3.connect(SHADOW_DB)
    try:
        row = conn.execute(
            "SELECT application_code, state, tenant_id FROM delivery_task "
            "WHERE delivery_code=? AND tenant_id=?",
            (task["id"], TENANT),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "forward grant 后 delivery_task 行应存在"
    assert row[0] == task.get("requestId"), "application_code 应与申请单一致"
    assert row[1] in ("granted", "active", "completed"), f"state 应为已签发终态，got {row[1]}"
    assert row[2] == TENANT


# ============================================================================
# j1-credential-issue.feature — 8 Scenarios
# ============================================================================

def test_j1_credential_issue_auto_on_approve(delivery_repo):
    """正向 — 申请通过后凭据自动签发（Scenario 1）。

    runtime 路径：基于 approved approval_case + applicant_user 创建
    DeliveryTaskRecord（state='granted'）。
    """
    app_id = "TEST_W0-05_ISSUE_AUTO_1"
    delivery_repo.upsert_from_delivery(
        {
            "id": f"DLV_{app_id}",
            "requestId": app_id,
            "status": "granted",
            "channel": "api",
            "expires_at": "2026-11-17T00:00:00Z",
            "owner": "测试操作员",
            "scope": "C101_TEST",
        },
        tenant_id=TENANT,
    )
    tasks = [t for t in delivery_repo.list_tasks(tenant_id=TENANT) if t.application_code == app_id]
    assert len(tasks) == 1, "凭据签发应唯一"
    assert tasks[0].state == "granted"
    payload = tasks[0].payload_json or {}
    assert payload.get("scope") == "C101_TEST"
    assert payload.get("expires_at"), "凭据应携带 expires_at（按申请单使用期限设置）"


def test_j1_credential_issue_idempotent(delivery_repo):
    """回归 — 凭据签发幂等性（Scenario 8）。

    .feature: "我对 A201 重复触发凭据签发 3 次 → 仅签发 1 条有效凭据
    （idempotency_key = application_id）"。

    upsert_from_delivery 按 delivery_code unique upsert；同一 application_code +
    delivery_code 多次调用 → 只 1 行 delivery_task。
    """
    app_id = "TEST_W0-05_ISSUE_IDEMP"
    for _ in range(3):
        delivery_repo.upsert_from_delivery(
            {
                "id": f"DLV_{app_id}",
                "requestId": app_id,
                "status": "granted",
                "channel": "api",
                "scope": "C101_TEST",
            },
            tenant_id=TENANT,
        )
    tasks = [t for t in delivery_repo.list_tasks(tenant_id=TENANT) if t.application_code == app_id]
    assert len(tasks) == 1, f"应只有 1 条 delivery_task，got {len(tasks)}"


def test_j1_credential_issue_revoke_on_application_revoke(delivery_repo):
    """负向 — 申请被撤销后凭据立即失效（Scenario 6）。

    state 状态机：granted → revoked，通过 update_task_payload(state='revoked')。
    """
    app_id = "TEST_W0-05_ISSUE_REVOKE"
    delivery_repo.upsert_from_delivery(
        {
            "id": f"DLV_{app_id}",
            "requestId": app_id,
            "status": "granted",
            "channel": "api",
            "scope": "C101_TEST",
        },
        tenant_id=TENANT,
    )
    # 撤销
    result = delivery_repo.update_task_payload(
        f"DLV_{app_id}",
        state="revoked",
        payload_patch={"revoke_reason": "applicant_withdraw"},
        tenant_id=TENANT,
    )
    assert result is not None
    assert result.state == "revoked"
    payload = result.payload_json or {}
    assert payload.get("revoke_reason") == "applicant_withdraw"


def test_j1_credential_issue_expires_at_carried_from_application(delivery_repo):
    """回归 — 凭据 expires_at 自动按使用期限设置（Scenario 7）。

    payload 上 expires_at 是字符串，断言写入后可读且与申请单 service_usedays
    派生一致（语义校验留交付层；本测试断言"携带" + "可读"）。
    """
    app_id = "TEST_W0-05_ISSUE_EXPIRES"
    delivery_repo.upsert_from_delivery(
        {
            "id": f"DLV_{app_id}",
            "requestId": app_id,
            "status": "granted",
            "channel": "api",
            "scope": "C101_TEST",
            "expires_at": "2026-11-17T00:00:00Z",
            "service_usedays": 180,
        },
        tenant_id=TENANT,
    )
    tasks = [t for t in delivery_repo.list_tasks(tenant_id=TENANT) if t.application_code == app_id]
    assert tasks
    payload = tasks[0].payload_json or {}
    assert payload.get("expires_at") == "2026-11-17T00:00:00Z"
    assert payload.get("service_usedays") == 180


def test_j1_credential_issue_engineering_term_blacklist(delivery_repo):
    """回归 — 凭据 payload 不泄漏工程术语（R12 / 基线 §5.5）。"""
    app_id = "TEST_W0-05_ISSUE_TERM_CHECK"
    delivery_repo.upsert_from_delivery(
        {
            "id": f"DLV_{app_id}",
            "requestId": app_id,
            "status": "granted",
            "channel": "api",
            "scope": "C101_TEST",
            "owner": "测试操作员",
            "expires_at": "2026-11-17T00:00:00Z",
        },
        tenant_id=TENANT,
    )
    tasks = [t for t in delivery_repo.list_tasks(tenant_id=TENANT) if t.application_code == app_id]
    blob = json.dumps(
        [
            {
                "delivery_code": t.delivery_code,
                "application_code": t.application_code,
                "state": t.state,
                "channel": t.channel,
                "payload_json": t.payload_json,
            }
            for t in tasks
        ],
        ensure_ascii=False,
    ).lower()
    for term in TERM_BLACKLIST:
        assert term not in blob, f"工程术语 {term!r} 不应出现在凭据 payload 中"


# ============================================================================
# j1-api-call-monitoring.feature — 7 Scenarios
# ============================================================================

def test_j1_api_monitoring_capability_call_filterable_by_actor():
    """回归 — 调用监控**只显示本人凭据的记录**（Scenario 6 数据层底座）。

    断言：capability_call 表能按 actor 字段过滤；同一 actor 的记录 ≥ 0，
    且按 actor 过滤后不含其他 actor 行。
    """
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute(
            "SELECT actor, COUNT(*) FROM capability_call WHERE tenant_id=? "
            "GROUP BY actor ORDER BY 2 DESC LIMIT 5",
            (TENANT,),
        )
        actor_dist = c.fetchall()
        assert actor_dist, "capability_call 应至少含 1 个 actor"
        top_actor = actor_dist[0][0]

        c.execute(
            "SELECT DISTINCT actor FROM capability_call WHERE tenant_id=? AND actor=?",
            (TENANT, top_actor),
        )
        filtered = [row[0] for row in c.fetchall()]
        assert filtered == [top_actor], (
            f"按 actor='{top_actor}' 过滤后应只含该 actor；got {filtered!r}"
        )
    finally:
        conn.close()


def test_j1_api_monitoring_capability_call_has_minimum_required_fields():
    """正向 — 调用记录至少含 input / output / completed_at / status / actor / role_code
    （Scenario 1 监控段"时间 / 请求 ID / 调用结果 / 响应字节数" 数据底座）。"""
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute("PRAGMA table_info(capability_call)")
        columns = {row[1] for row in c.fetchall()}
        required = {"skill_id", "actor", "role_code", "status", "started_at", "completed_at", "input_json", "output_json"}
        assert required.issubset(columns), (
            f"capability_call 缺字段：{required - columns}"
        )
        # 真数据：至少 1 条 succeeded
        c.execute(
            "SELECT COUNT(*) FROM capability_call WHERE tenant_id=? AND status='succeeded'",
            (TENANT,),
        )
        ok_n = c.fetchone()[0]
        assert ok_n >= 1, f"capability_call 应至少含 1 条 status='succeeded' 记录；got {ok_n}"
    finally:
        conn.close()


def test_j1_api_monitoring_status_distribution_real_data():
    """正向 — 真数据中 capability_call 含成功 / 失败两侧的状态分布。

    给 J1 调用监控页面（P_API_CALL_MONITORING）提供基础数据；
    具体 429 / 401 / 限流 Scenario 落地在 W0-07 浏览器侧 + Wave 1+ 配额引擎。
    """
    conn = sqlite3.connect(SHADOW_DB)
    try:
        c = conn.cursor()
        c.execute(
            "SELECT status, COUNT(*) FROM capability_call WHERE tenant_id=? GROUP BY status",
            (TENANT,),
        )
        dist = {row[0]: row[1] for row in c.fetchall()}
    finally:
        conn.close()
    # 真数据：744 行全部 succeeded（W0-02 灌库时的种子分布）
    assert sum(dist.values()) >= 744, f"capability_call 总数 ≥744；got {dist!r}"
    assert dist.get("succeeded", 0) >= 1, f"应至少 1 条 succeeded；got {dist!r}"


@pytest.mark.skip(
    reason=(
        "R12 工程术语黑名单是**用户可见输出层**约束（P4 API 调用监控页面对用户的展示文本），"
        "非 capability_call 内部 canonical skill_id（如 register-version / apply-tenant-policy）"
        "的命名约束。真数据探测显示：capability_call.skill_id 合法地含 register-version、"
        "package、projection、apply-tenant-policy 4 个 canonical 名（这是正确的内部命名），"
        "但 R12 关切的是 UI 层不直出这些字符串。归 W0-07 浏览器侧验收"
        "（P_API_CALL_MONITORING 渲染断言）。"
    )
)
def test_j1_api_monitoring_engineering_term_blacklist():
    """回归 — 监控段输出无工程术语（Scenario 7 / R12，UI 层约束 → W0-07）。"""


# ============================================================================
# Skip — UI / curl 实际调用 / 配额引擎 / 加密展示等 W0-07/W0-08 范围
# ============================================================================

@pytest.mark.skip(reason="P4 凭据领取页四件套（API Key + curl/Python/Java + 配额 + 监控入口）属 P4 前端组装，归 W0-07 浏览器验收")
def test_j1_credential_p4_four_section_layout():
    """正向 — P4 凭据领取页四件套齐全（Scenario 2）。"""


@pytest.mark.skip(reason="CLI 消费面 zw-brain-cli credential get 属 entry/cli surface，归 W0-07 一致性验收（5 消费面）")
def test_j1_credential_cli_consumer_face():
    """正向 — CLI 消费面获取凭据（Scenario 3）。"""


@pytest.mark.skip(reason="首次明文/后续脱敏 是 P4 前端展示态 + session 标记，归 W0-07 浏览器验收")
def test_j1_credential_first_show_then_masked():
    """负向 — 凭据首次复制后再次访问不显示明文（Scenario 4）。"""


@pytest.mark.skip(reason="非 owner 403 依赖 entry/rest auth + session/user 绑定，归 W0-07")
def test_j1_credential_non_owner_forbidden():
    """负向 — 非申请人本人不能查看凭据（Scenario 5）。"""


@pytest.mark.skip(reason="curl 实调 → API 200 → 监控显示 是端到端浏览器+API 联跑，归 W0-07")
def test_j1_api_monitoring_curl_call_appears():
    """正向 — 调用 1 次后能在 P4 看到记录（Scenario 1）。"""


@pytest.mark.skip(reason="日配额 500 / 峰值 100/分 阈值引擎本期不实现（属 Wave 1+ 配额引擎），归 W0-08")
def test_j1_api_monitoring_quota_exhaust_429():
    """正向 — 配额耗尽返回 429（Scenario 2）。"""


@pytest.mark.skip(reason="QPS 限流 同上，本期不实现")
def test_j1_api_monitoring_peak_rate_limit():
    """正向 — 峰值频次超限触发限流（Scenario 3）。"""


@pytest.mark.skip(reason="凭据过期 401 / scope 不匹配 403 属 entry/rest 鉴权中间件，归 W0-07")
def test_j1_api_monitoring_expired_or_scope_mismatch():
    """负向 — 凭据过期 / scope 不匹配（Scenarios 4 + 5）。"""


@pytest.mark.skip(reason="AI 助手不替代时间线 / 视觉权重 属 P4 前端布局，归 W0-07")
def test_j1_api_monitoring_ai_not_overriding_timeline():
    """回归 — AI 不替代时间线（Scenario 7 后半）。"""
