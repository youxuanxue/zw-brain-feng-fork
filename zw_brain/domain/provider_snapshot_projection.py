"""Live provider inbox projection for WebUI P5.

P5Provider.vue reads ``provider.field_decisions`` / ``hookup_reviews`` /
``demand_matches`` for todo counts. Canonical DB state is projected here on
each ``system.snapshot`` call — not stored in seed_snapshot.json.
"""

from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.lifecycle_timeline import (
    catalog_lifecycle_timeline,
    lifecycle_sideline_note,
    objection_sideline_note,
    objection_timeline,
    resource_lifecycle_timeline,
)
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.repositories.topic_package import TopicPackageRepository
from zw_brain.domain.resource_kind import canonical_resource_kind
from zw_brain.domain.services.reference_service import ReferenceService
from zw_brain.domain.supply_demand_phase import (
    PHASE_MANUAL_REGISTERED,
    PHASE_RECOMMEND_FAILED,
    PHASE_REGISTERED,
)
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEMAND_PROVIDER_PHASES = frozenset(
    {PHASE_REGISTERED, PHASE_MANUAL_REGISTERED, PHASE_RECOMMEND_FAILED}
)

# 模块级深拷贝引用：enrich_* 的 ``copy: bool`` 形参会在函数体内遮蔽 ``copy`` 模块名，
# 故经此别名调用 deepcopy，不受形参遮蔽影响（S3 deepcopy 开关）。
_deepcopy = copy.deepcopy


def _copy_snapshot(snapshot: dict[str, Any], do_copy: bool) -> dict[str, Any]:
    """``do_copy=True`` → deepcopy（默认纯函数语义）；False → 原样返回供原地写（handler 已统一拷过）。"""
    return _deepcopy(snapshot) if do_copy else snapshot


def _entry_to_field_decision(record: Any, *, owner_name: str = "") -> dict[str, Any]:
    """反向编目草稿 → 部门审收件箱/详情行（D57⑧）。

    带被审内容（去盲批，同 D57⑨/R10 口径）：责任单位中文名（缺则回落 org id 诚实展示）
    + 字段建议数（向导生成的 draft_field_suggestions 条数，缺省 0）。
    """
    summary = record.summary_json if isinstance(record.summary_json, dict) else {}
    suggestions = summary.get("draft_field_suggestions")
    return {
        "id": record.catalog_code,
        "title": record.title,
        "status": record.lifecycle_status,
        "owner_org_id": record.owner_org_id,
        "owner": owner_name or str(record.owner_org_id or ""),
        "field_count": len(suggestions) if isinstance(suggestions, list) else 0,
    }


# 共享类型机器值 → 政务白话（与 discovery 投影同口径；缺省诚实留空）。
_SHARE_TYPE_LABELS = {"1": "无条件共享", "2": "有条件共享", "3": "不予共享"}

# 资源物化形态 → 中文标签（挂接审核收件箱被审内容用；canonical 折叠后仅 table/file 进收件箱）。
_HOOKUP_KIND_LABELS = {"table": "库表", "file": "文件"}


def _asset_to_hookup_review(
    record: Any,
    *,
    catalog_title: str = "",
    owner_name: str = "",
) -> dict[str, Any]:
    """挂接资产 → 审核收件箱行（D57⑨/R10 去盲批：带被审登记信息，审核者看得到被审内容）。

    resource_name/catalog_name 喂前端「关联资源」列（此前两键缺失 → safeCatalogName 恒「—」）；
    kind/owner/source_ref/desc/share_type/field_count 喂行内被审详情（挂接登记信息），
    全部取真实登记字段、缺省诚实留空（D11，不造假）。
    """
    summary = record.summary_json if isinstance(record.summary_json, dict) else {}
    policy = record.access_policy_json if isinstance(record.access_policy_json, dict) else {}
    kind = canonical_resource_kind(getattr(record, "resource_kind", None))
    fields = summary.get("fields")
    # 挂接位置：legacy 导入走 source_ref 列；UI 新挂接（resource_mount）落 summary（文件
    # access_path / 库表 table_name），按此回落链取，仍缺则诚实留空。
    mount_ref = (
        str(record.source_ref or "")
        or str(summary.get("access_path") or "")
        or str(summary.get("table_name") or "")
    )
    return {
        "id": record.resource_code,
        "title": record.title,
        "status": record.lifecycle_status,
        "catalog_code": record.catalog_code,
        "resource_name": record.title or "",
        "catalog_name": catalog_title,
        "resource_kind": kind,
        "kind_label": _HOOKUP_KIND_LABELS.get(kind, ""),
        "owner": owner_name or str(record.owner_org_id or ""),
        "source_ref": mount_ref,
        # 资源描述：挂接向导业务块键 resource_desc；legacy/api 同义键 desc/description 回落。
        "desc": str(summary.get("resource_desc") or summary.get("desc") or summary.get("description") or ""),
        "share_type_label": _SHARE_TYPE_LABELS.get(str(policy.get("share_type") or ""), ""),
        "field_count": len(fields) if isinstance(fields, list) else 0,
    }


