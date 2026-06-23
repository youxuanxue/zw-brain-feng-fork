"""J1 catalog_entry handlers — 12 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from zw_brain.domain.models import CatalogEntryRecord, ResourceSchemaSnapshotRecord

import copy
import hashlib

from zw_brain.command.brain import BrainServiceError, InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import catalog as catalog_ser
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.resource_lifecycle import with_lifecycle_label
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sanitization import safe_json
from zw_brain.shared.session_context import caller_org_code

# ──────────────────────────────────────────────────────────────────────────
# 在线编制「基本信息」必填口径（提交审核时校验）
#
# 口径单源 = 《问题反馈-0611 业务口径确认单》§A（16 字段），负责人薛娇 2026-06-12 确认
# （草案建议全采纳，含 内部部门=选填、数据资源摘要=必填）。
# 前端字典权威 = zw-brain-web/src/lib/catalogCompileFields.ts `BASIC_INFO_FIELDS`；
# 本表为后端镜像（无现成生成物同步机制，两表改动必须同步；新增/调整必填位先改前端字典）。
#
# 校验范围：仅经 catalog.entry.create_draft 新铸的在线编制目录（其 summary_json 顶层
# 必有本 handler 注入的 data_catalog_code 业务码）。存量导入目录（旧平台迁移，约 1200+
# 条，大量缺字段）与反向编目草稿无此键 → 不回溯，避免必填校验卡死存量流转（fail-closed 误伤）。
# ──────────────────────────────────────────────────────────────────────────

_INLINE_BASIC_REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("catalog_type", "数据资源分类"),
    ("source_system", "来源系统"),
    ("domain", "所属领域"),
    ("application_scenario", "应用场景"),
    ("resource_format", "信息资源格式"),
    ("business_update_cycle", "业务更新周期"),
    ("data_update_cycle", "数据更新周期"),
    ("shared_way", "共享方式"),
    ("shared_type", "共享类型"),
    ("open_type", "开放类型"),
    ("description", "数据资源摘要"),
)
# 「有条件共享」码（dsp_catalog shared_type=2）→ 共享条件转必填；其余共享类型选填。
_CONDITIONAL_SHARE_TYPE = "2"


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _missing_inline_required_basic_fields(existing: Any) -> list[str]:
    """返回在线编制目录缺失的必填基本信息中文名；存量导入/反向编目目录恒返回 []。

    字段读取口径：create_draft 把表单基本信息嵌在 summary_json["summary_json"]，
    update 则展开到顶层（既有行为）——两处合并后取顶层优先，覆盖「创建即提交」与
    「保存元数据后提交」两条路径。
    """
    summary = existing.summary_json if isinstance(existing.summary_json, dict) else {}
    if "data_catalog_code" not in summary:
        return []
    nested = summary.get("summary_json")
    merged = {**(nested if isinstance(nested, dict) else {}), **summary}
    missing = [label for key, label in _INLINE_BASIC_REQUIRED_FIELDS if _is_blank(merged.get(key))]
    if not str(existing.title or "").strip():
        missing.insert(0, "数据资源目录名称")
    if str(merged.get("shared_type") or "") == _CONDITIONAL_SHARE_TYPE and _is_blank(merged.get("shared_condition")):
        missing.append("共享条件")
    return missing


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _derive_data_catalog_code(catalog_code: str, region_code: Any) -> str:
    """在线编制目录的「数据资源目录代码」业务码（T3②/T11）。

    内部 ``catalog_code`` slug（j2-inline-…）只作技术 id / 路由键 / 资源 join 键；
    用户面要看一个稳定、可读、明确为本地系统生成的业务码——不伪造 24-hex 国家登记码。
    格式 ``DRC-{region}-{8 位 slug 派生 hex}``：region 体现属地，hex 由 slug 确定性派生
    （同一草稿恒等、不每次重算），落 summary_json 单源、详情端按此投影。
    """
    region = str(region_code or "000000").strip() or "000000"
    digest = hashlib.sha256(catalog_code.encode("utf-8")).hexdigest()[:8]
    return f"DRC-{region}-{digest}"


def _create_catalog_entry_draft(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    catalog_code = str(payload["catalog_code"])
    data_catalog_code = _derive_data_catalog_code(catalog_code, payload.get("region_code"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        store = deps.state_store.database_store
        # 业务码注入资源 dict **顶层**（在线编制起）：upsert_from_resource 把整个 dict 落 record.
        # summary_json，summary_body() 不剥 `summary_json` 内层键、只读顶层；故 data_catalog_code 须
        # 与 id/name 平级才被 catalog_meta body.get 读到。update 路径 `**existing.summary_json`
        # 顶层展开保留它。存量导入目录无此键 → 详情端 catalogCode 回落 record.catalog_code，互不干扰。
        catalog_payload = {
            "id": catalog_code,
            "name": str(payload.get("title", catalog_code)),
            "status": "draft",
            # owner（供数面 org_in_scope 行级过滤源）：显式 owner_org_id 优先、回落可信会话当前
            # 机构 caller_org_code。前端在线编制向导原硬编码常量 owner_org_id=省大数据局码（已删），
            # 故现回落到 caller_org_code——否则非省大数据局操作员建目录后在自己「目录管理」清单
            # 看不到刚建草稿（owner 恒省大数据局，不在自己机构域内被 org_in_scope 过滤掉）。
            "provider": payload.get("owner_org_id") or caller_org_code(payload) or "",
            "region_code": payload.get("region_code"),
            "source_ref": payload.get("source_ref"),
            "legacy_object_ref": payload.get("legacy_object_ref") or catalog_code,
            "data_catalog_code": data_catalog_code,
            "summary_json": safe_json(payload.get("summary_json") or {}),
        }
        repo = deps.repos.catalog if store is not None else CatalogRepository()
        repo.upsert_from_resource(catalog_payload, tenant_id=_DEFAULT_TENANT_ID)
        for item in payload.get("items") or []:
            repo.upsert_item({**item, "catalog_code": catalog_code}, tenant_id=_DEFAULT_TENANT_ID)
        deps.append_audit_feed("catalog.entry.create_draft", catalog_code, "ok", actor)
        return with_lifecycle_label(
            {
                "catalog_code": catalog_code,
                "data_catalog_code": data_catalog_code,
                "lifecycle_status": "draft",
                "audit_id": audit_id,
            }
        )

    return deps.write(ctx, payload, mutation)

def _transition_catalog_entry(brain, deps, ctx, catalog_code: str, status: str, skill_id: str, role: str, confirmed: bool, review_note: str | None = None) -> dict[str, Any]:
    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
        existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if existing is None:
            raise NotFoundError(catalog_code)
        summary = copy.deepcopy(existing.summary_json)
        # D57⑨/R10：审核退回/驳回理由落 summary_json.review_return_reason（与资源侧同键，
        # 供数方在「目录管理清单」看到整改依据）。退回/驳回写理由；通过则清掉陈旧理由
        # （review_note 显式传入；通过路径传 "" 清除，其余路径 None 不触碰已存理由）。
        if review_note is not None:
            note = str(review_note).strip()
            if note:
                summary["review_return_reason"] = note
            else:
                summary.pop("review_return_reason", None)
        repo.upsert_from_resource(
            {
                **summary,
                "id": existing.catalog_code,
                "name": existing.title,
                "status": status,
                "provider": existing.owner_org_id or "",
                "region_code": existing.region_code,
                "source_ref": existing.summary_json.get("source_ref"),
                "legacy_object_ref": existing.catalog_code,
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        if status in {"active", "retired"}:
            repo.create_entry_version(
                {
                    "catalog_code": existing.catalog_code,
                    "version_no": f"{status}:{audit_id}",
                    "version_status": status,
                    "snapshot_json": {
                        "catalog_code": existing.catalog_code,
                        "title": existing.title,
                        "lifecycle_status": status,
                        "summary_json": copy.deepcopy(existing.summary_json),
                    },
                    "audit_ref": audit_id,
                    "created_by": actor,
                }
            )
        # Action C — deps.repos.approval always wired (DB or in-memory fallback)
        deps.repos.approval.upsert_catalog_entry_lifecycle(
            catalog_code,
            status,
            actor=actor,
            skill_id=skill_id,
            audit_id=audit_id,
            decision="return" if status in {"draft", "rejected"} else None,
            tenant_id=_DEFAULT_TENANT_ID,
        )
        deps.append_audit_feed(skill_id, catalog_code, "ok", actor)
        return with_lifecycle_label({"catalog_code": catalog_code, "lifecycle_status": status, "audit_id": audit_id})

    return deps.write(ctx, {"catalog_code": catalog_code, "status": status}, mutation)

def _parse_query_limit(value: Any) -> int | None:
    if value is None or value == "":
        return None
    parsed = int(value)
    if parsed < 1:
        raise ValueError("limit must be >= 1")
    return parsed


def _parse_query_offset(value: Any) -> int:
    if value is None or value == "":
        return 0
    parsed = int(value)
    if parsed < 0:
        raise ValueError("offset must be >= 0")
    return parsed


def _filter_entries_by_source(records: list[Any], source: Any) -> list[Any]:
    if not source:
        return records
    wanted_src = str(source)
    return [
        record
        for record in records
        if isinstance(record.summary_json, dict) and record.summary_json.get("source") == wanted_src
    ]


def _query_catalog_entries(
    brain,
    deps,
    ctx,
    *,
    query: Any = None,
    catalog_code: Any = None,
    source: Any = None,
    lifecycle_status: Any = None,
    limit: Any = None,
    offset: Any = None,
    order: Any = None,
) -> dict[str, Any]:
    """Query catalog entries with optional structural filters.

    `source` matches `summary_json.source` exactly (e.g. 'reverse' for
    reverse-cataloging drafts). `lifecycle_status` matches the column
    directly. Together they let the 业务运营员 inbox list "pending reverse
    draft" entries without an extra skill.

    ``order='updated_desc'`` 按 updated_at 倒序（工作队列「最新提交在前」口径，
    0611 断点 A：缺省 catalog_code 升序时新审结 j2-* 目录永排存量数字码之后、
    配合截断就永不可见）。缺省保持 catalog_code 升序（稳定浏览序）。仅结构化
    列表路径生效（query 检索路径按相关性返回）。
    """
    repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
    limit_value = _parse_query_limit(limit)
    offset_value = _parse_query_offset(offset)
    wanted_lc = str(lifecycle_status) if lifecycle_status else None
    order_by_recency = str(order or "") == "updated_desc"

    if query:
        records = repo.search_entries(str(query), tenant_id=_DEFAULT_TENANT_ID)
        if wanted_lc:
            records = [record for record in records if record.lifecycle_status == wanted_lc]
        records = _filter_entries_by_source(records, source)
        total = len(records)
        if limit_value is not None:
            records = records[offset_value : offset_value + limit_value]
    else:
        records = repo.list_entries(
            tenant_id=_DEFAULT_TENANT_ID,
            lifecycle_status=wanted_lc,
            limit=limit_value,
            offset=offset_value,
            order_by_recency=order_by_recency,
        )
        records = _filter_entries_by_source(records, source)
        if source:
            total = len(records)
        elif limit_value is not None:
            total = repo.count_entries(tenant_id=_DEFAULT_TENANT_ID, lifecycle_status=wanted_lc)
        else:
            total = len(records)

    entries = [catalog_ser.catalog_entry_to_dict(item) for item in records]
    if catalog_code:
        wanted_code = str(catalog_code)
        entries = [item for item in entries if item["catalog_code"] == wanted_code]
        total = len(entries)
    _attach_reference_names(entries)
    return {"items": entries, "total": total}


def _attach_reference_names(entries: list[dict[str, Any]]) -> None:
    """补机构/区划中文名（owner_org_name / region_name），收件箱等列表面不再裸出
    org id / 区划码（R12）。ReferenceService fail-soft：未命中留空，前端回落原值诚实展示。
    唯一码去重后逐个 lookup（一页 ≤20 行、机构/区划基数远小于行数，命中即缓存）。"""
    if not entries:
        return
    from zw_brain.domain.services.reference_service import ReferenceService  # noqa: PLC0415

    ref = ReferenceService()
    org_cache: dict[str, str] = {}
    region_cache: dict[str, str] = {}
    for item in entries:
        org_id = str(item.get("owner_org_id") or "")
        if org_id:
            if org_id not in org_cache:
                organ = ref.organ(org_id)
                org_cache[org_id] = str(organ["org_name"]) if organ and organ.get("org_name") else ""
            item["owner_org_name"] = org_cache[org_id]
        region_code = str(item.get("region_code") or "")
        if region_code:
            if region_code not in region_cache:
                region = ref.region(region_code)
                region_cache[region_code] = str(region["region_name"]) if region and region.get("region_name") else ""
            item["region_name"] = region_cache[region_code]

def _suggest_catalog_entry_reverse_draft(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    """Return three-tier field suggestions for a given schema snapshot.

    Read-only. Resolves `schema_ref` against ResourceSchemaSnapshotRecord
    and runs the tiered suggestion logic in `reverse_draft_suggest`.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from zw_brain.command.reverse_draft_suggest import (  # noqa: PLC0415
        build_field_suggestions,
        build_title_suggestion,
    )
    from zw_brain.domain.models import ResourceSchemaSnapshotRecord  # noqa: PLC0415
    from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

    tenant_id = str(payload.get("tenant_id") or _DEFAULT_TENANT_ID)
    schema_ref = str(payload["schema_ref"])
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        exact = session.execute(
            select(ResourceSchemaSnapshotRecord)
            .where(ResourceSchemaSnapshotRecord.tenant_id == tenant_id)
            .where(ResourceSchemaSnapshotRecord.snapshot_ref == schema_ref)
        ).scalar_one_or_none()
        catalog = _resolve_reverse_draft_catalog(session, tenant_id, schema_ref, payload)
        snapshots = _resolve_reverse_draft_snapshots(
            session,
            tenant_id,
            schema_ref=schema_ref,
            exact=exact,
            catalog=catalog,
            payload=payload,
        )
    if not snapshots:
        return {
            "schema_ref": schema_ref,
            "title_suggestion": build_title_suggestion(None),
            "fields": [],
            "coverage": {"green": 0, "yellow": 0, "orange": 0, "total": 0},
            "found": False,
        }
    schema_json = _reverse_draft_schema_payload(snapshots)
    first = snapshots[0]
    title_context = dict(schema_json)
    if catalog is not None:
        title_context.setdefault("title", catalog.title)
        title_context.setdefault("catalog_code", catalog.catalog_code)
    title_context.setdefault("schema_ref", schema_ref)
    title_context.setdefault("resource_code", first.resource_code)
    suggestions, coverage = build_field_suggestions(schema_json)
    title_suggestion = build_title_suggestion(title_context)
    return {
        "schema_ref": schema_ref,
        "resource_code": first.resource_code,
        "binding_code": first.binding_code,
        "title_suggestion": title_suggestion,
        "fields": suggestions,
        "coverage": coverage,
        "found": True,
    }


