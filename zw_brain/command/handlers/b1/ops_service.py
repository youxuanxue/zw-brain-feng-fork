"""B1 ops_service handlers — 2 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import ops_metrics as ops_metrics_ser
from zw_brain.domain.errors import AccessDeniedError
from zw_brain.domain.serializers.ops_metrics import metric_summary as _metric_summary

_MANAGER_ROLE = "ROLE_ORGAN_MANAGER"

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────


def _caller_org_code(ctx: SkillContext, payload: dict[str, Any]) -> str:
    """会话机构解析（同 j1/approval._actor_org_code 口径）：BFF build_trusted_skill_payload
    把 current_org_code 钉进 payload['org_code']；bearer/CLI 等无机构上下文路径取不到则空。"""
    snapshot = payload.get("actor_snapshot") if isinstance(payload.get("actor_snapshot"), dict) else {}
    return str(
        payload.get("org_code")
        or payload.get("current_org_code")
        or snapshot.get("current_org_code")
        or snapshot.get("org_code")
        or ""
    )


def _scope_invocations_for_manager(
    deps, ctx, payload: dict[str, Any], metrics: list[dict[str, Any]], resource_code: Any, *, db_mode: bool
) -> list[dict[str, Any]]:
    """D57⑥ 服务端 scope：部门管理员仅见「自家资源被调用情况」，不再得全平台监控面。

    全局监控面（service-ops 导航 + report.query）已按裁决去 MANAGER；invocation.query 为
    P4 凭据门内读面保留 MANAGER，但「自家」语义必须是系统机制而非注释承诺（REST 是 D2 一等
    消费面，UI 门拦不住直调）。规则（fail-closed）：
      - 会话无机构上下文 → 拒（无法证明「自家」就不给）；
      - 显式查询的资源可解析且 owner_org ≠ 会话机构 → 拒（明确 403，P4 已有无权文案）；
      - 行级过滤：metric.provider_org_id == 会话机构，或 resource_code ∈ 本机构注册资产
        （两条真实库锚，覆盖 provider_org 缺省的 legacy 行）；summary 在过滤后计算，不经
        聚合数泄漏。业务运营员 / 平台运维员（v5 全局口径）不经此 scope。
    """
    role = str(payload.get("role", ctx.role))
    if role != _MANAGER_ROLE:
        return metrics
    org = _caller_org_code(ctx, payload)
    if not org:
        raise AccessDeniedError(
            "ops.service.invocation.query: 部门管理员会话缺少机构上下文，无法限定自家资源（fail-closed）"
        )
    owned_codes: set[str] = set()
    if db_mode:
        owned_codes = {
            str(rec.resource_code)
            for rec in deps.repos.resource_api.list_assets()
            if str(rec.owner_org_id or "") == org
        }
        if resource_code:
            asset = deps.services.provider.find_api_resource(str(resource_code))
            asset_owner = str((asset or {}).get("owner_org_id") or "")
            if asset_owner and asset_owner != org:
                raise AccessDeniedError(
                    "ops.service.invocation.query: 部门管理员仅可查看本机构提供资源的调用记录"
                )
    return [
        item
        for item in metrics
        if str(item.get("provider_org_id") or "") == org or str(item.get("resource_code") or "") in owned_codes
    ]


def _query_service_invocations(
    brain,
    deps,
    ctx,
    *,
    payload: dict[str, Any],
    resource_code: Any = None,
    capability_id: Any = None,
    metric_scope: Any = None,
) -> dict[str, Any]:
    store = deps.state_store.database_store
    if store is None:
        metrics = copy.deepcopy(deps.brain_legacy._snapshot.get("service_invocation_metrics", []))
        if resource_code:
            metrics = [item for item in metrics if item.get("resource_code") == resource_code]
        if capability_id:
            metrics = [item for item in metrics if item.get("capability_id") == capability_id]
        if metric_scope:
            metrics = [item for item in metrics if item.get("metric_scope") == metric_scope]
    else:
        metrics = [
            ops_metrics_ser.metric_to_dict(item)
            for item in deps.repos.service_invocation.list_metrics(
                resource_code=str(resource_code) if resource_code else None,
                capability_id=str(capability_id) if capability_id else None,
                metric_scope=str(metric_scope) if metric_scope else None,
            )
        ]
    metrics = _scope_invocations_for_manager(
        deps, ctx, payload, metrics, resource_code, db_mode=store is not None
    )
    return {"items": metrics, "summary": _metric_summary(metrics)}

def _query_service_report(brain, deps, ctx) -> dict[str, Any]:
    store = deps.state_store.database_store
    if store is None:
        gateways = copy.deepcopy(deps.brain_legacy._snapshot.get("gateway_runtime_statuses", []))
        metrics = copy.deepcopy(deps.brain_legacy._snapshot.get("service_invocation_metrics", []))
    else:
        gateways = [ops_metrics_ser.gateway_to_dict(item) for item in deps.repos.gateway_runtime.list_statuses()]
        metrics = [ops_metrics_ser.metric_to_dict(item) for item in deps.repos.service_invocation.list_metrics()]
    offline = sum(1 for item in gateways if item.get("status") != "online")
    summary = _metric_summary(metrics)
    return {
        "gateways": gateways,
        "metrics": metrics,
        "summary": {
            "gatewayCount": len(gateways),
            "gatewayWarnings": offline,
            "invokeCount": summary["invokeCount"],
            "failedCount": summary["failedCount"],
            "errorCount": summary["errorCount"],
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_ops_service_invocation_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_service_invocations(brain, deps, ctx, payload=payload, resource_code=payload.get("resource_code"), capability_id=payload.get("capability_id"), metric_scope=payload.get("metric_scope"))

def handler_ops_service_report_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_service_report(brain, deps, ctx)

