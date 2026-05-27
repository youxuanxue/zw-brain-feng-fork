from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import json

# Default read-side mask role. Per [2026-05-06] sensitive-field policy: business-
# visible PII (name / phone / email / id / address) is ingested raw, masked on
# read. Set ZW_BRAIN_MASK_ROLE=internal_admin to opt up (audit replay only).
import os as _os
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import zw_brain.shared.audit as audit_bus
import zw_brain.shared.clock as clock
import zw_brain.shared.ids as ids
from zw_brain.command.serializers import delivery as delivery_ser
from zw_brain.command.serializers import metadata as metadata_ser
from zw_brain.command.serializers import quality as quality_ser
from zw_brain.command.serializers import resource_api as resource_api_ser
from zw_brain.command.serializers import topic_package as topic_package_ser
from zw_brain.domain import policy
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.domain.repositories.delivery import DeliveryRepository
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.domain.repositories.topic_package import TopicPackageRepository
from zw_brain.shared import queue
from zw_brain.shared.auth_context import get_auth_context
from zw_brain.shared.runtime_config import get_dev_iam_bypass_enabled
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id
from zw_brain.shared.sanitization import safe_json
from zw_brain.shared.sensitive_mask import apply_field_masks
from zw_brain.shared.state_store import StateStore
from zw_brain.shared.ui_request_context import get_current_role, set_current_role
from zw_brain.skill_registration.runtime import get_manifest, load_manifests

_DEFAULT_MASK_ROLE = _os.environ.get("ZW_BRAIN_MASK_ROLE", "external")
_DEFAULT_TENANT_ID = get_runtime_tenant_id()


def _expected_iaf_issuer() -> str:
    return _os.environ.get("ZW_BRAIN_IAF_ISSUER", "")


def _expected_iaf_audience() -> str:
    return _os.environ.get("ZW_BRAIN_IAF_AUDIENCE", _os.environ.get("ZW_BRAIN_IAF_CLIENT_ID", "zw-brain"))


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _mask(payload: Any) -> Any:
    """Apply default-role mask to a serializer's outgoing payload."""
    return apply_field_masks(payload, role=_DEFAULT_MASK_ROLE)


DEFAULT_DISCOVERY_QUERY = "停车场信息"


class BrainServiceError(RuntimeError):
    pass


class UnknownSkillError(BrainServiceError):
    pass


class AccessDeniedError(BrainServiceError):
    pass


class ConfirmationRequiredError(BrainServiceError):
    pass


class InvalidStateError(BrainServiceError):
    pass


class NotFoundError(BrainServiceError):
    pass


class InvalidTokenError(BrainServiceError):
    pass


@dataclass
class _RequestBatchContext:
    """Prefetched indices for list_requests N+1 elimination (D-9).

    Why: list_requests previously called delivery_repo.list_tasks() /
    application_repo.list_records() / legacy_mapping_repo.list_mappings() /
    resource_api_repo.list_assets() / metadata_evidence_repo.list_schema_*()
    once per item (deep N+1 through get_resource → _enrich_catalog_detail),
    ~37s on the customer browser replay. This context bundles prefetched
    indices that helpers consult instead of re-fetching.
    """

    delivery_by_appcode: dict[str, Any] = field(default_factory=dict)
    application_records: list[Any] = field(default_factory=list)
    legacy_mappings_by_ref: dict[tuple[str, str], list[Any]] = field(default_factory=dict)
    quality_by_target: dict[tuple[str, str], list[Any]] = field(default_factory=dict)
    resource_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Enrichment-layer prefetches (consumed by _enrich_catalog_detail / _mapping_diagnostics).
    resource_assets_by_catalog: dict[str, list[Any]] = field(default_factory=dict)
    schema_mappings_by_catalog: dict[str, list[Any]] = field(default_factory=dict)
    schema_snapshots_by_resource: dict[str, list[Any]] = field(default_factory=dict)
    catalog_items_by_catalog: dict[str, list[Any]] = field(default_factory=dict)
    catalog_items_by_item_code: dict[str, Any] = field(default_factory=dict)