def _resolve_reverse_draft_catalog(
    session: Session,
    tenant_id: str,
    schema_ref: str,
    payload: dict[str, Any],
) -> CatalogEntryRecord | None:
    """Resolve the catalog selected by P5 reverse-cataloging.

    The UI operates on catalogs, but legacy import rows often expose a
    ``dsp-catalog3:data_catalog:*`` source ref while field snapshots are keyed by
    resource/table IDs. Keep exact ``catalog_code`` fast-path, then tolerate
    source/legacy refs from older snapshots.
    """
    from sqlalchemy import or_, select  # noqa: PLC0415

    from zw_brain.domain.models import CatalogEntryRecord  # noqa: PLC0415

    candidates = [
        str(payload.get("catalog_code") or "").strip(),
        str(payload.get("catalog_id") or "").strip(),
        schema_ref.strip(),
    ]
    codes = [c for c in dict.fromkeys(candidates) if c]
    if codes:
        direct = session.execute(
            select(CatalogEntryRecord)
            .where(CatalogEntryRecord.tenant_id == tenant_id)
            .where(CatalogEntryRecord.catalog_code.in_(codes))
            .order_by(CatalogEntryRecord.updated_at.desc())
        ).scalars().first()
        if direct is not None:
            return direct

    if not schema_ref:
        return None
    return session.execute(
        select(CatalogEntryRecord)
        .where(CatalogEntryRecord.tenant_id == tenant_id)
        .where(
            or_(
                CatalogEntryRecord.summary_json["source_ref"].as_string() == schema_ref,
                CatalogEntryRecord.summary_json["legacy_object_ref"].as_string() == schema_ref,
                CatalogEntryRecord.summary_json["schema_ref"].as_string() == schema_ref,
            )
        )
        .order_by(CatalogEntryRecord.updated_at.desc())
        .limit(1)
    ).scalars().first()


