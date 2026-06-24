from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from zw_brain.command.brain import AccessDeniedError, BrainService
from zw_brain.domain import policy
from zw_brain.domain.repositories.agent_runtime_state import AgentRuntimeStateRepository
from zw_brain.domain.role_codes import BUSINESS_ROLE_CODES, ROLE_DISPLAY_NAMES_ZH
from zw_brain.shared.agent_runtime.capability_provider import (
    agent_directory_for_id,
    load_capability_bindings,
)
from zw_brain.shared.agent_runtime.config import agents_dir, is_agent_runtime_enabled

# 异常类住 shared 层（service.py 在 shared，不得反向 import command）；此处重导出，
# 保持 `bridge.AgentRuntimeNotEnabledError` / `bridge.AgentRuntimeNotFoundError`
# 既有引用有效，且与 service.py raise 的是同一个类对象（except 能接住）。
from zw_brain.shared.agent_runtime.errors import (  # noqa: F401  (re-export)
    AgentRuntimeNotEnabledError,
    AgentRuntimeNotFoundError,
    AgentRuntimePermissionError,
)

_TASK_METADATA_FIELDS = frozenset(
    {
        "request_id",
        "tenant_id",
        "org_code",
        "current_org_code",
    }
)

_DEFAULT_TENANT_ID = "sd-default"
_AGENT_ASSIGNABLE_ROLE_CODES = tuple(role for role in BUSINESS_ROLE_CODES if role != "ROLE_SYSTEM")
_AGENT_ASSIGNABLE_ROLE_SET = set(_AGENT_ASSIGNABLE_ROLE_CODES)


class AgentRuntimeDisabledByOpsError(PermissionError):
    pass


def runtime_status() -> dict[str, Any]:
    # 公开健康面只暴露 enable/ready/status；Agent topology（agent_id / capability_skills）
    # 仅通过 /api/agent-runtime/agents 在鉴权后返回。
    if not is_agent_runtime_enabled():
        return {"enabled": False, "ready": False, "status": "disabled"}
    try:
        from zw_brain.shared.agent_runtime.service import runtime_health

        runtime_health()
    except Exception as exc:  # noqa: BLE001 — health 必须 fail-closed，但不把拓扑泄漏到公网健康面。
        return {
            "enabled": False,
            "configured": True,
            "ready": False,
            "status": "service_unreachable",
            "detail": str(exc)[:200],
        }
    return {"enabled": True, "configured": True, "ready": True, "status": "running"}


def _authorization_mode(labels: dict[str, Any]) -> str:
    mode = str(labels.get("agent_authorization_mode") or "all_tools").strip().lower()
    return mode if mode in {"all_tools", "any_read_tool"} else "all_tools"


def _role_can_use_bindings(
    *,
    role: str,
    bindings: list[dict[str, Any]],
    authorization_mode: str,
) -> bool:
    from zw_brain.capability_registry.runtime import get_manifest

    matched = False
    for binding in bindings:
        skill_id = binding["skill_id"]
        try:
            manifest = get_manifest(skill_id)
            policy.enforce_manifest_policy(skill_id, manifest, role, {})
        except (KeyError, policy.DomainAccessDeniedError):
            if authorization_mode == "all_tools":
                return False
            continue
        matched = True
        if authorization_mode == "any_read_tool":
            return True
    return matched


def _roles_that_can_use(
    bindings: list[dict[str, Any]],
    *,
    authorization_mode: str = "all_tools",
) -> list[str]:
    """返回能通过该 Agent 绑定 skill policy 的角色集。这是 UI 落位的单一事实源：

      - 数据应用画廊只渲染 caller 角色 ∈ 该集合的卡片（no-permission=invisible，
        不再「可见+403」死胡同，见 #294/#296/#297 反复诉讼的反模式）；
      - 403 文案据此列出「可切换到」的具体岗位名。

    默认 ``all_tools`` 沿用历史口径；显式声明 ``any_read_tool`` 的统一只读入口，
    只要求角色至少能使用一个绑定能力。单个能力调用仍由 ``invoke_skill`` 按
    原 manifest policy 守门。返回 [] 表示无任何角色可用（视为对所有人不可见）。"""

    allowed: list[str] = []
    for role in BUSINESS_ROLE_CODES:
        if _role_can_use_bindings(
            role=role,
            bindings=bindings,
            authorization_mode=authorization_mode,
        ):
            allowed.append(role)
    return allowed


