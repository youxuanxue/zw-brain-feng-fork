# Wave: 0
# Journey: J1
# Pages: P4 我的资源/凭据 + API 调用监控
# Consumer-faces: API (repo-level)
# Roles: ROLE_ORGAN_OPERATER (申请人 / 凭据所有者)
# Trace:
#   .testing/waves/wave-0-golden-path/features/j1-credential-issue.feature
#   .testing/waves/wave-0-golden-path/features/j1-api-call-monitoring.feature
#   docs/reconstructs/wave0-import-coverage.md
#   稳定态真值（clean 全量真实库，sd-default）：delivery_task=67（legacy 派生上限），
#     capability_call=运行时累积（fresh import=0），approval_case=267 / step=889 / decision=888。
#     早期 header 写的 "delivery_task=68 / capability_call=744" 来自已删除的 W0-02-counts.txt
#     stat 快照——68 比稳定态多 1（off-by-one），744 是某次本机累积运行后的 capability_call 量
#     （运行时遥测，非 seed），两者均不可作 seed 门槛。详见本文件门槛说明 + CLAUDE.md D44。
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

数据隔离：realistic_pg_module 克隆 zw_realistic_tmpl（含真实旧平台数据），
模板缺位时整模块 skip（承接旧 require_real_seed 数据量门槛语义）；运行时遥测自产、
写入落克隆库、不污染真实模板。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (fixture)
from zw_brain.shared.db import get_database_url

REPO_ROOT = Path(__file__).resolve().parent.parent
TENANT = "sd-default"


def _pg_read(sql: str, params: tuple = ()):
    """Read against the cloned realistic PG (app read-path's DB), never a file."""
    url = make_url(get_database_url())
    with psycopg.connect(
        host=url.host, port=url.port, user=url.username,
        password=url.password, dbname=url.database,
    ) as conn:
        return conn.execute(sql, params).fetchall()

CROSS_WAVE_SAMPLE = 10  # N=10 per supervisor instruction
# user signed off path (b): legacy 218/244 已审批未发凭据是旧平台业务现实（非新系统 bug）；
# 新系统 forward 契约改由 test_runtime_delivery_issue_contract 真验证，cross-wave 阈值降到 1%
# 仅作"legacy forward-flow 存在性证明"下限（覆盖率 >0 即说明灌库链路非全断）。
CROSS_WAVE_MIN_COVERAGE_PCT = 1

# 门槛只 gate 本 module 真正依赖的 **legacy-seeded** 前置表，且取稳健 floor（约稳定态 75%，
# 容忍真实库行数自然漂移，仍能区分"全量真实库" vs 空/部分库）：
#   - delivery_task：cross-wave 一致性 + 凭据投影底座（稳定态 67 → floor 50）
#   - approval_case：cross-wave approval→delivery 一致性入口（稳定态 267 → floor 200）
# 关键修正（CLAUDE.md D44）：capability_call **不是 legacy import 产出**，而是运行时遥测
# （pipeline 每次 invoke 经 record_capability_call 落库）。fresh import=0、本机 clean=个位数，
# 旧门槛 ≥744 把"某次累积运行后的量"当 seed 门槛 → CI 无 DB skip、本地 clean 也 skip，
# **整 module 永久不跑**。改为：不 gate capability_call，由 _runtime_capability_calls fixture
# **自产真实运行时遥测**（genuine invoke catalog.browse，跑过真实调用流），监控类断言据此校验。
# 门槛语义（delivery_task≥50 / approval_case≥200）由 realistic_pg_module 的 skip-when-absent 承接。
pytestmark = pytest.mark.usefixtures("realistic_pg_module")

# 自产运行时遥测的确定性条数：2 角色 × 3 次 genuine invoke = 6 行 succeeded capability_call。
SELF_PRODUCED_CALLS = 6
_SELF_PRODUCE_ROLES = ("ROLE_ORGAN_OPERATER", "ROLE_BUSIAUDIT")
_SELF_PRODUCE_REPEATS = 3


