"""Live provider inbox projection for WebUI P5.

P5Provider.vue reads ``provider.field_decisions`` / ``hookup_reviews`` /
``demand_matches`` for todo counts. Canonical DB state is projected here on
each ``system.snapshot`` call — not stored in seed_snapshot.json.
"""

from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.repositories.topic_package import TopicPackageRepository
from zw_brain.domain.resource_kind import canonical_resource_kind
from zw_brain.domain.supply_demand_phase import (
    PHASE_MANUAL_REGISTERED,
    PHASE_RECOMMEND_FAILED,
    PHASE_REGISTERED,
)
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEMAND_PROVIDER_PHASES = frozenset(
    {PHASE_REGISTERED, PHASE_MANUAL_REGISTERED, PHASE_RECOMMEND_FAILED}
)


def _entry_to_field_decision(record: Any) -> dict[str, Any]:
    return {
        "id": record.catalog_code,
        "title": record.title,
        "status": record.lifecycle_status,
        "owner_org_id": record.owner_org_id,
    }


def _asset_to_hookup_review(record: Any) -> dict[str, Any]:
    return {
        "id": record.resource_code,
        "title": record.title,
        "status": record.lifecycle_status,
        "catalog_code": record.catalog_code,
    }


def _demand_to_match(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "title": str(payload.get("title") or ""),
        "status": str(payload.get("demand_phase") or payload.get("status") or ""),
        "applicant_dept": str(payload.get("applicantDept") or ""),
    }


def _case_to_objection_inbox(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "status": record.status,
        "target_type": record.target_type,
        "target_id": record.target_id,
    }


# API 服务资源生命周期 → 政务白话状态（R12，与 statusLabels 同口径）。
_API_SERVICE_STATUS_LABELS = {
    "draft": "草稿",
    "pending_review": "待审核",
    "approved": "已通过",
    "approved_pending_publish": "待发布",
    "test_failed": "测试未通过",
    "active": "已发布",
    "suspended": "已暂停",
    "revoked": "已撤销",
    "retired": "已退役",
}


def _api_asset_to_service(record: Any) -> dict[str, Any]:
    """真实 API 服务资产 → P5 API 服务列表/详情卡（D2，去 seed 演示服务）。

    id=resource_code（向导/列表/详情同锚），name=title，status=白话化生命周期，
    note=来源系统/描述（缺则空，诚实空态 D11）。qps 旧平台无此真实运行量 → 不伪造，留空。
    """
    summary = record.summary_json if isinstance(record.summary_json, dict) else {}
    return {
        "id": record.resource_code,
        "name": record.title or record.resource_code,
        "status": _API_SERVICE_STATUS_LABELS.get(str(record.lifecycle_status), record.lifecycle_status),
        "lifecycle_status": record.lifecycle_status,
        "catalog_code": record.catalog_code,
        "note": summary.get("desc") or summary.get("description") or summary.get("source_system") or "",
    }


