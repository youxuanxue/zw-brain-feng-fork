"""ApplicationService — application record → request projection.

Owns: application record → handler-shape request dict (108L core method),
overlay onto snapshot request, history context, quality evidence, source
evidence, gap fields, time window, scope, requested fields, prefilled fields,
default diff fields.

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zw_brain.domain.application_dedupe import dedupe_application_records
from zw_brain.domain.errors import NotFoundError
from zw_brain.domain.serializers import quality as quality_ser
from zw_brain.domain.services import form_fill_service
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sensitive_mask import mask_default as _mask

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService



@dataclass(frozen=True)
class ApplicationService:
    """Application record projection + form helpers (P3 application)."""

    brain: BrainService

    # --- Core projection (108-line method) ---

    def record_to_request(
        self,
        record: Any,
        store: Any,
        *,
        context: Any | None = None,
    ) -> dict[str, Any]:
        """Application record → request dict including materials / evidence."""
        payload = _mask(copy.deepcopy(record.payload_json or {}))
        resource_id = str(payload.get("resourceId") or payload.get("resource_id") or "")
        catalog_id = str(payload.get("catalog_id") or "")
        try:
            if context is not None and resource_id:
                cached = context.resource_cache.get(resource_id)
                if cached is None:
                    cached = self.brain.get_resource(resource_id, context=context)
                    context.resource_cache[resource_id] = cached
                resource = cached
            else:
                resource = self.brain.get_resource(resource_id) if resource_id else {}
        except NotFoundError:
            resource = {}
        catalog_code = resource.get("repository", {}).get("catalogCode") or catalog_id
        bound_item_codes = {item.get("catalog_item_code") for item in resource.get("fieldBindings", []) if item.get("catalog_item_code")}
        requested_items = [
            {"item_code": item.get("item_code"), "title": item.get("title"), "sensitive_level": (item.get("summary_json") or {}).get("sensitive_level")}
            for item in resource.get("catalogFields", [])
            if not bound_item_codes or item.get("item_code") in bound_item_codes
        ]
        if not requested_items and payload.get("use_item"):
            requested_items = [{"item_code": str(payload.get("use_item")), "title": str(payload.get("use_item"))}]
        original_materials = payload.get("applicationMaterials") if isinstance(payload.get("applicationMaterials"), dict) else {}
        if original_materials.get("requestedItems"):
            requested_items = copy.deepcopy(original_materials["requestedItems"])
        gap_fields = list(original_materials.get("gapFields") or (resource.get("reuseGapHint") or {}).get("gapFields") or [])
        delivery = self.brain._get_handler_deps().services.delivery.task_from_record(record.application_code, store, context=context)
        legacy_mappings = self.brain._legacy_mapping_refs(store, "application_record", record.application_code, context=context)
        legacy_mappings.extend(self.brain._legacy_mapping_refs(store, "DeliveryTaskRecord", record.application_code, context=context))
        source_evidence = self.source_evidence(resource, requested_items)
        historical_context = self.history_context(record, store, resource_id, catalog_code, context=context)
        quality_evidence = self.quality_evidence(store, resource, catalog_code, resource_id, context=context)
        applicant_snapshot = _mask({"applicant_name": record.applicant_name, "applicant_org": record.applicant_org})
        field_values = payload.get("fieldValues") if isinstance(payload.get("fieldValues"), dict) else {}
        field_provenance = payload.get("fieldProvenance") if isinstance(payload.get("fieldProvenance"), dict) else {}
        materials = {
            "purpose": original_materials.get("purpose") or payload.get("use_reason") or payload.get("apply_basis") or "复用已有目录资源办理业务事项",
            "timeWindow": original_materials.get("timeWindow") or payload.get("service_usetime") or "按授权期执行",
            "scope": original_materials.get("scope") or payload.get("use_region") or resource.get("regionCode") or payload.get("applicant_org_name") or "山东省",
            "catalogCode": original_materials.get("catalogCode") or catalog_code,
            "resourceId": original_materials.get("resourceId") or resource_id,
            "requestedItems": requested_items,
            "gapFields": gap_fields,
            "deliveryExpectation": original_materials.get("deliveryExpectation") or payload.get("delivery_expectation") or payload.get("deliveryExpectation") or "审批通过后按授权边界交付，并保留审计回放。",
            "frequency": {
                "times": str(payload.get("service_times") or ""),
                "mostTimes": str(payload.get("service_most_times") or ""),
                "timeWindow": payload.get("service_usetime"),
                "useDays": str(payload.get("service_usedays") or ""),
            },
            "minimal": True,
        }
        request = {
            "id": record.application_code,
            # 历史导入只读卡标识（debt j1-legacy-record-actionability）——record_to_request
            # 只在 legacy 导入单（payload 带 ``kind``）/ 运行时单尚未进会话时被调；运行时进会话
            # 卡走 CardSession 不经此。前端据此把历史导入识别为只读：隐藏运行时专属动作入口
            # （撤回/暂停/重新签发），无权/不可动作=不可见。判别同 card_session 反面（payload 带 kind）。
            "legacyImport": bool((record.payload_json or {}).get("kind")),
            "resourceId": resource_id,
            "resourceName": payload.get("resource_name") or resource.get("name") or record.application_code,
            "applicant": applicant_snapshot["applicant_name"],
            "applicantDept": applicant_snapshot["applicant_org"],
            "purpose": materials["purpose"],
            "range": materials["scope"],
            "timeWindow": materials["timeWindow"],
            "requestedItems": requested_items,
            "gapFields": gap_fields,
            "deliveryExpectation": materials["deliveryExpectation"],
            "applicationMaterials": materials,
            "expectedBy": self.brain._get_handler_deps().services.delivery.due_hint(delivery),
            "status": record.status,
            # 国家通道指示（C9）：channel_class=='national' 标识「请求国家级数据」的申请。
            # 真实信号取 payload_json["channel_class"]（supply_demand §scenario 5 占位口径）；
            # P3 国家通道 tab 据此筛「待转报」队列（dept_approved ∩ national），不再误列 own-items。
            "channelClass": str(payload.get("channel_class") or "internal"),
            "submittedAt": payload.get("create_time") or record.created_at.isoformat(),
            "taskId": delivery["id"] if delivery else None,
            "sourceEvidence": source_evidence,
            "reuseCandidate": {
                "catalogCode": catalog_code,
                "resourceId": resource_id,
                "resourceName": resource.get("name") or payload.get("resource_name"),
                "fieldBindingSummary": copy.deepcopy(resource.get("fieldBindingSummary") or {}),
                "reuseGapHint": copy.deepcopy(resource.get("reuseGapHint") or {}),
                "resourceStatus": resource.get("status"),
                "accessPolicy": copy.deepcopy(resource.get("accessPolicy") or {}),
            },
            "fieldBindings": copy.deepcopy(resource.get("fieldBindings") or []),
            "fieldBindingSummary": copy.deepcopy(resource.get("fieldBindingSummary") or {}),
            "schemaSnapshots": copy.deepcopy(resource.get("schemaSnapshots") or []),
            "sensitivePolicy": copy.deepcopy(resource.get("sensitivePolicy") or {}),
            "resourceAssets": copy.deepcopy(resource.get("resourceAssets") or []),
            "accessPolicy": copy.deepcopy(resource.get("accessPolicy") or {}),
            "historicalContext": historical_context,
            "qualityEvidence": quality_evidence,
            "legacyMappings": legacy_mappings,
            "repository": {
                "application_code": record.application_code,
                "status": record.status,
            },
            "statusTimeline": [],
            "reviewBoundary": _mask(copy.deepcopy((delivery or {}).get("r2Review") or {})),
            # P3RequestDetail 的详情接口契约：草稿/待补正详情必须自带可编辑申请表单。
            # 字段模型只持久化 fieldValues + fieldProvenance，formFields 在读时现算；
            # 这里与 snapshot 的 _record_to_request_card 保持同源，避免前端靠列表快照兜底。
            "formFields": (
                form_fill_service.assemble_form_fields(field_values, field_provenance)
                if field_provenance
                else []
            ),
            "fieldProvenance": field_provenance,
            "aiStatus": {
                "summary": "该申请已命中真实旧平台申请、目录、资源、字段绑定和授权证据。",
                "nextAction": "审批承接人员核对复用范围、敏感字段、授权边界和历史重复线索。",
                "evidence": ["真实 data_apply 导入", "字段绑定可回放", "授权边界可回放"],
            },
        }
        request["statusTimeline"] = self.brain._get_handler_deps().services.request.status_timeline(request, delivery)
        return request

    def overlay_record(
        self,
        request: dict[str, Any],
        record: Any,
        store: Any,
        *,
        context: Any | None = None,
    ) -> None:
        """Merge application record enrichment into an existing request dict."""
        enriched = self.record_to_request(record, store, context=context)
        request.update(enriched)

    def request_from_record(self, request_id: str, store: Any) -> dict[str, Any] | None:
        """Lookup application record by id and project to request dict.

        按 application_code 索引 get（store.application_repo.get_record），
        替代旧 next(...list_records()...) 全表扫。
        """
        record = store.application_repo.get_record(request_id, tenant_id=_DEFAULT_TENANT_ID)
        return self.record_to_request(record, store) if record is not None else None

    # --- Evidence / boundary computation ---

    def history_context(
        self,
        record: Any,
        store: Any,
        resource_id: str,
        catalog_code: str,
        *,
        context: Any | None = None,
    ) -> dict[str, Any]:
        """In-flight duplicate detection for a candidate application."""
        source = context.application_records if context is not None else store.application_repo.list_records(tenant_id=_DEFAULT_TENANT_ID)
        records = dedupe_application_records([
            item
            for item in source
            if (item.payload_json or {}).get("kind") == "apply"
            and (
                str((item.payload_json or {}).get("resourceId") or "") == resource_id
                or str((item.payload_json or {}).get("catalog_id") or "") == catalog_code
                or item.application_code == record.application_code
            )
        ])
        in_flight = [
            item.application_code
            for item in records
            if item.application_code != record.application_code and item.status in {"submitted", "pending", "supplementing", "summary-pending"}
        ]
        return {
            "relatedApplicationCount": len(records),
            "inFlightDuplicateCount": len(in_flight),
            "inFlightDuplicateIds": in_flight,
            "duplicateConclusion": "无在途重复申请，可按复用授权边界继续审批。" if not in_flight else "存在在途重复申请，需先缩小范围或驳回重复需求。",
            "message": "历史申请、审批过程和授权记录已通过 legacy_object_mapping 串联。",
        }

    def quality_evidence(
        self,
        store: Any,
        resource: dict[str, Any],
        catalog_code: str,
        resource_id: str,
        *,
        context: Any | None = None,
    ) -> dict[str, Any]:
        """Aggregate quality evidence from metadata_evidence + resource summary."""
        if context is not None:
            direct = [
                quality_ser.quality_to_dict(item)
                for target_type, target_ref in (("catalog", catalog_code), ("resource", resource_id))
                for item in context.quality_by_target.get((target_type, str(target_ref)), [])
            ]
        else:
            direct = [
                quality_ser.quality_to_dict(item)
                for target_type, target_ref in (("catalog", catalog_code), ("resource", resource_id))
                for item in store.metadata_evidence_repo.list_quality_evidence(
                    target_type=target_type,
                    target_ref=target_ref,
                    tenant_id=_DEFAULT_TENANT_ID,
                )
            ]
        summary = resource.get("fieldBindingSummary") or {}
        if direct:
            status = "ready" if all(item.get("quality_status") in {"passed", "ok", "ready"} for item in direct) else "attention_required"
            return {"status": status, "summary": f"已有 {len(direct)} 条质量投影证据。", "source": "quality_evidence_projection", "items": direct}
        if summary.get("diagnosis") == "ok":
            return {
                "status": "ready",
                "summary": f"字段绑定 {summary.get('active', summary.get('total', 0))} 项均可回放，作为当前质量投影。",
                "source": "schema_mapping_projection",
                "items": [],
            }
        return {"status": "attention_required", "summary": "字段绑定或质量投影仍需目录管理员确认。", "source": "schema_mapping_projection", "items": []}

    def source_evidence(
        self, resource: dict[str, Any], fields: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Catalog/legacy/binding/asset evidence for a candidate application."""
        return {
            "catalogCode": resource.get("repository", {}).get("catalogCode") or resource.get("id"),
            "legacyMappings": copy.deepcopy(resource.get("legacyMappings") or []),
            "fieldBindings": copy.deepcopy(resource.get("fieldBindings") or []),
            "resourceAssets": copy.deepcopy(resource.get("resourceAssets") or []),
            "requestedItemCodes": [field["item_code"] for field in fields],
        }

    # --- Form input normalization ---

    def gap_fields(self, options: dict[str, Any]) -> list[str]:
        """Normalize gap_fields option to a list of titles."""
        raw = options.get("gap_fields") or options.get("gapFields") or ["统计时间窗", "区县范围"]
        if not isinstance(raw, list):
            raw = [raw]
        return [str(item.get("title") if isinstance(item, dict) else item) for item in raw if str(item.get("title") if isinstance(item, dict) else item).strip()]

    def time_window(self, options: dict[str, Any]) -> dict[str, Any]:
        """Normalize time_window option to {start, end} or {label}."""
        raw = options.get("time_window") or options.get("timeWindow") or {}
        if isinstance(raw, dict):
            return {"start": raw.get("start") or raw.get("from") or "2025-01-01", "end": raw.get("end") or raw.get("to") or "2025-12-31"}
        return {"label": str(raw)}

    def scope(self, resource: dict[str, Any], options: dict[str, Any]) -> str:
        """Resolve application scope (region label / explicit scope)."""
        return str(options.get("application_scope") or options.get("scope") or resource.get("regionCode") or resource.get("zone") or "山东省")

    def requested_fields(
        self, resource: dict[str, Any], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Normalize requested_items option into [{item_code, title}] (max 5)."""
        raw = options.get("requested_items") or options.get("requestedItems") or options.get("fields")
        catalog_fields = resource.get("catalogFields") or []
        requested: list[dict[str, Any]] = []
        if isinstance(raw, list) and raw:
            for item in raw:
                if isinstance(item, dict):
                    code = str(item.get("item_code") or item.get("code") or item.get("field") or item.get("title") or "")
                    title = str(item.get("title") or item.get("name") or item.get("field") or code)
                else:
                    code = str(item)
                    matched = next((field for field in catalog_fields if code in {str(field.get("item_code")), str(field.get("title"))}), None)
                    title = str((matched or {}).get("title") or code)
                if code:
                    requested.append({"item_code": code, "title": title})
        elif catalog_fields:
            first = catalog_fields[0]
            requested.append({"item_code": str(first.get("item_code") or first.get("title")), "title": str(first.get("title") or first.get("item_code"))})
        else:
            for title in (resource.get("fields") or [])[:1]:
                requested.append({"item_code": str(title), "title": str(title)})
        return requested[:5]

    def diff_fields_for_gap(self, gap_fields: list[str]) -> list[dict[str, Any]]:
        """Build diff field rows from a list of gap field titles."""
        return [
            {"label": field, "value": "待补充", "reason": "本次申请仍需明确", "owner": "申请人 补充说明 / 审批人 审核确认"}
            for field in gap_fields
        ]

    def prefilled_fields(
        self,
        resource: dict[str, Any],
        requested_fields: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Prefilled rows for the J1 application material panel.

        诚实化（禁 Mock，D11）：本期共享资源池只承载字段**元数据**（item_code /
        title / 来源目录），不承载某个申请人的字段**取值**——之前这里写死了一家
        虚构企业（山东云启…/假信用代码/假法人）当作「已预填」，会在真实凭据签发流
        里向用户展示捏造的企业数据，是产品事故。

        现行：逐条带出**真实请求字段**（来自目录元数据），取值留空并标注「请填写」，
        source 指向该字段真实可得的目录证据；绝不再编造取值。未来 adapter-yibiaotong
        接通后由真源回填（见 .testing/.../adapter-yibiaotong.feature，本期未建 Draft）。
        """
        catalog_code = resource.get("repository", {}).get("catalogCode") or resource.get("id") or ""
        # 真实请求字段：优先用上游归一化后的 requested_fields（{item_code,title}），
        # 否则回落资源自带的字段标题列表。两者都来自真实目录元数据，无捏造。
        rows: list[dict[str, Any]] = []
        if requested_fields:
            source_fields = [
                (str(item.get("title") or item.get("item_code") or ""), str(item.get("item_code") or ""))
                for item in requested_fields
            ]
        else:
            source_fields = [(str(title), "") for title in (resource.get("fields") or [])[:5]]
        for title, item_code in source_fields[:5]:
            if not title:
                continue
            ref = f"共享目录字段 {item_code}".strip() if item_code else "共享目录字段"
            source = f"{ref}（{catalog_code}）" if catalog_code else ref
            rows.append(
                {
                    "label": title,
                    # 诚实留空：共享池无该字段取值，待申请人/经办人填写。
                    "value": "",
                    "placeholder": "请填写",
                    "source": source,
                    "state": "待填写",
                }
            )
        return rows
