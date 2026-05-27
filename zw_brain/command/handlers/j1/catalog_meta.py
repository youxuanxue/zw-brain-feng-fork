"""J1 catalog_meta handlers — 10 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy

from zw_brain.command.brain import InvalidStateError, NotFoundError, _RequestBatchContext
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import catalog as catalog_ser
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _browse_catalog_entries(
    brain,
    deps,
    ctx,
    *,
    page: Any = None,
    limit: Any = None,
    lifecycle: Any = None,
    kind: Any = None,
    owner_org_id: Any = None,
    query: Any = None,
) -> dict[str, Any]:
    """Paginated browse of catalog_entry. Defaults filter out retired/draft
    noise and api-group nodes so the WebUI surface stays customer-grade.

    Filters:
      - lifecycle: 'active' (default) | 'approved_pending_publish' | 'draft' | 'pending_review' | 'rejected' | 'all'
      - kind: 'real' (default; excludes catalog_code starting with 'api-group:') | 'api-group' | 'all'

    Quality sort: legacy 测试条目（title 为纯 ASCII / 与 catalog_code 同名 /
    长度 < 4）一律推到末尾，让首屏 / 首页 / demo 第一眼看到的是真业务目录
    （含 CJK 字符 + 长度 ≥ 4）。退役类垃圾条目应由 业务运营员 用 catalog.entry.withdraw
    清理，本排序只是不在客户面前展示噪声。
    """
    page = max(int(page or 1), 1)
    limit = max(min(int(limit or 20), 100), 1)
    lifecycle = str(lifecycle or "active")
    kind = str(kind or "real")

    repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
    lifecycle_status = None if lifecycle == "all" else lifecycle
    catalog_code_prefix = "api-group:" if kind == "api-group" else None
    exclude_catalog_code_prefix = "api-group:" if kind == "real" else None
    owner = str(owner_org_id) if owner_org_id else None
    browse_filters = {
        "tenant_id": _DEFAULT_TENANT_ID,
        "lifecycle_status": lifecycle_status,
        "owner_org_id": owner,
        "catalog_code_prefix": catalog_code_prefix,
        "exclude_catalog_code_prefix": exclude_catalog_code_prefix,
    }
    if query:
        records = repo.search_entries(str(query), **browse_filters)
    else:
        records = repo.list_entries(**browse_filters)

    def _quality_key(r: Any) -> tuple[int, str]:
        title = (getattr(r, "title", "") or "").strip()
        code = getattr(r, "catalog_code", "") or ""
        # 高分（排前）= 真业务目录；低分（排后）= legacy 测试噪声
        has_cjk = any("一" <= ch <= "鿿" for ch in title)
        long_enough = len(title) >= 4
        # 仅当 title 与 code 完全相等才视为 placeholder（如 title='1' code='1'）；
        # startswith 会把短数字 title 误伤合法长 catalog_code 的 owner_prefix。
        distinct_from_code = title != code
        score = (2 if has_cjk else 0) + (1 if long_enough else 0) + (1 if distinct_from_code else 0)
        # 同分按 title 字典序稳定
        return (-score, title)

    records = sorted(records, key=_quality_key)

    total = len(records)
    start = (page - 1) * limit
    end = start + limit
    items = [catalog_ser.catalog_entry_to_dict(r) for r in records[start:end]]
    return {"items": items, "total": total, "page": page, "limit": limit}

def _query_catalog_groups(brain, deps, ctx) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    catalogs = copy.deepcopy(deps.brain_legacy._snapshot.get("provider", {}).get("catalogs", []))
    groups: dict[str, dict[str, Any]] = {}
    for catalog in catalogs:
        key = str(catalog.get("domain") or catalog.get("group") or "default")
        group = groups.setdefault(key, {"group_code": key, "title": key, "catalog_count": 0})
        group["catalog_count"] += 1
    store = deps.state_store.database_store
    if store is None:
        return {"items": list(groups.values()), "total": len(groups)}
    packages = [
        brain._topic_package_list_projection(item)
        for item in deps.repos.topic_package.list_packages(tenant_id=_DEFAULT_TENANT_ID)
        if brain._topic_projection_kind(item) == "catalog_group"
    ]
    if packages:
        return {"items": packages, "total": len(packages)}
    return {"items": list(groups.values()), "total": len(groups)}

def _manage_catalog_entry(brain, deps, ctx, catalog_id: str, action: str, role: str, confirmed: bool) -> dict[str, Any]:
    # Action C — provider is read-then-mutated (catalog["status"] = "已发布" etc.);
    # use brain_legacy escape hatch to keep in-place semantics until Action D
    # retires the snapshot dict.
    provider = deps.brain_legacy._snapshot["provider"]
    catalog = next((item for item in provider["catalogs"] if item["id"] == catalog_id), None)
    if catalog is None:
        raise NotFoundError(catalog_id)
    if action not in {"publish", "revise"}:
        raise InvalidStateError(f"unsupported catalog action: {action}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        if action == "publish":
            store = deps.state_store.database_store
            if store is not None:
                deps.repos.catalog.upsert_from_resource(
                    {
                        "id": catalog["id"],
                        "name": catalog.get("name", catalog["id"]),
                        "status": "approved_pending_publish",
                        "provider": catalog.get("owner", ""),
                        "source_ref": catalog.get("source_ref") or f"provider:catalog:{catalog['id']}",
                        "legacy_object_ref": catalog.get("legacy_object_ref") or catalog["id"],
                        "summary_json": catalog,
                    }
                )
            catalog["status"] = "已发布"
            catalog["issue"] = f"已由 {actor} 完成目录发布确认"
            result = "published"
            event_type = "catalog.publish"
        else:
            catalog["issue"] = f"已由 {actor} 修正目录说明与默认复用入口文案"
            result = "revised"
            event_type = "catalog.revise"
        catalog["governanceLocked"] = True
        provider["aiGovernance"]["summary"] = "目录治理动作已落账，当前可继续推进资源状态和专区正式投影。"
        deps.append_audit_feed(event_type, catalog_id, "ok", actor)
        return {"catalog_id": catalog_id, "status": catalog["status"], "result": result}

    return deps.write(ctx, {"catalog_id": catalog_id, "action": action}, mutation)

def _query_catalog_models(brain, deps, ctx, *, model_code: Any = None) -> dict[str, Any]:
    repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
    models = [catalog_ser.catalog_model_to_dict(item) for item in repo.list_models(tenant_id=_DEFAULT_TENANT_ID)]
    if model_code:
        models = [item for item in models if item["model_code"] == str(model_code)]
    return {"items": models, "total": len(models)}

def _query_catalog_model_fields(brain, deps, ctx, model_code: str) -> dict[str, Any]:
    repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
    fields = [catalog_ser.catalog_model_field_to_dict(item) for item in repo.list_model_fields(model_code, tenant_id=_DEFAULT_TENANT_ID)]
    return {"items": fields, "total": len(fields)}

def _upsert_catalog_model(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
        model = repo.upsert_model(payload)
        for fld in payload.get("fields") or []:
            repo.upsert_model_field({**fld, "model_code": model.model_code})
        deps.append_audit_feed("catalog.model.upsert", model.model_code, "ok", actor)
        return {"model_code": model.model_code, "status": model.status, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _bind_catalog_resource(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))
    # F2 (E2 J2)：物化形式（table/file/api 等）由调用方在 payload 显式声明，
    # 仓库层不增列，handler 在 return 反射给前端 / e2e 判定。
    materialization_kind = payload.get("materialization_kind")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.metadata_evidence  # Action C — deps.repos always wired (DB or in-memory fallback)
        mapping = repo.upsert_schema_mapping({**payload, "confirmed_by": payload.get("confirmed_by") or actor})
        deps.append_audit_feed("catalog.resource.bind", mapping.mapping_code, "ok", actor)
        result: dict[str, Any] = {
            "mapping_code": mapping.mapping_code,
            "status": mapping.status,
            "audit_id": audit_id,
        }
        if materialization_kind:
            result["materialization_kind"] = str(materialization_kind)
        return result

    return deps.write(ctx, payload, mutation)

def _get_resource(brain, deps, ctx, resource_id: str, *, context: _RequestBatchContext | None = None) -> dict[str, Any]:
    store = deps.state_store.database_store
    snapshot_miss = False
    try:
        resource = copy.deepcopy(brain._resource_by_id(resource_id))
    except NotFoundError:
        if store is None:
            raise
        snapshot_miss = True
        resource = {}
    if store is None:
        return resource
    record = deps.repos.catalog.get_entry(resource_id, tenant_id=_DEFAULT_TENANT_ID)
    if record is not None:
        detail = brain._catalog_record_to_card_dict(record)
        brain._enrich_catalog_detail(detail, record, store, context=context)
        return detail
    asset = deps.repos.resource_api.get_asset(resource_id, tenant_id=_DEFAULT_TENANT_ID)
    if asset is not None and asset.catalog_code:
        record = deps.repos.catalog.get_entry(asset.catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if record is not None:
            detail = brain._catalog_record_to_card_dict(record)
            brain._enrich_catalog_detail(detail, record, store, focused_resource_code=asset.resource_code, context=context)
            return detail
    if snapshot_miss:
        raise NotFoundError(resource_id)
    return resource

def _upsert_catalog_schema_mapping(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.metadata_evidence  # Action C — deps.repos always wired (DB or in-memory fallback)
        mapping = repo.upsert_schema_mapping({**payload, "confirmed_by": payload.get("confirmed_by") or actor})
        deps.append_audit_feed("catalog.schema.mapping.upsert", mapping.mapping_code, "ok", actor)
        return {"mapping_code": mapping.mapping_code, "status": mapping.status, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _query_catalog_share_zones(brain, deps, ctx) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    store = deps.state_store.database_store
    if store is None:
        zones = []
        for zone in deps.brain_legacy._snapshot.get("zones", []):
            zones.append(
                {
                    "zone_id": zone.get("id"),
                    "title": zone.get("title") or zone.get("name"),
                    "status": zone.get("status"),
                    "trust": copy.deepcopy(zone.get("trust", [])),
                    "next_actions": copy.deepcopy(zone.get("nextActions", [])),
                }
            )
        return {"items": zones, "total": len(zones)}
    packages = [
        brain._topic_package_list_projection(item)
        for item in deps.repos.topic_package.list_packages(tenant_id=_DEFAULT_TENANT_ID)
        if brain._topic_projection_kind(item) in {"catalog_group", "share_zone"}
    ]
    return {
        "items": packages,
        "total": len(packages),
        "source_fact": "legacy share_zone/share_group dump rows are empty; data_catalog_group/data_group_permission are projected through TopicPackage records.",
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_catalog_browse(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _browse_catalog_entries(brain, deps, ctx, page=payload.get("page"), limit=payload.get("limit"), lifecycle=payload.get("lifecycle"), kind=payload.get("kind"), owner_org_id=payload.get("owner_org_id"), query=payload.get("query"))

def handler_catalog_group_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_catalog_groups(brain, deps, ctx)

def handler_catalog_manage_entry(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _manage_catalog_entry(brain, deps, ctx, str(payload["catalog_id"]), str(payload["action"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_catalog_model_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_catalog_models(brain, deps, ctx, model_code=payload.get("model_code"))

def handler_catalog_model_field_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_catalog_model_fields(brain, deps, ctx, str(payload["model_code"]))

def handler_catalog_model_upsert(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _upsert_catalog_model(brain, deps, ctx, payload)

def handler_catalog_resource_bind(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _bind_catalog_resource(brain, deps, ctx, payload)

def handler_catalog_resource_view(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _get_resource(brain, deps, ctx, str(payload["resource_id"]))

def handler_catalog_schema_mapping_upsert(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _upsert_catalog_schema_mapping(brain, deps, ctx, payload)

def handler_catalog_share_zone_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_catalog_share_zones(brain, deps, ctx)