def list_builtin_agents(
    *,
    role: str | None = None,
    tenant_id: str = _DEFAULT_TENANT_ID,
    state_overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    state_repo = AgentRuntimeStateRepository()
    state_by_agent = state_repo.list_states(tenant_id=tenant_id)
    if state_overrides:
        state_by_agent = {**state_by_agent, **state_overrides}
    items: list[dict[str, Any]] = []
    for agent_yaml in sorted(agents_dir().glob("*/AGENT.yaml")):
        agent, sidecar = _load_agent_files(agent_yaml)
        metadata = agent.get("metadata") if isinstance(agent.get("metadata"), dict) else {}
        agent_id = str(metadata.get("id") or "")
        if not agent_id:
            continue
        # UI 落位的单一事实源：labels.surface 显式声明该 Agent 属哪种产品对象。
        # D68 后 /data-apps 升级为【智能体】入口，surface=agent 是 A/B 场景智能体清单；
        # 旧 data-app 仍兼容归入 agent，copilot 保留给页内嵌副驾。
        labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
        surface = str(labels.get("surface") or "").strip().lower()
        category = "agent" if surface in {"agent", "data-app"} else "copilot"
        agent_class = str(labels.get("scenario_class") or sidecar.get("scenario_class") or "").strip().upper()
        if agent_class not in {"A", "B"}:
            agent_class = "A" if category == "copilot" else "B"
        runtime_ready = _truthy(labels.get("runtime_ready")) or bool(sidecar.get("runtime_ready"))
        net_new = str(labels.get("net_new") or sidecar.get("net_new") or "none").strip() or "none"
        bindings = load_capability_bindings(agent_yaml.parent)
        raw_quick_questions = metadata.get("quick_questions")
        if not isinstance(raw_quick_questions, list):
            raw_quick_questions = sidecar.get("quick_questions")
        quick_questions = [
            str(item).strip()
            for item in (raw_quick_questions if isinstance(raw_quick_questions, list) else [])
            if str(item).strip()
        ][:3]
        authorization_mode = _authorization_mode(labels)
        policy_allowed_roles = _roles_that_can_use(bindings, authorization_mode=authorization_mode)
        default_allowed_roles = [
            role_code for role_code in policy_allowed_roles if role_code in _AGENT_ASSIGNABLE_ROLE_SET
        ]
        state_record = state_by_agent.get(agent_id)
        raw_state = state_repo.to_dict(state_record, default_roles=default_allowed_roles)
        configured_roles = [
            role_code
            for role_code in raw_state["allowed_roles"]
            if role_code in _AGENT_ASSIGNABLE_ROLE_SET
        ]
        if state_record is not None and not raw_state["allowed_roles"]:
            configured_roles = []
        state = dict(raw_state)
        state["allowed_roles"] = configured_roles
        visible_enabled = bool(state["enabled"])
        # ROLE_SYSTEM 是平台运维调试旁路：可查看、可打开全部已启用且 runtime-ready 的智能体。
        # configured_roles 仍只表示业务岗位授权，不限制平台运维员本人。
        caller_can_use = bool(
            role
            and visible_enabled
            and runtime_ready
            and (role == "ROLE_SYSTEM" or role in configured_roles)
        )
        ops_visible = role == "ROLE_SYSTEM"
        if role and not ops_visible and not caller_can_use:
            continue
        items.append(
            {
                "id": agent_id,
                "agent_id": agent_id,
                "name": metadata.get("name"),
                "version": metadata.get("version"),
                "trust_level": metadata.get("trust_level") or sidecar.get("trust_level"),
                "description": metadata.get("description"),
                "quick_questions": quick_questions,
                "capability_skills": [b["skill_id"] for b in bindings],
                "category": category,
                "surface": surface or "copilot",
                "agent_class": agent_class,
                "agent_type_label": "A 类 · 平台办事助手" if agent_class == "A" else "B 类 · 场景用数助手",
                "runtime_ready": runtime_ready,
                "enabled": visible_enabled,
                "callable": caller_can_use,
                "assignable_roles": list(_AGENT_ASSIGNABLE_ROLE_CODES),
                "assignable_role_names": [ROLE_DISPLAY_NAMES_ZH.get(r, r) for r in _AGENT_ASSIGNABLE_ROLE_CODES],
                "policy_allowed_roles": policy_allowed_roles,
                "policy_allowed_role_names": [ROLE_DISPLAY_NAMES_ZH.get(r, r) for r in policy_allowed_roles],
                "authorization_mode": authorization_mode,
                "net_new": net_new,
                "tool_count": len(bindings),
                # 调用方角色须 ∈ allowed_roles 才可用本 Agent（与 task 启动鉴权同口径）。
                # 前端据此过滤卡片（无权不渲染）+ 渲染 403「可切换到」岗位名。
                "allowed_roles": configured_roles,
                "allowed_role_names": [ROLE_DISPLAY_NAMES_ZH.get(r, r) for r in configured_roles],
                "state": state,
            }
        )
    return items


def update_agent_state(
    *,
    agent_id: str,
    enabled: bool,
    allowed_roles: list[str] | None,
    updated_by: str | None,
    reason: str | None,
    tenant_id: str = _DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    agent = _agent_catalog_item(agent_id, tenant_id=tenant_id)
    default_roles = [
        role_code for role_code in agent["policy_allowed_roles"] if role_code in _AGENT_ASSIGNABLE_ROLE_SET
    ]
    requested_set = set(default_roles if allowed_roles is None else allowed_roles)
    invalid = sorted(requested_set - _AGENT_ASSIGNABLE_ROLE_SET)
    if invalid:
        raise AccessDeniedError(f"invalid agent authorization roles: {', '.join(invalid)}")
    requested_roles = [role_code for role_code in _AGENT_ASSIGNABLE_ROLE_CODES if role_code in requested_set]
    record = AgentRuntimeStateRepository().set_state(
        agent_id,
        tenant_id=tenant_id,
        enabled=enabled,
        allowed_roles=requested_roles,
        updated_by=updated_by,
        reason=reason,
    )
    return _agent_catalog_item(agent_id, tenant_id=tenant_id, state_record=record)


def reload_agents() -> dict[str, Any]:
    if not is_agent_runtime_enabled():
        raise AgentRuntimeNotEnabledError("ZW_BRAIN_AGENT_RUNTIME_ENABLED is not set")
    from zw_brain.shared.agent_runtime.service import reload_agents as _reload

    try:
        return _reload()
    except AgentRuntimeNotFoundError:
        return {"ok": False, "status": "unsupported", "detail": "runtime reload endpoint is not available"}


def runtime_diagnostics() -> dict[str, Any]:
    if not is_agent_runtime_enabled():
        return {"enabled": False, "status": "service_not_started"}
    from zw_brain.shared.agent_runtime.service import runtime_diagnostics as _diagnostics

    try:
        return _diagnostics()
    except AgentRuntimeNotFoundError:
        return runtime_status() | {"diagnostics": "unsupported"}
    except Exception as exc:  # noqa: BLE001
        return runtime_status() | {"diagnostics": "unavailable", "detail": str(exc)[:200]}


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_task_metadata(
    *,
    role: str,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一构建传递给 AgentRuntime 的 task_metadata。

    Browser BFF calls pass through ``build_trusted_skill_payload`` and therefore
    carry process-local trust markers plus actor snapshots. Those are meaningful
    only inside zw-brain and must not cross the standalone AR HTTP JSON boundary.
    """
    raw = metadata or {}
    task_metadata = {
        key: value
        for key in _TASK_METADATA_FIELDS
        if _metadata_scalar(value := raw.get(key))
    }
    if request_id:
        task_metadata["request_id"] = request_id
    task_metadata["caller_role"] = role
    return task_metadata


def _metadata_scalar(value: Any) -> bool:
    return value is not None and isinstance(value, str | int | float | bool)


def _verify_agent_and_policy(
    *,
    agent_id: str,
    role: str,
) -> None:
    """鉴权：验证 agent 存在且调用方有权限访问其绑定的所有 skill。"""
    agent_path = _resolve_agent_dir(agent_id)
    if agent_path is None:
        raise AgentRuntimeNotFoundError(agent_id)

    bindings = load_capability_bindings(agent_path)
    if not bindings:
        raise AgentRuntimeNotFoundError(f"agent {agent_id} has no capability_tools")

    catalog_item = _agent_catalog_item(agent_id)
    if not catalog_item["enabled"]:
        raise AgentRuntimeDisabledByOpsError("agent disabled by platform operator")
    is_platform_operator = role == "ROLE_SYSTEM"
    if not is_platform_operator and role not in catalog_item["allowed_roles"]:
        raise AccessDeniedError("current role is not allowed to use this agent")


def start_agent_task(
    *,
    brain: BrainService,
    role: str,
    agent_id: str,
    user_input: str,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """阻塞模式：启动 Agent 任务并等待完成。

    当 HTTP 客户端超时较短（浏览器 ~15 秒）而 Agent 多轮工具调用可能超时时，
    建议改用 start_agent_task_background() + poll_agent_task() 的非阻塞模式。
    """
    if not is_agent_runtime_enabled():
        raise AgentRuntimeNotEnabledError("ZW_BRAIN_AGENT_RUNTIME_ENABLED is not set")

    _verify_agent_and_policy(agent_id=agent_id, role=role)

    task_metadata = _resolve_task_metadata(role=role, request_id=request_id, metadata=metadata)

    from zw_brain.shared.agent_runtime.service import run_agent_task_sync

    return run_agent_task_sync(
        agent_id=agent_id,
        user_input=user_input,
        metadata=task_metadata,
        brain=brain,
    )


def start_agent_task_background(
    *,
    brain: BrainService,
    role: str,
    agent_id: str,
    user_input: str,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """非阻塞模式：启动 Agent 任务后立即返回 task_id，客户端轮询结果。

    返回 ``{"task_id": ..., "status": "pending"}``。
    调用方随后可用 ``poll_agent_task(task_id)`` 获取最终结果。

    解决浏览器 HTTP 客户端超时（~15 秒）导致 (canceled) 的问题。
    """
    if not is_agent_runtime_enabled():
        raise AgentRuntimeNotEnabledError("ZW_BRAIN_AGENT_RUNTIME_ENABLED is not set")

    _verify_agent_and_policy(agent_id=agent_id, role=role)

    task_metadata = _resolve_task_metadata(role=role, request_id=request_id, metadata=metadata)

    from zw_brain.shared.agent_runtime.service import start_agent_task_background as _start_bg

    return _start_bg(
        agent_id=agent_id,
        user_input=user_input,
        metadata=task_metadata,
    )


def poll_agent_task(task_id: str) -> dict[str, Any]:
    """轮询 Agent 任务状态。返回与 start_agent_task() 相同的结构。"""
    from zw_brain.shared.agent_runtime.service import poll_agent_task as _poll

    return _poll(task_id)


def resume_agent_task(
    *,
    task_id: str,
    input_data: str | dict[str, Any],
    brain: BrainService | None = None,
) -> dict[str, Any]:
    """恢复处于 waiting 状态的 Agent 任务（ask_user 等待用户输入后继续）。

    同步函数（可在同步 HTTP handler 中直接调用）。
    返回 ``{"task_id": ..., "status": "resumed"}``。
    调用方随后用 ``poll_agent_task(task_id)`` 轮询最终结果。
    """
    if not is_agent_runtime_enabled():
        raise AgentRuntimeNotEnabledError("ZW_BRAIN_AGENT_RUNTIME_ENABLED is not set")

    from zw_brain.shared.agent_runtime.service import (
        resume_agent_task as _resume,
    )

    # 单一模型：resume 为同步 HTTP（独立 AR），无需后台事件循环包裹（embedded 退役）。
    return _resume(task_id=task_id, input_data=input_data)


def _resolve_agent_dir(agent_id: str) -> Path | None:
    candidate = agent_directory_for_id(agent_id)
    if (candidate / "AGENT.yaml").is_file():
        return candidate
    return None


def _agent_catalog_item(
    agent_id: str,
    *,
    tenant_id: str = _DEFAULT_TENANT_ID,
    state_record: Any | None = None,
) -> dict[str, Any]:
    if state_record is None:
        for item in list_builtin_agents(role="ROLE_SYSTEM", tenant_id=tenant_id):
            if item["agent_id"] == agent_id:
                return item
    else:
        for item in list_builtin_agents(
            role="ROLE_SYSTEM",
            tenant_id=tenant_id,
            state_overrides={agent_id: state_record},
        ):
            if item["agent_id"] == agent_id:
                return item
    raise AgentRuntimeNotFoundError(agent_id)


def _load_agent_files(agent_yaml: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    agent = yaml.safe_load(agent_yaml.read_text(encoding="utf-8")) or {}
    sidecar_path = agent_yaml.parent / "capabilities.json"
    sidecar: dict[str, Any] = {}
    if sidecar_path.is_file():
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    return agent, sidecar