def _resolve_reverse_draft_snapshots(
    session: Session,
    tenant_id: str,
    *,
    schema_ref: str,
    exact: ResourceSchemaSnapshotRecord | None,
    catalog: CatalogEntryRecord | None,
    payload: dict[str, Any],
) -> list[ResourceSchemaSnapshotRecord]:
    if exact is not None:
        related = _schema_snapshots_for_codes(session, tenant_id, [exact.resource_code, exact.binding_code or ""])
        return related or [exact]

    from sqlalchemy import select  # noqa: PLC0415

    from zw_brain.domain.models import ResourceAssetRecord  # noqa: PLC0415

    resource_codes: list[str] = []
    if catalog is not None:
        assets = session.execute(
            select(ResourceAssetRecord)
            .where(ResourceAssetRecord.tenant_id == tenant_id)
            .where(ResourceAssetRecord.catalog_code == catalog.catalog_code)
            .order_by(ResourceAssetRecord.lifecycle_status.desc(), ResourceAssetRecord.updated_at.desc())
        ).scalars()
        resource_codes.extend(asset.resource_code for asset in assets)

    for key in ("resource_code", "binding_code"):
        value = str(payload.get(key) or "").strip()
        if value:
            resource_codes.append(value)
    if schema_ref:
        resource_codes.append(schema_ref)

    return _schema_snapshots_for_codes(session, tenant_id, resource_codes)