class _UIStateProxy(MutableMapping[str, Any]):
    """Drop-in replacement for the old ``_ui_state`` dict.

    ``role`` is per-request and must NOT live on the process-global BrainService
    singleton (concurrent requests would overwrite each other between resolve and
    read). This proxy routes the ``role`` key to a ContextVar (thread / asyncio
    task isolated) while keeping ``discoveryQuery`` / ``brainOutage`` on a real
    backing dict. The mapping API is preserved so existing call sites
    (``_ui_state["role"]`` / ``.get("role", d)`` / ``_ui_state["role"] = x``)
    work unchanged and become concurrency-safe for free.

    Invariant locked by ``scripts/check_brain_no_request_state_singleton.py``:
    the backing dict must never seed a ``role`` key.
    """

    _CONTEXT_KEYS = ("role",)

    def __init__(self, backing: dict[str, Any]) -> None:
        self._backing = backing

    def __getitem__(self, key: str) -> Any:
        if key == "role":
            return get_current_role()
        return self._backing[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "role":
            set_current_role(value)
            return
        self._backing[key] = value

    def __delitem__(self, key: str) -> None:
        if key == "role":
            raise KeyError("role is a per-request context value and cannot be deleted")
        del self._backing[key]

    def __iter__(self) -> Iterator[str]:
        yield "role"
        yield from self._backing

    def __len__(self) -> int:
        return len(self._backing) + len(self._CONTEXT_KEYS)

    def persistable_view(self) -> dict[str, Any]:
        # Per-request keys (ContextVar-backed) must not enter durable storage —
        # their value is meaningful only inside the request that wrote them.
        return dict(self._backing)


class BrainService:
    # Cached HandlerDeps built lazily on first invoke_skill (Action A); the
    # container is process-wide stable except for `brain_legacy=self`, so a
    # one-time build is correct.
    _handler_deps: Any = None

    def __init__(self, state_store: StateStore | None = None) -> None:
        self._state_store = state_store or StateStore()
        self._snapshot = self._state_store.load()
        # role is per-request → ContextVar via _UIStateProxy; only true-global
        # keys are seeded on the backing dict (see _UIStateProxy docstring).
        self._ui_state = _UIStateProxy({
            "discoveryQuery": DEFAULT_DISCOVERY_QUERY,
            "brainOutage": False,
        })
        self._sync_state_views()
        self._persist()
        if self._state_store.database_store is not None:
            self._sync_database_aggregates()

    def snapshot(self) -> dict[str, Any]:
        state = copy.deepcopy(self._snapshot)
        # dict(...) materializes the proxy (role read from ContextVar now) into a
        # plain JSON-serializable dict; deepcopy of the proxy object would leak it.
        state["state"] = dict(self._ui_state)
        _iaf_url = (_os.environ.get("ZW_BRAIN_IAF_AUTH_SERVER_URL") or "").strip()
        _dev_bypass = get_dev_iam_bypass_enabled()
        _allow_switch_env = _os.environ.get("ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH", "").strip()
        # Dev IAM bypass 默认打开岗位切换（与 scripts/start-local.sh 一致）；显式 =0 时仍关闭。
        _allow_role_switch = _allow_switch_env == "1" or (_dev_bypass and _allow_switch_env != "0")
        state["webui"] = {
            "deploymentLabel": _os.environ.get("ZW_BRAIN_DEPLOYMENT_LABEL", "").strip(),
            "legalNotice": _os.environ.get("ZW_BRAIN_WEBUI_LEGAL_NOTICE", "").strip(),
            "identityLabel": _os.environ.get("ZW_BRAIN_WEBUI_IDENTITY_LABEL", "当前账号").strip() or "当前账号",
            "allowRoleSwitch": _allow_role_switch,
            "iafIam": {"configured": bool(_iaf_url), "developmentBypassEnabled": _dev_bypass},
        }
        return state

    def manifests(self) -> dict[str, dict[str, Any]]:
        return load_manifests()

    @staticmethod
    def _validate_required_input(skill_id: str, manifest: dict[str, Any], payload: dict[str, Any]) -> None:
        # JSON Schema "required" = key presence; value-shape constraints belong elsewhere.
        # `confirmed` is intentionally skipped: it's a control signal whose absence is handled
        # by _enforce_manifest_policy (human_confirmation_required → ConfirmationRequiredError
        # → HTTP 409), not a 400 missing-field error.
        required = [
            k for k in ((manifest.get("input_schema") or {}).get("required") or [])
            if k != "confirmed"
        ]
        missing = [k for k in required if k not in payload]
        if missing:
            raise BrainServiceError(
                f"missing required input field(s): {', '.join(missing)} (skill: {skill_id})"
            )

    # --- Split-refactor delegation shims (PR #86) -------------------------
    # PR #86 拆分 brain.py 时把这些方法体抽成 handler 层 `_X(brain, ...)` 模块级
    # helper，但 brain.py 内部 (self.X) 与多个 handler (brain.X) 调用点未同步更新，
    # 真实 J1/J2 路径会 AttributeError（仅在 CI 跳过的真数据测试里才暴露）。这些薄
    # 委托方法把公开 API 恢复到 BrainService，实现仍在 handler helper（local import
    # 避免与 handler→brain 的模块级反向依赖成环）。
    def get_resource(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.j1.catalog_meta import _get_resource
        return _get_resource(self, *args, **kwargs)

    def get_request(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.j1.request import _get_request
        return _get_request(self, *args, **kwargs)

    def create_request(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.j1.request import _create_request
        return _create_request(self, *args, **kwargs)

    def get_delivery_task(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.j1.delivery import _get_delivery_task
        return _get_delivery_task(self, *args, **kwargs)

    def review_request(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.j1.approval import _review_request
        return _review_request(self, *args, **kwargs)

    def transition_api_resource(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.j1.resource_api import _transition_api_resource
        return _transition_api_resource(self, *args, **kwargs)

    def get_dispute(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.j1.governance_dispute import _get_dispute
        return _get_dispute(self, *args, **kwargs)

    def list_audit_events(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.b1.audit import _list_audit_events
        return _list_audit_events(self, *args, **kwargs)

    def list_packages(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.b1.capability_admin import _list_packages
        return _list_packages(self, *args, **kwargs)

    def evaluate_tenant_policy(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.j2.tenant_policy import _evaluate_tenant_policy
        return _evaluate_tenant_policy(self, *args, **kwargs)

    def list_zones(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.j2.zone import _list_zones
        return _list_zones(self, *args, **kwargs)

    def update_topic_package_policy(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.handlers.j2.topic_package import _update_topic_package_policy
        return _update_topic_package_policy(self, *args, **kwargs)

    def invoke_skill(self, skill_id: str, payload: dict[str, Any] | None = None) -> Any:
        payload = payload or {}
        try:
            manifest = get_manifest(skill_id)
        except KeyError as exc:
            raise UnknownSkillError(skill_id) from exc
        self._validate_required_input(skill_id, manifest, payload)
        role = self._resolve_role(payload)
        self._ui_state["role"] = role
        self._enforce_manifest_policy(skill_id, manifest, role, payload)
        # Action A: build per-call SkillContext + cached HandlerDeps. Handlers
        # signature is `(deps, ctx, payload)`; brain reverse-access goes
        # through deps.brain_legacy.X (preflight 段 38 whitelists allowed surface).
        ctx = self._build_skill_context(skill_id, role, payload, manifest)
        deps = self._get_handler_deps()
        if manifest.get("audit_required") and not manifest.get("side_effects"):
            return self._invoke_traced_read(skill_id, role, payload, lambda: self._dispatch_skill(deps, ctx, payload))
        return self._dispatch_skill(deps, ctx, payload)

    def _build_skill_context(self, skill_id: str, role: str, payload: dict[str, Any], manifest: dict[str, Any]) -> Any:
        """Build SkillContext for a call — used by commit-2+ migration; commit 1 only.

        Public on BrainService so tests and runtime can construct contexts
        without touching internals.
        """
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        return SkillContext(
            skill_id=skill_id,
            role=role,
            actor=self._actor_for_role(role),
            confirmed=bool(payload.get("confirmed")),
            manifest=manifest,
        )

    def _get_handler_deps(self) -> Any:
        """Lazy-build cached HandlerDeps — commit-1 introduces; commits 2+ use.

        Cached because brain_legacy=self and repos are bound to the same store
        for the lifetime of this BrainService. runtime.reset_service() rebuilds
        both together.
        """
        if self._handler_deps is None:
            from zw_brain.command.deps import HandlerDeps  # noqa: PLC0415
            self._handler_deps = HandlerDeps.from_brain(self)
        return self._handler_deps

    def _dispatch_skill(self, deps: Any, ctx: Any, payload: dict[str, Any]) -> Any:
        # F1 split (turn 6 收官): 全 185 cap 已注册到 DISPATCH_TABLE；命中即 return，未注册视为 unknown skill。
        # Action A 升级 2026-05-27: handler 接收 (deps, ctx, payload) 而非 (brain, skill_id, payload)；
        # 未迁的 god-object surface 通过 deps.brain_legacy.X escape hatch（preflight 段 38 受控）。
        # Lazy import to break circular dep (brain → dispatch → handlers → brain.exceptions).
        from zw_brain.command import dispatch as _dispatch  # noqa: PLC0415
        handler = _dispatch.lookup(ctx.skill_id)
        if handler is None:
            raise UnknownSkillError(ctx.skill_id)
        return handler(deps, ctx, payload)

    def _objection_repo(self):
        store = self._state_store.database_store
        return store.objection_repo if store is not None else __import__("zw_brain.domain.repositories.objection", fromlist=["ObjectionRepository"]).ObjectionRepository()

    def _external_adapter_repo(self) -> ExternalAdapterRepository:
        store = self._state_store.database_store
        return store.external_adapter_repo if store is not None else ExternalAdapterRepository()

    def _governance_projection_repo(self) -> GovernanceProjectionRepository:
        store = self._state_store.database_store
        return store.governance_projection_repo if store is not None else GovernanceProjectionRepository()

    def _topic_package_repo(self) -> TopicPackageRepository:
        store = self._state_store.database_store
        return store.topic_package_repo if store is not None else TopicPackageRepository()

    def _capability_package_repo(self):
        store = self._state_store.database_store
        if store is not None:
            return store.capability_package_repo
        return __import__("zw_brain.domain.repositories.capability_package", fromlist=["CapabilityPackageRepository"]).CapabilityPackageRepository()

    @staticmethod
    def _build_m0_work_queue_cards(
        *,
        totals: dict[str, int],
        by_canonical: dict[str, dict[str, int]],
        adapter_runs: list[dict[str, Any]],
        rollbacks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Project aggregated state onto the 11 fixed M0 work-queue cards.

        Each card has a deterministic status (ready / partial / pending / failed)
        derived only from what we already loaded — no extra queries.
        """
        succeeded_runs = sum(1 for r in adapter_runs if r["status"] == "succeeded")
        failed_runs = sum(1 for r in adapter_runs if r["status"] == "failed")
        has_runs = bool(adapter_runs)
        has_mappings = totals["mappings"] > 0
        any_conflicted = totals.get("conflicted", 0) > 0
        any_rolled_back = totals.get("rolled_back", 0) > 0
        catalog_count = by_canonical.get("catalog_entry", {}).get("total", 0)
        resource_count = (
            by_canonical.get("ResourceAssetRecord", {}).get("total", 0)
            + by_canonical.get("resource_asset", {}).get("total", 0)
        )
        application_count = by_canonical.get("application_record", {}).get("total", 0)
        topic_count = by_canonical.get("TopicPackageRecord", {}).get("total", 0)
        objection_count = by_canonical.get("ObjectionCaseRecord", {}).get("total", 0)
        delivery_count = by_canonical.get("DeliveryTaskRecord", {}).get("total", 0)

        def status(condition_ready: bool, condition_partial: bool = False) -> str:
            if condition_ready:
                return "ready"
            if condition_partial:
                return "partial"
            return "pending"

        return [
            {
                "id": "export",
                "title": "一键导出",
                "owner": "M0 + 客户授权",
                "status": "ready" if has_runs else "pending",
                "summary": f"已识别 {len(adapter_runs)} 次最近导入运行" if has_runs else "等待客户现场导出",
            },
            {
                "id": "import",
                "title": "批量导入",
                "owner": "M0 实施人",
                "status": status(succeeded_runs >= 5, has_runs),
                "summary": f"{succeeded_runs} 个 adapter 已成功，{failed_runs} 个失败",
            },
            {
                "id": "mapping_verify",
                "title": "对象映射核验",
                "owner": "M0 + 数据提供方 / 业务运营员 抽样",
                "status": status(has_mappings and not any_conflicted, has_mappings),
                "summary": f"映射 {totals['mappings']} 条；冲突 {totals.get('conflicted', 0)}",
            },
            {
                "id": "catalog_migration_review",
                "title": "目录迁移审核",
                "owner": "M0 + 业务运营员 抽样",
                "status": status(catalog_count > 0, False),
                "summary": f"catalog_entry 映射 {catalog_count} 条",
            },
            {
                "id": "schema_mapping",
                "title": "schema 快照与挂接核验",
                "owner": "M0 + 数据提供方 抽样",
                "status": status(resource_count > 0, False),
                "summary": f"resource_asset 映射 {resource_count} 条",
            },
            {
                "id": "application_history",
                "title": "申请审批授权历史核验",
                "owner": "M0 + 审批人 抽样",
                "status": status(application_count > 0 and delivery_count > 0, application_count > 0),
                "summary": f"application_record {application_count} / delivery_task {delivery_count}",
            },
            {
                "id": "projection",
                "title": "投影生成",
                "owner": "M0 自动 + 失败摘要",
                "status": status((topic_count + objection_count) > 0, has_runs),
                "summary": f"topic_package {topic_count} / objection_case {objection_count}",
            },
            {
                "id": "compliance_sample",
                "title": "合规与断链抽查",
                "owner": "安全审计员 抽样",
                "status": status(objection_count > 0, has_mappings),
                "summary": f"已建立 objection_case {objection_count} 条样本" if objection_count else "等待 安全审计员 抽查",
            },
            {
                "id": "handover",
                "title": "验收移交",
                "owner": "客户验收人 + M0 实施人",
                "status": status(
                    has_mappings and not any_conflicted and succeeded_runs >= 5,
                    has_mappings,
                ),
                "summary": "等待客户验收签字" if not has_mappings else "可移交（缺口请检查冲突映射）",
            },
            {
                "id": "gap_reimport",
                "title": "缺口补迁",
                "owner": "M0 + 客户授权",
                "status": "ready" if has_runs else "pending",
                "summary": "支持按 schema 递增追加，回指旧对象",
            },
            {
                "id": "rollback",
                "title": "回滚",
                "owner": "M0 + 客户授权",
                "status": "ready" if any_rolled_back or has_runs else "pending",
                "summary": (
                    f"已记录 {len(rollbacks)} 次 rollback；最近 actor={rollbacks[0]['actor']}"
                    if rollbacks
                    else "尚未触发"
                ),
            },
        ]

    # ----- W1 skill implementations (reverse-cataloging, quality tasks, direct
    # access, require dispatch, withdrawal handling). These follow the existing
    # _mutate / get_manifest write-path or the read-only query path used by
    # legacy.migration.status.query. Each method is intentionally compact —
    # heavier business logic lives in dedicated repositories in W2/W3 if needed.

    def _filter_governance_actor(self, item: dict[str, Any], *, status_filter: str, role_filter: str, actor_filter: str) -> bool:
        profile = item.get("profile_json") if isinstance(item.get("profile_json"), dict) else {}
        if status_filter and item.get("status") != status_filter and profile.get("binding_status") != status_filter:
            return False
        if role_filter and role_filter not in (item.get("role_codes_json") or []):
            return False
        if actor_filter and item.get("external_actor_id") != actor_filter:
            return False
        return True

    def _governance_import_issues(self, adapter_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for run in adapter_runs:
            receipt = run.get("receipt_json") if isinstance(run.get("receipt_json"), dict) else {}
            for issue in receipt.get("issues") or []:
                if not isinstance(issue, dict):
                    continue
                issues.append(copy.deepcopy(issue) | {"adapter_run_id": run.get("id"), "adapter_status": run.get("status"), "source_ref": run.get("source_ref")})
        store = self._state_store.database_store
        if store is not None:
            for call in store.list_capability_calls():
                if call.skill_id != "legacy.bsp.mapping.import":
                    continue
                for item in call.output_json.get("items") or []:
                    if isinstance(item, dict) and item.get("reason"):
                        issues.append({"type": item["reason"], "table": "legacy.bsp.mapping.import", "legacy_ref": item.get("legacy_permission_ref"), "detail": {"legacy_role_ref": item.get("legacy_role_ref"), "capability_id": item.get("capability_id")}, "capability_call_ref": call.call_ref})
        return issues

    def _governance_audit_events(self, *, tenant_id: str, capability_filter: str = "", actor_filter: str = "") -> list[dict[str, Any]]:
        store = self._state_store.database_store
        if store is None:
            return []
        events = []
        for item in store.list_audit_events():
            payload = item.payload_json if isinstance(item.payload_json, dict) else {}
            if payload.get("tenant_id") not in {None, "", tenant_id}:
                continue
            if capability_filter and payload.get("capability_id") != capability_filter and payload.get("capability_slug") != capability_filter:
                continue
            if actor_filter and actor_filter not in {str(payload.get("external_actor_id", "")), str(payload.get("actor_id", "")), str(payload.get("actor_snapshot", {}).get("subject", "")) if isinstance(payload.get("actor_snapshot"), dict) else ""}:
                continue
            if item.skill_id in {
                "tenant.policy.evaluate",
                "legacy.bsp.mapping.import",
                "org.projection.sync",
                "actor.projection.sync",
                "governance.iam_overview",
                "governance.policy_candidate.list",
                "governance.policy_candidate.review",
            }:
                events.append({"id": item.request_id, "skill_id": item.skill_id, "phase": item.phase, "actor": item.actor, "occurred_at": item.occurred_at.isoformat(), "payload_json": copy.deepcopy(payload)})
        return events

    def _topic_package_list_projection(self, item: Any) -> dict[str, Any]:
        repo = self._topic_package_repo()
        items = [topic_package_ser.topic_item_to_dict(record) for record in repo.list_items(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        visibility = [topic_package_ser.topic_visibility_to_dict(record) for record in repo.list_visibility(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        return topic_package_ser.topic_package_to_dict(item) | self._topic_projection_summary(item, items, visibility)

    def _topic_package_detail_to_dict(self, item: Any) -> dict[str, Any]:
        repo = self._topic_package_repo()
        items = [topic_package_ser.topic_item_to_dict(record) for record in repo.list_items(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        visibility = [topic_package_ser.topic_visibility_to_dict(record) for record in repo.list_visibility(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        return topic_package_ser.topic_package_to_dict(item) | self._topic_projection_summary(item, items, visibility) | {
            "items": items,
            "visibility": visibility,
            "catalogProjectionItems": self._topic_catalog_projection_items(items),
            "reviews": [topic_package_ser.topic_review_to_dict(record) for record in repo.list_review_records(item.package_code, tenant_id=_DEFAULT_TENANT_ID)],
            "evidence": [topic_package_ser.topic_evidence_to_dict(record) for record in repo.list_evidence(item.package_code, tenant_id=_DEFAULT_TENANT_ID)],
            "metrics": [topic_package_ser.topic_metric_to_dict(record) for record in repo.list_metrics(item.package_code, tenant_id=_DEFAULT_TENANT_ID)],
        }

    def _topic_projection_summary(self, item: Any, items: list[dict[str, Any]], visibility: list[dict[str, Any]]) -> dict[str, Any]:
        approved_visibility = [record for record in visibility if record.get("policy_status") == "approved"]
        catalog_items = [record for record in items if record.get("ref_type") == "catalog_entry"]
        catalog_projection_items = self._topic_catalog_projection_items(catalog_items)
        visible_catalog_items = [record for record in catalog_projection_items if record.get("visible")]
        active_catalog_items = [record for record in catalog_projection_items if record.get("lifecycle_status") == "active"]
        authorization = self._topic_authorization_summary(catalog_items)
        failure_reasons: list[str] = []
        if item.status != "published":
            failure_reasons.append(f"topic_status:{item.status}")
        if catalog_items and not active_catalog_items:
            failure_reasons.append("no_active_catalog_item")
        if catalog_items and len(active_catalog_items) < len(catalog_items):
            failure_reasons.append("inactive_catalog_item_hidden")
        if active_catalog_items and not visible_catalog_items:
            failure_reasons.append("resource_binding_has_no_visible_fields")
        if active_catalog_items and any(record.get("resource_count", 0) > 0 and record.get("field_count", 0) == 0 for record in active_catalog_items):
            failure_reasons.append("resource_attached_but_no_visible_fields")
        if not approved_visibility:
            failure_reasons.append("no_approved_visibility")
        if authorization["effectiveGrantCount"] == 0:
            failure_reasons.append("authorization_not_effective")
        projection_status = "projected" if item.status == "published" and visible_catalog_items and approved_visibility else "blocked"
        return {
            "projectionKind": self._topic_projection_kind(item),
            "projectionStatus": projection_status,
            "projectionFailureReasons": failure_reasons,
            "visibleOrgCount": len(approved_visibility),
            "visibleOrgs": [record["visible_org"] for record in approved_visibility],
            "applicationBoundary": self._topic_application_boundary(approved_visibility),
            "authorizationStatus": authorization,
            "activeCatalogCount": len(active_catalog_items),
            "hiddenCatalogCount": max(0, len(catalog_items) - len(visible_catalog_items)),
            "sourceFact": "share_zone/share_group legacy tables are empty; this projection is derived from data_catalog_group/data_group_permission only.",
        }

    def _topic_projection_kind(self, item: Any) -> str:
        display = item.display_snapshot_json if isinstance(item.display_snapshot_json, dict) else {}
        return str(display.get("projection_kind") or display.get("source") or "topic_package")

    def _topic_application_boundary(self, visibility: list[dict[str, Any]]) -> dict[str, Any]:
        sources = sorted({str(record.get("source")) for record in visibility if record.get("source")})
        return {
            "visibilitySource": sources or ["none"],
            "approvedViewPolicyCount": sum(1 for record in visibility if record.get("policy_status") == "approved" and record.get("intent") == "view"),
            "conditions": [record.get("condition_json") or {} for record in visibility],
            "rule": "目录专题只解释可见与申请边界；实际资源申请仍走 application.resource.submit/application.resource.review。",
        }

    def _topic_catalog_projection_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        store = self._state_store.database_store
        for item in items:
            if item.get("ref_type") != "catalog_entry":
                continue
            catalog_code = str(item.get("ref_id"))
            status = self._catalog_entry_status(catalog_code)
            field_count = 0
            resource_count = 0
            if store is not None:
                assets = [asset for asset in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID) if asset.catalog_code == catalog_code]
                resource_codes = {asset.resource_code for asset in assets}
                catalog_field_count = len(store.catalog_repo.list_items(catalog_code, tenant_id=_DEFAULT_TENANT_ID))
                mapping_field_count = len(store.metadata_evidence_repo.list_schema_mappings(catalog_code=catalog_code, tenant_id=_DEFAULT_TENANT_ID))
                snapshot_field_count = sum(
                    len(store.metadata_evidence_repo.list_schema_snapshots(resource_code=resource_code, tenant_id=_DEFAULT_TENANT_ID))
                    for resource_code in resource_codes
                )
                field_count = catalog_field_count + mapping_field_count + snapshot_field_count
                resource_count = len(assets)
            out.append(
                item | {
                    "catalog_code": catalog_code,
                    "lifecycle_status": status,
                    "visible": status == "active" and field_count > 0,
                    "field_count": field_count,
                    "resource_count": resource_count,
                    "hidden_reason": None if status == "active" and field_count > 0 else ("catalog_not_active" if status != "active" else "resource_binding_has_no_visible_fields"),
                }
            )
        return out

    def _topic_authorization_summary(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        store = self._state_store.database_store
        catalog_codes = {str(item.get("ref_id")) for item in items if item.get("ref_type") == "catalog_entry" and item.get("ref_id")}
        resource_codes: set[str] = set()
        effective_grants = []
        pending_grants = []
        if store is not None:
            for asset in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID):
                if asset.catalog_code in catalog_codes:
                    resource_codes.add(asset.resource_code)
            for delivery in store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID):
                payload = delivery.payload_json if isinstance(delivery.payload_json, dict) else {}
                if payload.get("resource_id") not in resource_codes:
                    continue
                grant = payload.get("access_grant") or {}
                row = {
                    "delivery_code": delivery.delivery_code,
                    "resource_code": payload.get("resource_id"),
                    "state": delivery.state,
                    "channel": delivery.channel,
                    "access_grant": _mask(copy.deepcopy(grant)),
                }
                if delivery.state == "granted" and grant:
                    effective_grants.append(row)
                else:
                    pending_grants.append(row)
        return {
            "effectiveGrantCount": len(effective_grants),
            "pendingOrInactiveGrantCount": len(pending_grants),
            "resourceCodes": sorted(resource_codes),
            "effectiveGrants": effective_grants,
            "pendingOrInactiveGrants": pending_grants,
            "renewalBoundary": "真实 data_apply_renewal 无行；不伪造续期成功路径。",
        }

    def _catalog_entry_status(self, catalog_code: Any) -> str | None:
        store = self._state_store.database_store
        if store is None or not catalog_code:
            return None
        record = store.catalog_repo.get_entry(str(catalog_code), tenant_id=_DEFAULT_TENANT_ID)
        return record.lifecycle_status if record is not None else None

    def _catalog_is_discoverable(self, record: Any, store: Any) -> bool:
        if record.lifecycle_status != "active":
            return False
        projections = self._catalog_topic_projection_cards(record.catalog_code, store)
        return any(projection.get("projectionStatus") == "projected" for projection in projections) or not projections

    def _catalog_topic_projection_cards(self, catalog_code: str, store: Any) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for package in self._topic_package_repo().list_packages(tenant_id=_DEFAULT_TENANT_ID):
            items = [topic_package_ser.topic_item_to_dict(record) for record in self._topic_package_repo().list_items(package.package_code, tenant_id=_DEFAULT_TENANT_ID)]
            if not any(item.get("ref_type") == "catalog_entry" and item.get("ref_id") == catalog_code for item in items):
                continue
            visibility = [topic_package_ser.topic_visibility_to_dict(record) for record in self._topic_package_repo().list_visibility(package.package_code, tenant_id=_DEFAULT_TENANT_ID)]
            summary = self._topic_projection_summary(package, items, visibility)
            cards.append({"package_code": package.package_code, "title": package.title, "projectionStatus": summary["projectionStatus"], "visibleOrgCount": summary["visibleOrgCount"], "projectionFailureReasons": summary["projectionFailureReasons"]})
        return cards

    def _adapter_operation_from_skill(self, skill_id: str, payload: dict[str, Any]) -> tuple[str, str, str]:
        if payload.get("adapter_slug") or payload.get("operation"):
            return str(payload.get("adapter_slug", skill_id.rsplit(".", 1)[0])), str(payload.get("operation", skill_id.rsplit(".", 1)[1])), str(payload.get("direction", "inbound"))
        if skill_id.startswith("adapter.cascade"):
            operation = "replay" if skill_id.endswith("replay") else "consume"
            return "cascade", operation, str(payload.get("direction", "inbound"))
        if skill_id.startswith("standard.asset"):
            return "standard_asset", skill_id.rsplit(".", 1)[1], str(payload.get("direction", "inbound"))
        if skill_id.startswith("security.scan"):
            return "security_scan", "result_sync", str(payload.get("direction", "inbound"))
        if skill_id.startswith("risk.event"):
            return "risk_event", "ingest", str(payload.get("direction", "inbound"))
        if skill_id.startswith("compliance.signal"):
            return "compliance_signal", "ingest", str(payload.get("direction", "inbound"))
        parts = skill_id.split(".")
        operation = parts[-1]
        if operation in {"pull", "receive", "reconcile", "sync"}:
            direction = "inbound" if operation in {"pull", "receive"} else str(payload.get("direction", "inbound"))
        else:
            direction = str(payload.get("direction", "outbound"))
        return "national", operation, direction

    def _aggregate_type_from_skill(self, skill_id: str) -> str:
        for value in ("catalog", "resource", "application", "delivery", "objection", "topic"):
            if f".{value}." in skill_id:
                return "topic_package" if value == "topic" else value
        return "external"

    def _adapter_idempotency_key(self, skill_id: str, payload: dict[str, Any]) -> str:
        return ":".join(
            [
                skill_id,
                str(payload.get("local_aggregate_type") or self._aggregate_type_from_skill(skill_id)),
                str(payload.get("local_aggregate_id") or payload.get("external_object_id") or payload.get("source_ref") or "pending"),
                str(payload.get("external_system") or "national_platform"),
            ]
        )


    def list_requests(self) -> list[dict[str, Any]]:
        items = copy.deepcopy(self._snapshot["requests"])
        store = self._state_store.database_store
        if store is None:
            return items
        # D-9 perf: prefetch four indices once, share via context to eliminate
        # ~5N full-table scans inside _application_record_to_request helpers.
        all_records = list(store.application_repo.list_records(tenant_id=_DEFAULT_TENANT_ID))
        records = {record.application_code: record for record in all_records}
        context = self._build_request_batch_context(store, all_records)
        for item in items:
            record = records.pop(item["id"], None)
            if record is not None:
                self._overlay_application_record(item, record, store, context=context)
        for record in records.values():
            if (record.payload_json or {}).get("kind") == "apply":
                items.append(self._application_record_to_request(record, store, context=context))
        return items

    def _build_request_batch_context(self, store: Any, application_records: list[Any]) -> _RequestBatchContext:
        """Prefetch four indices and a resource cache for list_requests (D-9).

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

    def _audit_event_target(self, item: Any) -> str:
        payload = item.payload_json if isinstance(item.payload_json, dict) else {}
        target = self._audit_target_from_payload(item.request_id, payload)
        decision = payload.get("decision")
        return f"{target}:{decision}" if decision else target

    def list_delivery_tasks(self) -> list[dict[str, Any]]:
        tasks = copy.deepcopy(self._snapshot["delivery_tasks"])
        store = self._state_store.database_store
        if store is None:
            return tasks
        records = {record.delivery_code: record for record in store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID)}
        receipts = {
            task_id: self.get_delivery_task(task_id).get("receipts", [])
            for task_id in [item["id"] for item in tasks]
        }
        for task in tasks:
            record = records.pop(task["id"], None)
            if record is not None:
                task["status"] = record.state
                task["repository"] = {
                    "deliveryCode": record.delivery_code,
                    "applicationCode": record.application_code,
                    "channel": record.channel,
                }
                task["receipts"] = receipts.get(task["id"], [])
        for record in records.values():
            task = self._delivery_task_from_record(record.delivery_code, store)
            if task is not None:
                tasks.append(task)
        return tasks

    def _provider_primary_resource_id(self) -> str | None:
        provider = self._snapshot.get("provider", {})
        resources = provider.get("resources", []) if isinstance(provider, dict) else []
        for item in resources:
            if isinstance(item, dict) and item.get("id"):
                return str(item["id"])
        return None

    def _provider_focus_delivery(self) -> dict[str, Any]:
        tasks = self.list_delivery_tasks()
        for item in tasks:
            backflow = item.get("backflow", {}) if isinstance(item, dict) else {}
            if isinstance(backflow, dict) and backflow.get("candidateFields"):
                return self.get_delivery_task(item["id"])
        if tasks:
            return self.get_delivery_task(tasks[0]["id"])
        return {}

    def _overlay_application_record(
        self,
        request: dict[str, Any],
        record: Any,
        store: Any,
        *,
        context: _RequestBatchContext | None = None,
    ) -> None:
        enriched = self._application_record_to_request(record, store, context=context)
        request.update(enriched)

    def _request_from_application_record(self, request_id: str, store: Any) -> dict[str, Any] | None:
        record = next((item for item in store.application_repo.list_records(tenant_id=_DEFAULT_TENANT_ID) if item.application_code == request_id), None)
        return self._application_record_to_request(record, store) if record is not None else None

    def _application_record_to_request(
        self,
        record: Any,
        store: Any,
        *,
        context: _RequestBatchContext | None = None,
    ) -> dict[str, Any]:
        payload = _mask(copy.deepcopy(record.payload_json or {}))
        resource_id = str(payload.get("resourceId") or payload.get("resource_id") or "")
        catalog_id = str(payload.get("catalog_id") or "")
        try:
            if context is not None and resource_id:
                cached = context.resource_cache.get(resource_id)
                if cached is None:
                    cached = self.get_resource(resource_id, context=context)
                    context.resource_cache[resource_id] = cached
                resource = cached
            else:
                resource = self.get_resource(resource_id) if resource_id else {}
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
        delivery = self._delivery_task_from_record(record.application_code, store, context=context)
        legacy_mappings = self._legacy_mapping_refs(store, "application_record", record.application_code, context=context)
        legacy_mappings.extend(self._legacy_mapping_refs(store, "DeliveryTaskRecord", record.application_code, context=context))
        source_evidence = self._application_source_evidence(resource, requested_items)
        historical_context = self._application_history_context(record, store, resource_id, catalog_code, context=context)
        quality_evidence = self._application_quality_evidence(store, resource, catalog_code, resource_id, context=context)
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
            "expectedBy": self._delivery_due_hint(delivery),
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
        request["statusTimeline"] = self._request_status_timeline(request, delivery)
        return request

    def _delivery_task_from_record(
        self,
        request_id: str,
        store: Any,
        *,
        context: _RequestBatchContext | None = None,
    ) -> dict[str, Any] | None:
        if context is not None:
            record = context.delivery_by_appcode.get(request_id)
        else:
            record = next((item for item in store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID) if item.delivery_code == request_id or item.application_code == request_id), None)
        if record is None:
            return None
        payload = record.payload_json or {}
        grant = _mask(copy.deepcopy(payload.get("access_grant") or {}))
        return {
            "id": record.delivery_code,
            "requestId": record.application_code,
            "name": payload.get("resource_name") or f"{record.delivery_code} 交付任务",
            "channel": record.channel,
            "status": record.state,
            "owner": "审批承接 → 交付执行",
            "updatedAt": record.updated_at.isoformat(),
            "note": "真实旧平台授权导入生成的交付边界。",
            "history": [
                {"time": record.created_at.strftime("%m-%d %H:%M"), "state": record.state, "detail": "授权边界已从 data_apply_authrization 导入。"}
            ],
            "aiSummary": {
                "summary": "已导入真实旧平台授权边界，交付侧按字段范围、频次和授权期回放。",
                "nextAction": "核对交付范围和续期缺口，不新增超出审批意见的授权。",
                "cause": "授权来自 data_apply_authrization，并可回指 legacy_object_mapping。",
                "impact": "通过、退回或驳回都能在审计链路中追溯到责任节点。",
            },
            "backflow": {
                "candidateObject": payload.get("resource_name") or record.delivery_code,
                "candidateFields": [],
                "status": "不适用",
                "note": "本任务来自既有授权回放；不把无真实续期行伪造成回流或续期成功。",
            },
            "accessGrantSnapshot": grant,
            "authorizationBoundary": self._authorization_boundary(grant),
            "r2Review": _mask(copy.deepcopy(payload.get("r2_review") or {})),
            "grantBoundary": _mask(copy.deepcopy(payload.get("grant_boundary") or {})),
            "supplementBoundary": _mask(copy.deepcopy(payload.get("supplement_boundary") or {})),
            "nonGrantBoundary": _mask(copy.deepcopy(payload.get("non_grant_boundary") or {})),
            "renewalBoundary": payload.get("renewal_boundary") or "真实 data_apply_renewal 无行；不伪造续期成功路径。",
            "repository": {"delivery_code": record.delivery_code, "application_code": record.application_code, "channel": record.channel},
        }

    def _delivery_grant_evidence(self, delivery: dict[str, Any] | None) -> dict[str, Any]:
        if not delivery:
            return {"state": "pending", "accessGrant": {}}
        return {"state": delivery.get("status"), "accessGrant": copy.deepcopy(delivery.get("accessGrantSnapshot") or {})}

    def _authorization_boundary(self, grant: dict[str, Any]) -> dict[str, Any]:
        return {
            "limitDays": grant.get("limit_day"),
            "resourceType": grant.get("res_type"),
            "applyStatus": grant.get("apply_status"),
            "renewalSourceRows": 0,
            "renewalPolicy": "真实 data_apply_renewal 无行；不伪造续期成功路径。",
        }

    def _application_history_context(
        self,
        record: Any,
        store: Any,
        resource_id: str,
        catalog_code: str,
        *,
        context: _RequestBatchContext | None = None,
    ) -> dict[str, Any]:
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

    def _application_quality_evidence(
        self,
        store: Any,
        resource: dict[str, Any],
        catalog_code: str,
        resource_id: str,
        *,
        context: _RequestBatchContext | None = None,
    ) -> dict[str, Any]:
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

    def _mask_actor_payload(self, value: Any) -> Any:
        return apply_field_masks(
            value,
            role=_DEFAULT_MASK_ROLE,
            field_policy={"user_name": "name", "approve_person": "name", "handler_name": "name"},
        )

    def _delivery_due_hint(self, delivery: dict[str, Any] | None) -> str:
        grant = (delivery or {}).get("accessGrantSnapshot") or {}
        limit_day = grant.get("limit_day")
        return f"授权 {limit_day} 天内有效" if limit_day else "按审批授权边界执行"

    def _approval_recommendation(self, approval: dict[str, Any], request: dict[str, Any], delivery: dict[str, Any] | None) -> dict[str, Any]:
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

    def _approval_business_defaults(self, request: dict[str, Any], delivery: dict[str, Any] | None) -> dict[str, Any]:
        recommendation = self._approval_recommendation({}, request, delivery)
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

    def _record_delivery_attempt(self, payload: dict[str, Any], skill_id: str, state: str, attempt_kind: str) -> dict[str, Any]:
        role = str(payload.get("role", self._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        task_id = str(payload["task_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task = self._delivery_by_id(task_id)
            attempt = self._delivery_repo().upsert_attempt({"attempt_code": payload.get("attempt_id") or f"{task_id}:{attempt_kind}:{audit_id}", "delivery_code": task_id, "subscription_code": payload.get("subscription_id"), "attempt_kind": attempt_kind, "state": state, "executor_ref": payload.get("executor_ref"), "evidence_ref": audit_id, "payload_json": payload.get("plan") or payload})
            task["updatedAt"] = clock.now_datetime()
            task.setdefault("history", []).append({"time": clock.now_short_time(), "state": f"交换交付{state}", "detail": str(payload.get("reason") or payload.get("mode") or attempt_kind)})
            self._delivery_repo().add_execution_evidence({"evidence_ref": audit_id, "delivery_code": task_id, "attempt_code": attempt.attempt_code, "executor_kind": "builtin_exchange", "executor_ref": payload.get("executor_ref"), "evidence_kind": attempt_kind, "result_status": state, "payload_json": payload})
            self._delivery_repo().upsert_exchange_metric({"metric_scope": "delivery", "delivery_code": task_id, "resource_code": payload.get("resource_id") or task.get("resourceId"), "subscription_code": payload.get("subscription_id"), "status": state, "success_count": 1 if state in {"published", "running", "planned"} else 0, "failed_count": 1 if state == "stopped" else 0, "summary_json": {"skill_id": skill_id, "state": state}})
            self._append_audit_feed(skill_id, task_id, "ok", actor)
            return {"task_id": task_id, "attempt_code": attempt.attempt_code, "state": attempt.state, "audit_id": audit_id}

        return self._mutate(skill_id, role, confirmed, payload, mutation)

    def _delivery_repo(self) -> DeliveryRepository:
        store = self._state_store.database_store
        return store.delivery_repo if store is not None else DeliveryRepository()

    def _discovery_summary(self, query: str, resources: list[dict[str, Any]]) -> dict[str, Any]:
        base = copy.deepcopy(self._snapshot["discovery"]["aiCopilot"])
        if resources and query:
            base["summary"] = f"已按“{query}”找到 {len(resources)} 条可复用目录或基础要素。先看字段、共享条件和字段证据；仍缺的字段再进入最小申请。"
            base["missingQuestions"] = ["是否限定使用区域或时间窗？", "本次只需要哪些字段，哪些字段属于缺口？"]
            base["nextActions"] = ["打开资源详情", "核对字段口径", "整理最小申请字段"]
            base["evidence"] = [item.get("name", item.get("id", "")) for item in resources[:3]]
        return base

    def _api_payload(self, payload: dict[str, Any], *, default_status: str) -> dict[str, Any]:
        resource_code = str(payload["resource_code"])
        return {
            "resource_code": resource_code,
            "resource_kind": "api",
            "title": str(payload.get("title", resource_code)),
            "lifecycle_status": str(payload.get("lifecycle_status", default_status)),
            "owner_org_id": payload.get("owner_org_id"),
            "owner_org_snapshot_json": self._safe_json(payload.get("owner_org_snapshot_json") or {}),
            "region_code": payload.get("region_code"),
            "catalog_code": payload.get("catalog_code"),
            "access_policy_json": self._safe_json(payload.get("access_policy_json") or {}),
            "qos_policy_json": self._safe_json(payload.get("qos_policy_json") or {}),
            "source_ref": payload.get("source_ref"),
            "summary_json": self._safe_json(payload.get("summary_json") or {"title": payload.get("title", resource_code)}),
        }

    def _upsert_api_resource(self, resource: dict[str, Any]) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            resources = self._snapshot.setdefault("api_resources", [])
            current = next((item for item in resources if item["resource_code"] == resource["resource_code"]), None)
            if current is None:
                current = copy.deepcopy(resource)
                current.setdefault("channel_bindings", [])
                resources.append(current)
            else:
                bindings = current.get("channel_bindings", [])
                current.update(copy.deepcopy(resource))
                current.setdefault("channel_bindings", bindings)
            return copy.deepcopy(current)
        return resource_api_ser.resource_asset_to_dict(store.resource_api_repo.upsert_asset(resource))

    def _upsert_api_binding(self, binding: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "binding_code": str(binding["binding_code"]),
            "resource_code": str(binding["resource_code"]),
            "channel_kind": str(binding.get("channel_kind", "api_gateway")),
            "route_ref": binding.get("route_ref"),
            "endpoint_ref": self._safe_json(binding.get("endpoint_ref", {})),
            "schema_ref": self._safe_json(binding.get("schema_ref", {})),
            "auth_ref": binding.get("auth_ref"),
            "request_schema_json": self._safe_json(binding.get("request_schema_json", {})),
            "response_schema_json": self._safe_json(binding.get("response_schema_json", {})),
            "gateway_policy_json": self._safe_json(binding.get("gateway_policy_json", {})),
            "lifecycle_status": str(binding.get("lifecycle_status", "draft")),
            "source_ref": binding.get("source_ref"),
        }
        store = self._state_store.database_store
        if store is None:
            resources = self._snapshot.setdefault("api_resources", [])
            resource = next((item for item in resources if item["resource_code"] == payload["resource_code"]), None)
            if resource is None:
                raise NotFoundError(payload["resource_code"])
            bindings = resource.setdefault("channel_bindings", [])
            current = next((item for item in bindings if item["binding_code"] == payload["binding_code"]), None)
            if current is None:
                current = copy.deepcopy(payload)
                bindings.append(current)
            else:
                current.update(copy.deepcopy(payload))
            return copy.deepcopy(current)
        return resource_api_ser.binding_to_dict(store.resource_api_repo.upsert_binding(payload))

    def _find_api_resource(self, resource_code: str) -> dict[str, Any] | None:
        store = self._state_store.database_store
        if store is None:
            item = next((item for item in self._snapshot.get("api_resources", []) if item["resource_code"] == resource_code), None)
            return copy.deepcopy(item) if item is not None else None
        record = store.resource_api_repo.get_asset(resource_code)
        return resource_api_ser.resource_asset_to_dict(record) if record is not None else None

    def _find_api_binding(self, binding_code: str) -> dict[str, Any] | None:
        store = self._state_store.database_store
        if store is None:
            for resource in self._snapshot.get("api_resources", []):
                binding = next((item for item in resource.get("channel_bindings", []) if item["binding_code"] == binding_code), None)
                if binding is not None:
                    return copy.deepcopy(binding)
            return None
        record = store.resource_api_repo.get_binding(binding_code)
        return resource_api_ser.binding_to_dict(record) if record is not None else None

    def _metric_summary(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "invokeCount": sum(int(item.get("invoke_count", 0)) for item in metrics),
            "successCount": sum(int(item.get("success_count", 0)) for item in metrics),
            "failedCount": sum(int(item.get("failed_count", item.get("failure_count", 0))) for item in metrics),
            "errorCount": sum(int(item.get("error_count", 0)) for item in metrics),
        }

    def _exchange_metric_summary(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "exchangeCount": sum(int(item.get("exchange_count", 0)) for item in metrics),
            "successCount": sum(int(item.get("success_count", 0)) for item in metrics),
            "failedCount": sum(int(item.get("failed_count", 0)) for item in metrics),
            "recordCount": sum(int(item.get("record_count", 0)) for item in metrics),
        }

    def _safe_json(self, value: dict[str, Any]) -> dict[str, Any]:
        return safe_json(value)

    def _decode_iaf_claims(self, iaf_claims: Any) -> dict[str, Any]:
        if isinstance(iaf_claims, dict):
            return self._safe_json(iaf_claims)
        token = str(iaf_claims or "")
        if not token:
            raise InvalidTokenError("missing token claims")
        if token.count(".") != 2:
            raise InvalidTokenError("invalid jwt format")
        payload_part = token.split(".")[1]
        payload_part += "=" * ((4 - len(payload_part) % 4) % 4)
        try:
            raw = base64.urlsafe_b64decode(payload_part.encode("utf-8")).decode("utf-8")
            payload = json.loads(raw)
        except Exception as exc:
            raise InvalidTokenError("invalid jwt payload") from exc
        if not isinstance(payload, dict):
            raise InvalidTokenError("invalid jwt claims type")
        return self._safe_json(payload)

    def _validate_iaf_claims(self, claims: dict[str, Any], *, expected_state: Any = None, expected_nonce: Any = None) -> None:
        now_ts = int(datetime.now(UTC).timestamp())
        exp = int(claims.get("exp") or 0)
        if exp <= now_ts:
            raise InvalidTokenError("token expired")
        expected_issuer = _expected_iaf_issuer()
        if expected_issuer and str(claims.get("iss") or "") != expected_issuer:
            raise InvalidTokenError("issuer mismatch")

        audience = claims.get("aud")
        if isinstance(audience, str):
            audience_set = {audience}
        elif isinstance(audience, list):
            audience_set = {str(item) for item in audience}
        else:
            audience_set = set()
        expected_audience = _expected_iaf_audience()
        client_id = str(claims.get("client_id") or claims.get("azp") or "")
        if expected_audience and expected_audience not in audience_set and client_id != expected_audience:
            raise InvalidTokenError("audience mismatch")

        if expected_state is not None and str(claims.get("state") or "") != str(expected_state):
            raise InvalidTokenError("state mismatch")
        if expected_nonce is not None and str(claims.get("nonce") or "") != str(expected_nonce):
            raise InvalidTokenError("nonce mismatch")

    def _build_actor_projection_from_claims(
        self,
        *,
        claims: Any,
        expected_state: Any = None,
        expected_nonce: Any = None,
        tenant_id: str,
        org_code: Any = None,
        fallback_roles: list[Any] | tuple[Any, ...] | None = None,
        display_name: Any = None,
    ) -> dict[str, Any]:
        claim_payload = self._decode_iaf_claims(claims)
        self._validate_iaf_claims(claim_payload, expected_state=expected_state, expected_nonce=expected_nonce)

        subject = str(claim_payload.get("sub") or "")
        if not subject:
            raise InvalidTokenError("missing sub")

        resource_roles = claim_payload.get("resource_access") or {}
        service_roles = resource_roles.get(_expected_iaf_audience(), {}) if isinstance(resource_roles, dict) else {}
        iam_roles = [str(item) for item in (service_roles.get("roles") if isinstance(service_roles, dict) else []) or []]
        realm_access = claim_payload.get("realm_access") or {}
        if isinstance(realm_access, dict):
            realm_role_source = realm_access.get("roles") or []
        elif isinstance(realm_access, list):
            realm_role_source = realm_access
        else:
            realm_role_source = []
        realm_roles = [str(item) for item in realm_role_source]
        from zw_brain.domain.policy import filter_product_role_codes

        merged_roles = filter_product_role_codes(sorted({*iam_roles, *realm_roles, *[str(item) for item in (fallback_roles or [])]}))

        return {
            "tenant_id": tenant_id,
            "external_actor_id": subject,
            "display_name": str(display_name or claim_payload.get("preferred_username") or subject),
            "org_code": org_code,
            "role_codes": merged_roles,
            "status": "active",
            "source_ref": "iaf:claims",
            "profile_json": {
                "username": claim_payload.get("preferred_username"),
                "project_id": claim_payload.get("project_id"),
                "project": claim_payload.get("project"),
                "iam_role_codes": iam_roles,
                "realm_roles": realm_roles,
                "account_admin": "ACCOUNT_ADMIN" in realm_roles,
                "email": claim_payload.get("email"),
                "phone": claim_payload.get("phone"),
            },
            "iaf_claims": claim_payload,
        }

    def _actor_snapshot_from_projection(self, item: Any, *, claims: dict[str, Any]) -> dict[str, Any]:
        from zw_brain.shared.session_context import apply_runtime_context, contexts_from_bindings

        profile = item.profile_json if isinstance(item.profile_json, dict) else {}
        role_codes = [str(role) for role in item.role_codes_json or []]
        snapshot = {
            "subject": item.external_actor_id,
            "actor": f"user:iaf:{item.external_actor_id}",
            "tenant_id": item.tenant_id,
            "display_name": item.display_name,
            "org_code": item.org_code,
            "status": item.status,
            "role_codes": role_codes,
            "iam_role_codes": [str(role) for role in profile.get("iam_role_codes") or []],
            "account_flags": {"account_admin": bool(profile.get("account_admin"))},
            "issuer": claims.get("iss"),
            "audience": claims.get("aud"),
            "project_id": claims.get("project_id") or profile.get("project_id"),
            "project": claims.get("project") or profile.get("project"),
            "issued_at": datetime.now(UTC).isoformat(),
        }
        bindings = self._governance_projection_repo().list_active_actor_contexts(
            tenant_id=str(item.tenant_id),
            external_actor_id=str(item.external_actor_id),
        )
        contexts = contexts_from_bindings(bindings, fallback_org_code=str(item.org_code or "") or None)
        preferred_org = str(claims.get("org_code") or item.org_code or "") or None
        return apply_runtime_context(snapshot, contexts, preferred_org_code=preferred_org)

    def enrich_actor_snapshot_for_session(self, actor_snapshot: dict[str, Any]) -> dict[str, Any]:
        from zw_brain.shared.session_context import apply_runtime_context, contexts_from_bindings

        subject = str(actor_snapshot.get("subject") or "")
        tenant_id = str(actor_snapshot.get("tenant_id") or "sd-default")
        if not subject:
            return actor_snapshot
        bindings = self._governance_projection_repo().list_active_actor_contexts(tenant_id=tenant_id, external_actor_id=subject)
        contexts = contexts_from_bindings(bindings, fallback_org_code=str(actor_snapshot.get("org_code") or "") or None)
        return apply_runtime_context(actor_snapshot, contexts, preferred_org_code=str(actor_snapshot.get("org_code") or "") or None)

    def _catalog_record_to_card_dict(self, record: Any) -> dict[str, Any]:
        summary = _mask(copy.deepcopy(record.summary_json or {}))
        body = self._catalog_summary_body(summary)
        provider = body.get("org_name") or body.get("imported_by_org_name") or record.owner_org_id or summary.get("provider", "—")
        desc = body.get("description") or body.get("source_service_item_catalog_name") or summary.get("desc") or record.title
        access_policy = self._catalog_access_policy(body, record)
        # Legacy migration occasionally carries an updated_at that is in the future
        # (planning-date semantics in dsp_catalog). Clamp to today so the customer
        # never sees "更新于 2026-08-19" on a UI rendered 2026-05-22.
        raw_updated = summary.get("updatedAt") or summary.get("updated_at") or summary.get("update_time") or record.updated_at.date().isoformat()
        today_iso = clock.now_date()
        if str(raw_updated)[:10] > today_iso:
            raw_updated = today_iso
        return {
            "id": record.catalog_code,
            "name": record.title,
            "status": record.lifecycle_status,
            "provider": provider,
            "zone": summary.get("zone") or self._region_label(record.region_code) or "官方目录推荐",
            "updatedAt": str(raw_updated),
            "coverage": summary.get("coverage", "真实旧平台目录"),
            "score": int(summary.get("score", 80 if record.catalog_code.startswith("basic-elem:") else 75)),
            "desc": str(desc),
            "fields": list(summary.get("fields", [])),
            "explain": list(summary.get("explain", ["已匹配真实旧平台目录", f"目录状态：{record.lifecycle_status}"])),
            "nextHints": list(summary.get("nextHints", ["先看字段证据", "只申请必要字段"])),
            "kind": summary.get("kind", "catalog_entry"),
            "regionCode": record.region_code,
            "accessPolicy": access_policy,
            "sensitivePolicy": self._catalog_sensitive_policy([]),
            "reuseGapHint": self._reuse_gap_hint([], []),
            "repository": {
                "catalogCode": record.catalog_code,
                "lifecycleStatus": record.lifecycle_status,
                "ownerOrgId": record.owner_org_id,
                "regionCode": record.region_code,
            },
        }

    def _enrich_catalog_detail(self, detail: dict[str, Any], record: Any, store: Any, *, focused_resource_code: str | None = None, context: _RequestBatchContext | None = None) -> None:
        catalog_code = record.catalog_code
        fields = self._catalog_field_dicts(catalog_code, store, context=context)
        if context is not None:
            mapping_records = list(context.schema_mappings_by_catalog.get(catalog_code, []))
        else:
            mapping_records = list(store.metadata_evidence_repo.list_schema_mappings(catalog_code=catalog_code, tenant_id=_DEFAULT_TENANT_ID))
        if focused_resource_code:
            # Focused-resource lookup is a tiny set; one filtered SQL is cheap.
            mapping_by_code = {item.mapping_code: item for item in mapping_records}
            for item in store.metadata_evidence_repo.list_schema_mappings(resource_code=focused_resource_code, tenant_id=_DEFAULT_TENANT_ID):
                mapping_by_code[item.mapping_code] = item
            mapping_records = list(mapping_by_code.values())
        mappings = self._mapping_diagnostics(mapping_records, store=store, context=context)
        if focused_resource_code:
            mappings["items"] = [item for item in mappings["items"] if item["resource_code"] == focused_resource_code]
            mappings["summary"] = self._mapping_summary(mappings["items"])
        if context is not None:
            asset_records = context.resource_assets_by_catalog.get(catalog_code, [])
        else:
            asset_records = [item for item in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID) if item.catalog_code == catalog_code]
        resources = [
            resource_api_ser.resource_asset_to_dict(item)
            for item in asset_records
            if not focused_resource_code or item.resource_code == focused_resource_code
        ]
        resource_codes = {item["resource_code"] for item in resources} | {item["resource_code"] for item in mappings["items"]}
        if context is not None:
            snapshot_records = [
                snapshot
                for code in resource_codes
                for snapshot in context.schema_snapshots_by_resource.get(code, [])
            ]
        else:
            snapshot_records = [item for item in store.metadata_evidence_repo.list_schema_snapshots(tenant_id=_DEFAULT_TENANT_ID) if item.resource_code in resource_codes]
        snapshots = [metadata_ser.schema_snapshot_to_dict(item) for item in snapshot_records]
        legacy_refs = self._legacy_mapping_refs(store, "catalog_entry", catalog_code, context=context)
        legacy_refs.extend(self._legacy_mapping_refs(store, "catalog_item", [field["item_code"] for field in fields], context=context))
        legacy_refs.extend(self._legacy_mapping_refs(store, "resource_schema_mapping", [item["mapping_code"] for item in mappings["items"]], context=context))
        legacy_refs.extend(self._legacy_mapping_refs(store, "resource_asset", list(resource_codes), context=context))
        detail["fields"] = [field["title"] for field in fields] or detail.get("fields", [])
        detail["catalogFields"] = fields
        detail["fieldBindings"] = mappings["items"]
        detail["fieldBindingSummary"] = mappings["summary"]
        detail["resourceAssets"] = resources
        detail["schemaSnapshots"] = snapshots
        detail["legacyMappings"] = legacy_refs
        detail["accessPolicy"] = self._catalog_access_policy(self._catalog_summary_body(_mask(copy.deepcopy(record.summary_json or {}))), record)
        detail["sensitivePolicy"] = self._catalog_sensitive_policy(fields)
        detail["reuseGapHint"] = self._reuse_gap_hint(fields, mappings["items"])
        detail["repository"] = detail.get("repository", {}) | {
            "catalogCode": catalog_code,
            "canonicalType": "catalog_entry",
            "legacyMappingCount": len(legacy_refs),
            "resourceCount": len(resources),
            "schemaSnapshotCount": len(snapshots),
        }
        detail["explain"] = self._catalog_explain(detail, fields, mappings["summary"])
        detail["nextHints"] = self._catalog_next_hints(fields, mappings["summary"])

    def _catalog_field_dicts(self, catalog_code: str, store: Any, *, context: _RequestBatchContext | None = None) -> list[dict[str, Any]]:
        source = context.catalog_items_by_catalog.get(catalog_code, []) if context is not None else store.catalog_repo.list_items(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        return [
            {
                "item_code": item.item_code,
                "catalog_code": item.catalog_code,
                "title": item.title,
                "item_kind": item.item_kind,
                "display_order": item.display_order,
                "summary_json": _mask(copy.deepcopy(item.summary_json or {})),
                "source_ref": item.source_ref,
            }
            for item in source
        ]

    def _legacy_mapping_refs(
        self,
        store: Any,
        canonical_type: str,
        canonical_ref: str | list[str],
        *,
        context: _RequestBatchContext | None = None,
    ) -> list[dict[str, Any]]:
        refs = canonical_ref if isinstance(canonical_ref, list) else [canonical_ref]
        rows: list[dict[str, Any]] = []
        for ref in refs:
            if context is not None:
                items = context.legacy_mappings_by_ref.get((canonical_type, str(ref)), [])
            else:
                items = store.legacy_mapping_repo.list_mappings(
                    canonical_type=canonical_type,
                    canonical_ref=str(ref),
                    tenant_id=_DEFAULT_TENANT_ID,
                )
            for item in items:
                rows.append(
                    {
                        "legacy_system": item.legacy_system,
                        "legacy_object_type": item.legacy_object_type,
                        "legacy_object_ref": item.legacy_object_ref,
                        "canonical_type": item.canonical_type,
                        "canonical_ref": item.canonical_ref,
                        "source_ref": item.source_ref,
                        "mapping_status": item.mapping_status,
                    }
                )
        return rows

    def _catalog_summary_body(self, summary: dict[str, Any]) -> dict[str, Any]:
        nested = summary.get("summary")
        return nested if isinstance(nested, dict) else summary

    def _catalog_access_policy(self, summary: dict[str, Any], record: Any) -> dict[str, Any]:
        return {
            "shareType": summary.get("shared_type"),
            "shareWay": summary.get("shared_way"),
            "shareCondition": summary.get("shared_condition") or "未登记附加共享条件，按受控申请审批。",
            "openType": summary.get("open_type"),
            "openCondition": summary.get("open_condition") or "未登记公开条件。",
            "regionCode": record.region_code,
            "provider": summary.get("org_name") or summary.get("imported_by_org_name") or record.owner_org_id,
        }

    def _catalog_sensitive_policy(self, fields: list[dict[str, Any]]) -> dict[str, Any]:
        levels = sorted({str((field.get("summary_json") or {}).get("sensitive_level")) for field in fields if (field.get("summary_json") or {}).get("sensitive_level") not in {None, ""}})
        return {
            "fieldSensitiveLevels": levels,
            "display": "查询与导出侧按字段敏感级别脱敏；申请侧只勾选必要字段。",
            "maskedOnRead": True,
        }

    def _reuse_gap_hint(self, fields: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> dict[str, Any]:
        mapped_codes = {item.get("catalog_item_code") for item in mappings}
        missing = [field["title"] for field in fields if field["item_code"] not in mapped_codes]
        return {
            "reusable": len(mappings) > 0 or len(fields) > 0,
            "readyFieldCount": len(fields) - len(missing),
            "gapFields": missing,
            "message": "已有目录字段和资源绑定证据，可先复用；未绑定字段作为缺口说明进入最小申请。" if missing else "已有字段证据可复用，申请时只选择本次确需字段。",
        }

    def _catalog_explain(self, detail: dict[str, Any], fields: list[dict[str, Any]], mapping_summary: dict[str, Any]) -> list[str]:
        out = ["已命中真实旧平台目录", f"提供方：{detail.get('provider') or '—'}"]
        if fields:
            out.append(f"字段清单 {len(fields)} 项")
        if mapping_summary.get("total"):
            out.append(f"字段绑定证据 {mapping_summary['total']} 条，可回放到 legacy_object_mapping")
        return out

    def _catalog_next_hints(self, fields: list[dict[str, Any]], mapping_summary: dict[str, Any]) -> list[str]:
        hints = ["先看字段口径和敏感级别", "只选择本次确需字段"]
        if not fields or mapping_summary.get("diagnosis") != "ok":
            hints.append("把未绑定字段写入缺口说明")
        return hints

    def _mapping_summary(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        missing = [item for item in items if any(issue["reason"] == "missing_source_schema_ref" for issue in item["diagnosis"]["issues"])]
        conflicts = [item for item in items if any(issue["reason"] == "mapping_conflict" for issue in item["diagnosis"]["issues"])]
        inactive = [item for item in items if item["status"] != "active"]
        return {
            "total": len(items),
            "active": sum(1 for item in items if item["status"] == "active"),
            "missing": len(missing),
            "conflicted": len(conflicts),
            "inactive": len(inactive),
            "diagnosis": "ok" if items and not missing and not conflicts and not inactive else ("missing_mapping" if not items else "attention_required"),
        }

    def _region_label(self, region_code: Any) -> str | None:
        text = str(region_code or "").strip()
        if not text:
            return None
        if text.startswith("370000"):
            return "山东省"
        return text

    def _mapping_diagnostics(self, records: list[Any], *, store: Any | None = None, context: _RequestBatchContext | None = None) -> dict[str, Any]:
        items = [metadata_ser.schema_mapping_to_dict(item) for item in records]
        if store is not None:
            source_column_titles = self._source_column_titles_for_mappings(items, store, context=context)
            catalog_codes = {item["catalog_code"] for item in items}
            fields_by_code = {
                field["item_code"]: field
                for catalog_code in catalog_codes
                for field in self._catalog_field_dicts(catalog_code, store, context=context)
            }
            missing_item_codes = {item["catalog_item_code"] for item in items if item["catalog_item_code"] not in fields_by_code}
            if missing_item_codes:
                if context is not None:
                    source_items = [context.catalog_items_by_item_code[code] for code in missing_item_codes if code in context.catalog_items_by_item_code]
                else:
                    source_items = [item for item in store.catalog_repo.list_items(tenant_id=_DEFAULT_TENANT_ID) if item.item_code in missing_item_codes]
                fields_by_code.update(
                    {
                        item.item_code: {
                            "item_code": item.item_code,
                            "title": item.title,
                            "summary_json": metadata_ser.mask_schema_mapping_payload(copy.deepcopy(item.summary_json or {})),
                        }
                        for item in source_items
                    }
                )
            for item in items:
                source_column = item.get("explain", {}).get("source_column")
                if source_column in source_column_titles:
                    item["source_column_title"] = source_column_titles[source_column]
                    item["explain"]["source_column_id"] = source_column
                    item["explain"]["source_column"] = source_column_titles[source_column]
                    for step in item.get("replay", {}).get("steps", []):
                        if step.get("step") == "source_field":
                            step["ref"] = source_column_titles[source_column]
                            step["source_column_id"] = source_column
                field = fields_by_code.get(item["catalog_item_code"])
                if field:
                    item["catalog_item_title"] = field["title"]
                    item["catalog_item_summary"] = field["summary_json"]
        return {"items": items, "summary": self._mapping_summary(items)}

    def _source_column_titles_for_mappings(self, items: list[dict[str, Any]], store: Any, *, context: _RequestBatchContext | None = None) -> dict[Any, Any]:
        refs = {item.get("explain", {}).get("source_column") for item in items}
        refs.discard(None)
        if not refs:
            return {}
        resource_codes = {item.get("resource_code") for item in items if item.get("resource_code")}
        if context is not None:
            snapshots_iter = [
                snapshot
                for code in resource_codes
                for snapshot in context.schema_snapshots_by_resource.get(code, [])
            ]
        else:
            snapshots_iter = [snapshot for snapshot in store.metadata_evidence_repo.list_schema_snapshots(tenant_id=_DEFAULT_TENANT_ID) if snapshot.resource_code in resource_codes]
        out: dict[Any, Any] = {}
        for snapshot in snapshots_iter:
            schema = snapshot.schema_json if isinstance(snapshot.schema_json, dict) else {}
            for ref_key in ("meta_id", "id", "column_id", "field_id"):
                ref = schema.get(ref_key)
                if ref in refs:
                    out[ref] = schema.get("column_name") or schema.get("name_en") or schema.get("name_cn") or ref
        return out

    def _enrich_provider_resource_asset(self, item: dict[str, Any], store: Any) -> dict[str, Any]:
        resource_code = str(item["resource_code"])
        bindings = [
            resource_api_ser.binding_to_dict(record)
            for record in store.resource_api_repo.list_bindings(resource_code=resource_code, tenant_id=_DEFAULT_TENANT_ID)
        ]
        mappings = store.metadata_evidence_repo.list_schema_mappings(
            resource_code=resource_code,
            include_inactive=True,
            tenant_id=_DEFAULT_TENANT_ID,
        )
        schema_snapshots = [
            metadata_ser.schema_snapshot_to_dict(record)
            for record in store.metadata_evidence_repo.list_schema_snapshots(resource_code=resource_code, tenant_id=_DEFAULT_TENANT_ID)
        ]
        gather_evidence = [
            metadata_ser.gather_evidence_to_dict(record)
            for record in store.metadata_evidence_repo.list_gather_evidence(resource_code=resource_code, tenant_id=_DEFAULT_TENANT_ID)
        ]
        lineage = [
            metadata_ser.lineage_to_dict(record)
            for record in store.metadata_evidence_repo.list_lineage_relations(resource_code=resource_code, tenant_id=_DEFAULT_TENANT_ID)
        ]
        quality = [
            quality_ser.quality_to_dict(record)
            for record in store.metadata_evidence_repo.list_quality_evidence(target_type="resource_asset", target_ref=resource_code, tenant_id=_DEFAULT_TENANT_ID)
        ]
        attempts = [
            delivery_ser.delivery_attempt_to_dict(record)
            for record in store.delivery_repo.list_attempts(delivery_code=f"provider-external:{resource_code}", tenant_id=_DEFAULT_TENANT_ID)
        ]
        execution_evidence = [
            delivery_ser.delivery_evidence_to_dict(record)
            for record in store.delivery_repo.list_execution_evidence(delivery_code=f"provider-external:{resource_code}", tenant_id=_DEFAULT_TENANT_ID)
        ]
        legacy_mappings = [
            {
                "legacy_system": record.legacy_system,
                "legacy_object_type": record.legacy_object_type,
                "legacy_object_ref": record.legacy_object_ref,
                "canonical_type": record.canonical_type,
                "canonical_ref": record.canonical_ref,
                "mapping_status": record.mapping_status,
                "source_ref": record.source_ref,
            }
            for record in store.legacy_mapping_repo.list_mappings(tenant_id=_DEFAULT_TENANT_ID, canonical_ref=resource_code)
        ]
        diagnostics = self._mapping_diagnostics(mappings, store=store)
        return item | {
            "channel_bindings": bindings,
            "schema_snapshots": schema_snapshots,
            "schema_mappings": diagnostics["items"],
            "mapping_summary": diagnostics["summary"],
            "gather_evidence": gather_evidence,
            "lineage_evidence": lineage,
            "quality_evidence": quality,
            "external_execution_tasks": attempts,
            "external_execution_receipts": execution_evidence,
            "legacy_object_mappings": legacy_mappings,
            "provider_diagnostics": self._provider_asset_diagnostics(item, bindings, diagnostics["summary"], schema_snapshots),
        }

    def _provider_asset_diagnostics(
        self,
        item: dict[str, Any],
        bindings: list[dict[str, Any]],
        mapping_summary: dict[str, Any],
        schema_snapshots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        if not bindings:
            issues.append({"stage": "channel", "reason": "missing_channel_binding", "detail": "resource has no channel binding"})
        if mapping_summary.get("diagnosis") != "ok":
            issues.append({"stage": "schema_mapping", "reason": str(mapping_summary.get("diagnosis")), "detail": "catalog item to resource field mapping needs attention"})
        if not schema_snapshots:
            issues.append({"stage": "schema_snapshot", "reason": "missing_schema_snapshot", "detail": "resource has no schema snapshot evidence"})
        if item.get("lifecycle_status") not in {"active", "approved_pending_publish", "pending_review"}:
            issues.append({"stage": "lifecycle", "reason": "not_ready_for_share", "detail": f"resource lifecycle is {item.get('lifecycle_status')}"})
        return {"ok": not issues, "issues": issues}

    def _review_application_record(self, request_id: str, decision: str, role: str, confirmed: bool, skill_id: str) -> dict[str, Any]:
        store = self._state_store.database_store
        if store is None:
            raise NotFoundError(request_id)
        request = self.get_request(request_id)
        delivery = self._delivery_task_from_record(request_id, store)
        if delivery is None:
            raise NotFoundError(request_id)
        existing_review = delivery.get("r2Review") if isinstance(delivery.get("r2Review"), dict) else {}
        if request["status"] != "pending" and existing_review.get("decision"):
            raise InvalidStateError("request is not pending approval")
        reason = self._r2_review_reason(decision, request)
        evidence = self._r2_review_evidence(decision, request, delivery)
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
            snapshot_request = self._maybe_request(request_id)
            if snapshot_request is not None:
                snapshot_request["status"] = result_status
            snapshot_delivery = self._delivery_by_request_id(request_id)
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
            self._append_audit_feed("application.resource.review", f"{request_id}:{decision}", "ok" if decision.startswith("approve") else "warning", actor)
            return {
                "request_id": request_id,
                "status": result_status,
                "decision": decision,
                "reason": reason,
                "evidence": evidence,
                "delivery_state": delivery_state,
            }

        result = self._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": decision, "reason": reason, "evidence": evidence}, mutation)
        # R-006 fix: 凭据签发作为审批之后的独立动作；audit 失败不污染审批 mutation
        if decision in {"approve_reuse", "approve_with_supplement"}:
            self._auto_issue_credential_on_approval(request_id, role, self._actor_for_role(role))
        return result

    def _r2_review_reason(self, decision: str, request: dict[str, Any]) -> str:
        labels = {
            "approve_reuse": "同意按既有授权复用，不扩大字段范围。",
            "approve_with_supplement": "同意先复用既有字段，局部缺口补录后再交付。",
            "return_for_fix": "退回申请方缩小字段或范围，补齐最小必要说明。",
            "reject_duplicate": "驳回重复需求，避免绕过既有目录重复要数。",
            "route_to_provider_or_catalog_admin": "转 数据提供方 / 业务运营员 确认目录口径或授权边界后再判定。",
        }
        return f"{labels[decision]} 申请：{request.get('resourceName') or request.get('id')}。"

    def _r2_review_evidence(self, decision: str, request: dict[str, Any], delivery: dict[str, Any]) -> dict[str, Any]:
        return {
            "decision": decision,
            "catalog_code": request.get("applicationMaterials", {}).get("catalogCode"),
            "resource_id": request.get("resourceId"),
            "field_scope": [item.get("title") for item in request.get("requestedItems", [])],
            "field_binding_diagnosis": request.get("fieldBindingSummary", {}).get("diagnosis"),
            "sensitive_levels": request.get("sensitivePolicy", {}).get("fieldSensitiveLevels", []),
            "duplicate_conclusion": request.get("historicalContext", {}).get("duplicateConclusion"),
            "quality_status": request.get("qualityEvidence", {}).get("status"),
            "legacy_mapping_count": len(request.get("legacyMappings") or []),
            "access_grant_source": "data_apply_authrization" if delivery.get("accessGrantSnapshot") else None,
            "renewal_source_rows": 0,
        }

    def _provider_manage_payload(self, resource_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "resource_id": resource_id,
            "action": action,
            "tenant_id": payload.get("tenant_id", _DEFAULT_TENANT_ID),
            "target_ref": resource_id,
            "field_evidence": self._safe_json(payload.get("field_evidence") or {}),
            "binding_confirmations": self._safe_json(payload.get("binding_confirmations") or []),
            "external_execution": self._safe_json(payload.get("external_execution") or {}),
        } | ({"role": payload["role"]} if "role" in payload else {})

    def _complete_provider_field_evidence(
        self,
        resource_id: str,
        payload: dict[str, Any],
        actor: str,
        audit_id: str,
    ) -> dict[str, Any]:
        field_evidence = self._safe_json(payload.get("field_evidence") or {})
        if not field_evidence:
            raise BrainServiceError("field_evidence is required")
        store = self._state_store.database_store
        resource = self._find_api_resource(resource_id)
        if resource is None:
            raise NotFoundError(resource_id)
        summary = copy.deepcopy(resource.get("summary_json") or {})
        existing_evidence = copy.deepcopy(summary.get("field_evidence") or {})
        existing_evidence.update(field_evidence)
        summary["field_evidence"] = existing_evidence
        summary["field_evidence_confirmed_by"] = actor
        summary["field_evidence_audit_ref"] = audit_id
        updated_resource = self._upsert_api_resource({**resource, "summary_json": summary})
        snapshot_refs: list[str] = []
        if store is not None:
            for field_ref, evidence in field_evidence.items():
                evidence_payload = evidence if isinstance(evidence, dict) else {"value": evidence}
                snapshot = store.metadata_evidence_repo.upsert_schema_snapshot(
                    {
                        "snapshot_ref": f"{resource_id}:provider-field:{field_ref}",
                        "resource_code": resource_id,
                        "binding_code": payload.get("binding_code"),
                        "schema_json": {
                            "field_ref": field_ref,
                            "name_cn": evidence_payload.get("name_cn") or evidence_payload.get("title"),
                            "data_format": evidence_payload.get("data_format") or evidence_payload.get("format"),
                            "length": evidence_payload.get("length"),
                            "sensitive_level": evidence_payload.get("sensitive_level"),
                            "masking_policy": evidence_payload.get("masking_policy") or evidence_payload.get("mask_rule"),
                            "source_note": evidence_payload.get("source_note") or evidence_payload.get("source"),
                            "provider_confirmed_by": actor,
                            "provider_audit_ref": audit_id,
                        },
                        "source_ref": f"resource.manage_asset:field_evidence:{audit_id}:{field_ref}",
                        "legacy_object_ref": field_ref,
                    },
                    tenant_id=_DEFAULT_TENANT_ID,
                )
                snapshot_refs.append(snapshot.snapshot_ref)
        return {
            "resource_id": resource_id,
            "lifecycle_status": updated_resource.get("lifecycle_status"),
            "field_evidence_count": len(field_evidence),
            "schema_snapshot_refs": snapshot_refs,
        }

    def _confirm_provider_field_binding(
        self,
        resource_id: str,
        payload: dict[str, Any],
        actor: str,
        audit_id: str,
    ) -> dict[str, Any]:
        confirmations = payload.get("binding_confirmations") or []
        if not isinstance(confirmations, list) or not confirmations:
            raise BrainServiceError("binding_confirmations is required")
        store = self._state_store.database_store
        if store is None:
            raise BrainServiceError("database store is required for provider binding confirmation")
        if self._find_api_resource(resource_id) is None:
            raise NotFoundError(resource_id)
        mapping_codes: list[str] = []
        for confirmation in confirmations:
            if not isinstance(confirmation, dict):
                raise BrainServiceError("binding confirmation must be an object")
            if str(confirmation.get("resource_code") or resource_id) != resource_id:
                raise AccessDeniedError("binding confirmation resource mismatch")
            mapping = store.metadata_evidence_repo.upsert_schema_mapping(
                {
                    **confirmation,
                    "resource_code": resource_id,
                    "confidence_level": confirmation.get("confidence_level", "confirmed"),
                    "status": confirmation.get("status", "active"),
                    "evidence_ref": confirmation.get("evidence_ref") or audit_id,
                    "source_ref": confirmation.get("source_ref") or f"resource.manage_asset:binding_confirmation:{audit_id}",
                    "legacy_object_ref": confirmation.get("legacy_object_ref") or confirmation.get("mapping_code"),
                    "confirmed_by": actor,
                },
                tenant_id=_DEFAULT_TENANT_ID,
            )
            mapping_codes.append(mapping.mapping_code)
        return {"resource_id": resource_id, "confirmed_mapping_codes": mapping_codes, "binding_confirmation_count": len(mapping_codes)}

    def _transition_provider_resource(self, resource_id: str, status: str, actor: str, audit_id: str) -> dict[str, Any]:
        store = self._state_store.database_store
        record = store.resource_api_repo.transition_asset(resource_id, status, tenant_id=_DEFAULT_TENANT_ID) if store is not None else None
        if store is None:
            resource = self._find_api_resource(resource_id)
            if resource is None:
                snapshot_resource = next((item for item in self._snapshot.get("provider", {}).get("resources", []) if item.get("id") == resource_id), None)
                if snapshot_resource is None:
                    raise NotFoundError(resource_id)
                resource = {
                    "resource_code": resource_id,
                    "title": snapshot_resource.get("name", resource_id),
                    "resource_kind": "dataset",
                    "lifecycle_status": status,
                    "source_ref": snapshot_resource.get("source_ref") or f"provider:resource:{resource_id}",
                    "summary_json": snapshot_resource,
                }
            resource["lifecycle_status"] = status
            resource["updated_at"] = clock.now_datetime()
            result = self._upsert_api_resource(resource)
        else:
            if record is None:
                snapshot_resource = next((item for item in self._snapshot.get("provider", {}).get("resources", []) if item.get("id") == resource_id), None)
                if snapshot_resource is None:
                    raise NotFoundError(resource_id)
                record = store.resource_api_repo.upsert_asset(
                    {
                        "resource_code": resource_id,
                        "title": snapshot_resource.get("name", resource_id),
                        "resource_kind": "dataset",
                        "lifecycle_status": status,
                        "owner_org_id": snapshot_resource.get("owner_org_id"),
                        "source_ref": snapshot_resource.get("source_ref") or f"provider:resource:{resource_id}",
                        "legacy_object_ref": snapshot_resource.get("legacy_object_ref") or resource_id,
                        "summary_json": snapshot_resource,
                    },
                    tenant_id=_DEFAULT_TENANT_ID,
                )
            store.approval_repo.upsert_api_resource_lifecycle(
                resource_id,
                status,
                actor=actor,
                skill_id="resource.manage_asset",
                audit_id=audit_id,
                decision="return" if status in {"draft", "suspended"} else None,
                tenant_id=_DEFAULT_TENANT_ID,
            )
            result = resource_api_ser.resource_asset_to_dict(record)
        return {"resource_id": resource_id, "lifecycle_status": status, "asset": result, "result": "published" if status == "active" else "suspended"}

    def _request_provider_external_execution(
        self,
        resource_id: str,
        payload: dict[str, Any],
        actor: str,
        audit_id: str,
    ) -> dict[str, Any]:
        execution = self._safe_json(payload.get("external_execution") or {})
        execution_kind = str(execution.get("execution_kind") or execution.get("kind") or "schema_structure")
        if execution_kind not in {"metadata_gather", "schema_structure", "materialize", "exchange"}:
            raise BrainServiceError(f"unsupported external execution kind: {execution_kind}")
        store = self._state_store.database_store
        if store is None:
            raise BrainServiceError("database store is required for external execution receipts")
        if self._find_api_resource(resource_id) is None:
            raise NotFoundError(resource_id)
        attempt_code = str(execution.get("attempt_code") or f"provider-external:{resource_id}:{execution_kind}:{audit_id}")
        delivery_code = str(execution.get("delivery_code") or f"provider-external:{resource_id}")
        callback_skill_id = str(
            execution.get("callback_skill_id")
            or ("metadata.schema.snapshot.upsert" if execution_kind in {"metadata_gather", "schema_structure"} else "delivery.receipt.ingest")
        )
        contract_skill_id = "external.schema.structure.apply" if execution_kind in {"metadata_gather", "schema_structure", "materialize"} else "external.exchange.executor.execute"
        attempt = store.delivery_repo.upsert_attempt(
            {
                "attempt_code": attempt_code,
                "delivery_code": delivery_code,
                "attempt_kind": execution_kind,
                "state": "planned",
                "executor_ref": execution.get("executor_ref") or contract_skill_id,
                "evidence_ref": audit_id,
                "payload_json": {
                    "resource_code": resource_id,
                    "contract_skill_id": contract_skill_id,
                    "callback_skill_id": callback_skill_id,
                    "change_plan_json": execution.get("change_plan_json") or {},
                    "canonical_write_policy": "callback_only",
                },
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        evidence = store.delivery_repo.add_execution_evidence(
            {
                "evidence_ref": f"{audit_id}:external-receipt",
                "delivery_code": delivery_code,
                "attempt_code": attempt.attempt_code,
                "executor_kind": "external_contract",
                "executor_ref": contract_skill_id,
                "evidence_kind": "executor_task_receipt",
                "result_status": "planned",
                "sanitized_payload_json": {
                    "resource_code": resource_id,
                    "attempt_code": attempt.attempt_code,
                    "callback_skill_id": callback_skill_id,
                    "canonical_write_policy": "callback_only",
                },
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        return {
            "resource_id": resource_id,
            "attempt_code": attempt.attempt_code,
            "delivery_code": delivery_code,
            "executor_contract": contract_skill_id,
            "callback_skill_id": callback_skill_id,
            "receipt_ref": evidence.evidence_ref,
            "core_state_unchanged": True,
        }

    def grant_delivery_access(self, task_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        task = self._delivery_by_id(task_id)
        if task["status"] not in {"pending", "warning", "reconciling", "supplementing"}:
            raise InvalidStateError("delivery task cannot grant access in current state")

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task["status"] = "completed"
            task["receiptStatus"] = task.get("receiptStatus") or "granted"
            task["updatedAt"] = clock.now_datetime()
            task["note"] = "访问授权已生效，交付事实已写入可回放任务链。"
            task.setdefault("access", {})
            task["access"]["grant_ref"] = task["access"].get("grant_ref") or f"grant-{task_id}"
            task["access"]["status"] = "effective"
            task["history"].append(
                {
                    "time": clock.now_short_time(),
                    "state": "授权已生效",
                    "detail": "核心审批后的授权交付已完成，并保留审计锚定。",
                }
            )
            task["aiSummary"]["summary"] = "访问授权已生效，当前可进入使用监测、回执对账或模板回流确认。"
            task["aiSummary"]["nextAction"] = "继续监测调用与回执，如存在高频差异字段再进入供给侧治理。"
            store = self._state_store.database_store
            if store is not None:
                store.delivery_repo.upsert_from_delivery(task, tenant_id=_DEFAULT_TENANT_ID)
            self._append_audit_feed("delivery.access.grant", task_id, "ok", actor)
            return {"task_id": task_id, "status": task["status"], "grant_ref": task["access"]["grant_ref"]}

        return self._mutate("delivery.access.grant", role, confirmed, {"task_id": task_id}, mutation)

    def _approve_request(self, request_id: str, role: str, confirmed: bool, skill_id: str = "approval.review_decide", *, decision: str = "approve_reuse") -> dict[str, Any]:
        request = self._request_by_id(request_id)
        approval = self._approval_by_id(request_id)
        delivery = self._delivery_by_request_id(request_id)
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
            self._append_audit_feed("request.approve", request_id, "ok", actor)
            return {"request_id": request_id, "status": request["status"]}

        result = self._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": decision}, mutation)
        # R-006 fix: 凭据签发作为审批之后的独立动作；audit 失败不污染审批 mutation
        self._auto_issue_credential_on_approval(request_id, role, self._actor_for_role(role))
        return result

    def _return_request_for_fix(self, request_id: str, role: str, confirmed: bool, skill_id: str = "approval.review_decide", *, decision: str = "return_for_fix") -> dict[str, Any]:
        request = self._request_by_id(request_id)
        approval = self._approval_by_id(request_id)
        delivery = self._delivery_by_request_id(request_id)
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
            self._append_audit_feed("request.return-for-fix", request_id, "warning", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": decision}, mutation)

    def _reject_request(self, request_id: str, role: str, confirmed: bool, skill_id: str = "approval.review_decide", *, decision: str = "reject_duplicate") -> dict[str, Any]:
        request = self._request_by_id(request_id)
        delivery = self._delivery_by_request_id(request_id)
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
            self._append_audit_feed("request.reject", request_id, "warning", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": decision}, mutation)

    def _route_request_for_catalog_confirmation(self, request_id: str, role: str, confirmed: bool, skill_id: str = "approval.review_decide") -> dict[str, Any]:
        request = self._request_by_id(request_id)
        approval = self._approval_by_id(request_id)
        delivery = self._delivery_by_request_id(request_id)
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
            self._append_audit_feed("request.route-to-provider-or-catalog-admin", request_id, "warning", actor)
            return {"request_id": request_id, "status": request["status"]}

        return self._mutate(skill_id, role, confirmed, {"request_id": request_id, "decision": "route_to_provider_or_catalog_admin"}, mutation)

    def _resolve_role(self, payload: dict[str, Any]) -> str:
        from zw_brain.shared.session_context import (
            TRUSTED_SESSION_CONTEXT_KEY,
            is_trusted_session_payload,
            resolve_trusted_role,
        )

        try:
            if is_trusted_session_payload(payload):
                snapshot = payload.get("actor_snapshot")
                if not isinstance(snapshot, dict):
                    raise AccessDeniedError("trusted session requires actor_snapshot")
                return resolve_trusted_role(payload, actor_snapshot=snapshot)
            # Client-supplied payloads (Bearer / A2A / MCP / CLI entry paths) cannot
            # claim trust: only `build_trusted_skill_payload` stamps the in-process
            # sentinel. Strip any smuggled value so downstream copies / audit dumps
            # don't surface a misleading "_trusted_session_context: True".
            payload.pop(TRUSTED_SESSION_CONTEXT_KEY, None)
            return policy.resolve_role(payload.get("role"), self._ui_state.get("role", "ROLE_ORGAN_OPERATER"))
        except DomainAccessDeniedError as exc:
            raise AccessDeniedError(str(exc)) from exc

    def _enforce_manifest_policy(self, skill_id: str, manifest: dict[str, Any], role: str, payload: dict[str, Any]) -> None:
        try:
            policy.enforce_manifest_policy(skill_id, manifest, role, payload)
        except DomainAccessDeniedError as exc:
            raise AccessDeniedError(str(exc)) from exc

    def _invoke_traced_read(self, skill_id: str, role: str, payload: dict[str, Any], operation: Any) -> Any:
        store = self._state_store.database_store
        if store is None:
            return operation()
        actor = self._actor_for_role(role)
        audit_id = ids.new_audit_id()
        started_at = datetime.now()
        self._emit_audit(audit_id, actor, skill_id, "before", payload)
        try:
            result = operation()
        except Exception as exc:
            self._emit_audit(audit_id, actor, skill_id, "error", {"error": exc.__class__.__name__, "message": str(exc)})
            self._record_capability_call(
                audit_id,
                actor,
                role,
                skill_id,
                payload,
                {"error": exc.__class__.__name__, "message": str(exc)},
                started_at,
                status="failed",
            )
            raise
        self._emit_audit(audit_id, actor, skill_id, "after", result if isinstance(result, dict) else {"result": result})
        self._record_capability_call(audit_id, actor, role, skill_id, payload, result if isinstance(result, dict) else {"result": result}, started_at)
        return result

    def _mutate(self, skill_id: str, role: str, confirmed: bool, payload: dict[str, Any], mutation: Any) -> dict[str, Any]:
        manifest = get_manifest(skill_id)
        self._enforce_manifest_policy(skill_id, manifest, role, payload | {"confirmed": confirmed})
        if manifest.get("human_confirmation_required") and not confirmed:
            raise ConfirmationRequiredError(skill_id)
        actor = self._actor_for_role(role)
        audit_id = ids.new_audit_id()
        started_at = datetime.now()
        self._emit_audit(audit_id, actor, skill_id, "before", payload)
        try:
            result = mutation(audit_id, actor)
        except Exception as exc:
            self._emit_audit(audit_id, actor, skill_id, "error", {"error": exc.__class__.__name__, "message": str(exc)})
            self._record_capability_call(
                audit_id,
                actor,
                role,
                skill_id,
                payload,
                {"error": exc.__class__.__name__, "message": str(exc)},
                started_at,
                status="failed",
            )
            raise
        self._sync_state_views()
        self._persist()
        self._emit_audit(audit_id, actor, skill_id, "after", result)
        self._record_capability_call(audit_id, actor, role, skill_id, payload, result, started_at)
        if manifest.get("side_effects"):
            self._sync_database_aggregates()
            self._enqueue_anchor(audit_id, actor, skill_id, payload | result)
        return {"ok": True, "skill_id": skill_id, "audit_id": audit_id, "result": result}

    def _record_capability_call(
        self,
        audit_id: str,
        actor: str,
        role: str,
        skill_id: str,
        payload: dict[str, Any],
        result: dict[str, Any],
        started_at: datetime,
        *,
        status: str = "succeeded",
    ) -> None:
        store = self._state_store.database_store
        if store is None:
            return
        store.append_capability_call(
            {
                "call_ref": audit_id,
                "tenant_id": str(payload.get("tenant_id", _DEFAULT_TENANT_ID)),
                "skill_id": skill_id,
                "actor": actor,
                "role_code": role,
                "status": status,
                "request_ref": self._audit_target_from_payload(audit_id, payload),
                "input_json": safe_json(payload),
                "output_json": safe_json(result),
                "started_at": started_at,
                "completed_at": datetime.now(),
            }
        )

    def _persist(self) -> None:
        self._state_store.save(self._snapshot, self._ui_state.persistable_view())

    def _emit_audit(self, request_id: str, actor: str, skill_id: str, phase: str, payload: dict[str, Any]) -> None:
        manifest = get_manifest(skill_id)
        actor_parts = actor.split(":", 3)
        payload_with_evidence = safe_json(payload)
        if isinstance(payload_with_evidence.get("actor_snapshot"), dict) and payload_with_evidence["actor_snapshot"]:
            actor_snapshot = copy.deepcopy(payload_with_evidence["actor_snapshot"])
        else:
            actor_snapshot = {"actor": actor}
            if len(actor_parts) >= 3 and actor_parts[:2] == ["user", "gov"]:
                actor_snapshot["role_code"] = actor_parts[2]
        ctx = get_auth_context()
        if ctx is not None and ctx.development_iam_bypass:
            actor_snapshot["development_iam_bypass"] = True
            payload_with_evidence["development_iam_bypass"] = True
        payload_with_evidence["skill_id"] = skill_id
        payload_with_evidence["audit_class"] = payload_with_evidence.get("audit_class") or manifest.get("audit_class")
        payload_with_evidence["actor_snapshot"] = actor_snapshot
        payload_with_evidence["policy_version"] = payload_with_evidence.get("policy_version") or manifest.get("version")
        payload_with_evidence["decision_reason"] = payload_with_evidence.get("decision_reason") or self._audit_decision_reason(phase, payload)
        payload_with_evidence["target_ref"] = payload_with_evidence.get("target_ref") or self._audit_target_from_payload(request_id, payload)
        audit_bus.emit(
            audit_bus.AuditEvent(
                request_id=request_id,
                actor=actor,
                skill_id=skill_id,
                phase=phase,
                payload=payload_with_evidence,
            )
        )

    def _audit_decision_reason(self, phase: str, payload: dict[str, Any]) -> str:
        value = payload.get("decision_reason") or payload.get("decision") or payload.get("error") or phase
        return str(value)

    def _enqueue_anchor(self, request_id: str, actor: str, skill_id: str, payload: dict[str, Any]) -> None:
        # safe_json strips the trust sentinel and other process-local objects that
        # cannot cross a JSON boundary. Without it, _mutate's `payload | result`
        # carries _TRUSTED_SESSION_MARKER (object()) and json.dumps below raises
        # TypeError → REST returns 500 to the caller.
        sanitized_payload = safe_json(payload)
        content_hash = hashlib.sha256(
            json.dumps(
                {
                    "request_id": request_id,
                    "actor": actor,
                    "skill_id": skill_id,
                    "payload": sanitized_payload,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        store = self._state_store.database_store
        if store is not None:
            store.append_anchor_outbox(request_id, skill_id, content_hash, "mock-chain")
        asyncio.run(
            queue.enqueue(
                "blockchain.anchor",
                {
                    "request_id": request_id,
                    "skill_id": skill_id,
                    "actor": actor,
                    "content_hash": content_hash,
                    "chain_id": "mock-chain",
                },
            )
        )

    def _sync_reference_tables(self) -> None:
        store = self._state_store.database_store
        if store is None:
            return
        store.sync_reference_tables(self.snapshot())

    def _sync_database_aggregates(self) -> None:
        store = self._state_store.database_store
        if store is None:
            return
        store.sync_aggregate_tables(self.snapshot())

    def _append_audit_feed(self, event_type: str, target: str, result: str, actor: str) -> None:
        self._snapshot["audit_events"].append(
            {
                "id": ids.new_audit_id(),
                "time": clock.month_day_time(),
                "actor": actor,
                "type": event_type,
                "target": target,
                "result": result,
                "chain": "pending" if result != "failed" else "n/a",
            }
        )

    def _audit_target_from_payload(self, request_id: str, payload: dict[str, Any]) -> str:
        for fld in (
            "dispute_id",
            "request_id",
            "task_id",
            "package_id",
            "resource_id",
            "catalog_id",
            "catalog_code",
            "resource_code",
            "service_id",
            "zone_id",
            "target_ref",
            "id",
        ):
            value = payload.get(fld)
            if value:
                return str(value)
        return request_id

    def _sync_state_views(self) -> None:
        self._sync_request_todos()
        # Demo-seed cascades live in a dedicated module (no demo entity IDs in core).
        # Lazy import breaks the demo_state_sync → brain module cycle.
        from zw_brain.command.demo_state_sync import sync_demo_state_views  # noqa: PLC0415
        sync_demo_state_views(self)

    # R-005 fix: 折叠后多个旧角色映射到同一 ROLE_*，原本不同语境（申请进度 vs 差异补录 vs 现场补录 vs 汇总）
    # 的同 item_id 待办若仅按 (role, item_id) 去重会互相覆盖。引入 category 作为第二维度。
    def _set_todo_status(self, role: str, item_id: str, status: str, *, category: str = "") -> None:
        bucket = self._snapshot["workbench"].get(role)
        if not bucket:
            return
        for todo in bucket["todos"]:
            if todo["id"] == item_id and todo.get("category", "") == category:
                todo["status"] = status
                return

    def _request_status_timeline(self, request: dict[str, Any], delivery: dict[str, Any] | None) -> list[dict[str, Any]]:
        decision = "已通过" if request.get("status") in {"supplementing", "summary-pending", "completed"} else "待审批结论"
        delivery_state = delivery.get("status") if delivery else "pending"
        return [
            {"stage": "待受理", "status": "done", "ref": request.get("id"), "label": "申请已提交"},
            {"stage": "审核中", "status": "done" if request.get("status") != "pending" else "current", "ref": request.get("id"), "label": self._request_status_text(request, "reviewer")},
            {"stage": "审批结论", "status": "done" if decision == "已通过" else "pending", "ref": request.get("id"), "label": decision},
            {"stage": "delivery_task", "status": delivery_state, "ref": delivery.get("id") if delivery else None, "label": delivery_state},
        ]

    # R-002 fix: 文案不再按 role 单维区分（折叠后同一 ROLE_* 无法承载"申请人 vs 填报人"双语义）。
    # 改为按业务视角（perspective）显示文案；调用方在每个待办语境下显式声明视角。
    # perspective 取值：
    #   "applicant"  — 申请人视角（看自己的申请进度）
    #   "reviewer"   — 审批人/审核人视角（看待我审批的项）
    #   "filler"     — 基层填报人视角（看待我补录的差异/现场任务）
    #   "summarizer" — 汇总审核人视角（看待我确认的异常项）
    def _request_status_text(self, item: dict[str, Any], perspective: str = "reviewer") -> str:
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

    def _package_status_text(self, item: dict[str, Any]) -> str:
        if item["status"] == "pending":
            return "待审核"
        if item["status"] == "pending-fix":
            return "待补正"
        if item["status"] == "approved":
            return "已上线"
        if item["status"] == "rejected":
            return "已驳回"
        return str(item["status"])

    def _actor_for_role(self, role: str) -> str:
        try:
            actor = policy.actor_for_role(role)
        except DomainAccessDeniedError as exc:
            raise AccessDeniedError(str(exc)) from exc
        # When the dev IAM bypass synthetic identity is active, suffix the actor so audit events and
        # capability_call rows are unambiguously attributable to bypass mode — not to the human user
        # whose role code was reused. Auditors filter on this suffix.
        ctx = get_auth_context()
        if ctx is not None and ctx.development_iam_bypass:
            return f"{actor}[bypass]"
        return actor

    def _request_by_id(self, request_id: str) -> dict[str, Any]:
        for item in self._snapshot["requests"]:
            if item["id"] == request_id:
                return item
        raise NotFoundError(request_id)

    def _maybe_request(self, request_id: str) -> dict[str, Any] | None:
        try:
            return self._request_by_id(request_id)
        except NotFoundError:
            return None

    def _approval_by_id(self, request_id: str) -> dict[str, Any]:
        for item in self._snapshot["approvals"]:
            if item["id"] == request_id:
                return item
        raise NotFoundError(request_id)

    def _maybe_approval(self, request_id: str) -> dict[str, Any] | None:
        try:
            return self._approval_by_id(request_id)
        except NotFoundError:
            return None

    def _delivery_by_request_id(self, request_id: str) -> dict[str, Any] | None:
        for item in self._snapshot["delivery_tasks"]:
            if item["requestId"] == request_id:
                return item
        return None

    def _delivery_by_id(self, task_id: str) -> dict[str, Any]:
        for item in self._snapshot["delivery_tasks"]:
            if item["id"] == task_id:
                return item
        raise NotFoundError(task_id)

    def _maybe_delivery(self, task_id: str) -> dict[str, Any] | None:
        try:
            return self._delivery_by_id(task_id)
        except NotFoundError:
            return None

    def _resource_by_id(self, resource_id: str) -> dict[str, Any]:
        for item in self._snapshot["discovery"]["resources"]:
            if item["id"] == resource_id:
                return item
        raise NotFoundError(resource_id)

    def _resolve_resource_for_application(self, resource_id: str) -> dict[str, Any]:
        """Resolve catalog/provider aliases (e.g. cat-parking) to canonical discovery.resources rows."""
        provider_cat = next(
            (c for c in self._snapshot.get("provider", {}).get("catalogs", []) if c.get("id") == resource_id),
            None,
        )
        provider_canonical_id = (provider_cat or {}).get("canonical_resource_id") or (provider_cat or {}).get("application_resource_id")
        if provider_canonical_id:
            try:
                return copy.deepcopy(self._resource_by_id(str(provider_canonical_id)))
            except NotFoundError as exc:
                raise BrainServiceError(
                    f"catalog {resource_id!r} declares canonical_resource_id {provider_canonical_id!r} but no matching discovery.resources entry exists"
                ) from exc
        try:
            return copy.deepcopy(self._resource_by_id(resource_id))
        except NotFoundError:
            pass

        store = self._state_store.database_store
        catalog_record = store.catalog_repo.get_entry(resource_id, tenant_id=_DEFAULT_TENANT_ID) if store is not None else None

        summary: dict[str, Any] = {}
        if catalog_record is not None:
            sr = catalog_record.summary_json
            summary = sr if isinstance(sr, dict) else {}
            if not summary.get("canonical_resource_id") and not summary.get("application_resource_id"):
                return self.get_resource(resource_id)

        if store is not None and store.resource_api_repo.get_asset(resource_id, tenant_id=_DEFAULT_TENANT_ID) is not None:
            return self.get_resource(resource_id)

        canonical_id = (
            summary.get("canonical_resource_id")
            or summary.get("application_resource_id")
            or (provider_cat or {}).get("canonical_resource_id")
            or (provider_cat or {}).get("application_resource_id")
        )
        if canonical_id:
            try:
                return copy.deepcopy(self._resource_by_id(str(canonical_id)))
            except NotFoundError as exc:
                raise BrainServiceError(
                    f"catalog {resource_id!r} declares canonical_resource_id {canonical_id!r} but no matching discovery.resources entry exists"
                ) from exc

        legacy_ref = summary.get("legacy_object_ref") or summary.get("legacyId")
        if provider_cat:
            legacy_ref = legacy_ref or provider_cat.get("legacy_object_ref")

        if legacy_ref:
            matches = [
                item
                for item in self._snapshot["discovery"]["resources"]
                if (item.get("trueData") or {}).get("catalog_code") == legacy_ref or item.get("legacyId") == legacy_ref
            ]
            if len(matches) == 1:
                return copy.deepcopy(matches[0])
            if len(matches) > 1:
                raise BrainServiceError(
                    f"ambiguous legacy mapping for catalog or alias {resource_id!r}: {len(matches)} discovery.resources "
                    f"match legacy_object_ref {legacy_ref!r}; set canonical_resource_id on the catalog entry to a single discovery.resources id"
                )

        if catalog_record is not None:
            cc = catalog_record.catalog_code
            matches = [
                item
                for item in self._snapshot["discovery"]["resources"]
                if (item.get("trueData") or {}).get("catalog_code") == cc
            ]
            if len(matches) == 1:
                return copy.deepcopy(matches[0])
            if len(matches) > 1:
                raise BrainServiceError(
                    f"ambiguous catalog_code mapping for {resource_id!r}: {len(matches)} resources share catalog_code {cc!r}; "
                    f"set canonical_resource_id on the catalog entry"
                )

        raise NotFoundError(resource_id)

    def _package_by_id(self, package_id: str) -> dict[str, Any]:
        for item in self._snapshot["capability_packages"]:
            if item["id"] == package_id:
                return item
        raise NotFoundError(package_id)

    def _maybe_package(self, package_id: str) -> dict[str, Any] | None:
        try:
            return self._package_by_id(package_id)
        except NotFoundError:
            return None

    def _zone_by_id(self, zone_id: str) -> dict[str, Any]:
        for item in self._snapshot["zones"]:
            if item["id"] == zone_id:
                return item
        raise NotFoundError(zone_id)


    # R-005 fix: 同 R-005 — 待办按 (role, item_id, category) 唯一；折叠后多个语境的同 item_id 可共存。
    def _upsert_todo(self, role: str, item_id: str, title: str, status: str, href: str, *, category: str = "") -> None:
        bucket = self._snapshot["workbench"].get(role)
        if not bucket:
            return
        for todo in bucket["todos"]:
            if todo["id"] == item_id and todo.get("category", "") == category:
                todo["title"] = title
                todo["status"] = status
                todo["href"] = href
                return
        bucket["todos"].insert(0, {"id": item_id, "title": title, "status": status, "href": href, "category": category})

    def _sync_request_todos(self) -> None:
        for request in self._snapshot["requests"]:
            request_id = request["id"]
            resource_name = request.get("resourceName", request_id)
            # R-002/R-005 fix: perspective + category 双维度（perspective 决定文案，category 区分同 REQ 在同 role 下的多个待办语境）
            self._upsert_todo("ROLE_ORGAN_OPERATER", request_id, f"{resource_name}复用申请进度跟踪", self._request_status_text(request, "applicant"), f"#/request-flow/request/{request_id}", category="apply-progress")
            self._upsert_todo("ROLE_ORGAN_MANAGER", request_id, f"{resource_name}复用申请待判定", self._request_status_text(request, "reviewer"), f"#/request-flow/review/{request_id}", category="review")
            if request["status"] in {"supplementing", "summary-pending", "completed", "need-fix"}:
                self._upsert_todo("ROLE_ORGAN_OPERATER", request_id, f"{resource_name}差异补录任务", self._request_status_text(request, "filler"), f"#/request-flow/request/{request_id}", category="supplement-township")
                self._upsert_todo("ROLE_ORGAN_OPERATER", request_id, f"{resource_name}现场补录任务", self._request_status_text(request, "filler"), f"#/request-flow/request/{request_id}", category="supplement-village")
            if request["status"] in {"pending", "summary-pending", "completed", "need-fix", "rejected"}:
                self._upsert_todo("ROLE_ORGAN_MANAGER", request_id, f"{resource_name}汇总/准入处理", self._request_status_text(request, "summarizer"), f"#/request-flow/review/{request_id}", category="summary")

    def _new_request_id(self) -> str:
        return ids.next_request_id(str(item.get("id", "")) for item in self._snapshot["requests"])

    def _delivery_task_id_for_request(self, request_id: str) -> str:
        return request_id.replace("REQ-", "DLV-", 1)

    def _requested_application_fields(self, resource: dict[str, Any], options: dict[str, Any]) -> list[dict[str, Any]]:
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

    def _application_gap_fields(self, options: dict[str, Any]) -> list[str]:
        raw = options.get("gap_fields") or options.get("gapFields") or ["统计时间窗", "区县范围"]
        if not isinstance(raw, list):
            raw = [raw]
        return [str(item.get("title") if isinstance(item, dict) else item) for item in raw if str(item.get("title") if isinstance(item, dict) else item).strip()]

    def _application_time_window(self, options: dict[str, Any]) -> dict[str, Any]:
        raw = options.get("time_window") or options.get("timeWindow") or {}
        if isinstance(raw, dict):
            return {"start": raw.get("start") or raw.get("from") or "2025-01-01", "end": raw.get("end") or raw.get("to") or "2025-12-31"}
        return {"label": str(raw)}

    def _application_scope(self, resource: dict[str, Any], options: dict[str, Any]) -> str:
        return str(options.get("application_scope") or options.get("scope") or resource.get("regionCode") or resource.get("zone") or "山东省")

    def _diff_fields_for_gap(self, gap_fields: list[str]) -> list[dict[str, Any]]:
        return [
            {"label": field, "value": "待补充", "reason": "本次申请仍需明确", "owner": "申请人 补充说明 / 审批人 审核确认"}
            for field in gap_fields
        ]

    def _application_source_evidence(self, resource: dict[str, Any], fields: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "catalogCode": resource.get("repository", {}).get("catalogCode") or resource.get("id"),
            "legacyMappings": copy.deepcopy(resource.get("legacyMappings") or []),
            "fieldBindings": copy.deepcopy(resource.get("fieldBindings") or []),
            "resourceAssets": copy.deepcopy(resource.get("resourceAssets") or []),
            "requestedItemCodes": [field["item_code"] for field in fields],
        }

    def _prefilled_fields_for_resource(self, resource: dict[str, Any], requested_fields: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
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

    def _default_diff_fields(self) -> list[dict[str, Any]]:
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


    # ============== J1 凭据签发与查询（D27/U-3 处置承诺的凭据领取闭环） ==============

    def _credential_for_request(self, request_id: str, seed: str | None = None) -> dict[str, Any]:
        """Demo credential — 同一 (request_id, seed) 永远生成同一凭据；不依赖 IAM 密钥管理。

        seed=None：首次签发（auto-on-approval），用 request_id 作种子，凭据可被 demo 用户重现。
        seed=<audit_id>：reissue 路径传入 audit_id 作种子，**每次重签都产生不同 app_secret**
        （旧 secret 立即失效语义；与生产 IAM reissue 行为对齐）。

        前缀 AK-DEMO- / SK-DEMO- 让 preflight 与 audit 一眼能区分 demo vs 生产。
        生产对接 IAM 时：替换本方法的实现 + 调用方在 reissue 路径必须传新 seed
        （已由 issue_credential 实现保障）。
        """
        seed_material = f"d23-credential-{request_id}" if seed is None else f"d23-credential-{request_id}-reissue-{seed}"
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

    def _auto_issue_credential_on_approval(self, request_id: str, role: str, actor: str) -> None:
        """审批通过路径的内部钩子 — 通过 credential.issue skill 完成签发.

        设计（R-006 + R-102）：
        - hook 在 `_mutate` return **之后**调用；审批 mutation 已成功落库，本钩子失败
          **不污染**审批 state（凭据可后续手工补签）。
        - 通过 `invoke_skill("credential.issue", ...)` 触发，自动获得完整 `_mutate`
          包装：capability_call ledger / audit before-after-error / D5 锚定 / 权限校验。
        - 凭据签发失败时错误冒泡到 dispatch 层（D4 不静默吞错）；但审批已成功不受影响，
          客户端可通过 P4 凭据领取页 `reissueCredential` 手工补签。

        前置守卫：
        - 无对应 delivery → 安全跳过（审批通过但无 delivery 投影是 demo 边界 case）
        - 已有 credential → 安全跳过（重复进入审批通过路径不重签）
        """
        delivery = self._delivery_by_request_id(request_id)
        if delivery is None:
            return
        if (delivery.get("accessGrantSnapshot") or {}).get("credential"):
            return
        # 通过 invoke_skill 路径触发；权限/审计/锚定一气呵成
        self.invoke_skill("credential.issue", {
            "request_id": request_id,
            "role": role,
            "confirmed": True,
        })