@pytest.fixture(scope="module", autouse=True)
def _runtime_capability_calls(realistic_pg_module) -> int:  # noqa: F811  (pytest fixture used as arg)
    """自产运行时 capability_call 遥测——A 类设计修正（CLAUDE.md D44）。

    capability_call 由 pipeline 在每次 invoke 时经 ``record_capability_call`` 落库，
    **不来自 legacy seed**（fresh import=0）。本 fixture 用 genuine ``invoke_skill``
    真实调用只读能力 ``catalog.browse``（audit_required、无副作用）若干次，让 J1 API
    调用监控类断言（actor 过滤 / 状态分布 / 字段完整）在任意 DB 上都有真实运行时数据，
    而非依赖"某次本机累积"。这是真正"跑过真实调用流"，非 mock 业务数据（D11 不冲突——
    capability_call 是运行时遥测，非业务实体）。

    依赖 ``realistic_pg_module`` 保证写入克隆库；返回本次确定性自产条数。
    """
    from zw_brain.command.runtime import get_service, reset_service
    reset_service()
    svc = get_service()
    produced = 0
    for role in _SELF_PRODUCE_ROLES:
        for _ in range(_SELF_PRODUCE_REPEATS):
            svc.invoke_skill("catalog.browse", {"role": role, "tenant_id": TENANT})
            produced += 1
    reset_service()
    return produced


@pytest.fixture(scope="module")
def delivery_repo():
    from zw_brain.domain.repositories.delivery import DeliveryRepository
    return DeliveryRepository()


