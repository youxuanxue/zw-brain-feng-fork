"""RequestService — request approval flow + status helpers.

Owns: request batch context (D-9 prefetch), status timeline, status text,
by-id / maybe lookups, approval flow methods (approve / return / reject /
route), review_application_record, new_request_id.

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zw_brain.domain.errors import InvalidStateError, NotFoundError, _RequestBatchContext
from zw_brain.shared import ids
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


def derive_demo_credential(request_id: str, seed: str | None = None) -> dict[str, Any]:
    """Deterministic demo credential — 同一 (request_id, seed) 永远生成同一凭据。

    Single source for the demo-credential shape, shared by
    ``RequestService.credential_for_request`` (auto-issue on approval / reissue)
    and the legacy exchange mapper (granted-delivery materialization). Keeps the
    invariant *granted ⟹ credential* satisfied by construction; legacy real
    ``app_key`` is scrubbed at the boundary (PII), so a granted access gets the
    same demo credential the approval flow would have issued.

    seed=None：首次签发（auto-on-approval），用 request_id 作种子；
    seed=<audit_id>：reissue 路径每次重签都产生不同 app_secret
    （旧 secret 立即失效语义；与生产 IAM reissue 行为对齐）.
    """
    import hashlib  # noqa: PLC0415
    from datetime import datetime, timedelta  # noqa: PLC0415

    import zw_brain.shared.clock as clock  # noqa: PLC0415

    seed_material = (
        f"d23-credential-{request_id}"
        if seed is None
        else f"d23-credential-{request_id}-reissue-{seed}"
    )
    digest = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
    app_key = f"AK-DEMO-{request_id}-{digest[:8].upper()}"
    app_secret = f"SK-DEMO-{digest[8:32]}"
    valid_from = clock.now_date()
    valid_to = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
    return {
        "app_key": app_key,
        "app_secret": app_secret,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "quota_per_day": 1000,
        "invoke_url_template": f"https://api.gov-data.local/v1/services/<resource_code>?app_key={app_key}",
    }


@dataclass(frozen=True)
class RequestService:
    """Request approval flow + status (P3 application + B1 review)."""

    brain: BrainService

    # --- Batch prefetch (D-9 N+1 elimination) ---

    def build_batch_context(self, store: Any, application_records: list[Any]) -> Any:
        """Build _RequestBatchContext with prefetched indices for list_requests.

        Cost: 1 delivery_repo.list_tasks + 2 legacy_mapping_repo.list_mappings
        (one per canonical_type) + 1 metadata_evidence_repo.list_quality_evidence
        + 0 application_repo.list_records (reuses caller's already-fetched list).
        Replaces ~5N per-item scans with O(1) lookups.
        """
        delivery_by_appcode: dict[str, Any] = {}
        for delivery in store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID):
            delivery_by_appcode[delivery.application_code] = delivery
            delivery_by_appcode[delivery.delivery_code] = delivery

        legacy_mappings_by_ref: dict[tuple[str, str], list[Any]] = {}
        # 8 canonical_types are touched by enrichment + request projection.
        for canonical_type in (
            "application_record",
            "DeliveryTaskRecord",
            "catalog_entry",
            "catalog_item",
            "resource_schema_mapping",
            "resource_asset",
            "approval_step",
            "approval_decision",
        ):
            for mapping in store.legacy_mapping_repo.list_mappings(
                tenant_id=_DEFAULT_TENANT_ID,
                canonical_type=canonical_type,
            ):
                key = (canonical_type, str(mapping.canonical_ref))
                legacy_mappings_by_ref.setdefault(key, []).append(mapping)

        quality_by_target: dict[tuple[str, str], list[Any]] = {}
        for item in store.metadata_evidence_repo.list_quality_evidence(tenant_id=_DEFAULT_TENANT_ID):
            key = (str(item.target_type), str(item.target_ref))
            quality_by_target.setdefault(key, []).append(item)

        resource_assets_by_catalog: dict[str, list[Any]] = {}
        for asset in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID):
            resource_assets_by_catalog.setdefault(asset.catalog_code, []).append(asset)

        schema_mappings_by_catalog: dict[str, list[Any]] = {}
        for mapping in store.metadata_evidence_repo.list_schema_mappings(tenant_id=_DEFAULT_TENANT_ID):
            schema_mappings_by_catalog.setdefault(mapping.catalog_code, []).append(mapping)

        schema_snapshots_by_resource: dict[str, list[Any]] = {}
        for snapshot in store.metadata_evidence_repo.list_schema_snapshots(tenant_id=_DEFAULT_TENANT_ID):
            schema_snapshots_by_resource.setdefault(snapshot.resource_code, []).append(snapshot)

        catalog_items_by_catalog: dict[str, list[Any]] = {}
        catalog_items_by_item_code: dict[str, Any] = {}
        for item in store.catalog_repo.list_items(tenant_id=_DEFAULT_TENANT_ID):
            catalog_items_by_catalog.setdefault(item.catalog_code, []).append(item)
            catalog_items_by_item_code[item.item_code] = item

        return _RequestBatchContext(
            delivery_by_appcode=delivery_by_appcode,
            application_records=list(application_records),
            legacy_mappings_by_ref=legacy_mappings_by_ref,
            quality_by_target=quality_by_target,
            resource_cache={},
            resource_assets_by_catalog=resource_assets_by_catalog,
            schema_mappings_by_catalog=schema_mappings_by_catalog,
            schema_snapshots_by_resource=schema_snapshots_by_resource,
            catalog_items_by_catalog=catalog_items_by_catalog,
            catalog_items_by_item_code=catalog_items_by_item_code,
        )

    # --- Approval recommendation / business defaults ---

    def approval_recommendation(
        self,
        approval: dict[str, Any],
        request: dict[str, Any],
        delivery: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build the recommended decision summary for an approval card.

        Action H commit 3: lifted from ``BrainService._approval_recommendation``;
        callers route through ``deps.services.request.approval_recommendation(...)``.
        """
        gap_fields = request.get("gapFields") or []
        grant = (delivery or {}).get("accessGrantSnapshot") or {}
        return {
            "primary": "approve_reuse" if not gap_fields else "approve_reuse_with_gap_attention",
            "reason": [
                "已有目录、资源、字段和 schema 绑定证据",
                "历史申请与授权可通过 legacy_object_mapping 回指",
                "申请字段保持最小必要范围",
            ],
            "alternatives": ["return_for_fix", "reject_duplicate", "route_to_provider_or_catalog_admin"],
            "grantBoundary": {"limit_day": grant.get("limit_day"), "res_type": grant.get("res_type"), "apply_status": grant.get("apply_status")},
            "renewalBoundary": "真实 data_apply_renewal 无行；不伪造续期成功路径。",
        }

    def credential_for_request(
        self, request_id: str, seed: str | None = None
    ) -> dict[str, Any]:
        """Demo credential — 同一 (request_id, seed) 永远生成同一凭据。

        Action H commit 4: lifted from ``BrainService._credential_for_request``.
        Pure derivation; no instance state used (kept on the service for
        cohesion with the rest of the request approval flow).

        seed=None：首次签发（auto-on-approval），用 request_id 作种子；
        seed=<audit_id>：reissue 路径每次重签都产生不同 app_secret
        （旧 secret 立即失效语义；与生产 IAM reissue 行为对齐）.

        Delegates to the module-level :func:`derive_demo_credential` so the
        credential shape has a single source shared with the legacy mapper.
        """
        return derive_demo_credential(request_id, seed)

    def approval_business_defaults(
        self,
        request: dict[str, Any],
        delivery: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build the business-default narrative / risk / draft note for an approval card.

        Action H commit 3: lifted from ``BrainService._approval_business_defaults``;
        callers route through ``deps.services.request.approval_business_defaults(...)``.
        """
        recommendation = self.approval_recommendation({}, request, delivery)
        resource_name = request.get("resourceName") or request.get("id")
        return {
            "suggestion": "建议通过复用" if recommendation["primary"] == "approve_reuse" else "建议通过并关注缺口",
            "confidence": 0.9,
            "reason": recommendation["reason"],
            "risk": [
                "若申请方扩大字段范围，应退回缩小到最小必要字段。",
                "若对资源口径有争议，应转 数据提供方 / 业务运营员 做口径确认。",
            ],
            "counterfactual": "如果发现同一资源存在在途重复申请，应驳回重复需求或合并到既有申请。",
            "impact": "通过后只按授权边界交付；退回或驳回也会保留理由、证据和责任节点。",
            "actions": ["通过复用", "退回缩小范围", "驳回重复需求", "转口径确认"],
            "draftNote": f"建议审批意见：{resource_name} 已具备目录、字段、资源和授权证据，按最小必要范围复用；续期无真实来源行，不在本次审批中伪造续期结论。",
            "exceptionItems": ["续期来源行缺失，仅回放既有授权边界。"],
            "autoSummary": "审批证据链已汇总到申请材料、字段绑定、历史线索、授权边界和旧平台回指。",
        }

    # --- Status timeline / text ---

    def status_timeline(
        self, request: dict[str, Any], delivery: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        """Compute status timeline rows for a request + its delivery."""
        decision = "已通过" if request.get("status") in {"supplementing", "summary-pending", "completed"} else "待审批结论"
        delivery_state = delivery.get("status") if delivery else "pending"
        return [
            {"stage": "待受理", "status": "done", "ref": request.get("id"), "label": "申请已提交"},
            {"stage": "审核中", "status": "done" if request.get("status") != "pending" else "current", "ref": request.get("id"), "label": self.status_text(request, "reviewer")},
            {"stage": "审批结论", "status": "done" if decision == "已通过" else "pending", "ref": request.get("id"), "label": decision},
            {"stage": "delivery_task", "status": delivery_state, "ref": delivery.get("id") if delivery else None, "label": delivery_state},
        ]

    def status_text(self, item: dict[str, Any], perspective: str = "reviewer") -> str:
        """Localized status text per perspective (applicant / reviewer / filler / summarizer).

        R-002 fix: 文案不再按 role 单维区分（折叠后同一 ROLE_* 无法承载"申请人 vs 填报人"双语义）。
        改为按业务视角（perspective）显示文案；调用方在每个待办语境下显式声明视角。
        """
        status = item["status"]
        if status == "pending":
            return {"applicant": "审批中", "reviewer": "待审批", "filler": "等待审批", "summarizer": "等待审批"}.get(perspective, "待审批")
        if status == "supplementing":
            return {"applicant": "补录中", "reviewer": "补录中", "filler": "待补录", "summarizer": "补录中"}.get(perspective, "补录中")
        if status == "summary-pending":
            return {"summarizer": "待汇总确认"}.get(perspective, "待汇总确认")
        if status == "completed":
            return "已汇总"
        if status == "need-fix":
            return "待补正"
        if status == "rejected":
            return "已驳回"
        if status == "approved":
            return {
                "applicant": "已通过",
                "reviewer": "已通过",
                "filler": "待补录",
                "summarizer": "待汇总确认",
            }.get(perspective, "已通过")
        if status == "in_delivery":
            return {
                "applicant": "交付中",
                "reviewer": "交付中",
                "filler": "交付中",
                "summarizer": "交付中",
            }.get(perspective, "交付中")
        if status == "granted":
            return "已授权"
        if status == "revoked":
            return "已撤销"
        _fallback = {
            "draft": "草稿",
            "open": "待处理",
            "reconciling": "待对账",
            "warning": "需关注",
            "failed": "失败",
            "online": "在线",
            "escalated": "已升级",
            "resolved": "已解决",
            "provider_investigating": "提供方核查中",
        }
        if status in _fallback:
            return _fallback[status]
        if isinstance(status, str) and status.isascii() and status.replace("-", "").replace("_", "").isalnum() and status == status.lower():
            return "待处理"
        return str(status)

    # --- Snapshot lookups ---

    def by_id(self, request_id: str) -> dict[str, Any]:
        """Request by id; raises NotFoundError when absent.

        先查内存快照（demo/seed 即时态），未命中再回 DB
        （application_repo.get_record → record_to_request）。修真 bug：M0 dump 导入的
        申请不在内存快照基底里，旧实现只读 brain._snapshot 漏查 → credential.issue 路径
        NotFoundError → P3 凭据签发 422。与 delivery_service.by_request_id 同范式
        （Fix B），DB 是真相。
        """
        for item in self.brain._snapshot["requests"]:
            if item["id"] == request_id:
                return item
        store = getattr(getattr(self.brain, "_state_store", None), "database_store", None)
        if store is not None:
            record = store.application_repo.get_record(request_id, tenant_id=_DEFAULT_TENANT_ID)
            if record is not None:
                return self.brain._get_handler_deps().services.application.record_to_request(record, store)
        raise NotFoundError(request_id)

    def maybe_by_id(self, request_id: str) -> dict[str, Any] | None:
        """Snapshot request by id; returns None when absent."""

        try:
            return self.by_id(request_id)
        except NotFoundError:
            return None

    def approval_by_id(self, request_id: str) -> dict[str, Any]:
        """Snapshot approval row by request id; raises NotFoundError."""

        for item in self.brain._snapshot["approvals"]:
            if item["id"] == request_id:
                return item
        raise NotFoundError(request_id)

    def maybe_approval_by_id(self, request_id: str) -> dict[str, Any] | None:
        """Snapshot approval row by request id; returns None when absent."""

        try:
            return self.approval_by_id(request_id)
        except NotFoundError:
            return None

    def new_request_id(self) -> str:
        """Mint a new request id following the REQ-NNN sequence."""
        return ids.next_request_id(str(item.get("id", "")) for item in self.brain._snapshot["requests"])

    # --- Approval flow (write path) ---

    def approve(
        self,
        request_id: str,
        role: str,
        confirmed: bool,
        skill_id: str = "approval.review_decide",
        *,
        decision: str = "approve_reuse",
    ) -> dict[str, Any]:
        """Approve a request and advance delivery state."""
        from zw_brain.shared import clock  # noqa: PLC0415

        request = self.by_id(request_id)
        approval = self.approval_by_id(request_id)
        delivery = self.brain._get_handler_deps().services.delivery.by_request_id(request_id)
        if request["status"] != "pending":
            raise InvalidStateError("current request cannot be approved")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request["status"] = "supplementing"
            request["chainAnchor"] = "pending"
            request["timeline"].append(
                {
                    "label": "审批通过并下发补录",
                    "time": clock.now_datetime(),
                    "note": "已进入镇街 / 社区差异补录阶段，基层只需补现场差异字段。",
                }
            )
            request["aiStatus"]["summary"] = "申请已通过准入判定，系统正在按模板预填并等待基层补录差异字段。"
            request["aiStatus"]["nextAction"] = "请 镇街填报人 / 村社区填报人 核对预填字段后提交差异补录。"
            approval["suggestion"] = "建议通过"
            approval["impact"] = "已创建基层预填任务，待补录完成后进入自动汇总确认。"
            if delivery:
                delivery["status"] = "supplementing"
                delivery["updatedAt"] = clock.now_datetime()
                delivery["note"] = "预填任务已下发，等待 镇街填报人 / 村社区填报人 完成差异补录。"
                delivery["history"].append(
                    {
                        "time": clock.now_short_time(),
                        "state": "预填任务已下发",
                        "detail": "系统已把共享模板字段下发到基层，只保留差异字段待补录。",
                    }
                )
                delivery["aiSummary"]["summary"] = "任务已进入“预填下发 → 差异补录”阶段，当前不需要人工拼表。"
                delivery["aiSummary"]["nextAction"] = "请基层完成经营状态、最近走访时间和现场备注补录。"
                delivery["aiSummary"]["cause"] = "审批已通过，模板字段可直接作为补录底座。"
                delivery["aiSummary"]["impact"] = "补录完成后会自动生成汇总结果并沉淀回流候选。"
                delivery["backflow"]["status"] = "待补录完成"
                delivery["backflow"]["note"] = "待基层补录和审核汇总完成后，再决定是否纳入模板。"
            self.brain._append_audit_feed("request.approve", request_id, "ok", actor)
            return {"request_id": request_id, "status": request["status"]}

        result = self.brain._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": decision}, mutation)
        # R-006 fix: 凭据签发作为审批之后的独立动作；audit 失败不污染审批 mutation
        self.brain._auto_issue_credential_on_approval(request_id, role, self.brain._actor_for_role(role))
        return result

    def return_for_fix(
        self,
        request_id: str,
        role: str,
        confirmed: bool,
        skill_id: str = "approval.review_decide",
        *,
        decision: str = "return_for_fix",
    ) -> dict[str, Any]:
        """Return a request for fix; delivery transitions to warning state."""
        from zw_brain.shared import clock  # noqa: PLC0415

        request = self.by_id(request_id)
        approval = self.approval_by_id(request_id)
        delivery = self.brain._get_handler_deps().services.delivery.by_request_id(request_id)
        if request["status"] not in {"pending", "summary-pending"}:
            raise InvalidStateError("current request cannot be returned for fix")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request["status"] = "need-fix"
            request["timeline"].append(
                {
                    "label": "已退回补正",
                    "time": clock.now_datetime(),
                    "note": "要求重新说明差异字段责任边界或补齐异常项说明。",
                }
            )
            request["aiStatus"]["summary"] = "申请已退回补正，当前不进入下一状态。"
            request["aiStatus"]["nextAction"] = "请补齐差异字段说明后重新提交。"
            approval["suggestion"] = "建议补正"
            approval["impact"] = "退回补正后，补录与汇总链路暂停，不继续向前推进。"
            if delivery:
                delivery["status"] = "warning"
                delivery["updatedAt"] = clock.now_datetime()
                delivery["note"] = "当前链路已退回补正，未继续推进补录或汇总。"
                delivery["history"].append(
                    {
                        "time": clock.now_short_time(),
                        "state": "退回补正",
                        "detail": "因责任边界或异常项说明不足，链路暂停。",
                    }
                )
                delivery["aiSummary"]["summary"] = "这不是执行失败，而是人工决定链路回退补正。"
                delivery["aiSummary"]["nextAction"] = "请申请方或基层先补齐说明，再重新进入下一步。"
                delivery["backflow"]["status"] = "不适用"
                delivery["backflow"]["note"] = "当前未形成可确认的回流候选。"
            self.brain._append_audit_feed("request.return-for-fix", request_id, "warning", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self.brain._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": decision}, mutation)

    def reject(
        self,
        request_id: str,
        role: str,
        confirmed: bool,
        skill_id: str = "approval.review_decide",
        *,
        decision: str = "reject_duplicate",
    ) -> dict[str, Any]:
        """Reject a request; delivery transitions to warning state."""
        from zw_brain.shared import clock  # noqa: PLC0415

        request = self.by_id(request_id)
        delivery = self.brain._get_handler_deps().services.delivery.by_request_id(request_id)
        if request["status"] not in {"pending", "summary-pending"}:
            raise InvalidStateError("current request cannot be rejected")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request["status"] = "rejected"
            request["timeline"].append(
                {
                    "label": "已驳回申请",
                    "time": clock.now_datetime(),
                    "note": "因重复要数或越界采集风险被终止。",
                }
            )
            request["aiStatus"]["summary"] = "该申请已被明确驳回，不再继续进入补录和汇总链路。"
            request["aiStatus"]["nextAction"] = "如需继续，请改为模板复用 + 差异补录模式重新发起。"
            if delivery:
                delivery["status"] = "warning"
                delivery["updatedAt"] = clock.now_datetime()
                delivery["note"] = "申请已驳回，链路终止。"
                delivery["history"].append(
                    {
                        "time": clock.now_short_time(),
                        "state": "申请驳回",
                        "detail": "因重复要数或越界采集风险，任务未继续推进。",
                    }
                )
                delivery["aiSummary"]["summary"] = "这是一次被明确终止的链路，不应伪装成业务成功。"
                delivery["aiSummary"]["nextAction"] = "如需重启，请先回到模板复用起点重新收敛需求。"
                delivery["backflow"]["status"] = "不适用"
                delivery["backflow"]["note"] = "驳回后不生成回流候选。"
            self.brain._append_audit_feed("request.reject", request_id, "warning", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self.brain._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": decision}, mutation)

    def route_for_catalog_confirmation(
        self,
        request_id: str,
        role: str,
        confirmed: bool,
        skill_id: str = "approval.review_decide",
    ) -> dict[str, Any]:
        """Route request for catalog/provider confirmation."""
        from zw_brain.shared import clock  # noqa: PLC0415

        request = self.by_id(request_id)
        approval = self.approval_by_id(request_id)
        delivery = self.brain._get_handler_deps().services.delivery.by_request_id(request_id)
        if request["status"] not in {"pending", "summary-pending"}:
            raise InvalidStateError("current request cannot be routed for catalog confirmation")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            request["status"] = "pending-provider-confirmation"
            request["timeline"].append(
                {
                    "label": "已转供给侧口径确认",
                    "time": clock.now_datetime(),
                    "note": "需要 数据提供方 / 业务运营员 确认目录字段口径或资源授权边界后再继续准入。",
                }
            )
            request["aiStatus"]["summary"] = "申请已转 数据提供方 / 业务运营员 口径确认，当前不生成新授权。"
            request["aiStatus"]["nextAction"] = "请供给侧确认目录字段口径、资源状态和授权边界。"
            approval["suggestion"] = "建议转口径确认"
            approval["impact"] = "转办期间暂停补录和交付，避免在口径未确认时扩大授权。"
            if delivery:
                delivery["status"] = "warning"
                delivery["updatedAt"] = clock.now_datetime()
                delivery["note"] = "已转供给侧口径确认，未生成新授权。"
                delivery["history"].append(
                    {
                        "time": clock.now_short_time(),
                        "state": "转口径确认",
                        "detail": "审批人 要求 数据提供方 / 业务运营员 先确认目录字段口径或授权边界。",
                    }
                )
                delivery["backflow"]["status"] = "不适用"
                delivery["backflow"]["note"] = "转办确认前不形成回流候选或授权变更。"
            self.brain._append_audit_feed("request.route-to-provider-or-catalog-admin", request_id, "warning", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self.brain._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": "route_to_provider_or_catalog_admin"}, mutation)

    def review_application_record(
        self,
        request_id: str,
        decision: str,
        role: str,
        confirmed: bool,
        skill_id: str,
    ) -> dict[str, Any]:
        """Persist review decision + delivery payload patch (full review flow)."""
        store = self.brain._state_store.database_store
        if store is None:
            raise NotFoundError(request_id)
        request = self.brain.get_request(request_id)
        delivery = self.brain._get_handler_deps().services.delivery.task_from_record(request_id, store)
        if delivery is None:
            raise NotFoundError(request_id)
        existing_review = delivery.get("r2Review") if isinstance(delivery.get("r2Review"), dict) else {}
        if request["status"] != "pending" and existing_review.get("decision"):
            raise InvalidStateError("request is not pending approval")
        reason = self.brain._r2_review_reason(decision, request)
        evidence = self.brain._r2_review_evidence(decision, request, delivery)
        result_status = {
            "approve_reuse": "granted",
            "approve_with_supplement": "supplementing",
            "return_for_fix": "need-fix",
            "reject_duplicate": "rejected",
            "route_to_provider_or_catalog_admin": "pending-provider-confirmation",
        }[decision]

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            store.approval_repo.append_application_review_decision(
                request_id,
                decision=decision,
                reason=reason,
                evidence=evidence,
                actor=actor,
                skill_id=skill_id,
                audit_id=audit_id,
                status=result_status,
                tenant_id=_DEFAULT_TENANT_ID,
            )
            payload_patch = {
                "r2_review": {
                    "decision": decision,
                    "reason": reason,
                    "evidence": evidence,
                    "actor": actor,
                    "audit_id": audit_id,
                },
                "renewal_boundary": "真实 data_apply_renewal 无行；不伪造续期成功路径。",
            }
            grant_snapshot = copy.deepcopy(delivery.get("accessGrantSnapshot") or {})
            common_boundary = {
                "field_scope": [item.get("title") for item in request.get("requestedItems", [])],
                "sensitive_levels": copy.deepcopy(request.get("sensitivePolicy", {}).get("fieldSensitiveLevels") or []),
                "frequency": copy.deepcopy(request.get("applicationMaterials", {}).get("frequency") or {}),
                "limit_day": grant_snapshot.get("limit_day"),
                "access_grant_snapshot": grant_snapshot,
            }
            if decision == "approve_reuse":
                payload_patch["grant_boundary"] = {
                    **common_boundary,
                    "mode": "reuse_existing_authorization",
                    "source": "data_apply_authrization",
                }
                delivery_state = "granted"
            elif decision == "approve_with_supplement":
                payload_patch["supplement_boundary"] = {
                    **common_boundary,
                    "mode": "local_supplement_before_delivery",
                    "gap_fields": copy.deepcopy(request.get("gapFields") or []),
                    "source": "application.resource.review",
                }
                delivery_state = "supplementing"
            else:
                payload_patch["non_grant_boundary"] = {"mode": decision, "no_new_grant": True}
                delivery_state = "blocked"
            snapshot_request = self.maybe_by_id(request_id)
            if snapshot_request is not None:
                snapshot_request["status"] = result_status
            snapshot_delivery = self.brain._get_handler_deps().services.delivery.by_request_id(request_id)
            if snapshot_delivery is not None:
                snapshot_delivery["status"] = delivery_state
                snapshot_delivery["r2_review"] = copy.deepcopy(payload_patch["r2_review"])
                snapshot_delivery["r2Review"] = copy.deepcopy(payload_patch["r2_review"])
                snapshot_delivery["renewal_boundary"] = payload_patch["renewal_boundary"]
                snapshot_delivery["renewalBoundary"] = payload_patch["renewal_boundary"]
                if "grant_boundary" in payload_patch:
                    snapshot_delivery["grant_boundary"] = copy.deepcopy(payload_patch["grant_boundary"])
                    snapshot_delivery["grantBoundary"] = copy.deepcopy(payload_patch["grant_boundary"])
                if "supplement_boundary" in payload_patch:
                    snapshot_delivery["supplement_boundary"] = copy.deepcopy(payload_patch["supplement_boundary"])
                    snapshot_delivery["supplementBoundary"] = copy.deepcopy(payload_patch["supplement_boundary"])
                if "non_grant_boundary" in payload_patch:
                    snapshot_delivery["non_grant_boundary"] = copy.deepcopy(payload_patch["non_grant_boundary"])
                    snapshot_delivery["nonGrantBoundary"] = copy.deepcopy(payload_patch["non_grant_boundary"])
            store.application_repo.update_status(request_id, result_status, tenant_id=_DEFAULT_TENANT_ID)
            store.delivery_repo.update_task_payload(delivery["id"], state=delivery_state, payload_patch=payload_patch, tenant_id=_DEFAULT_TENANT_ID)
            self.brain._append_audit_feed("application.resource.review", f"{request_id}:{decision}", "ok" if decision.startswith("approve") else "warning", actor)
            return {
                "request_id": request_id,
                "status": result_status,
                "decision": decision,
                "reason": reason,
                "evidence": evidence,
                "delivery_state": delivery_state,
            }

        result = self.brain._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": decision, "reason": reason, "evidence": evidence}, mutation)
        # R-006 fix: 凭据签发作为审批之后的独立动作；audit 失败不污染审批 mutation
        if decision in {"approve_reuse", "approve_with_supplement"}:
            self.brain._auto_issue_credential_on_approval(request_id, role, self.brain._actor_for_role(role))
        return result
