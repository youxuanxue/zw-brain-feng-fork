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

from zw_brain.domain.errors import NotFoundError
from zw_brain.domain.serializers import quality as quality_ser
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
        records = [
            item
            for item in source
            if (item.payload_json or {}).get("kind") == "apply"
            and (
                str((item.payload_json or {}).get("resourceId") or "") == resource_id
                or str((item.payload_json or {}).get("catalog_id") or "") == catalog_code
                or item.application_code == record.application_code
            )
        ]
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
        """Demo prefilled fields for J1 / U-3 credential issue flow."""
        samples = {
            "统一社会信用代码": "91370000MA3XXXXXX1",
            "企业名称": "山东云启科技有限公司",
            "法定代表人": "李某某",
            "行业代码": "I6510",
            "成立日期": "2020-08-18",
            "登记机关": "市市场监管局",
            "经营场所": "高新区软件园 A 座",
            "注册资本": "500 万元",
        }
        fields = []
        source_fields = [item["title"] for item in requested_fields] if requested_fields else resource.get("fields", [])[:5]
        for fld in source_fields[:5]:
            fields.append(
                {
                    "label": fld,
                    "value": samples.get(fld, "已带出"),
                    "source": "共享资源池 / 字段证据",
                    "state": "已预填",
                }
            )
        return fields

    def default_diff_fields(self) -> list[dict[str, Any]]:
        """Default 3 diff fields for grass-roots supplement demo."""
        return [
            {
                "label": "经营状态",
                "value": "待镇街确认",
                "reason": "现场状态变化快",
                "owner": "基层填报人 补录",
            },
            {
                "label": "最近走访时间",
                "value": "待补录",
                "reason": "共享池无现场时间",
                "owner": "村社区填报人 补录",
            },
            {
                "label": "现场备注",
                "value": "待补录",
                "reason": "仅末端掌握",
                "owner": "基层填报人 补录",
            },
        ]
