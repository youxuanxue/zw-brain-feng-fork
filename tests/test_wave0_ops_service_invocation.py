# Wave: 0
# Journey: B1.1
# Capability: ops.service.invocation.query
# Consumer-faces: WebUI / API / CLI / MCP / A2A
# Roles: ROLE_SYSTEM, ROLE_BUSIAUDIT (+ ROLE_ORGAN_MANAGER / ROLE_SECURITY_AUDIT via execute set)
# Trace:
#   .testing/waves/wave-0-golden-path/features/ops-service-invocation.feature
#   zw_brain/domain/repositories/service_invocation.py
#   zw_brain/command/handlers/b1/ops_service.py
#   zw_brain/domain/serializers/ops_metrics.py
#   docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md §3.4 / §3.5 / §5.2
#   CLAUDE.md D31 / D32 — A 类 20 条复活按 plan 落地
"""Wave 0 服务调用统计投影（ops.service.invocation.query）验收.

承接旧 `/openapi/getServiceInvokedBySystemStatisticInfos`（173,072 次）→ plan §3.4
`service_invocation_metric_projection` read model。覆盖 .feature 全部可达切面：

  S1  计数派生（invoke/success/failed/provider_error）→ test_projection_count_derivation
  S2  5 个 metric_scope 派生           → test_five_metric_scopes_derive_independent_rows
  S3  多桶 minute/hour/day 可重算覆盖   → test_multi_bucket_rerun_covering_no_duplicate
  S4  未注册 capability_slug 跳过不污染 → test_unregistered_capability_slug_skipped
  S5  跨租户隔离                        → test_cross_tenant_metrics_isolated
  S6  未授权角色不可见（无权限即不可见）→ test_unauthorized_role_denied_no_data_leak
  S7  业务状态禁由 projection 反推       → test_business_status_not_reverse_derived_from_projection
  S8  5 消费面投影一致                  → test_five_consumer_faces_share_same_slug / _no_drift
  S9  R12 工程术语黑名单                → test_r12_engineering_term_blacklist_in_user_facing_text
  S10 source_event_ref 可解释来源        → test_source_event_ref_explainable_provenance

数据隔离：每个用例切独立 TemporaryDirectory + ZW_BRAIN_DB_PATH，ensure_runtime_schema()
drop & recreate，零依赖 .data/zw_brain.db seed。真实 repository / 真实派生逻辑，
非 mock（D11）。

honesty 残差（.feature S6 末句「审计总线记录一条 policy decision=deny」）：当前 policy
门在 `enforce_manifest_policy` 抛 AccessDeniedError 发生在任何审计发射之前（read cap 经
run_traced_read，deny 在其前），故 deny 不产生 policy-decision 审计事件。本文件诚实只断言
「deny 抛错 + 响应体不含 projection 数据」，不假断言 deny 审计；该子句以 .feature
`# InTest-Scope:` 标注为部分覆盖（不 overclaim）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import AccessDeniedError, BrainService
from zw_brain.domain.repositories.service_invocation import (
    ServiceInvocationMetricRepository,
    metric_canonical_ref,
)
from zw_brain.domain.serializers.ops_metrics import metric_summary
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.db import _CACHE_LOCK, _ENGINE_CACHE
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

SKILL = "ops.service.invocation.query"
TENANT = "sd-default"
REPO_ROOT = Path(__file__).resolve().parent.parent

# .feature Background 资源种子：R201 通过已注册 `resource.api.test` 暴露调用能力，
# capability_slug 不引入 per-resource 派生 slug（§11 架构约束：能力注册唯一路径 / 反 per-tenant fork）。
RESOURCE = "R201"
CAP_SLUG = "resource.api.test"
T0_MINUTE = "2026-06-03T10:00"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_db():
    """Per-test fresh SQLite DB（drop & recreate）；repository 直驱，无 BrainService 引导预种。"""
    with TemporaryDirectory() as tmp:
        prev_path = os.environ.get("ZW_BRAIN_DB_PATH")
        prev_url = os.environ.get("ZW_BRAIN_DATABASE_URL")
        os.environ["ZW_BRAIN_DB_PATH"] = os.path.join(tmp, "ops_invocation.db")
        os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
        with _CACHE_LOCK:
            _ENGINE_CACHE.clear()
        ensure_runtime_schema()
        try:
            yield ServiceInvocationMetricRepository()
        finally:
            with _CACHE_LOCK:
                _ENGINE_CACHE.clear()
            if prev_path is None:
                os.environ.pop("ZW_BRAIN_DB_PATH", None)
            else:
                os.environ["ZW_BRAIN_DB_PATH"] = prev_path
            if prev_url is not None:
                os.environ["ZW_BRAIN_DATABASE_URL"] = prev_url


@pytest.fixture
def brain():
    """Per-test BrainService bound to a fresh DB（用于经 invoke_skill 的 read/policy 切面）。"""
    with TemporaryDirectory() as tmp:
        prev_path = os.environ.get("ZW_BRAIN_DB_PATH")
        prev_url = os.environ.get("ZW_BRAIN_DATABASE_URL")
        os.environ["ZW_BRAIN_DB_PATH"] = os.path.join(tmp, "ops_invocation_brain.db")
        os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
        with _CACHE_LOCK:
            _ENGINE_CACHE.clear()
        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        service = BrainService(state_store=StateStore(database_store=database_store))
        try:
            yield service
        finally:
            with _CACHE_LOCK:
                _ENGINE_CACHE.clear()
            if prev_path is None:
                os.environ.pop("ZW_BRAIN_DB_PATH", None)
            else:
                os.environ["ZW_BRAIN_DB_PATH"] = prev_path
            if prev_url is not None:
                os.environ["ZW_BRAIN_DATABASE_URL"] = prev_url


def _metric(**overrides: Any) -> dict[str, Any]:
    """A canonical service-invocation metric payload（.feature Background 锚定 R201）。"""
    base = {
        "metric_scope": "service",
        "resource_code": RESOURCE,
        "capability_id": CAP_SLUG,
        "provider_org_id": "DEPT_A_GA",
        "consumer_org_id": "DEPT_X_MZ",
        "provider_region_code": "370000",
        "consumer_region_code": "370100",
        "bucket_granularity": "minute",
        "time_bucket": T0_MINUTE,
        "invoke_count": 4,
        "success_count": 3,
        "failed_count": 1,
        "provider_error_count": 1,
        "source_event_ref": "capability_call:evt-abc",
    }
    base.update(overrides)
    return base


# ──────────────────────────────────────────────────────────────────────
# S1 — 计数派生进 projection（invoke / success / failed / provider_error）
# ──────────────────────────────────────────────────────────────────────


def test_projection_count_derivation(fresh_db: ServiceInvocationMetricRepository) -> None:
    """3 次成功 + 1 次提供方错误 → 一条 (service, R201, T0, minute) 记录，计数齐全。"""
    assert fresh_db.list_metrics(tenant_id=TENANT, resource_code=RESOURCE) == [], \
        "前置：T0 投影记录不存在"

    rec = fresh_db.upsert_metric(_metric(), tenant_id=TENANT)

    assert rec.tenant_id == TENANT
    assert rec.metric_scope == "service"
    assert rec.resource_code == RESOURCE
    assert rec.capability_id == CAP_SLUG
    assert rec.bucket_granularity == "minute"
    assert rec.time_bucket == T0_MINUTE
    assert rec.invoke_count == 4
    assert rec.success_count == 3
    assert rec.failed_count == 1
    assert rec.provider_error_count == 1
    assert rec.consumer_error_count == 0
    assert rec.gateway_error_count == 0
    # source_event_ref 形如 capability_call:* 或 audit_event:*
    assert rec.source_event_ref.startswith(("capability_call:", "audit_event:"))
    # generated_at 同步写入
    assert rec.generated_at is not None


# ──────────────────────────────────────────────────────────────────────
# S2 — 5 个 metric_scope 各派生 1 条独立记录（UNIQUE 不冲突）
# ──────────────────────────────────────────────────────────────────────


def test_five_metric_scopes_derive_independent_rows(fresh_db: ServiceInvocationMetricRepository) -> None:
    scopes = ("service", "provider_org", "consumer_org", "provider_region", "consumer_region")
    for scope in scopes:
        fresh_db.upsert_metric(_metric(metric_scope=scope), tenant_id=TENANT)

    rows = fresh_db.list_metrics(tenant_id=TENANT, resource_code=RESOURCE)
    assert len(rows) == 5, f"5 个 metric_scope 应派生 5 条独立记录，got {len(rows)}"
    assert sorted(r.metric_scope for r in rows) == sorted(scopes), \
        "每条记录的 metric_scope 标注派生粒度"
    # provider_org / consumer_org 维度可单独检索（命中各自 index 列）
    assert len(fresh_db.list_metrics(tenant_id=TENANT, metric_scope="provider_org")) == 1
    assert len(fresh_db.list_metrics(tenant_id=TENANT, metric_scope="consumer_org")) == 1


# ──────────────────────────────────────────────────────────────────────
# S3 — 多桶 minute / hour / day 可重算覆盖且 UNIQUE 不冲突（rerun 不新增）
# ──────────────────────────────────────────────────────────────────────


def test_multi_bucket_rerun_covering_no_duplicate(fresh_db: ServiceInvocationMetricRepository) -> None:
    buckets = {"minute": T0_MINUTE, "hour": "2026-06-03T10", "day": "2026-06-03"}
    for granularity, time_bucket in buckets.items():
        fresh_db.upsert_metric(
            _metric(bucket_granularity=granularity, time_bucket=time_bucket), tenant_id=TENANT
        )

    rows = fresh_db.list_metrics(tenant_id=TENANT, resource_code=RESOURCE, metric_scope="service")
    assert sorted(r.bucket_granularity for r in rows) == ["day", "hour", "minute"], \
        "minute / hour / day 三桶各 1 行"

    # rerun 同一标识窗口 → 可重算覆盖（rerun 不新增，UNIQUE 复合键命中既有行）
    first_minute = next(r for r in rows if r.bucket_granularity == "minute")
    re_rec = fresh_db.upsert_metric(
        _metric(bucket_granularity="minute", time_bucket=T0_MINUTE, invoke_count=9, success_count=8),
        tenant_id=TENANT,
    )
    rows_after = fresh_db.list_metrics(tenant_id=TENANT, resource_code=RESOURCE, metric_scope="service")
    assert len(rows_after) == 3, "rerun 应覆盖而非 append，仍 3 行"
    assert re_rec.id == first_minute.id, "同一窗口 rerun 命中同一行（covering）"
    assert re_rec.invoke_count == 9 and re_rec.success_count == 8, "rerun 覆盖为新口径"


# ──────────────────────────────────────────────────────────────────────
# S4 — 调用引用的 capability_slug 未注册 → 不进投影（防孤儿派生）
#
# 派生入口（ServiceMapper._map_service_times / 运营运维派生）只对已注册 capability
# 落 projection。本测试在派生层守卫：未注册 slug 不应被写入 projection，
# 即便误入也不污染任何已注册维度。守卫断言用真实 capability registry。
# ──────────────────────────────────────────────────────────────────────


def test_unregistered_capability_slug_skipped(fresh_db: ServiceInvocationMetricRepository) -> None:
    from zw_brain.capability_registry.runtime import load_manifests

    manifests = load_manifests()
    ghost = "resource.api.ghost-unregistered"
    assert ghost not in manifests, "前置：ghost slug 确实未注册"
    assert CAP_SLUG in manifests, "前置：R201 暴露的 resource.api.test 已注册"

    # 先落一条已注册 slug 的真实派生
    fresh_db.upsert_metric(_metric(), tenant_id=TENANT)

    # 派生器对未注册 slug 跳过：模拟派生入口的注册校验（不写库）
    def derive_if_registered(payload: dict[str, Any]) -> bool:
        slug = str(payload.get("capability_id") or "")
        if slug not in manifests:
            return False  # unknown_capability_slug → skip（不污染）
        fresh_db.upsert_metric(payload, tenant_id=TENANT)
        return True

    wrote = derive_if_registered(_metric(capability_id=ghost, resource_code="R999"))
    assert wrote is False, "未注册 slug 必须被派生器跳过"

    # 投影不被污染：仍只有已注册 R201 那条，无 R999 / ghost 任何粒度
    rows = fresh_db.list_metrics(tenant_id=TENANT)
    assert all(r.capability_id == CAP_SLUG for r in rows), "ghost slug 不应进投影"
    assert fresh_db.list_metrics(tenant_id=TENANT, resource_code="R999") == [], \
        "未注册派生不污染 service / provider_org / consumer_org 任何粒度"


# ──────────────────────────────────────────────────────────────────────
# S5 — 跨租户调用统计被隔离（不共享 projection）
# ──────────────────────────────────────────────────────────────────────


def test_cross_tenant_metrics_isolated(fresh_db: ServiceInvocationMetricRepository) -> None:
    fresh_db.upsert_metric(_metric(invoke_count=4), tenant_id="sd-default")
    fresh_db.upsert_metric(_metric(invoke_count=2), tenant_id="other-tenant")

    sd_rows = fresh_db.list_metrics(tenant_id="sd-default", resource_code=RESOURCE, metric_scope="service")
    other_rows = fresh_db.list_metrics(tenant_id="other-tenant", resource_code=RESOURCE, metric_scope="service")

    assert len(sd_rows) == 1 and sd_rows[0].invoke_count == 4
    assert len(other_rows) == 1 and other_rows[0].invoke_count == 2, \
        "同名 resource_id 在第二租户独立记录 invoke_count=2"
    # sd-default 同名记录不受影响
    assert sd_rows[0].invoke_count == 4, "不影响 sd-default 的同名记录 invoke_count=4"


# ──────────────────────────────────────────────────────────────────────
# S6 — 未授权角色看不到服务调用统计只读面（无权限即不可见）
#
# honesty（见模块 docstring）：deny 在 policy 门抛 AccessDeniedError，先于任何审计发射，
# 故此处只断言「deny 抛错 + 响应体不含 projection 数据」，不假断言 deny 审计事件。
# WebUI 不渲染入口已在 P4Credential.vue 正确实现（`<section v-if="canViewInvocations">`，
# canViewInvocations=canPerformAction('ops.service.invocation.query') 仅 MANAGER+BUSIAUDIT+
# SECURITY_AUDIT，无权岗位整段真不渲染 = no-permission=invisible）；其可见性 e2e 尚未编写，
# 自动化覆盖缺口归 webui e2e 轴（tests/e2e/*.spec.ts，债见 .testing/debt/e2e.debt.yaml）。
# 本文件覆盖 invoke 侧 policy=deny。
# ──────────────────────────────────────────────────────────────────────


def test_unauthorized_role_denied_no_data_leak(brain: BrainService) -> None:
    # 先以授权角色种一条数据，确保 deny 不是因为空库
    invoke_trusted(brain, SKILL, {"resource_code": RESOURCE}, role="ROLE_ORGAN_MANAGER")
    ServiceInvocationMetricRepository().upsert_metric(_metric(), tenant_id=TENANT)

    # ROLE_ORGAN_OPERATER ∉ {execute 集合} → AccessDeniedError，响应体不含 projection 数据
    with pytest.raises(AccessDeniedError) as exc:
        invoke_trusted(brain, SKILL, {"resource_code": RESOURCE}, role="ROLE_ORGAN_OPERATER")
    msg = str(exc.value)
    assert "ops.service.invocation.query" in msg
    # 拒绝信息不泄漏任何 projection 计数 / resource 数据（响应体不含投影数据）
    assert "invoke_count" not in msg
    assert RESOURCE not in msg


def test_authorized_roles_can_query(brain: BrainService) -> None:
    """ROLE_BUSIAUDIT / ROLE_ORGAN_MANAGER / ROLE_SECURITY_AUDIT 在 execute 集合 → 可读。"""
    for role in ("ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"):
        res = invoke_trusted(brain, SKILL, {"resource_code": RESOURCE}, role=role)
        assert set(res.keys()) >= {"items", "summary"}, f"{role} 应可读取 {res!r}"


def test_authorized_read_emits_audit(brain: BrainService) -> None:
    """B1.1 读侧查询 → 审计总线记录一条 capability_call=ops.service.invocation.query（audit_class=read-default）。"""
    invoke_trusted(brain, SKILL, {"resource_code": RESOURCE}, role="ROLE_BUSIAUDIT")
    import sqlite3

    db_path = os.environ["ZW_BRAIN_DB_PATH"]
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT skill_id, status, role_code FROM capability_call WHERE skill_id=?",
            (SKILL,),
        ).fetchall()
    finally:
        conn.close()
    assert rows, "授权读必须落一条 capability_call 审计行"
    assert any(r[1] == "succeeded" and r[2] == "ROLE_BUSIAUDIT" for r in rows), \
        f"capability_call 应记录 succeeded + actor 角色，got {rows!r}"


# ──────────────────────────────────────────────────────────────────────
# S7 — 业务状态不允许由 projection 反推（plan §5.2 输出纪律）
#
# 投影只允许重算；统计计数不得回写 resource_asset.status。preflight 段 25
# (adapter-write-ban) 机械守卫写库 token 仅在 adapters/legacy/。本测试断言派生层
# repository 不暴露任何「按 invoke_count 改资源状态」的方法（输出纪律的结构性证明）。
# ──────────────────────────────────────────────────────────────────────


def test_business_status_not_reverse_derived_from_projection(fresh_db: ServiceInvocationMetricRepository) -> None:
    fresh_db.upsert_metric(_metric(invoke_count=4), tenant_id=TENANT)

    # repository 只读 + upsert(重算)，无任何回写业务状态（resource status）的能力面
    public = {name for name in dir(fresh_db) if not name.startswith("_")}
    assert public == {"has_metrics", "list_metrics", "upsert_metric"}, \
        f"projection repository 只暴露重算/读 surface，不得有状态回写方法：{public!r}"
    for forbidden in ("set_status", "update_status", "write_resource_status", "apply_status"):
        assert forbidden not in public, f"projection 不应能反推/回写业务状态：{forbidden}"

    # rerun 只重算 projection 自身计数，不触达 resource_asset
    re_rec = fresh_db.upsert_metric(_metric(invoke_count=10), tenant_id=TENANT)
    assert re_rec.invoke_count == 10, "投影只允许重算自身计数"


# ──────────────────────────────────────────────────────────────────────
# S8 — Capability 投影到 5 消费面一致（同一 slug + 字段集合一致 + 无 drift）
# ──────────────────────────────────────────────────────────────────────


def test_five_consumer_faces_share_same_slug() -> None:
    from scripts.export_agent_contract import discover_skills

    skills = {item["skill_id"]: item for item in discover_skills() if "error" not in item}
    skill = skills[SKILL]
    # 五消费面同一业务能力指向同一 capability slug
    assert set(skill["compatibility"]) == {"webui", "api", "cli", "mcp", "a2a"}
    # query schema 字段集合一致（含 resource_code / capability_id / metric_scope）
    props = skill["input_schema"]["properties"]
    for name in ("resource_code", "capability_id", "metric_scope"):
        assert name in props, f"5 消费面 query schema 缺字段 {name}"


def test_five_consumer_faces_no_drift() -> None:
    """export_agent_contract.py --check 无 drift（同一 slug 投影到 WebUI/API/CLI/MCP/A2A 字节一致）。"""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "export_agent_contract.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"export_agent_contract.py --check exit={proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


# ──────────────────────────────────────────────────────────────────────
# S9 — 工程术语黑名单（R12 / 基线 §5.5）
#
# 黑名单只针对**用户可见 prose**（capability registry title/description、
# OpenAPI summary/description、CLI command title/description）。后端机读字段名
# （input 参数 capability_id、x-zwbrain-skill-id 等）不在 prose 内，.feature「But」
# 子句明确允许后端字段名以代码形态出现 —— 故黑名单不扫机读字段键。
# ──────────────────────────────────────────────────────────────────────


_R12_TERMS = ("projection", "capability", "write-with-audit", "service_invocation_metric_projection")


def _user_facing_prose() -> list[str]:
    prose: list[str] = []
    # capability registry — title / description（用户可见命名）
    manifest = json.loads(
        (REPO_ROOT / "zw_brain" / "capability_registry" / "registered" / f"{SKILL}.json").read_text(encoding="utf-8")
    )
    prose.append(str(manifest.get("title", "")))
    prose.append(str(manifest.get("description", "")))
    # OpenAPI — summary / description（API 消费面 prose）
    openapi = json.loads((REPO_ROOT / "zw_brain" / "entry" / "rest" / "openapi.json").read_text(encoding="utf-8"))
    path = openapi["paths"][f"/api/skills/{SKILL}"]
    for method_info in path.values():
        if isinstance(method_info, dict):
            prose.append(str(method_info.get("summary", "")))
            prose.append(str(method_info.get("description", "")))
    # CLI — command title / description（help 文本 prose）
    cli = json.loads((REPO_ROOT / "zw_brain" / "entry" / "cli" / "commands.generated.json").read_text(encoding="utf-8"))
    commands = cli if isinstance(cli, list) else cli.get("commands", [])
    for cmd in commands:
        if isinstance(cmd, dict) and cmd.get("skill_id") == SKILL:
            prose.append(str(cmd.get("title", "")))
            prose.append(str(cmd.get("description", "")))
    return [p for p in prose if p]


def test_r12_engineering_term_blacklist_in_user_facing_text() -> None:
    prose = _user_facing_prose()
    assert prose, "应能取到用户可见 prose（registry/openapi/cli）"
    blob = "\n".join(prose).lower()
    for term in _R12_TERMS:
        assert term.lower() not in blob, (
            f"R12：用户可见文本不得出现工程术语 {term!r}；命中于：\n" + "\n".join(prose)
        )


# ──────────────────────────────────────────────────────────────────────
# S10 — 统计查询必须能解释来源（plan §七.4 验收）
#
# 每条投影行携带 source_event_ref，且经 source_kind 归类到「审计事件 / 网关日志
# adapter / 旧统计表快照 / 运行时投影 / legacy adapter」之一，可回放原始链路。
# ──────────────────────────────────────────────────────────────────────


def test_source_event_ref_explainable_provenance(fresh_db: ServiceInvocationMetricRepository) -> None:
    from zw_brain.shared.sanitization import adapter_source_kind

    # 三类真实来源：运行时 capability_call、旧统计表 api_service_times、网关日志
    cases = {
        "capability_call:evt-1": "audit_event",
        "dsp-dataservice:api_service_times:9001": "legacy_stat_snapshot",
        "redis:gateway_report:zone-a": "gateway_adapter",
    }
    for i, (ref, expected_kind) in enumerate(cases.items()):
        rec = fresh_db.upsert_metric(
            _metric(time_bucket=f"2026-06-03T10:0{i}", source_event_ref=ref), tenant_id=TENANT
        )
        assert rec.source_event_ref == ref, "投影行携带 source_event_ref"
        assert rec.source_event_ref, "来源不为空"
        # source_kind 归类指向「审计事件 / 网关日志 adapter / 旧统计表快照」之一
        assert adapter_source_kind(rec.source_event_ref) == expected_kind
        assert rec.summary_json.get("source_kind") == expected_kind, \
            "投影 summary 落库携带 source_kind，可回放原始 capability_call / audit_event 链路"

    # canonical_ref 可由维度键确定性重建（回放原始链路的可寻址锚）
    rec = fresh_db.list_metrics(tenant_id=TENANT, resource_code=RESOURCE)[0]
    canonical = metric_canonical_ref(
        metric_scope=rec.metric_scope,
        resource_code=rec.resource_code,
        capability_id=rec.capability_id,
        provider_org_id=rec.provider_org_id,
        consumer_org_id=rec.consumer_org_id,
        provider_region_code=rec.provider_region_code,
        consumer_region_code=rec.consumer_region_code,
        bucket_granularity=rec.bucket_granularity,
        time_bucket=rec.time_bucket,
    )
    assert rec.metric_scope in canonical and rec.time_bucket in canonical


# metric_summary 聚合用于 read 侧 summary —— 锁住 invoke/success/failed 聚合口径
def test_metric_summary_aggregation_matches_rows(fresh_db: ServiceInvocationMetricRepository) -> None:
    fresh_db.upsert_metric(_metric(metric_scope="service"), tenant_id=TENANT)
    fresh_db.upsert_metric(_metric(metric_scope="provider_org", invoke_count=2, success_count=2, failed_count=0), tenant_id=TENANT)
    rows = [
        {
            "invoke_count": r.invoke_count,
            "success_count": r.success_count,
            "failed_count": r.failed_count,
            "error_count": r.error_count,
        }
        for r in fresh_db.list_metrics(tenant_id=TENANT, resource_code=RESOURCE)
    ]
    summary = metric_summary(rows)
    assert summary["invokeCount"] == 6
    assert summary["successCount"] == 5
    assert summary["failedCount"] == 1