def project_api_services(*, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """真实 resource_asset(kind=api) → API 服务列表（D2）。无则空（不回退演示 seed）。"""
    tenant_id = tenant_id or get_runtime_tenant_id()
    repo = ResourceApiRepository()
    return [
        _api_asset_to_service(record)
        for record in repo.list_assets(tenant_id=tenant_id)
        if str(getattr(record, "resource_kind", "")) in {"api", "service"}
    ]


# 目录管理清单排除的 catalog_code 前缀（语境收口，一词一概念）：
#   api-group:*  —— legacy API 分组目录（dsp-dataservice 导入物），其 live 形态由
#                   「接口服务注册」列表以真实 resource_asset(kind=api) 呈现，不属政务目录管理清单；
#   basic-elem:* —— 国家基本要素目录（D50 国家通道轨，入口在 P5 国家扩展要素编制），
#                   与政务目录编制双轨独立。
_MANAGE_EXCLUDED_CATALOG_PREFIXES = ("api-group:", "basic-elem:")


def _org_name_resolver(tenant_id: str):
    """org_code → 机构中文名（ReferenceService fail-soft：未命中回落 org id，诚实不造假）。"""
    from zw_brain.domain.services.reference_service import ReferenceService  # noqa: PLC0415

    ref = ReferenceService()
    cache: dict[str, str] = {}

    def resolve(org_id: Any) -> str:
        code = str(org_id or "")
        if not code:
            return ""
        if code not in cache:
            organ = ref.organ(code, tenant_id=tenant_id)
            cache[code] = str(organ["org_name"]) if organ and organ.get("org_name") else code
        return cache[code]

    return resolve


def project_provider_catalogs(*, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """真实 catalog_entry → 供数侧「目录管理」清单/概览行（T9 诚实化，承 #191 读路径单源）。

    口径：政务数据目录主线（排除前缀见 _MANAGE_EXCLUDED_CATALOG_PREFIXES）+ 排除已退役行
    （retired 是导入版本翻转的历史尾巴，不属管理态浏览）。无行时返回 []，由 enrich 回落
    seed 视图（与其他 enrich_* 的 replace-when-DB-nonempty 同模式）。
    schema_ref 批量预解析（list_schema_snapshots(resource_codes=…) 单查），保持与
    _attach_reverse_catalog_fields 同一回落链，反向编目向导零行级 N+1。
    """
    tenant_id = tenant_id or get_runtime_tenant_id()
    repo = CatalogRepository()
    records = [
        rec
        # api-group:* 占行最大（近千行）→ SQL 侧先排，其余 python 侧收口。
        for rec in repo.list_entries(tenant_id=tenant_id, exclude_catalog_code_prefix="api-group:")
        if rec.lifecycle_status != "retired"
        and not str(rec.catalog_code).startswith(_MANAGE_EXCLUDED_CATALOG_PREFIXES)
    ]
    if not records:
        return []

    metadata_repo = MetadataEvidenceRepository()
    snaps = metadata_repo.list_schema_snapshots(
        resource_codes=[str(rec.catalog_code) for rec in records], tenant_id=tenant_id
    )
    schema_by_code: dict[str, str] = {}
    for snap in snaps:  # captured_at 升序：首个兜底，table 快照优先（与 _attach 同序）
        code = str(snap.resource_code)
        if ":db_meta_table:" in snap.snapshot_ref:
            schema_by_code[code] = snap.snapshot_ref
        else:
            schema_by_code.setdefault(code, snap.snapshot_ref)

    org_name = _org_name_resolver(tenant_id)
    rows: list[dict[str, Any]] = []
    for rec in records:
        summary = rec.summary_json if isinstance(rec.summary_json, dict) else {}
        code = str(rec.catalog_code)
        source_ref = str(summary.get("source_ref") or "")
        rows.append(
            {
                "id": code,
                "catalog_code": code,
                "data_catalog_code": str(summary.get("data_catalog_code") or ""),
                "name": rec.title or code,
                "status": rec.lifecycle_status,
                "lifecycle_status": rec.lifecycle_status,
                "owner_org_id": rec.owner_org_id,
                "owner": org_name(rec.owner_org_id) or str(rec.owner_org_id or ""),
                "source_ref": source_ref,
                "legacy_object_ref": str(summary.get("legacy_object_ref") or ""),
                # 与 _attach_reverse_catalog_fields 同回落链：表快照 > 任一快照 > source_ref；
                # 都没有则诚实留空（反向编目向导 validate 会拦「缺 schema 引用」）。
                "schema_ref": schema_by_code.get(code, "") or source_ref,
            }
        )
    return rows


def project_provider_resources(*, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """真实 resource_asset → 供数侧「资源管理」清单/概览行（T9 诚实化）。

    全物化形态（库表/文件/接口）一并呈现、kind 标签区分；排除已退役行。无行返回 []
    （enrich 回落 seed 视图）。
    """
    tenant_id = tenant_id or get_runtime_tenant_id()
    repo = ResourceApiRepository()
    org_name = _org_name_resolver(tenant_id)
    rows: list[dict[str, Any]] = []
    for rec in repo.list_assets(tenant_id=tenant_id):
        if rec.lifecycle_status == "retired":
            continue
        rows.append(
            {
                "id": rec.resource_code,
                "name": rec.title or rec.resource_code,
                "status": rec.lifecycle_status,
                "lifecycle_status": rec.lifecycle_status,
                "resource_kind": canonical_resource_kind(rec.resource_kind),
                "catalog_code": rec.catalog_code,
                "owner_org_id": rec.owner_org_id,
                "owner": org_name(rec.owner_org_id) or str(rec.owner_org_id or ""),
                "source_ref": rec.source_ref,
            }
        )
    return rows


def project_provider_inbox(*, tenant_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    tenant_id = tenant_id or get_runtime_tenant_id()
    catalog_repo = CatalogRepository()
    resource_repo = ResourceApiRepository()
    supply_repo = SupplyDemandRepository()
    objection_repo = ObjectionRepository()

    # 反向编目审核收件箱（0611 修复项 R-4 / 6.9#6）：口径 = source=reverse ∧ lifecycle=draft，
    # 与 confirm/reject handler 的可办前置严格一致（catalog_entry.py 要求 source=='reverse'
    # 且 lifecycle=='draft'）。此前列 pending_review 全集——既含正向编制在审单、又含已确认
    # 的反向单，待审草稿反而不出现，收件箱里每行点「通过审核」必 409 死循环。
    # source 在 summary_json（无列），lifecycle 先在 SQL 收窄、source 在 python 收口。
    field_decisions = [
        _entry_to_field_decision(record)
        for record in catalog_repo.list_entries(tenant_id=tenant_id, lifecycle_status="draft")
        if isinstance(record.summary_json, dict) and record.summary_json.get("source") == "reverse"
    ]
    # 待发布目录（业务运营员待办，业务方原话锚点）：已审过待发布的目录。
    publish_queue = [
        _entry_to_field_decision(record)
        for record in catalog_repo.list_entries(
            tenant_id=tenant_id, lifecycle_status="approved_pending_publish"
        )
    ]
    # G4：挂接审核收件箱按 resource_kind 分流——API/service 资产走独立向导页（行内注册审核），
    # 其余（库表/文件，**含 kind 缺失的脏行**）都进挂接收件箱：审核正是兜住脏数据的环节，
    # kind 缺失行若被过滤会静默卡死在 pending_review（违诚实呈现），故用「排除 API」而非
    # 「白名单 table/file」；canonical_resource_kind 折叠 legacy 值（service→api、folder→file）。
    hookup_reviews = [
        _asset_to_hookup_review(record)
        for record in resource_repo.list_assets(tenant_id=tenant_id, lifecycle_status="pending_review")
        if canonical_resource_kind(getattr(record, "resource_kind", None)) != "api"
    ]
    demand_matches = [
        _demand_to_match(item)
        for item in supply_repo.list_demands(tenant_id=tenant_id)
        if item.get("demand_phase") in _DEMAND_PROVIDER_PHASES
    ]
    objection_cases = [
        _case_to_objection_inbox(record)
        for record in objection_repo.list_cases(tenant_id=tenant_id, status="provider_investigating")
    ]
    return {
        "field_decisions": field_decisions,
        "publish_queue": publish_queue,
        "hookup_reviews": hookup_reviews,
        "demand_matches": demand_matches,
        "objection_cases": objection_cases,
    }


def _attach_reverse_catalog_fields(catalog: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    """Ensure P5 反向编目 wizard 能拿到 catalog_code / schema_ref。"""
    out = copy.deepcopy(catalog)
    out.setdefault("catalog_code", out.get("legacy_object_ref") or out.get("id"))
    if out.get("schema_ref"):
        return out
    metadata_repo = MetadataEvidenceRepository()
    resource_code = out.get("canonical_resource_id") or out.get("id")
    if resource_code:
        snaps = metadata_repo.list_schema_snapshots(resource_code=str(resource_code), tenant_id=tenant_id)
        table_ref = next((snap.snapshot_ref for snap in snaps if ":db_meta_table:" in snap.snapshot_ref), None)
        if table_ref:
            out["schema_ref"] = table_ref
            return out
        if snaps:
            out["schema_ref"] = snaps[0].snapshot_ref
            return out
    legacy = out.get("legacy_object_ref")
    canonical = out.get("canonical_resource_id")
    if canonical and legacy:
        out["schema_ref"] = f"{canonical}:legacy:{legacy}"
    elif out.get("source_ref"):
        out["schema_ref"] = str(out["source_ref"])
    return out


def enrich_zones_snapshot(snapshot: dict[str, Any], *, tenant_id: str | None = None) -> dict[str, Any]:
    """Attach subscribe-ready package_code to P7 zone cards."""
    tenant_id = tenant_id or get_runtime_tenant_id()
    out = copy.deepcopy(snapshot)
    zones = out.get("zones")
    if not isinstance(zones, list):
        return out
    repo = TopicPackageRepository()
    published = [p for p in repo.list_packages(tenant_id=tenant_id) if p.status == "published"]
    fallback = published[0].package_code if published else None
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        zid = str(zone.get("id") or "")
        if repo.get_package(zid, tenant_id=tenant_id) is not None:
            zone["package_code"] = zid
        elif fallback:
            zone["package_code"] = fallback
    return out


def enrich_provider_snapshot(snapshot: dict[str, Any], *, tenant_id: str | None = None) -> dict[str, Any]:
    """Merge live inbox projection into *snapshot*['provider'] (deep copy)."""
    tenant_id = tenant_id or get_runtime_tenant_id()
    out = copy.deepcopy(snapshot)
    provider = out.setdefault("provider", {})
    inbox = project_provider_inbox(tenant_id=tenant_id)
    provider["field_decisions"] = inbox["field_decisions"]
    provider["publish_queue"] = inbox["publish_queue"]
    provider["hookup_reviews"] = inbox["hookup_reviews"]
    provider["demand_matches"] = inbox["demand_matches"]
    provider["objection_cases"] = inbox["objection_cases"]
    # D2：API 服务列表来自真实 resource_asset(kind=api)，不再读 seed 写死的演示 services
    # （承 D47 演示诚实化）。注册产出（resource.api.register）即时在此可见。
    provider["services"] = project_api_services(tenant_id=tenant_id)
    # T9 诚实化（承 #191 读路径单源 / D11）：目录·资源管理清单与概览读真实库现算，
    # 不再停留在 seed 演示行——新编目录/新挂资源即时可见。DB 空时回落 seed 视图
    # （replace-when-DB-nonempty，与 discovery/requests 等 enrich 同模式）。
    live_catalogs = project_provider_catalogs(tenant_id=tenant_id)
    if live_catalogs:
        # schema_ref 已在投影内批量预解析（同回落链），不再走行级 _attach（防 N+1）。
        provider["catalogs"] = live_catalogs
    else:
        catalogs = provider.get("catalogs")
        if isinstance(catalogs, list):
            provider["catalogs"] = [
                _attach_reverse_catalog_fields(item, tenant_id=tenant_id) if isinstance(item, dict) else item
                for item in catalogs
            ]
    live_resources = project_provider_resources(tenant_id=tenant_id)
    if live_resources:
        provider["resources"] = live_resources
    return out
