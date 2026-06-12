from __future__ import annotations

import base64
import copy
import json
import logging

# Default read-side mask role. Per [2026-05-06] sensitive-field policy: business-
# visible PII (name / phone / email / id / address) is ingested raw, masked on
# read. Set ZW_BRAIN_MASK_ROLE=internal_admin to opt up (audit replay only).
import os as _os
from collections.abc import Iterator, MutableMapping
from datetime import UTC, datetime
from typing import Any

import zw_brain.shared.audit as audit_bus
import zw_brain.shared.clock as clock
from zw_brain.capability_registry.runtime import get_manifest, load_manifests
from zw_brain.command.card_session import is_runtime_delivery_payload, is_runtime_request_payload
from zw_brain.command.serializers import metadata as metadata_ser
from zw_brain.domain import policy
from zw_brain.domain.errors import AccessDeniedError as AccessDeniedError  # R-016 re-export
from zw_brain.domain.errors import BrainServiceError as BrainServiceError  # R-016 re-export
from zw_brain.domain.errors import ConfirmationRequiredError as ConfirmationRequiredError  # R-016 re-export
from zw_brain.domain.errors import InvalidStateError as InvalidStateError  # R-016 re-export
from zw_brain.domain.errors import InvalidTokenError as InvalidTokenError  # R-016 re-export
from zw_brain.domain.errors import NotFoundError as NotFoundError  # R-016 re-export
from zw_brain.domain.errors import QuotaExceededError as QuotaExceededError  # R-016 re-export
from zw_brain.domain.errors import TrustLevelInsufficientError as TrustLevelInsufficientError  # R-016 re-export
from zw_brain.domain.errors import UnknownSkillError as UnknownSkillError  # R-016 re-export
from zw_brain.domain.errors import _RequestBatchContext as _RequestBatchContext  # R-016 re-export
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.domain.repositories.delivery import DeliveryRepository
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.domain.repositories.topic_package import TopicPackageRepository
from zw_brain.domain.services.delivery_service import (
    RETIRED_RESOURCE_KINDS as _RETIRED_RESOURCE_KINDS,
)
from zw_brain.domain.services.delivery_service import (
    _delivery_resource_kind,
)
from zw_brain.domain.services.delivery_service import (
    delivery_record_hidden_from_consumer as _delivery_record_hidden_from_consumer,
)
from zw_brain.shared import ids, queue
from zw_brain.shared.auth_context import get_auth_context
from zw_brain.shared.runtime_config import get_dev_iam_bypass_enabled
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sanitization import safe_json
from zw_brain.shared.sensitive_mask import mask_default
from zw_brain.shared.state_store import StateStore
from zw_brain.shared.ui_request_context import get_current_role, set_current_role

# P1-3: terminal-negative application statuses. Granting delivery access against an
# application in one of these states is the 46f0 cross-aggregate hole (access still
# grantable after the bound application was withdrawn/rejected/revoked). Only unambiguous
# terminal-negative states are listed — `suspended` (reversible) and `expired` (not in the
# application_record APPLY_STATUS_MAP) are deliberately excluded to avoid blocking legit
# flows. Values are the runtime application_record.status vocabulary (legacy import
# APPLY_STATUS_MAP {-1:"withdrawn",7/8/12:"rejected",15:"revoked"} +
# request_service reject_duplicate→"rejected"/revoked).
_TERMINAL_NEGATIVE_APPLICATION_STATUSES = frozenset({"withdrawn", "rejected", "revoked"})

_LOGGER = logging.getLogger("zw_brain.command.brain")


def _national_channel_webui_state() -> dict[str, Any]:
    """国家通道运行三态投影到 snapshot.webui（C5b / D50 §二运行门）。

    单一事实源 = shared.national.resolve_national_channel_state（gate 与前端共用）。
    前端用 enabled 决定 P5「国家扩展要素」入口是否渲染（off→不渲染，承「无权=不可见」），
    用 provisioned 决定「发布/同步国家平台」按钮是否可用（未配置→置灰、草拟仍可）。
    notice 用人话（R12，禁 flag/binding/provision/endpoint 工程术语）；不含任何密钥。
    """
    from zw_brain.shared.national import (  # noqa: PLC0415  (避免模块级反向依赖)
        NationalChannelState,
        resolve_national_channel_state,
    )

    state = resolve_national_channel_state()
    notice = {
        NationalChannelState.OFF: "国家通道未开启",
        NationalChannelState.ON_UNPROVISIONED: "国家通道待配置接入信息",
        NationalChannelState.ON_PROVISIONED: "国家通道已就绪",
    }[state]
    return {
        "enabled": state is not NationalChannelState.OFF,
        "provisioned": state is NationalChannelState.ON_PROVISIONED,
        "status": state.value,
        "notice": notice,
    }


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


# Module-level alias kept for callers that still reference `_mask` from brain.py
# (a few serializer-call lines in this file). Domain services should import
# ``mask_default`` from ``zw_brain.shared.sensitive_mask`` directly.
_mask = mask_default


DEFAULT_DISCOVERY_QUERY = "停车场信息"


# R-016: BrainServiceError + 6 subclasses + _RequestBatchContext moved to
# zw_brain.domain.errors; re-exported above via ``import X as X`` for handler /
# test call sites that still spell ``from zw_brain.command.brain import
# NotFoundError``. The domain layer no longer pays the cost of 25 lazy imports
# per service body to dodge a circular dependency.