def _schema_snapshots_for_codes(
    session: Session,
    tenant_id: str,
    codes: list[str],
) -> list[ResourceSchemaSnapshotRecord]:
    normalized = [code for code in dict.fromkeys(codes) if code]
    if not normalized:
        return []
    from sqlalchemy import or_, select  # noqa: PLC0415

    from zw_brain.domain.models import ResourceSchemaSnapshotRecord  # noqa: PLC0415

    return list(
        session.execute(
            select(ResourceSchemaSnapshotRecord)
            .where(ResourceSchemaSnapshotRecord.tenant_id == tenant_id)
            .where(
                or_(
                    ResourceSchemaSnapshotRecord.resource_code.in_(normalized),
                    ResourceSchemaSnapshotRecord.binding_code.in_(normalized),
                )
            )
            .order_by(ResourceSchemaSnapshotRecord.captured_at)
        ).scalars()
    )


def _reverse_draft_schema_payload(snapshots: list[ResourceSchemaSnapshotRecord]) -> dict[str, Any]:
    columns: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    for snap in snapshots:
        schema = snap.schema_json if isinstance(snap.schema_json, dict) else {}
        if not meta:
            meta = {k: v for k, v in schema.items() if k not in {"columns", "fields", "column_list", "field_list"}}
        for key in ("columns", "fields", "column_list", "field_list"):
            value = schema.get(key)
            if isinstance(value, list):
                columns.extend(col for col in value if isinstance(col, dict))
                break
        else:
            if any(k in schema for k in ("column_name", "field_name", "name", "name_en", "column_code")):
                columns.append(schema)
    if columns:
        return {**meta, "columns": columns}
    return meta

