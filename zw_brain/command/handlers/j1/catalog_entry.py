"""J1 catalog_entry handlers — 12 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy
import hashlib

from zw_brain.command.brain import BrainServiceError, InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import catalog as catalog_ser
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.resource_lifecycle import with_lifecycle_label
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sanitization import safe_json

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
            "provider": payload.get("owner_org_id", ""),
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

def _transition_catalog_entry(brain, deps, ctx, catalog_code: str, status: str, skill_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = deps.repos.catalog  # Action C — deps.repos always wired (DB or in-memory fallback)
        existing = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        if existing is None:
            raise NotFoundError(catalog_code)
        repo.upsert_from_resource(
            {
                **copy.deepcopy(existing.summary_json),
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
        snap = session.execute(
            select(ResourceSchemaSnapshotRecord)
            .where(ResourceSchemaSnapshotRecord.tenant_id == tenant_id)
            .where(ResourceSchemaSnapshotRecord.snapshot_ref == schema_ref)
        ).scalar_one_or_none()
    if snap is None:
        return {
            "schema_ref": schema_ref,
            "title_suggestion": build_title_suggestion(None),
            "fields": [],
            "coverage": {"green": 0, "yellow": 0, "orange": 0, "total": 0},
            "found": False,
        }
    schema_json = snap.schema_json if isinstance(snap.schema_json, dict) else {}
    suggestions, coverage = build_field_suggestions(schema_json)
    title_suggestion = build_title_suggestion(
        schema_json | {"schema_ref": schema_ref, "resource_code": snap.resource_code}
    )
    return {
        "schema_ref": schema_ref,
        "resource_code": snap.resource_code,
        "binding_code": snap.binding_code,
        "title_suggestion": title_suggestion,
        "fields": suggestions,
        "coverage": coverage,
        "found": True,
    }

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
        summary["status"] = "pending_review"
        summary["field_decisions"] = payload.get("field_decisions") or []
        summary["confirmation_comment"] = payload.get("comment")
        summary["confirmed_by_audit"] = audit_id
        repo.upsert_from_resource(summary, tenant_id=_DEFAULT_TENANT_ID)
        deps.append_audit_feed("catalog.entry.reverse_draft.confirm", catalog_code, "ok", actor)
        return with_lifecycle_label({"catalog_code": catalog_code, "lifecycle_status": "pending_review", "audit_id": audit_id})

    return deps.write(ctx, payload, mutation)

def _reject_catalog_entry_reverse_draft(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
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

def _review_catalog_entry(brain, deps, ctx, catalog_code: str, decision: str, role: str, confirmed: bool) -> dict[str, Any]:
    # F1 (E2 J2 3-layer): stage-aware approval.
    #   pending_review            ← 部门待审（MANAGER 审）
    #   pending_platform_review   ← 平台待审（BUSIAUDIT 复核；F1 新增运行时态，不入 CATALOG_STATUS_TO_LIFECYCLE）
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
        return _transition_catalog_entry(brain, deps, ctx, catalog_code, target, "catalog.entry.review", role, confirmed)
    if decision == "return_for_fix":
        return _transition_catalog_entry(brain, deps, ctx, catalog_code, "draft", "catalog.entry.review", role, confirmed)
    if decision == "reject":
        return _transition_catalog_entry(brain, deps, ctx, catalog_code, "rejected", "catalog.entry.review", role, confirmed)
    raise BrainServiceError(f"unsupported catalog entry review decision: {decision}")

def _submit_catalog_entry_review(brain, deps, ctx, catalog_code: str, role: str, confirmed: bool) -> dict[str, Any]:
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
    return _review_catalog_entry(brain, deps, ctx, str(payload["catalog_code"]), str(payload["decision"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_catalog_entry_submit_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _submit_catalog_entry_review(brain, deps, ctx, str(payload["catalog_code"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_catalog_entry_update(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _update_catalog_entry(brain, deps, ctx, payload)

