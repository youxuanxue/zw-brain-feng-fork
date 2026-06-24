"""B1 system_ops handlers — 3 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.discovery_snapshot_projection import (
    _share_policy_by_catalog,
    enrich_approvals_snapshot,
    enrich_delivery_tasks_snapshot,
    enrich_discovery_resources_snapshot,
    enrich_requests_snapshot,
)
from zw_brain.domain.dispute_snapshot_projection import enrich_disputes_snapshot
from zw_brain.domain.provider_snapshot_projection import enrich_provider_snapshot, enrich_zones_snapshot
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.schemas import describe_schemas
from zw_brain.domain.services.reference_service import ReferenceService
from zw_brain.domain.web_snapshot_redaction import redact_webui_snapshot
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id
from zw_brain.shared.session_context import caller_org_code

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _toggle_outage(brain, deps, ctx, role: str, confirmed: bool) -> dict[str, Any]:
    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        brain._ui_state["brainOutage"] = not brain._ui_state["brainOutage"]
        deps.append_audit_feed(
            "dashboard.snapshot-toggle",
            "brain",
            "warning" if brain._ui_state["brainOutage"] else "ok",
            actor,
        )
        return {"brainOutage": brain._ui_state["brainOutage"]}

    return deps.write(ctx, {}, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_system_toggle_outage(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _toggle_outage(brain, deps, ctx, str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_system_snapshot(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    role = str(payload.get("role", ctx.role))
    tenant_id = str(payload.get("tenant_id") or get_runtime_tenant_id())
    # 部门数据可见域：从可信会话取调用者机构 + 个人身份，一次算出 visible 集后透传各 enrich。
    # 全局角色→None（放行全量）；部门角色→本机构(+下级)；缺机构上下文→空集 fail-closed。
    # 发现面（zones/discovery_resources）刻意不传 = 永久全局（跨部门共享市场，by design）。
    caller_actor = ctx.actor
    visible_org_codes = ReferenceService().visible_org_codes(
        caller_org_code(payload), role, tenant_id=tenant_id
    )
    # 万级规模性能（S3）：一次 system.snapshot 内 resource_asset 全表此前被 api_services /
    # resources / share_map / discovery_cards 各无 where 全扫一遍——资源迈向万级前收口为单次
    # 预取，行级 kind/lifecycle/owner 过滤在各投影内存做（assets=None 时各函数仍回落自查、保独立可测）。
    prefetched_assets = ResourceApiRepository().list_assets(tenant_id=tenant_id)
    catalog_share_policies = _share_policy_by_catalog(tenant_id, prefetched_assets)
    # deepcopy 收口（S3）：brain.snapshot() 已返回新鲜深拷贝（copy.deepcopy(self._snapshot)），
    # 故链上第一个 enrich 即可 copy=False 原地写、各 enrich 不再各自深拷整个胖快照（纯 CPU 浪费）；
    # enrich_disputes_snapshot（他流文件、无 copy 形参）自带一次深拷，其后各 enrich 原地写其产物安全。
    enriched = enrich_provider_snapshot(
        brain.snapshot(), tenant_id=tenant_id, visible_org_codes=visible_org_codes,
        assets=prefetched_assets, copy=False,
    )
    enriched = enrich_zones_snapshot(enriched, tenant_id=tenant_id, copy=False)
    enriched = enrich_disputes_snapshot(enriched, tenant_id=tenant_id, visible_org_codes=visible_org_codes)
    # D45 — J1 列表字段全量真实库投影（DB 有行替换 / 空库保留 seed）
    # 申请人进度 stepper：把后端权威 status_timeline 接到申请卡（读侧 enrich，单一事实源）。
    enriched = enrich_requests_snapshot(
        enriched, tenant_id=tenant_id,
        request_service=deps.services.request if deps is not None else None,
        visible_org_codes=visible_org_codes, caller_actor=caller_actor,
        assets=prefetched_assets, copy=False,
    )
    # 交叉引用图（O(1)、避 N+1）：交付页脊柱复用同一条已挂好的申请 timeline。
    request_map = {str(r.get("id")): r for r in (enriched.get("requests") or [])}
    enriched = enrich_approvals_snapshot(
        enriched, tenant_id=tenant_id, visible_org_codes=visible_org_codes, copy=False
    )
    enriched = enrich_discovery_resources_snapshot(
        enriched, tenant_id=tenant_id, assets=prefetched_assets,
        catalog_share_policies=catalog_share_policies, copy=False
    )
    if role in {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"}:
        # 交付脊柱：把后端权威 status_timeline 接到交付任务卡（P4 第一次看见整单进度）。
        # 部门数据可见域收口（#294 集成期遗漏补口）：交付任务随其申请单收口——dept 角色
        # （visible≠None）只见 request_map（已按机构收口）内申请对应的交付卡；全局视角(None)全量。
        enriched["delivery_tasks"] = enrich_delivery_tasks_snapshot(
            brain.list_delivery_tasks(),
            request_service=deps.services.request if deps is not None else None,
            request_map=request_map,
            dept_scoped=visible_org_codes is not None,
        )
    return redact_webui_snapshot(enriched, role)

def handler_system_schema_info(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return {"schemas": describe_schemas()}