def _demand_to_match(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "title": str(payload.get("title") or ""),
        "status": str(payload.get("demand_phase") or payload.get("status") or ""),
        "applicant_dept": str(payload.get("applicantDept") or ""),
    }


def _case_to_objection_inbox(record: Any) -> dict[str, Any]:
    """供方异议收件箱行（G：补回必要字段——此前只产 5 字段，列表比详情还薄）。

    补 objection_kind（异议类型）+ complainant/provider org（target_org_id 滤器原是死代码：
    列表无此字段无法按机构筛）+ created_at（提交时间排序/展示）+ basis/expected（一句话诉求摘要，
    审办人列表即可判轻重，不必每行进详情）+ status timeline（办理脊柱「卡在谁桌上」现算）。
    全部取真实记录字段、缺省诚实留空（D11，不造假）。
    """
    return {
        "id": record.id,
        "title": record.title,
        "status": record.status,
        "objection_kind": getattr(record, "objection_kind", ""),
        "target_type": record.target_type,
        "target_id": record.target_id,
        "complainant_org_id": getattr(record, "complainant_org_id", "") or "",
        "provider_org_id": getattr(record, "provider_org_id", "") or "",
        "basis_text": getattr(record, "basis_text", "") or "",
        "expected_result": getattr(record, "expected_result", "") or "",
        "created_at": record.created_at.isoformat() if getattr(record, "created_at", None) else "",
        # G 脊柱：异议办理 timeline（提交→受理→核查→办结→归档）现算 + 支线态（驳回）标注。
        "statusTimeline": objection_timeline(record.status),
        "lifecycleNote": objection_sideline_note(record.status),
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


def project_api_services(
    *, tenant_id: str | None = None, visible_org_codes: set[str] | None = None,
    assets: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """真实 resource_asset(kind=api) → API 服务列表（D2）。无则空（不回退演示 seed）。

    部门数据可见域收口（M4）：按资产 owner_org_id 过滤——visible_org_codes=None 全量放行
    （全局角色），集=仅本机构(+下级)，空集=fail-closed 返空。org_in_scope 三态 + 名/码归一。

    ``assets`` 万级规模性能（S3）：调用方（handler_system_snapshot）可一次性预取全量
    resource_asset 传入，避免一次 system.snapshot 内 resource_asset 全表被各投影各扫一遍。
    行级 kind/owner 过滤在内存做。``None``=回落自查（保函数独立可测/独立调用方不变）。
    """
    tenant_id = tenant_id or get_runtime_tenant_id()
    repo = ResourceApiRepository()
    ref = ReferenceService()
    rows = assets if assets is not None else repo.list_assets(tenant_id=tenant_id)
    return [
        _api_asset_to_service(record)
        for record in rows
        if str(getattr(record, "resource_kind", "")) in {"api", "service"}
        and ref.org_in_scope(record.owner_org_id, visible_org_codes, tenant_id=tenant_id)
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


def project_provider_catalogs(
    *, tenant_id: str | None = None, visible_org_codes: set[str] | None = None
) -> list[dict[str, Any]]:
    """真实 catalog_entry → 供数侧「目录管理」清单/概览行（T9 诚实化，承 #191 读路径单源）。

    口径：政务数据目录主线（排除前缀见 _MANAGE_EXCLUDED_CATALOG_PREFIXES）+ 排除已退役行
    （retired 是导入版本翻转的历史尾巴，不属管理态浏览）。无行时返回 []，由 enrich 回落
    seed 视图（与其他 enrich_* 的 replace-when-DB-nonempty 同模式）。
    schema_ref 批量预解析（list_schema_snapshots(resource_codes=…) 单查），保持与
    _attach_reverse_catalog_fields 同一回落链，反向编目向导零行级 N+1。

    部门数据可见域收口（M4）：按 catalog rec.owner_org_id 过滤——visible_org_codes=None 全量
    放行（全局角色），集=仅本机构(+下级)，空集=fail-closed 返空。org_in_scope 三态 + 名/码归一。
    """
    tenant_id = tenant_id or get_runtime_tenant_id()
    repo = CatalogRepository()
    ref = ReferenceService()
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
        # 部门数据可见域行级过滤（M4）：按目录责任单位收口本机构(+下级)。
        if not ref.org_in_scope(rec.owner_org_id, visible_org_codes, tenant_id=tenant_id):
            continue
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
                # D57⑨/R-10 闭环（目录侧）：审核退回/驳回理由随清单行回显（return_for_fix /
                # reject 落 summary.review_return_reason）。供数方在目录管理清单看到整改依据；
                # 与资源侧 project_provider_resources 同键。无驳回则空。
                "review_return_reason": str(summary.get("review_return_reason") or ""),
                # J2 供数脊柱（F）：生命周期 timeline 现算（草稿→部门审→平台审→待发布→已发布），
                # 前端 PhaseTrack 渲「卡在谁桌上」。支线态（驳回/退役）无 stepper、给中文标注。
                "statusTimeline": catalog_lifecycle_timeline(rec.lifecycle_status),
                "lifecycleNote": lifecycle_sideline_note(rec.lifecycle_status),
            }
        )
    return rows


def project_provider_resources(
    *, tenant_id: str | None = None, visible_org_codes: set[str] | None = None,
    assets: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """真实 resource_asset → 供数侧「资源管理」清单/概览行（T9 诚实化）。

    全物化形态（库表/文件/接口）一并呈现、kind 标签区分；排除已退役行。无行返回 []
    （enrich 回落 seed 视图）。

    部门数据可见域收口（M4）：按资源 rec.owner_org_id 过滤——visible_org_codes=None 全量
    放行（全局角色），集=仅本机构(+下级)，空集=fail-closed 返空。org_in_scope 三态 + 名/码归一。

    ``assets`` 万级规模性能（S3）：调用方可预取全量 resource_asset 传入，避免重复全扫；
    行级 lifecycle/owner 过滤在内存做。``None``=回落自查（保函数独立可测/独立调用方不变）。
    """
    tenant_id = tenant_id or get_runtime_tenant_id()
    repo = ResourceApiRepository()
    ref = ReferenceService()
    org_name = _org_name_resolver(tenant_id)
    rows: list[dict[str, Any]] = []
    source = assets if assets is not None else repo.list_assets(tenant_id=tenant_id)
    for rec in source:
        if rec.lifecycle_status == "retired":
            continue
        # 部门数据可见域行级过滤（M4）：按资源责任单位收口本机构(+下级)。
        if not ref.org_in_scope(rec.owner_org_id, visible_org_codes, tenant_id=tenant_id):
            continue
        summary = rec.summary_json if isinstance(rec.summary_json, dict) else {}
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
                # D57⑨/R-10 闭环：审核驳回理由（return_for_fix 落 summary）随清单行回显，
                # 提交方在「资源管理清单」看到整改依据（写了就必须有读面）；无驳回则空。
                "review_return_reason": str(summary.get("review_return_reason") or ""),
                # J2 供数脊柱（F）：资源生命周期 timeline 现算（草稿→挂接审核→待发布→已发布）。
                "statusTimeline": resource_lifecycle_timeline(rec.lifecycle_status),
                "lifecycleNote": lifecycle_sideline_note(rec.lifecycle_status),
            }
        )
    return rows