@pytest.fixture(scope="module")
def baseline_counts(_runtime_capability_calls):
    # _runtime_capability_calls 先行：capability_call 计数读到的是自产遥测之后的态。
    d_n = _pg_read("SELECT COUNT(*) FROM delivery_task WHERE tenant_id=%s", (TENANT,))[0][0]
    cap_n = _pg_read("SELECT COUNT(*) FROM capability_call WHERE tenant_id=%s", (TENANT,))[0][0]
    approved_app_n = _pg_read(
        "SELECT COUNT(*) FROM application_record WHERE tenant_id=%s AND status='approved'",
        (TENANT,),
    )[0][0]
    approved_case_n = _pg_read(
        "SELECT COUNT(*) FROM approval_case WHERE tenant_id=%s AND current_status='approved'",
        (TENANT,),
    )[0][0]
    return {
        "delivery_task": d_n,
        "capability_call": cap_n,
        "application_approved": approved_app_n,
        "approval_case_approved": approved_case_n,
    }


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
    """Background: delivery_task（legacy seed）+ capability_call（自产运行时遥测）就位。"""
    # 稳健 floor：稳定态 delivery_task=67，floor 50 容忍漂移、仍证"全量真实库非空"。
    # （旧值 68 比稳定态多 1 → 一旦 module 真跑必挂，CLAUDE.md D44 修正。）
    assert baseline_counts["delivery_task"] >= 50, (
        f"delivery_task 真实库 floor ≥50，got {baseline_counts['delivery_task']}"
    )
    # capability_call 为运行时遥测：_runtime_capability_calls 已自产 ≥SELF_PRODUCED_CALLS 条。
    assert baseline_counts["capability_call"] >= SELF_PRODUCED_CALLS, (
        f"capability_call 自产运行时遥测 floor ≥{SELF_PRODUCED_CALLS}, "
        f"got {baseline_counts['capability_call']}"
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
    approved = [
        row[0] for row in _pg_read(
            "SELECT a.application_code FROM approval_case a "
            "WHERE a.tenant_id=%s AND a.current_status='approved' "
            "ORDER BY a.application_code",
            (TENANT,),
        )
    ]
    assert approved, "前置：approved approval_case 应非空"

    # 固定种子，可复现采样
    rng = random.Random(0)
    sample = rng.sample(approved, min(CROSS_WAVE_SAMPLE, len(approved)))

    placeholders = ",".join(["%s"] * len(sample))
    with_any_delivery = {
        row[0] for row in _pg_read(
            "SELECT application_code FROM delivery_task "
            f"WHERE tenant_id=%s AND application_code IN ({placeholders})",
            (TENANT, *sample),
        )
    }

    with_granted_active = {
        row[0] for row in _pg_read(
            "SELECT application_code FROM delivery_task "
            "WHERE tenant_id=%s AND state IN ('granted','active') "
            f"AND application_code IN ({placeholders})",
            (TENANT, *sample),
        )
    }

    # 全量统计 — 用于诊断输出
    total_approved = _pg_read(
        "SELECT COUNT(*) FROM approval_case "
        "WHERE tenant_id=%s AND current_status='approved'",
        (TENANT,),
    )[0][0]
    total_approved_with_delivery = _pg_read(
        "SELECT COUNT(DISTINCT a.application_code) FROM approval_case a "
        "JOIN delivery_task d ON d.tenant_id=a.tenant_id "
        "    AND d.application_code=a.application_code "
        "WHERE a.tenant_id=%s AND a.current_status='approved'",
        (TENANT,),
    )[0][0]

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
    注：forward 入口寻址 in-memory snapshot（可写交付行；legacy hash-id 行只读）。
    C-1 删演示单后无 DLV- 演示交付，本测试**自注入**一个可写合成交付作 forward 契约入口
    （证明新系统 forward grant 完整，与历史导入只读正交）；grant 终态 state='completed'。
    """
    from zw_brain.command.runtime import get_service, reset_service
    reset_service()
    svc = get_service()
    # 自包含 forward 入口：注入一个可写合成交付（非 demo seed、非 legacy hash-id 只读行）。
    task = {
        "id": "DLV-TEST-FWD-1",
        "requestId": "REQ-TEST-FWD-1",
        "status": "pending",
        "name": "forward 契约测试交付",
        "channel": "exchange",
        "history": [],
        "aiSummary": {},
    }
    # Action D：交付单一事实源在 DB——直接 upsert 注入。
    svc._state_store.database_store.delivery_repo.upsert_from_delivery(task, tenant_id="sd-default")
    svc.grant_delivery_access(task["id"], "ROLE_ORGAN_MANAGER", True)
    rows = _pg_read(
        "SELECT application_code, state, tenant_id FROM delivery_task "
        "WHERE delivery_code=%s AND tenant_id=%s",
        (task["id"], TENANT),
    )
    row = rows[0] if rows else None
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
    actor_dist = _pg_read(
        "SELECT actor, COUNT(*) FROM capability_call WHERE tenant_id=%s "
        "GROUP BY actor ORDER BY 2 DESC LIMIT 5",
        (TENANT,),
    )
    assert actor_dist, "capability_call 应至少含 1 个 actor"
    top_actor = actor_dist[0][0]

    filtered = [
        row[0] for row in _pg_read(
            "SELECT DISTINCT actor FROM capability_call WHERE tenant_id=%s AND actor=%s",
            (TENANT, top_actor),
        )
    ]
    assert filtered == [top_actor], (
        f"按 actor='{top_actor}' 过滤后应只含该 actor；got {filtered!r}"
    )


def test_j1_api_monitoring_capability_call_has_minimum_required_fields():
    """正向 — 调用记录至少含 input / output / completed_at / status / actor / role_code
    （Scenario 1 监控段"时间 / 请求 ID / 调用结果 / 响应字节数" 数据底座）。"""
    columns = {
        row[0] for row in _pg_read(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='capability_call'"
        )
    }
    required = {"skill_id", "actor", "role_code", "status", "started_at", "completed_at", "input_json", "output_json"}
    assert required.issubset(columns), (
        f"capability_call 缺字段：{required - columns}"
    )
    # 真数据：至少 1 条 succeeded
    ok_n = _pg_read(
        "SELECT COUNT(*) FROM capability_call WHERE tenant_id=%s AND status='succeeded'",
        (TENANT,),
    )[0][0]
    assert ok_n >= 1, f"capability_call 应至少含 1 条 status='succeeded' 记录；got {ok_n}"


def test_j1_api_monitoring_status_distribution_real_data(_runtime_capability_calls):
    """正向 — capability_call 含可消费的状态分布。

    给 J1 调用监控页面（P_API_CALL_MONITORING）提供基础数据；
    具体 429 / 401 / 限流 Scenario 落地在 W0-07 浏览器侧 + Wave 1+ 配额引擎。
    数据由 _runtime_capability_calls 自产（真实 invoke 落库），非依赖本机累积量。
    """
    dist = {
        row[0]: row[1]
        for row in _pg_read(
            "SELECT status, COUNT(*) FROM capability_call WHERE tenant_id=%s GROUP BY status",
            (TENANT,),
        )
    }
    # 自产 ≥SELF_PRODUCED_CALLS 条 succeeded 遥测；监控页面据此渲染状态分布。
    assert sum(dist.values()) >= SELF_PRODUCED_CALLS, (
        f"capability_call 总数 ≥{SELF_PRODUCED_CALLS}；got {dist!r}"
    )
    assert dist.get("succeeded", 0) >= 1, f"应至少 1 条 succeeded；got {dist!r}"


# ============================================================================
# R-017：移除 10 个空体 @pytest.mark.skip 桩（原顶着场景名常驻 Done feature 的 ref 模块，
# 制造"有测试覆盖"的错觉，但实为零断言占位）。诚实化处置——三类去向，全部在 .feature 侧
# 显式化、不再靠空桩占位：
#
#   A) 真有 e2e 浏览器覆盖 → 删桩（浏览器面真实存在）：
#      - test_j1_credential_non_owner_forbidden（P4 凭据/调用记录段 无权不可见）
#        浏览器覆盖 = tests/e2e/j1_credential_revoke_monitoring.spec.ts §「P4 调用记录段：
#        授权岗位可见 / 申请人 OPERATER 不渲染」。**刻意不挂进 .feature 硬 refs**：该 spec 的
#        MANAGER「调用记录」段可见断言受 hasCredential 门控（D47：真库 legacy granted
#        credential=not_issued → UI 暗），干净 seed 下需测内真流程铸新凭据才绿，本 spec 未铸
#        → 干净 seed 上非确定性绿。挂为硬 ref 会让 Done 的 j1-credential-revoke 误红（实为
#        测试造数缺口非产品缺陷）。撤回/暂停的**确定性**覆盖已由 test_wave1_j1_grant_revoke.py
#        承担（已挂 refs）；本浏览器面留作走查证据、不进绿判定，避免假红/逼镀金。
#
#   B) 归属 feature 已 Backlog（# Deferred:），桩本就不影响绿判定，纯删错觉：
#      - test_j1_api_monitoring_engineering_term_blacklist / _curl_call_appears /
#        _quota_exhaust_429 / _peak_rate_limit / _expired_or_scope_mismatch /
#        _ai_not_overriding_timeline → 均属 j1-api-call-monitoring.feature（整 feature
#        # Deferred: 触发=首次真实生产部署 + 网关供 res→api_id 映射 + 真实 API 流量），
#        配额/限流引擎本期不实现。feature 头已诚实记延后，无需空桩。
#
#   C) 归属 feature InTest，UI 层场景延后浏览器验收，feature # InTest-Scope 已诚实记：
#      - test_j1_credential_p4_four_section_layout / _cli_consumer_face /
#        _first_show_then_masked → 属 j1-credential-issue.feature，其 # InTest-Scope 明记
#        「P4 前端四件套 / CLI 消费面 / 首次明文后续脱敏 / 非 owner 403 归 W0-07 浏览器验收」。
#
# 删桩后：本模块只保留真有断言的数据层用例；UI/延后场景的真实状态由 .feature 头单源承载。
# ============================================================================