def _create_catalog_entry_reverse_draft(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    catalog_code = str(payload["catalog_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
        schema_ref = str(payload.get("schema_ref", ""))
        # CatalogRepository.upsert_from_resource stores the whole resource
        # dict as summary_json, so put reverse-draft markers at top level.
        repo.upsert_from_resource(
            {
                "id": catalog_code,
                "name": str(payload.get("title", catalog_code)),
                "status": "draft",
                "provider": payload.get("owner_org_id", ""),
                "region_code": payload.get("region_code"),
                "source_ref": schema_ref,
                "legacy_object_ref": catalog_code,
                "source": "reverse",
                "schema_ref": schema_ref,
                "draft_field_suggestions": payload.get("draft_field_suggestions") or [],
                "created_by_audit": audit_id,
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        deps.append_audit_feed("catalog.entry.reverse_draft.create", catalog_code, "ok", actor)
        return with_lifecycle_label({"catalog_code": catalog_code, "lifecycle_status": "draft", "schema_ref": schema_ref, "audit_id": audit_id})

    return deps.write(ctx, payload, mutation)

def _confirm_catalog_entry_reverse_draft(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    """反向编目部门审通过（D57⑧ 两级管线第一级，部门管理员）。

    字段口径裁决（field_decisions）随部门审落 summary（语义保留在部门审级）。通过后
    直接落 ``pending_platform_review`` 汇入正向目录审核的**平台档**——由业务运营员在
    目录审核收件箱经既有 ``catalog.entry.review``（pending_platform_review + BUSIAUDIT
    → approved_pending_publish）复核，不另造第二套审核状态机。不落 ``pending_review``：
    那是正向编制的部门档，落它会让同一管理员对同一草稿部门审两遍（三级化）。
    """
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    catalog_code = str(payload["catalog_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
        existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if existing is None:
            raise NotFoundError(catalog_code)
        summary = copy.deepcopy(existing.summary_json or {})
        if summary.get("source") != "reverse":
            raise InvalidStateError(f"catalog_entry {catalog_code} is not a reverse draft (source={summary.get('source')!r})")
        if existing.lifecycle_status != "draft":
            raise InvalidStateError(f"catalog_entry {catalog_code} is not in draft (current={existing.lifecycle_status})")
        summary["status"] = "pending_platform_review"
        summary["field_decisions"] = payload.get("field_decisions") or []
        summary["confirmation_comment"] = payload.get("comment")
        summary["confirmed_by_audit"] = audit_id
        repo.upsert_from_resource(summary, tenant_id=_DEFAULT_TENANT_ID)
        deps.append_audit_feed("catalog.entry.reverse_draft.confirm", catalog_code, "ok", actor)
        return with_lifecycle_label({"catalog_code": catalog_code, "lifecycle_status": "pending_platform_review", "audit_id": audit_id})

    return deps.write(ctx, payload, mutation)

def _reject_catalog_entry_reverse_draft(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    """反向编目部门审驳回（D57⑧ 两级管线第一级，部门管理员；理由必填）。"""
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    catalog_code = str(payload["catalog_code"])
    reason = str(payload["reject_reason"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
        existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if existing is None:
            raise NotFoundError(catalog_code)
        summary = copy.deepcopy(existing.summary_json or {})
        if summary.get("source") != "reverse":
            raise InvalidStateError(f"catalog_entry {catalog_code} is not a reverse draft (source={summary.get('source')!r})")
        summary["status"] = "rejected"
        summary["rejected_reason"] = reason
        summary["rejected_by_audit"] = audit_id
        repo.upsert_from_resource(summary, tenant_id=_DEFAULT_TENANT_ID)
        deps.append_audit_feed("catalog.entry.reverse_draft.reject", catalog_code, "ok", actor)
        return with_lifecycle_label({"catalog_code": catalog_code, "lifecycle_status": "rejected", "reason": reason, "audit_id": audit_id})

    return deps.write(ctx, payload, mutation)

def _review_catalog_entry(brain, deps, ctx, catalog_code: str, decision: str, role: str, confirmed: bool, reason: str | None = None) -> dict[str, Any]:
    # F1 (E2 J2 3-layer): stage-aware approval.
    #   pending_review            ← 部门待审（MANAGER 审）
    #   pending_platform_review   ← 平台待审（BUSIAUDIT 复核；F1 新增运行时态，不入 CATALOG_STATUS_TO_LIFECYCLE）
    # D57⑧：反向编目草稿经部门审（reverse_draft.confirm，MANAGER）后直接落
    # pending_platform_review 汇入本管线平台档；BUSIAUDIT 在此复核即两级闭环。
    # return_for_fix 对反向单回 draft = 回部门审收件箱（source=reverse ∧ draft 口径）。
    # 旧单步兼容路径：state=pending_review + role=BUSIAUDIT → 直达 approved_pending_publish。
    # 留作渐进迁移，待全部调用方迁到 3 层后再决策是否移除（见 F1 review skeleton 决策点②）。
    if decision == "approve":
        repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
        existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if existing is None:
            raise NotFoundError(catalog_code)
        state = existing.lifecycle_status
        if state == "pending_review" and role == "ROLE_ORGAN_MANAGER":
            target = "pending_platform_review"
        elif state == "pending_platform_review" and role == "ROLE_BUSIAUDIT":
            target = "approved_pending_publish"
        elif state == "pending_review" and role == "ROLE_BUSIAUDIT":
            # 兼容旧单步路径
            target = "approved_pending_publish"
        else:
            raise InvalidStateError(
                f"catalog_entry {catalog_code} cannot be approved from state={state} by role={role}; "
                "expected pending_review+MANAGER, pending_platform_review+BUSIAUDIT, or pending_review+BUSIAUDIT (legacy single-step)"
            )
        # 通过：清掉历史驳回理由（陈旧整改依据不再展示）——传 review_note="" 触发清除。
        return _transition_catalog_entry(brain, deps, ctx, catalog_code, target, "catalog.entry.review", role, confirmed, review_note="")
    # D57⑨/R10：退回/驳回须带理由（fail-closed）——REST/CLI 直调不带理由同样拦（前端 toast
    # 只是第一道），让供数方拿到整改依据。落 summary_json.review_return_reason。
    if decision in {"return_for_fix", "reject"}:
        if not (reason or "").strip():
            raise InvalidStateError("目录审核退回/驳回须填写理由（退回提交方整改的依据）")
        target = "draft" if decision == "return_for_fix" else "rejected"
        return _transition_catalog_entry(brain, deps, ctx, catalog_code, target, "catalog.entry.review", role, confirmed, review_note=reason)
    raise BrainServiceError(f"unsupported catalog entry review decision: {decision}")

def _submit_catalog_entry_review(brain, deps, ctx, catalog_code: str, role: str, confirmed: bool) -> dict[str, Any]:
    # 在线编制目录提交审核前的必填校验（0611 口径确认单 §A）。目录不存在时不在此抛错，
    # 交给 _transition_catalog_entry 统一抛 NotFoundError（错误语义单一）。
    repo = deps.repos.catalog
    existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
    if existing is not None:
        missing = _missing_inline_required_basic_fields(existing)
        if missing:
            raise InvalidStateError(f"基本信息未填全，暂不能提交审核。请补全必填项：{'、'.join(missing)}。")
    return _transition_catalog_entry(brain, deps, ctx, catalog_code, "pending_review", "catalog.entry.submit_review", role, confirmed)

def _update_catalog_entry(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    catalog_code = str(payload["catalog_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
        existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if existing is None:
            raise NotFoundError(catalog_code)
        repo.upsert_from_resource(
            {
                **copy.deepcopy(existing.summary_json),
                **safe_json(payload.get("summary_json") or {}),
                "id": catalog_code,
                "name": str(payload.get("title", existing.title)),
                "status": existing.lifecycle_status,
                "provider": payload.get("owner_org_id", existing.owner_org_id or ""),
                "region_code": payload.get("region_code", existing.region_code),
                "source_ref": payload.get("source_ref") or existing.summary_json.get("source_ref"),
                "legacy_object_ref": payload.get("legacy_object_ref") or catalog_code,
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        for item in payload.get("items") or []:
            repo.upsert_item({**item, "catalog_code": catalog_code}, tenant_id=_DEFAULT_TENANT_ID)
        deps.append_audit_feed("catalog.entry.update", catalog_code, "ok", actor)
        return with_lifecycle_label({"catalog_code": catalog_code, "lifecycle_status": existing.lifecycle_status, "audit_id": audit_id})

    return deps.write(ctx, payload, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_catalog_entry_create(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _create_catalog_entry_draft(brain, deps, ctx, payload)

def handler_catalog_entry_create_draft(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _create_catalog_entry_draft(brain, deps, ctx, payload)

def handler_catalog_entry_publish(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    # F3 (E2 J2)：发布前自动跑 catalog.duplicate.check skill；非硬拦——warnings 透传到
    # publish envelope.result.duplicate_warnings 字段供 UI 展示，**不阻断** publish。
    # 走 brain.invoke_skill 而非 helper：让 duplicate.check capability_call 独立落账
    # （F3 evidence_plan: 提醒事件 audit）。catalog 不存在时跳过预检，让下面的 _transition
    # 抛 NotFoundError 保持错误语义单一。
    code = str(payload["catalog_code"])
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    duplicate_warnings: list[dict[str, Any]] = []
    try:
        dup_envelope = brain.invoke_skill(
            "catalog.duplicate.check",
            {"catalog_code": code, "role": role},
        )
        if isinstance(dup_envelope, dict):
            duplicate_warnings = dup_envelope.get("duplicate_warnings") or []
    except NotFoundError:
        pass
    envelope = _transition_catalog_entry(brain, deps, ctx, code, "active", "catalog.entry.publish", role, confirmed)
    if isinstance(envelope, dict) and isinstance(envelope.get("result"), dict):
        envelope["result"]["duplicate_warnings"] = duplicate_warnings
    return envelope

def handler_catalog_entry_withdraw(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_catalog_entry(brain, deps, ctx, str(payload["catalog_code"]), "retired", "catalog.entry.withdraw", str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_catalog_entry_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_catalog_entries(
        brain,
        deps,
        ctx,
        query=payload.get("query"),
        catalog_code=payload.get("catalog_code"),
        source=payload.get("source"),
        lifecycle_status=payload.get("lifecycle_status"),
        limit=payload.get("limit"),
        offset=payload.get("offset"),
        order=payload.get("order"),
    )

def handler_catalog_entry_reverse_draft_suggest(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _suggest_catalog_entry_reverse_draft(brain, deps, ctx, payload)

def handler_catalog_entry_reverse_draft_create(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _create_catalog_entry_reverse_draft(brain, deps, ctx, payload)

def handler_catalog_entry_reverse_draft_confirm(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _confirm_catalog_entry_reverse_draft(brain, deps, ctx, payload)

def handler_catalog_entry_reverse_draft_reject(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _reject_catalog_entry_reverse_draft(brain, deps, ctx, payload)

def handler_catalog_entry_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    # reason / review_note 同义键（前端传 reason；与资源侧 review_note 命名各自历史，此处两收）。
    reason = payload.get("reason")
    if reason is None:
        reason = payload.get("review_note")
    return _review_catalog_entry(brain, deps, ctx, str(payload["catalog_code"]), str(payload["decision"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")), reason=reason)

def handler_catalog_entry_submit_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_catalog_entry_review(brain, deps, ctx, str(payload["catalog_code"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_catalog_entry_update(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _update_catalog_entry(brain, deps, ctx, payload)