class _UIStateProxy(MutableMapping[str, Any]):
    """Drop-in replacement for the old ``_ui_state`` dict.

    ``role`` is per-request and must NOT live on the process-global BrainService
    singleton (concurrent requests would overwrite each other between resolve and
    read). This proxy routes the ``role`` key to a ContextVar (thread / asyncio
    task isolated) while keeping ``discoveryQuery`` / ``brainOutage`` on a real
    backing dict. The mapping API is preserved so existing call sites
    (``_ui_state["role"]`` / ``.get("role", d)`` / ``_ui_state["role"] = x``)
    work unchanged and become concurrency-safe for free.

    Action F: per-request role lives in ``shared.ui_request_context`` ContextVar
    and is the authoritative read site for handlers/helpers (via ``ctx.role``).
    ``_ui_state`` is retained only as the persistence-shaped snapshot dict (for
    ``snapshot()`` / ``StateStore.save()`` round-tripping); no NEW handler code
    should access it — segment 46 (``check_handler_no_ui_state.py``) enforces
    this invariant. The single legitimate handler-side user (read+write) is
    ``b1/system_ops.py`` (process-global ``brainOutage`` toggle).

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
    def __init__(self, state_store: StateStore | None = None) -> None:
        self._state_store = state_store or StateStore()
        self._snapshot = self._state_store.load()
        # Action D：申请/审批/交付三聚合 DB 单一事实源——per-dispatch 卡片会话
        # （identity map + 指纹脏检），PersistMiddleware 写括号末尾 flush 落库。
        from zw_brain.command.card_session import CardSession  # noqa: PLC0415
        self._card_session = CardSession(
            lambda: getattr(self._state_store, "database_store", None)
        )
        # 顶层 dispatch 计数：invoke_skill 进入 0→1 时清会话纪元（防跨 dispatch 陈旧卡）；
        # 嵌套 dispatch（审批后自动签发凭据等）复用同一会话。
        self._dispatch_depth = 0
        # Cached HandlerDeps built lazily on first invoke_skill (Action A); the
        # container is process-wide stable except for `brain_legacy=self`, so a
        # one-time build is correct. Declared here (not as class attr) so each
        # BrainService instance has its own cache and reset_service() always
        # returns a fresh one.
        self._handler_deps: Any = None
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
            "nationalChannel": _national_channel_webui_state(),
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
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.j1.catalog_meta import _get_resource  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _get_resource(self, deps, ctx, *args, **kwargs)

    def get_request(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.j1.request import _get_request  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _get_request(self, deps, ctx, *args, **kwargs)

    def create_request(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.j1.request import _create_request  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _create_request(self, deps, ctx, *args, **kwargs)

    def get_delivery_task(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.j1.delivery import _get_delivery_task  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _get_delivery_task(self, deps, ctx, *args, **kwargs)

    def review_request(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.j1.approval import _review_request  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _review_request(self, deps, ctx, *args, **kwargs)

    def transition_api_resource(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.j1.resource_api import _transition_api_resource  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _transition_api_resource(self, deps, ctx, *args, **kwargs)

    def get_dispute(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.j1.governance_dispute import _get_dispute  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _get_dispute(self, deps, ctx, *args, **kwargs)

    def list_audit_events(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.b1.audit import _list_audit_events  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _list_audit_events(self, deps, ctx, *args, **kwargs)

    def list_packages(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.b1.capability_admin import _list_packages  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _list_packages(self, deps, ctx, *args, **kwargs)

    def evaluate_tenant_policy(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.j2.tenant_policy import _evaluate_tenant_policy  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _evaluate_tenant_policy(self, deps, ctx, *args, **kwargs)

    def list_zones(self, *args: Any, **kwargs: Any) -> Any:
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415
        from zw_brain.command.handlers.j2.zone import _list_zones  # noqa: PLC0415
        deps = self._get_handler_deps()
        # Delegate-shim ctx is a stub: callers may not have a skill_id in scope.
        # Helper body's ctx use is for ctx.role fallback (handled via payload.get) and
        # pipeline.write skill_id (which gets routed through brain._mutate adapter anyway).
        ctx = SkillContext(skill_id="", role=self._ui_state.get("role", ""), actor="",
                            confirmed=False, manifest={})
        return _list_zones(self, deps, ctx, *args, **kwargs)

    def invoke_skill(
        self, skill_id: str, payload: dict[str, Any] | None = None, *, source: str | None = None
    ) -> Any:
        # Action D：顶层 dispatch 进入清卡片会话纪元（嵌套 dispatch 复用，
        # 由写括号 flush 落库后自清）。try/finally 保证深度计数异常安全。
        if self._dispatch_depth == 0:
            self._card_session.clear()
        self._dispatch_depth += 1
        try:
            return self._invoke_skill_inner(skill_id, payload or {}, source=source)
        finally:
            self._dispatch_depth -= 1

    def _invoke_skill_inner(
        self, skill_id: str, payload: dict[str, Any], *, source: str | None = None
    ) -> Any:
        try:
            manifest = get_manifest(skill_id)
        except KeyError as exc:
            raise UnknownSkillError(skill_id) from exc
        self._validate_required_input(skill_id, manifest, payload)
        # mcp-hardening S2: stamp the calling surface into the payload so the
        # audit_event + capability_call rows carry provenance. A client-supplied
        # ``source`` key in the payload is NOT trusted — only the entry layer's
        # explicit ``source`` arg sets it (caller-controlled, never wire-controlled).
        if source is not None:
            payload = {**payload, "source": str(source)}
        role = self._resolve_role(payload, manifest=manifest)
        self._ui_state["role"] = role
        self._enforce_manifest_policy(skill_id, manifest, role, payload)
        # Action A: build per-call SkillContext + cached HandlerDeps. Handlers
        # signature is `(deps, ctx, payload)`; brain reverse-access goes
        # through deps.brain_legacy.X (preflight 段 40 whitelists allowed surface).
        ctx = self._build_skill_context(skill_id, role, payload, manifest, source=source)
        deps = self._get_handler_deps()
        if manifest.get("audit_required") and not manifest.get("side_effects"):
            # Route the traced read through the source-carrying ctx (not a rebuilt one),
            # so AuditEmitMiddleware stamps source=mcp on every phase (S2). _invoke_traced_read
            # stays as the legacy positional shim for in-process callers.
            from zw_brain.command import pipeline_ops  # noqa: PLC0415
            return pipeline_ops.run_traced_read(
                deps.pipeline, self._state_store, ctx, payload,
                lambda: self._dispatch_skill(deps, ctx, payload),
            )
        return self._dispatch_skill(deps, ctx, payload)

    def _build_skill_context(
        self, skill_id: str, role: str, payload: dict[str, Any], manifest: dict[str, Any],
        *, source: str | None = None,
    ) -> Any:
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
            source=source,
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
        # 未迁的 god-object surface 通过 deps.brain_legacy.X escape hatch（preflight 段 40 受控）。
        # Lazy import to break circular dep (brain → dispatch → handlers → brain.exceptions).
        from zw_brain.command import dispatch as _dispatch  # noqa: PLC0415
        handler = _dispatch.lookup(ctx.skill_id)
        if handler is None:
            raise UnknownSkillError(ctx.skill_id)
        return handler(deps, ctx, payload)

    def _governance_projection_repo(self) -> GovernanceProjectionRepository:
        store = self._state_store.database_store
        return store.governance_projection_repo if store is not None else GovernanceProjectionRepository()

    def _topic_package_repo(self) -> TopicPackageRepository:
        store = self._state_store.database_store
        return store.topic_package_repo if store is not None else TopicPackageRepository()

    # --- Action D commit 2: governance methods migrated to GovernanceService ---

    def _governance_audit_events(self, *, tenant_id: str, capability_filter: str = "", actor_filter: str = "") -> list[dict[str, Any]]:
        return self._get_handler_deps().services.governance.audit_events(
            tenant_id=tenant_id, capability_filter=capability_filter, actor_filter=actor_filter,
        )

    # --- Action D commit 2: topic_package methods migrated to TopicPackageService ---

    def _topic_package_list_projection(self, item: Any) -> dict[str, Any]:
        return self._get_handler_deps().services.topic_package.list_projection(item)

    def _topic_package_detail_to_dict(self, item: Any) -> dict[str, Any]:
        return self._get_handler_deps().services.topic_package.detail_to_dict(item)

    # --- Action D commit 2: catalog methods migrated to CatalogService ---
    # Body lives in zw_brain/domain/services/catalog_service.py; these are one-line
    # delegation shims so existing callers (test fixtures, sibling helpers) keep
    # working. Commit 5 retires the shims after the handler sweep is complete.

    def _catalog_is_discoverable(self, record: Any, store: Any) -> bool:
        return self._get_handler_deps().services.catalog.is_discoverable(record, store)

    # Action H commit 4: bodies lifted to zw_brain.command.adapter_routing.
    def _adapter_operation_from_skill(self, skill_id: str, payload: dict[str, Any]) -> tuple[str, str, str]:
        from zw_brain.command.adapter_routing import adapter_operation_from_skill  # noqa: PLC0415
        return adapter_operation_from_skill(skill_id, payload)

    def _aggregate_type_from_skill(self, skill_id: str) -> str:
        from zw_brain.command.adapter_routing import aggregate_type_from_skill  # noqa: PLC0415
        return aggregate_type_from_skill(skill_id)

    def _adapter_idempotency_key(self, skill_id: str, payload: dict[str, Any]) -> str:
        from zw_brain.command.adapter_routing import adapter_idempotency_key  # noqa: PLC0415
        return adapter_idempotency_key(skill_id, payload)


    def list_requests(self) -> list[dict[str, Any]]:
        """全部申请（运行时卡 + legacy 导入 apply 单）——Action D：DB 单一事实源。

        运行时单 = payload 卡（权威 status 列覆盖）+ ``record_to_request`` 增益
        覆盖（与退役前「快照行 + overlay」语义逐位一致：增益键覆盖、卡片特有键
        —— sharedType / fieldValues / timeline / aiDraft 等——存续），创建时间倒序；
        legacy 导入单走只读合成投影，随后追加。
        """
        store = self._state_store.database_store
        if store is None:
            return []
        # D-9 perf: prefetch four indices once, share via context to eliminate
        # ~5N full-table scans inside _application_record_to_request helpers.
        all_records = list(store.application_repo.list_records(tenant_id=_DEFAULT_TENANT_ID))
        context = self._build_request_batch_context(store, all_records)
        runtime_records = [r for r in all_records if is_runtime_request_payload(r.payload_json)]
        runtime_records.sort(key=lambda r: str(r.created_at or ""), reverse=True)
        items: list[dict[str, Any]] = []
        for record in runtime_records:
            item = copy.deepcopy(record.payload_json)
            item["status"] = record.status
            self._overlay_application_record(item, record, store, context=context)
            items.append(item)
        for record in all_records:
            if (record.payload_json or {}).get("kind") == "apply":
                items.append(self._application_record_to_request(record, store, context=context))
        return items

    # --- Action D commit 3: request methods migrated to RequestService ---

    def _build_request_batch_context(self, store: Any, application_records: list[Any]) -> _RequestBatchContext:
        return self._get_handler_deps().services.request.build_batch_context(store, application_records)

    def _audit_event_target(self, item: Any) -> str:
        payload = item.payload_json if isinstance(item.payload_json, dict) else {}
        target = self._audit_target_from_payload(item.request_id, payload)
        decision = payload.get("decision")
        return f"{target}:{decision}" if decision else target

    def list_delivery_tasks(self) -> list[dict[str, Any]]:
        """全部交付任务（运行时卡 + legacy 导入合成投影）——Action D：DB 单一事实源。

        运行时卡 = payload 卡（权威 state 列覆盖）+ repository/receipts 增益
        （与退役前「快照行 + overlay」语义一致），创建时间倒序；legacy 导入
        交付走 ``_delivery_task_from_record`` 只读合成，随后追加。
        """
        store = self._state_store.database_store
        if store is None:
            return []
        # 消费视图隐藏：退役类型（folder/url/link）来源 + 草稿态（存量交换流水线残留，未激活、含
        # hex 缺名/重复/测试噪声）。详见 delivery_record_hidden_from_consumer。先一次性建退役码集合。
        retired_codes = {
            asset.resource_code
            for asset in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID)
            if str(asset.resource_kind).strip().lower() in _RETIRED_RESOURCE_KINDS
        }
        runtime_records: list[Any] = []
        legacy_records: list[Any] = []
        for record in store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID):
            if _delivery_record_hidden_from_consumer(record, retired_codes):
                continue  # 退役类型 / 草稿态残留：不进消费视图
            if is_runtime_delivery_payload(record.payload_json):
                runtime_records.append(record)
            else:
                legacy_records.append(record)
        runtime_records.sort(key=lambda r: str(r.created_at or ""), reverse=True)
        tasks: list[dict[str, Any]] = []
        for record in runtime_records:
            task = copy.deepcopy(record.payload_json)
            task["status"] = record.state
            if not task.get("resourceKind"):
                # 与 legacy 合成投影同口径兜底（F3/F4 操作分流依赖此键；直写
                # 注入的运行时卡可能只带 snake resource_kind）。
                task["resourceKind"] = _delivery_resource_kind(
                    task.get("resource_kind") or (task.get("access_grant") or {}).get("res_type"),
                    record.channel,
                )
            task["repository"] = {
                "deliveryCode": record.delivery_code,
                "applicationCode": record.application_code,
                "channel": record.channel,
            }
            task["receipts"] = self._get_handler_deps().services.delivery.receipts_for(
                store.delivery_repo, record.delivery_code
            )
            tasks.append(task)
        for record in legacy_records:
            task = self._delivery_task_from_record(record.delivery_code, store, record=record)
            if task is not None:
                tasks.append(task)
        return tasks

    # --- Action D commit 4: provider methods migrated to ProviderService ---

    def _overlay_application_record(
        self,
        request: dict[str, Any],
        record: Any,
        store: Any,
        *,
        context: _RequestBatchContext | None = None,
    ) -> None:
        return self._get_handler_deps().services.application.overlay_record(request, record, store, context=context)

    # --- Action D commit 3: application_record_to_request migrated to ApplicationService ---

    def _application_record_to_request(
        self,
        record: Any,
        store: Any,
        *,
        context: _RequestBatchContext | None = None,
    ) -> dict[str, Any]:
        return self._get_handler_deps().services.application.record_to_request(record, store, context=context)

    # --- Action D commit 3: delivery methods migrated to DeliveryService ---

    def _delivery_task_from_record(
        self,
        request_id: str,
        store: Any,
        *,
        context: _RequestBatchContext | None = None,
        record: Any | None = None,
    ) -> dict[str, Any] | None:
        return self._get_handler_deps().services.delivery.task_from_record(request_id, store, context=context, record=record)

    def _mask_actor_payload(self, value: Any) -> Any:
        """Legacy shim — Action H commit 4 lifted to shared.sensitive_mask.mask_actor_payload."""
        from zw_brain.shared.sensitive_mask import mask_actor_payload  # noqa: PLC0415
        return mask_actor_payload(value)

    def _approval_recommendation(self, approval: dict[str, Any], request: dict[str, Any], delivery: dict[str, Any] | None) -> dict[str, Any]:
        """Legacy shim — Action H commit 3 lifted to request_service.approval_recommendation."""
        return self._get_handler_deps().services.request.approval_recommendation(approval, request, delivery)

    def _approval_business_defaults(self, request: dict[str, Any], delivery: dict[str, Any] | None) -> dict[str, Any]:
        """Legacy shim — Action H commit 3 lifted to request_service.approval_business_defaults."""
        return self._get_handler_deps().services.request.approval_business_defaults(request, delivery)

    def _delivery_repo(self) -> DeliveryRepository:
        store = self._state_store.database_store
        return store.delivery_repo if store is not None else DeliveryRepository()

    def _discovery_summary(self, query: str, resources: list[dict[str, Any]]) -> dict[str, Any]:
        """Legacy shim — Action H commit 3 lifted body to catalog_service.discovery_summary."""
        return self._get_handler_deps().services.catalog.discovery_summary(query, resources)

    def _api_payload(self, payload: dict[str, Any], *, default_status: str) -> dict[str, Any]:
        """Legacy shim — Action H commit 3 lifted body to provider_service.api_payload."""
        return self._get_handler_deps().services.provider.api_payload(payload, default_status=default_status)

    # Action H commit 2: bodies lifted to provider_service / ops_metrics serializers.
    def _upsert_api_resource(self, resource: dict[str, Any]) -> dict[str, Any]:
        return self._get_handler_deps().services.provider.upsert_api_resource(resource)

    def _upsert_api_binding(self, binding: dict[str, Any]) -> dict[str, Any]:
        return self._get_handler_deps().services.provider.upsert_api_binding(binding)

    # Action E: _find_api_resource retired — call deps.services.provider.find_api_resource directly.

    def _find_api_binding(self, binding_code: str) -> dict[str, Any] | None:
        return self._get_handler_deps().services.provider.find_api_binding(binding_code)

    def _metric_summary(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        from zw_brain.domain.serializers.ops_metrics import metric_summary  # noqa: PLC0415
        return metric_summary(metrics)

    def _decode_iaf_claims(self, iaf_claims: Any) -> dict[str, Any]:
        if isinstance(iaf_claims, dict):
            return safe_json(iaf_claims)
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
        return safe_json(payload)

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
        return self._get_handler_deps().services.catalog.record_to_card_dict(record)

    def _enrich_catalog_detail(self, detail: dict[str, Any], record: Any, store: Any, *, focused_resource_code: str | None = None, context: _RequestBatchContext | None = None) -> None:
        return self._get_handler_deps().services.catalog.enrich_detail(detail, record, store, focused_resource_code=focused_resource_code, context=context)

    def _catalog_field_dicts(self, catalog_code: str, store: Any, *, context: _RequestBatchContext | None = None) -> list[dict[str, Any]]:
        return self._get_handler_deps().services.catalog.field_dicts(catalog_code, store, context=context)

    def _legacy_mapping_refs(
        self,
        store: Any,
        canonical_type: str,
        canonical_ref: str | list[str],
        *,
        context: _RequestBatchContext | None = None,
    ) -> list[dict[str, Any]]:
        """Legacy shim — Action H commit 2 lifted body to serializers/legacy_mapping.py."""
        from zw_brain.domain.serializers.legacy_mapping import legacy_mapping_refs  # noqa: PLC0415
        return legacy_mapping_refs(store, canonical_type, canonical_ref, context=context)

    def _reuse_gap_hint(self, fields: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> dict[str, Any]:
        mapped_codes = {item.get("catalog_item_code") for item in mappings}
        missing = [field["title"] for field in fields if field["item_code"] not in mapped_codes]
        return {
            "reusable": len(mappings) > 0 or len(fields) > 0,
            "readyFieldCount": len(fields) - len(missing),
            "gapFields": missing,
            "message": "已有目录字段和资源绑定证据，可先复用；未绑定字段作为缺口说明进入最小申请。" if missing else "已有字段证据可复用，申请时只选择本次确需字段。",
        }

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
            # PERF: push resource_code filter into SQL (.in_()) — see catalog_service
            # 同款收口；空 set → repo 直接返回 []。
            snapshots_iter = store.metadata_evidence_repo.list_schema_snapshots(resource_codes=list(resource_codes), tenant_id=_DEFAULT_TENANT_ID)
        out: dict[Any, Any] = {}
        for snapshot in snapshots_iter:
            schema = snapshot.schema_json if isinstance(snapshot.schema_json, dict) else {}
            for ref_key in ("meta_id", "id", "column_id", "field_id"):
                ref = schema.get(ref_key)
                if ref in refs:
                    out[ref] = schema.get("column_name") or schema.get("name_en") or schema.get("name_cn") or ref
        return out

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

    def grant_delivery_access(self, task_id: str, role: str, confirmed: bool) -> dict[str, Any]:
        task = self._get_handler_deps().services.delivery.by_id(task_id)
        if task["status"] not in {"pending", "warning", "reconciling", "supplementing"}:
            raise InvalidStateError("delivery task cannot grant access in current state")

        # P1-3 cross-aggregate fail-closed guard (46f0): the delivery task status alone does
        # not reflect the bound application being withdrawn/rejected/revoked. Re-check the
        # bound application's status against the terminal-negative set before granting; a
        # terminal-negative application can no longer authorize delivery. (Lookup miss →
        # do not invent a new failure mode; the task-status gate above still applies.)
        application_code = task.get("requestId")
        store = self._state_store.database_store
        if application_code and store is not None:
            bound_application = store.application_repo.get_record(
                application_code, tenant_id=_DEFAULT_TENANT_ID
            )
            if (
                bound_application is not None
                and bound_application.status in _TERMINAL_NEGATIVE_APPLICATION_STATUSES
            ):
                raise InvalidStateError(
                    "cannot grant delivery access: bound application is in a terminal-negative "
                    f"state ({bound_application.status})"
                )

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
            task["aiSummary"]["summary"] = "访问授权已生效，当前可进入使用监测、交换结果核对或模板回流确认。"
            task["aiSummary"]["nextAction"] = "继续监测调用与回执，如存在高频差异字段再进入供给侧治理。"
            store = self._state_store.database_store
            if store is not None:
                store.delivery_repo.upsert_from_delivery(task, tenant_id=_DEFAULT_TENANT_ID)
            self._append_audit_feed("delivery.access.grant", task_id, "ok", actor)
            return {"task_id": task_id, "status": task["status"], "grant_ref": task["access"]["grant_ref"]}

        return self._mutate("delivery.access.grant", role, confirmed, {"task_id": task_id}, mutation)

    def _resolve_role(self, payload: dict[str, Any], *, manifest: dict[str, Any] | None = None) -> str:
        from zw_brain.shared.auth_context import (
            SYSTEM_ORIGIN_KEY,
            IdentityRoleForbiddenError,
            is_system_origin_payload,
            resolve_role_from_identity,
        )
        from zw_brain.shared.session_context import (
            TRUSTED_SESSION_CONTEXT_KEY,
            is_trusted_session_payload,
            resolve_trusted_role,
        )

        try:
            if is_trusted_session_payload(payload):
                # Cookie BFF path: role already stamped from the verified session by
                # build_trusted_skill_payload. The trusted-session branch is exempt from
                # the identity-boundary resolver below and stays unchanged.
                snapshot = payload.get("actor_snapshot")
                if not isinstance(snapshot, dict):
                    raise AccessDeniedError("trusted session requires actor_snapshot")
                return resolve_trusted_role(payload, actor_snapshot=snapshot)
            # System-origin / internal already-authorized call (in-process sentinel; a
            # remote client cannot forge `is`-equality): act as the supplied infra role
            # (e.g. "system" for IAM first-login projection) without the identity boundary.
            # policy.resolve_role + enforce_manifest_policy still validate the role/perms.
            system_origin = is_system_origin_payload(payload)
            # Client-supplied payloads (Bearer / A2A / MCP / CLI entry paths) cannot
            # claim trust: only `build_trusted_skill_payload` stamps the in-process
            # sentinel. Strip any smuggled value so downstream copies / audit dumps
            # don't surface a misleading "_trusted_session_context: True".
            payload.pop(TRUSTED_SESSION_CONTEXT_KEY, None)
            payload.pop(SYSTEM_ORIGIN_KEY, None)
            if system_origin:
                return policy.resolve_role(payload.get("role"), self._ui_state.get("role", "ROLE_ORGAN_OPERATER"))
            # C1/N1 shared boundary: the role a non-cookie caller may act as is governed
            # by the *verified identity* in the request-scoped AuthContext, NOT by the
            # literal payload["role"]. Every authenticated consumer surface (REST bearer,
            # MCP, A2A, CLI) establishes an AuthContext (real token claims, or the
            # dev-bypass synthetic full-role identity), so this one resolver protects all
            # of them. In-process / system-origin calls set no AuthContext and keep legacy
            # resolution. side_effects → write semantics (forge of an unheld role is denied,
            # not degraded). filter validity / unknown-role checks stay in policy.resolve_role.
            side_effects = bool((manifest or {}).get("side_effects"))
            candidate = resolve_role_from_identity(
                str(payload.get("role") or ""),
                self._ui_state.get("role", "ROLE_ORGAN_OPERATER"),
                is_write=side_effects,
            )
            return policy.resolve_role(candidate, self._ui_state.get("role", "ROLE_ORGAN_OPERATER"))
        except IdentityRoleForbiddenError as exc:
            raise AccessDeniedError(str(exc)) from exc
        except DomainAccessDeniedError as exc:
            raise AccessDeniedError(str(exc)) from exc

    def _enforce_manifest_policy(self, skill_id: str, manifest: dict[str, Any], role: str, payload: dict[str, Any]) -> None:
        try:
            policy.enforce_manifest_policy(skill_id, manifest, role, payload)
        except DomainAccessDeniedError as exc:
            # ops-deny-audit (D4 审计脊柱): 越权 deny 此前无痕 —— deny 在 PolicyMiddleware
            # 最外层抛出，AuditEmitMiddleware（更内层）的 try/except 看不到，故零审计事件。
            # _enforce_manifest_policy 是读/写两条路径策略门的唯一收口点（invoke_skill 读前 +
            # PolicyMiddleware 写前都经此），在此统一发 decision=deny 审计事件，覆盖 5 消费面。
            denied = AccessDeniedError(str(exc))
            try:
                self._emit_deny_audit(skill_id, role, payload, str(exc))
            except Exception as audit_exc:  # noqa: BLE001
                # 非阻塞：deny 审计写失败仅告警，不把既有 deny→403 契约改成 500。
                # 「deny 审计写失败是否熔断」是状态机决策，须业务方 sign-off（debt ops-deny-audit），
                # 本期不擅改 —— 保守保留 deny 响应不变，仍抛 deny（满足 D4 段7a「不得吞错继续」：
                # 此处不静默继续，而是抛出 deny）。成功路径既有熔断语义一字未动。
                _LOGGER.warning(
                    "deny-audit emit failed (deny still enforced): skill=%s role=%s err=%s",
                    skill_id, role, audit_exc,
                )
                raise denied from exc
            raise denied from exc

    def _emit_deny_audit(self, skill_id: str, role: str, payload: dict[str, Any], reason: str) -> None:
        """Emit a synchronous ``decision=deny`` audit event for a refused capability.

        Reuses the canonical ``_emit_audit`` path (pipeline_ops.emit_audit 10-branch
        enrichment) so deny rows carry the same actor_snapshot / audit_class /
        source provenance as success-path rows. ``phase="error"`` mirrors the
        AuditEmitMiddleware error-phase shape; ``decision="deny"`` makes the row
        queryable as an authorization refusal. ``payload`` is passed through
        ``safe_json`` inside emit_audit (trust sentinel stripped); only the attempted
        skill + refusal reason are added — no widening of what gets logged.
        """
        actor = self._actor_for_role(role)
        deny_payload = {
            **payload,
            "decision": "deny",
            "decision_reason": reason,
            "outcome": "denied",
            "attempted_skill_id": skill_id,
        }
        self._emit_audit(ids.new_audit_id(), actor, skill_id, "error", deny_payload)

    def _invoke_traced_read(self, skill_id: str, role: str, payload: dict[str, Any], operation: Any) -> Any:
        """Legacy shim — delegates to ``pipeline_ops.run_traced_read``.

        Action E: cross-cutting body lives in ``zw_brain.command.pipeline_ops``.
        Kept on BrainService as a thin adapter for in-process callers (test
        fixtures, scripts) that still construct skill_id/role/operation
        positionally rather than going through ``deps.pipeline.read``.
        """
        from zw_brain.command import pipeline_ops  # noqa: PLC0415
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415

        ctx = SkillContext(
            skill_id=skill_id, role=role, actor=self._actor_for_role(role),
            confirmed=False, manifest=get_manifest(skill_id),
        )
        deps = self._get_handler_deps()
        return pipeline_ops.run_traced_read(deps.pipeline, self._state_store, ctx, payload, operation)

    def _mutate(self, skill_id: str, role: str, confirmed: bool, payload: dict[str, Any], mutation: Any) -> dict[str, Any]:
        """Legacy shim — delegates to ``pipeline_ops.run_mutation``.

        Action E: cross-cutting body lives in ``zw_brain.command.pipeline_ops``.
        Kept on BrainService as a thin adapter for legacy callers that pass
        skill_id/role/confirmed positionally rather than going through
        ``deps.pipeline.write``.
        """
        from zw_brain.command import pipeline_ops  # noqa: PLC0415
        from zw_brain.command.deps import SkillContext  # noqa: PLC0415

        ctx = SkillContext(
            skill_id=skill_id, role=role, actor=self._actor_for_role(role),
            confirmed=confirmed, manifest=get_manifest(skill_id),
        )
        deps = self._get_handler_deps()
        return pipeline_ops.run_mutation(deps.pipeline, ctx, payload, mutation)

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
        """Legacy shim — delegates to ``pipeline_ops.record_capability_call``."""
        from zw_brain.command import pipeline_ops  # noqa: PLC0415

        pipeline_ops.record_capability_call(
            self._state_store, self._audit_target_from_payload,
            audit_id, actor, role, skill_id, payload, result, started_at, status=status,
        )

    def _persist(self) -> None:
        """Legacy shim — delegates to ``sync.persist``."""
        from zw_brain.command import sync as state_sync  # noqa: PLC0415
        state_sync.persist(self._state_store, self._snapshot, self._ui_state.persistable_view())

    def _emit_audit(self, request_id: str, actor: str, skill_id: str, phase: str, payload: dict[str, Any]) -> None:
        """Legacy shim — delegates to ``pipeline_ops.emit_audit``.

        Action E: 10-branch payload enrichment lives in
        ``zw_brain.command.pipeline_ops.emit_audit``. The two small resolvers
        (``_audit_decision_reason`` / ``_audit_target_from_payload``) are
        passed as callables so callers that need custom resolution can
        override; default path uses the legacy resolvers verbatim.
        """
        from zw_brain.command import pipeline_ops  # noqa: PLC0415

        pipeline_ops.emit_audit(
            audit_bus,
            get_manifest,
            self._audit_decision_reason,
            self._audit_target_from_payload,
            request_id, actor, skill_id, phase, payload,
        )

    def _audit_decision_reason(self, phase: str, payload: dict[str, Any]) -> str:
        from zw_brain.command import pipeline_ops  # noqa: PLC0415
        return pipeline_ops.default_decision_reason(phase, payload)

    def _enqueue_anchor(self, request_id: str, actor: str, skill_id: str, payload: dict[str, Any]) -> None:
        """Legacy shim — delegates to ``pipeline_ops.enqueue_anchor``.

        Action E: content hash + outbox row + asyncio.run(queue.enqueue)
        body lives in ``zw_brain.command.pipeline_ops.enqueue_anchor``. Fail-
        soft semantics (per D4) live in ``AnchorMiddleware`` — this shim
        propagates any exception verbatim.
        """
        from zw_brain.command import pipeline_ops  # noqa: PLC0415
        pipeline_ops.enqueue_anchor(queue, self._state_store, request_id, actor, skill_id, payload)

    def _sync_reference_tables(self) -> None:
        """Legacy shim — delegates to ``sync.sync_reference_tables``."""
        from zw_brain.command import sync as state_sync  # noqa: PLC0415
        state_sync.sync_reference_tables(self._state_store, self.snapshot())

    def _sync_database_aggregates(self) -> None:
        """Legacy shim — delegates to ``sync.sync_database_aggregates``."""
        from zw_brain.command import sync as state_sync  # noqa: PLC0415
        state_sync.sync_database_aggregates(self._state_store, self.snapshot())

    def _append_audit_feed(self, event_type: str, target: str, result: str, actor: str) -> None:
        """Legacy shim — delegates to ``pipeline_ops.append_audit_feed``."""
        from zw_brain.command import pipeline_ops  # noqa: PLC0415
        pipeline_ops.append_audit_feed(self._snapshot, event_type, target, result, actor)

    def _audit_target_from_payload(self, request_id: str, payload: dict[str, Any]) -> str:
        from zw_brain.command import pipeline_ops  # noqa: PLC0415
        return pipeline_ops.default_target_ref(request_id, payload)

    def _sync_state_views(self) -> None:
        """Legacy shim — delegates to ``sync.sync_state_views``.

        Action H: ``sync_state_views`` now takes the snapshot dict and a
        pure ``status_text`` callback; no BrainService reference required
        inside the sync module.
        """
        from zw_brain.command import sync as state_sync  # noqa: PLC0415
        state_sync.sync_state_views(
            self._snapshot,
            self._state_store.database_store,
            self._get_handler_deps().services.request.status_text,
        )

    # R-005 fix: 折叠后多个旧角色映射到同一 ROLE_*，原本不同语境（申请进度 vs 差异补录 vs 现场补录 vs 汇总）
    # 的同 item_id 待办若仅按 (role, item_id) 去重会互相覆盖。引入 category 作为第二维度。
    # Action H: thin delegate to demo_state_sync module-level helper; remaining
    # call sites in handlers/j2/compliance.py + demo cascade are unchanged.
    def _set_todo_status(self, role: str, item_id: str, status: str, *, category: str = "") -> None:
        from zw_brain.command import demo_state_sync  # noqa: PLC0415
        demo_state_sync.set_todo_status(self._snapshot, role, item_id, status, category=category)

    def _request_status_text(self, item: dict[str, Any], perspective: str = "reviewer") -> str:
        return self._get_handler_deps().services.request.status_text(item, perspective)

    def _package_status_text(self, item: dict[str, Any]) -> str:
        """Legacy shim — delegates to demo_state_sync.package_status_text (Action H)."""
        from zw_brain.command import demo_state_sync  # noqa: PLC0415
        return demo_state_sync.package_status_text(item)

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

    # Action E: _request_by_id / _delivery_by_id / _delivery_by_request_id /
    # _find_api_resource retired — call deps.services.{request,delivery,provider}.X
    # or deps.view.<entity>.find_by_id directly. _maybe_* helpers kept because
    # demo_state_sync / brain.py internal call sites tolerate None on miss.

    def _resource_by_id(self, resource_id: str) -> dict[str, Any]:
        """Legacy shim — delegates to demo_state_sync.resource_by_id (Action H)."""
        from zw_brain.command import demo_state_sync  # noqa: PLC0415
        return demo_state_sync.resource_by_id(self._snapshot, resource_id)

    def _resolve_resource_for_application(self, resource_id: str) -> dict[str, Any]:
        """Legacy shim — Action H commit 4 lifted to catalog_service.resolve_resource_for_application."""
        return self._get_handler_deps().services.catalog.resolve_resource_for_application(resource_id)

    def _zone_by_id(self, zone_id: str) -> dict[str, Any]:
        """Legacy shim — delegates to demo_state_sync.zone_by_id (Action H)."""
        from zw_brain.command import demo_state_sync  # noqa: PLC0415
        return demo_state_sync.zone_by_id(self._snapshot, zone_id)


    # R-005 fix: 同 R-005 — 待办按 (role, item_id, category) 唯一；折叠后多个语境的同 item_id 可共存。
    # Action H: thin delegate to demo_state_sync module-level helper.
    def _upsert_todo(self, role: str, item_id: str, title: str, status: str, href: str, *, category: str = "") -> None:
        from zw_brain.command import demo_state_sync  # noqa: PLC0415
        demo_state_sync.upsert_todo(self._snapshot, role, item_id, title, status, href, category=category)

    def _sync_request_todos(self) -> None:
        """Legacy shim — delegates to ``sync.sync_request_todos``.

        Action H: takes snapshot dict + status_text callback; no BrainService
        reference required inside the sync module.
        """
        from zw_brain.command import sync as state_sync  # noqa: PLC0415
        state_sync.sync_request_todos(
            self._snapshot,
            self._state_store.database_store,
            self._get_handler_deps().services.request.status_text,
        )

    def _new_request_id(self) -> str:
        return self._get_handler_deps().services.request.new_request_id()

    def _delivery_task_id_for_request(self, request_id: str) -> str:
        return self._get_handler_deps().services.delivery.task_id_for_request(request_id)

    # ============== J1 凭据签发与查询（D27/U-3 处置承诺的凭据领取闭环） ==============

    def _credential_for_request(self, request_id: str, seed: str | None = None) -> dict[str, Any]:
        """Legacy shim — Action H commit 4 lifted to request_service.credential_for_request."""
        return self._get_handler_deps().services.request.credential_for_request(request_id, seed=seed)

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
        delivery = self._get_handler_deps().services.delivery.by_request_id(request_id)
        if delivery is None:
            return
        # Action D：secret 不落库——已签发与否看签发事实（issued_audit_id），
        # 不看 credential 键（持久化后必缺）。
        grant_snapshot = delivery.get("accessGrantSnapshot") or {}
        if grant_snapshot.get("credential") or grant_snapshot.get("issued_audit_id"):
            return
        # 通过 invoke_skill 路径触发；权限/审计/锚定一气呵成
        self.invoke_skill("credential.issue", {
            "request_id": request_id,
            "role": role,
            "confirmed": True,
        })

