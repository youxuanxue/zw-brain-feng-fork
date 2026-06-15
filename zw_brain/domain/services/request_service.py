"""RequestService — request approval flow + status helpers.

Owns: request batch context (D-9 prefetch), status timeline, status text,
by-id / maybe lookups, approval flow methods (approve / return / reject /
route), review_application_record, new_request_id.

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from zw_brain.domain.errors import InvalidStateError, NotFoundError, _RequestBatchContext
from zw_brain.shared import ids
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


def derive_platform_credential(request_id: str, seed: str | None = None) -> dict[str, Any]:
    """Deterministic platform self-signed credential — 同一 (request_id, seed) 永生同一凭据。

    在产单审批通过时**平台自签**签发的真实凭据（D47：平台自签合法）。前缀 ``AK-SELF-``
    诚实标识"平台自签"，**不再打 ``AK-DEMO-`` 假证牌**——这是真实已签发凭据，不是演示物。
    legacy 导入的 granted 授权**不**走此路径（D47：诚实标 not_issued，见 exchange mapper）。

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
    app_key = f"AK-SELF-{request_id}-{digest[:8].upper()}"
    app_secret = f"SK-SELF-{digest[8:32]}"
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

    def build_batch_context(
        self, store: Any, application_records: list[Any], *, canonical_refs: list[str] | None = None
    ) -> Any:
        """Build _RequestBatchContext with prefetched indices for list_requests.

        Cost: 1 delivery_repo.list_tasks + 8 legacy_mapping_repo.list_mappings
        (one per canonical_type) + 1 metadata_evidence_repo.list_quality_evidence
        + 0 application_repo.list_records (reuses caller's already-fetched list).
        Replaces ~5N per-item scans with O(1) lookups.

        ``canonical_refs`` (MEDIUM-1 scope pushdown): the legacy_object_mapping
        table holds ~68k rows. Even type-filtered, catalog_item / approval_*
        each carry ~1.4k rows the request page rarely touches. When the caller
        knows the exact set of canonical_refs in scope (e.g. the provider asset
        path — every consumed ref is one of the page's resource_codes), pass it
        so every legacy-mapping query pushes ``canonical_refs IN (...)`` down
        and the prefetch fetches only referenced rows.

        When ``canonical_refs is None`` (request-list path, where catalog /
        resource refs are discovered lazily during nested enrichment and cannot
        be enumerated up front), the two request-keyed types
        (application_record / DeliveryTaskRecord) are still scoped to the
        page's application_codes — those refs ARE known here — while the
        catalog / resource / approval types keep their type-filtered scan. The
        consumed map slices are byte-identical in both modes (the map
        default-returns ``[]`` for absent keys; scoping only drops rows no
        ``.get`` ever reads).
        """
        delivery_by_appcode: dict[str, Any] = {}
        for delivery in store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID):
            delivery_by_appcode[delivery.application_code] = delivery
            delivery_by_appcode[delivery.delivery_code] = delivery

        legacy_mappings_by_ref: dict[tuple[str, str], list[Any]] = {}
        # 8 canonical_types are touched by enrichment + request projection.
        # request-keyed types are scoped to the page's application_codes when
        # no explicit canonical_refs scope is given.
        application_codes = [str(record.application_code) for record in application_records]
        request_keyed_types = {"application_record", "DeliveryTaskRecord"}
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
            if canonical_refs is not None:
                refs_scope = canonical_refs
            elif canonical_type in request_keyed_types:
                refs_scope = application_codes
            else:
                refs_scope = None
            for mapping in store.legacy_mapping_repo.list_mappings(
                tenant_id=_DEFAULT_TENANT_ID,
                canonical_type=canonical_type,
                canonical_refs=refs_scope,
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
        """Platform self-signed credential — 同一 (request_id, seed) 永生同一凭据。

        Action H commit 4: lifted from ``BrainService._credential_for_request``.
        Pure derivation; no instance state used (kept on the service for
        cohesion with the rest of the request approval flow).

        seed=None：首次签发（auto-on-approval），用 request_id 作种子；
        seed=<audit_id>：reissue 路径每次重签都产生不同 app_secret
        （旧 secret 立即失效语义；与生产 IAM reissue 行为对齐）.

        Delegates to the module-level :func:`derive_platform_credential`（前缀
        AK-SELF，平台自签真实凭据，非演示物）。
        """
        return derive_platform_credential(request_id, seed)

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

    # 申请权威 status → 当前所处里程碑指针（1 待受理 / 2 审核 / 3 审批结论 / 4 交付 / 5 已完成）。
    # 单一事实源：4 段进度只读这张表 + status，前端 stepper 不重派生（D56 读侧呈现）。
    _TIMELINE_POINTER: ClassVar[dict[str, int]] = {
        "submitted": 2, "pending": 2, "need-fix": 2, "supplementing": 2,
        "dept_approved": 3, "rejected": 3,
        "approved": 4, "summary-pending": 4, "in_delivery": 4,
        "granted": 5, "completed": 5, "revoked": 5, "suspended": 5,
    }

    def status_timeline(
        self, request: dict[str, Any], delivery: dict[str, Any] | None, *, perspective: str = "reviewer"
    ) -> list[dict[str, Any]]:
        """Compute the applicant-facing 4-stage progress timeline for a request.

        待受理 → 审核中 → 审批结论 → 交付，各段 done/current/pending 由申请权威 ``status``
        单调现算（单一事实源；不在前端重新派生）。``delivery`` 仅用于交付段 ``ref`` 回链——
        缺省 ``None`` 时交付段亦由 ``status`` 推断，供快照读侧 enrich（无 delivery join）。
        ``perspective`` 决定文案视角（applicant / reviewer / …，PII-safe，见 ``status_text``）。
        未提交草稿无流转 → 返回空列表（stepper 不渲染）。
        """
        status = request.get("status")
        if status in (None, "", "draft"):
            return []
        ptr = self._TIMELINE_POINTER.get(str(status))
        if ptr is None:
            return []  # 非运行时旅程词汇（含 legacy 旧平台态 under_review/effective/…）→ 不渲染 stepper
        rid = request.get("id")

        def _seg(i: int) -> str:
            return "done" if ptr > i else ("current" if ptr == i else "pending")

        # 每段标签描述「该段自身」状态，不把整单 status 泄漏到已过去的段：
        # 审核中——当前段给视角文案（审批中/已提交待受理/待补正…），已过给「已受理」。
        review_label = self.status_text(request, perspective) if ptr == 2 else "已受理"
        if ptr > 3:
            decision_label = "已通过"
        elif status in {"rejected", "need-fix"}:
            decision_label = self.status_text(request, perspective)  # 「已驳回」/「待补正」
        elif ptr == 3:
            decision_label = "审核中"
        else:
            decision_label = "待审批结论"
        deliver_label = {"done": "已交付", "current": "交付中", "pending": "待交付"}[_seg(4)]
        # 「卡在谁桌上」——holder 只挂在当前段（status=='current'），状态驱动、诚实、不捏造。
        holder = self._holder_for(str(status), request, delivery)
        steps = [
            {"stage": "待受理", "status": _seg(1), "ref": rid, "label": "申请已提交", "holder": ""},
            {"stage": "审核中", "status": _seg(2), "ref": rid, "label": review_label, "holder": ""},
            {"stage": "审批结论", "status": _seg(3), "ref": rid, "label": decision_label, "holder": ""},
            {"stage": "交付", "status": _seg(4), "ref": delivery.get("id") if delivery else None, "label": deliver_label, "holder": ""},
        ]
        for step in steps:
            if step["status"] == "current":
                step["holder"] = holder
        return steps

    @staticmethod
    def _holder_for(status: str, request: dict[str, Any], delivery: dict[str, Any] | None) -> str:
        """当前段「在谁桌上」——只由 status（+真实 delivery 态）现算，取不到诚实留空，绝不捏造。

        受理/审核两关是申请真正卡住处，holder 确证可答（业务运营员受理 / 部门管理员审核+提供方部门）；
        交付/终态仅当真有补录态 delivery 才答基层填报人，否则空（不假设一表通补录）。
        """
        if status in {"submitted", "pending", "need-fix", "supplementing"}:
            return "业务运营员（受理）"
        if status == "dept_approved":
            prov = str(request.get("providerOrgName") or request.get("provider_org_name") or "").strip()
            return f"部门管理员·{prov}" if prov else "部门管理员（部门审核）"
        if status in {"approved", "in_delivery"} and delivery is not None and str(
            delivery.get("status") or delivery.get("state") or ""
        ) in {"pending", "supplementing", "reconciling", "warning"}:
            return "镇街/村社区填报人（补录）"
        return ""

    def status_text(self, item: dict[str, Any], perspective: str = "reviewer") -> str:
        """Localized status text per perspective (applicant / reviewer / filler / summarizer).

        R-002 fix: 文案不再按 role 单维区分（折叠后同一 ROLE_* 无法承载"申请人 vs 填报人"双语义）。
        改为按业务视角（perspective）显示文案；调用方在每个待办语境下显式声明视角。
        """
        status = item["status"]
        if status == "pending":
            return {"applicant": "审批中", "reviewer": "待审批", "filler": "等待审批", "summarizer": "等待审批"}.get(perspective, "待审批")
        if status == "submitted":
            # D55/P21 受理两级入口态（有条件直提/提交单，状态词汇桥接方案 B）。
            return {"applicant": "已提交待受理", "reviewer": "待受理", "filler": "已提交待受理", "summarizer": "已提交待受理"}.get(perspective, "待受理")
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
        if status == "dept_approved":
            # D55/P21：受理通过待部门审核（中间态）。受理人视角=已受理；部门审核人视角=待审核。
            return {"applicant": "已受理待审核", "reviewer": "待审核", "filler": "已受理待审核", "summarizer": "已受理待审核"}.get(perspective, "已受理待审核")
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
            "reconciling": "待核对",
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

    # --- Card lookups (Action D: DB 单一事实源，经 CardSession) ---

    def by_id(self, request_id: str) -> dict[str, Any]:
        """Request by id; raises NotFoundError when absent.

        运行时单经 CardSession 载入（payload_json 卡 + 权威 status 列覆盖，
        同 dispatch 内同一实例——处理器闭包就地变更由写括号末尾 flush 落库）；
        legacy 导入单走 record_to_request 只读合成投影（不进会话、不被回写）。
        """
        card = self.brain._card_session.get_request(request_id)
        if card is not None:
            return card
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

    def is_legacy_import(self, request_id: str) -> bool:
        """该申请是否为历史导入（M0 一次性迁移）记录 = 只读迁移卡，非运行时实体。

        判别口径同 ``card_session.is_runtime_request_payload`` 的反面（legacy 导入 payload
        一律带 ``kind``，运行时卡从不带）——此处在 domain 层内联该一行判别（``"kind" in
        payload``），不反向 import command 层（4 层 entry→command→domain→shared）。
        已进会话的运行时卡 → False；申请不存在 → False（交由调用方按 NotFound 处理）。

        用于凭据/动作面把历史导入识别为只读：无 delivery 实体时不抛 422，改诚实空态。
        """
        if self.brain._card_session.get_request(request_id) is not None:
            return False  # 已进会话的运行时卡
        store = getattr(getattr(self.brain, "_state_store", None), "database_store", None)
        if store is None:
            return False
        record = store.application_repo.get_record(request_id, tenant_id=_DEFAULT_TENANT_ID)
        if record is None:
            return False
        payload = record.payload_json or {}
        return bool(payload) and "kind" in payload

    def approval_by_id(self, request_id: str) -> dict[str, Any]:
        """Approval row by request id; raises NotFoundError when absent.

        运行时审批卡经 CardSession 载入（approval_case.decision_payload_json，
        闭包就地变更由 flush 落库）；legacy 导入 case 现算一张**只读展示卡**。
        DB 展示卡只供详情/收件箱显示——真实导入审批的两步流转动作由 UI 按运行时实体可解析性
        门控（历史导入=只读），不走这里 mutate。
        """
        card = self.brain._card_session.get_approval(request_id)
        if card is not None:
            return card
        store = getattr(getattr(self.brain, "_state_store", None), "database_store", None)
        if store is not None:
            case = store.approval_repo.get_case(request_id, tenant_id=_DEFAULT_TENANT_ID)
            if case is not None:
                return {
                    "id": case.application_code,
                    "status": case.current_status,
                    "suggestion": "待审",
                    "legacyImport": bool(getattr(case, "legacy_id", None)),
                }
        raise NotFoundError(request_id)

    def maybe_approval_by_id(self, request_id: str) -> dict[str, Any] | None:
        """Snapshot approval row by request id; returns None when absent."""

        try:
            return self.approval_by_id(request_id)
        except NotFoundError:
            return None

    def new_request_id(self) -> str:
        """Mint a new application code（Action D：不透明 uuid4().hex，与导入单同形）。"""
        return ids.new_application_code()

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
        # D55/P21 状态机挡板：有条件共享 (shared_type=2) 须走受理两级
        # （application.platform_approve 受理 → application.dept_approve 部门审核，
        # 后者承 R11 方向 + self-approval guard）。本单步路径无这两道 guard，
        # 放行即绕过已裁状态机——payload 显式值优先，缺位按资源 access_policy 回源
        # （与申请卡投影同源；legacy 导入单 payload 常缺 shared_type）。
        from zw_brain.domain.discovery_snapshot_projection import (  # noqa: PLC0415
            _share_type_by_resource,
            _shared_type_for,
        )
        record = store.application_repo.get_record(request_id, tenant_id=_DEFAULT_TENANT_ID)
        record_payload = (record.payload_json or {}) if record is not None else {}
        if _shared_type_for(record_payload, _share_type_by_resource(_DEFAULT_TENANT_ID)) == 2:
            raise InvalidStateError(
                "有条件共享申请须走受理两级（application.platform_approve 受理 → "
                "application.dept_approve 部门审核），不支持单步受理"
            )
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