def project_provider_inbox(
    *, tenant_id: str | None = None, visible_org_codes: set[str] | None = None
) -> dict[str, list[dict[str, Any]]]:
    """供数侧收件箱投影（部门审/挂接审/待发布/供需/异议）。

    部门数据可见域收口（M4）：仅 field_decisions（反向编目部门审）与 hookup_reviews（挂接审核）
    按其底层记录 owner_org_id 过滤本机构(+下级)。其余三键保持全量、不按部门收口（见各自落点注释）。
    """
    tenant_id = tenant_id or get_runtime_tenant_id()
    catalog_repo = CatalogRepository()
    resource_repo = ResourceApiRepository()
    supply_repo = SupplyDemandRepository()
    objection_repo = ObjectionRepository()
    ref = ReferenceService()

    org_name = _org_name_resolver(tenant_id)

    # 反向编目审核收件箱（0611 修复项 R-4 / 6.9#6；D57⑧ 后=部门审收件箱）：口径 =
    # source=reverse ∧ lifecycle=draft，与 confirm/reject handler 的可办前置严格一致
    # （catalog_entry.py 要求 source=='reverse' 且 lifecycle=='draft'）。此前列 pending_review
    # 全集——既含正向编制在审单、又含已确认的反向单，待审草稿反而不出现，收件箱里每行点
    # 「通过审核」必 409 死循环。source 在 summary_json（无列），lifecycle 先在 SQL 收窄、
    # source 在 python 收口。
    field_decisions = [
        _entry_to_field_decision(record, owner_name=org_name(record.owner_org_id))
        for record in catalog_repo.list_entries(tenant_id=tenant_id, lifecycle_status="draft")
        if isinstance(record.summary_json, dict) and record.summary_json.get("source") == "reverse"
        # 部门数据可见域行级过滤（M4）：部门审收件箱仅见本机构(+下级)目录。
        and ref.org_in_scope(record.owner_org_id, visible_org_codes, tenant_id=tenant_id)
    ]
    # 待发布目录（业务运营员待办，业务方原话锚点）：已审过待发布的目录。
    # M4 不按部门收口：待发布是平台级发布动作（BUSIAUDIT 业务运营员全局待办），非部门管理面。
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
    # D57⑨/R10 去盲批：行内补被审登记信息——所属目录名（catalog_entry 解析）+ 提供方
    # 机构名（ReferenceService）+ 登记字段（形态/挂接位置/描述/共享类型/字段数）。
    hookup_assets = [
        record
        for record in resource_repo.list_assets(tenant_id=tenant_id, lifecycle_status="pending_review")
        if canonical_resource_kind(getattr(record, "resource_kind", None)) != "api"
        # 部门数据可见域行级过滤（M4）：挂接审核收件箱仅见本机构(+下级)资源。
        and ref.org_in_scope(record.owner_org_id, visible_org_codes, tenant_id=tenant_id)
    ]
    catalog_title_cache: dict[str, str] = {}

    def _catalog_title(code: Any) -> str:
        key = str(code or "")
        if not key:
            return ""
        if key not in catalog_title_cache:
            entry = catalog_repo.get_entry(key, tenant_id=tenant_id)
            catalog_title_cache[key] = str(entry.title) if entry is not None and entry.title else ""
        return catalog_title_cache[key]

    hookup_reviews = [
        _asset_to_hookup_review(
            record,
            catalog_title=_catalog_title(record.catalog_code),
            owner_name=org_name(record.owner_org_id),
        )
        for record in hookup_assets
    ]
    # M4 不按部门收口：供需对接属 J2 供需脊柱（需求侧驱动），非供数方部门管理面，本切片不纳入。
    demand_matches = [
        _demand_to_match(item)
        for item in supply_repo.list_demands(tenant_id=tenant_id)
        if item.get("demand_phase") in _DEMAND_PROVIDER_PHASES
    ]
    # 异议收件箱（D57①，R-6）：纳入在办全态——submitted（待受理，接 objection.case.accept）、
    # platform_investigating（受理后平台核查中，受理动作的落点态，不纳则案件受理即从唯一
    # 工作面消失=新死端）、provider_investigating（部门核查中，原有口径）。终态
    # （resolved/rejected/closed）与 draft（未提交）不进收件箱。
    # M4 不按部门收口：异议收件箱的部门可见域由独立切片（M7 disputes）按 complainant/provider org 收口，本切片不重复过滤。
    _OBJECTION_INBOX_STATUSES = ("submitted", "platform_investigating", "provider_investigating")
    objection_cases = [
        _case_to_objection_inbox(record)
        for status in _OBJECTION_INBOX_STATUSES
        for record in objection_repo.list_cases(tenant_id=tenant_id, status=status)
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


def enrich_zones_snapshot(
    snapshot: dict[str, Any], *, tenant_id: str | None = None, copy: bool = True
) -> dict[str, Any]:
    """Attach subscribe-ready package_code to P7 zone cards.

    ``copy`` 万级规模性能（S3）：默认 True 深拷（纯函数语义）；handler 链路传 ``copy=False`` 原地写。
    """
    tenant_id = tenant_id or get_runtime_tenant_id()
    out = _copy_snapshot(snapshot, copy)
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


def enrich_provider_snapshot(
    snapshot: dict[str, Any], *, tenant_id: str | None = None,
    visible_org_codes: set[str] | None = None,
    assets: list[Any] | None = None, copy: bool = True,
) -> dict[str, Any]:
    """Merge live inbox projection into *snapshot*['provider'].

    ``visible_org_codes`` 部门数据可见域（M3 接入，M4 落过滤）：None=全局放行 / 集=按
    owner_org_id 收口本机构(+下级) / 空集=fail-closed 返空。见 ReferenceService.visible_org_codes。

    ``copy``/``assets`` 万级规模性能（S3）：``copy`` 默认 True 深拷快照（纯函数语义，独立测试
    不变异入参）；handler 链路传 ``copy=False`` 原地写。``assets`` 预取的 resource_asset 供
    project_api_services/project_provider_resources 复用，避免重复全扫；``None``=回落各自自查。
    """
    tenant_id = tenant_id or get_runtime_tenant_id()
    out = _copy_snapshot(snapshot, copy)
    provider = out.setdefault("provider", {})
    inbox = project_provider_inbox(tenant_id=tenant_id, visible_org_codes=visible_org_codes)
    provider["field_decisions"] = inbox["field_decisions"]
    provider["publish_queue"] = inbox["publish_queue"]
    provider["hookup_reviews"] = inbox["hookup_reviews"]
    provider["demand_matches"] = inbox["demand_matches"]
    provider["objection_cases"] = inbox["objection_cases"]
    # D2：API 服务列表来自真实 resource_asset(kind=api)，不再读 seed 写死的演示 services
    # （承 D47 演示诚实化）。注册产出（resource.api.register）即时在此可见。
    provider["services"] = project_api_services(
        tenant_id=tenant_id, visible_org_codes=visible_org_codes, assets=assets
    )
    # T9 诚实化（承 #191 读路径单源 / D11）：目录·资源管理清单与概览读真实库现算，
    # 不再停留在 seed 演示行——新编目录/新挂资源即时可见。DB 空时回落 seed 视图
    # （replace-when-DB-nonempty，与 discovery/requests 等 enrich 同模式）。
    live_catalogs = project_provider_catalogs(tenant_id=tenant_id, visible_org_codes=visible_org_codes)
    if live_catalogs:
        # schema_ref 已在投影内批量预解析（同回落链），不再走行级 _attach（防 N+1）。
        provider["catalogs"] = live_catalogs
    elif visible_org_codes is None:
        # 仅**全局视角**（未部门收口）下 DB 真空才回落 seed 视图；部门收口下的空=权威空，
        # 绝不回落——否则 fail-closed（无机构上下文）/ 零目录部门会漏看 seed 演示目录，
        # 既破坏部门隔离、又违 D47 演示诚实化（回潮被删的演示单）。
        catalogs = provider.get("catalogs")
        if isinstance(catalogs, list):
            provider["catalogs"] = [
                _attach_reverse_catalog_fields(item, tenant_id=tenant_id) if isinstance(item, dict) else item
                for item in catalogs
            ]
    else:
        provider["catalogs"] = []  # 部门收口空 = 权威空（不回落 seed）
    live_resources = project_provider_resources(
        tenant_id=tenant_id, visible_org_codes=visible_org_codes, assets=assets
    )
    if live_resources:
        provider["resources"] = live_resources
    elif visible_org_codes is not None:
        provider["resources"] = []  # 部门收口空 = 权威空（同 catalogs，不保留 seed resources）
    return out
