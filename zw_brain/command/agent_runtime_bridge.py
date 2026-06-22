from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from zw_brain.command.brain import AccessDeniedError, BrainService
from zw_brain.domain import policy
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
)


def runtime_status() -> dict[str, Any]:
    # 仅暴露 enable bit；Agent topology（agent_id / capability_skills）属敏感信息，
    # 仅通过 /api/agent-runtime/agents 在鉴权后返回。
    return {"enabled": is_agent_runtime_enabled()}


def _roles_that_can_use(bindings: list[dict[str, Any]]) -> list[str]:
    """返回能通过该 Agent **全部**绑定 skill policy 的角色集——与 _verify_agent_and_policy
    完全同口径（同一 enforce_manifest_policy 链）。这是 UI 落位的单一事实源：

      - 数据应用画廊只渲染 caller 角色 ∈ 该集合的卡片（no-permission=invisible，
        不再「可见+403」死胡同，见 #294/#296/#297 反复诉讼的反模式）；
      - 403 文案据此列出「可切换到」的具体岗位名。

    返回 [] 表示无任何角色可用（视为对所有人不可见）。"""
    from zw_brain.capability_registry.runtime import get_manifest

    allowed: list[str] = []
    for role in BUSINESS_ROLE_CODES:
        ok = True
        for binding in bindings:
            skill_id = binding["skill_id"]
            try:
                manifest = get_manifest(skill_id)
                policy.enforce_manifest_policy(skill_id, manifest, role, {})
            except (KeyError, policy.DomainAccessDeniedError):
                ok = False
                break
        if ok:
            allowed.append(role)
    return allowed


def list_builtin_agents() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for agent_yaml in sorted(agents_dir().glob("*/AGENT.yaml")):
        agent, sidecar = _load_agent_files(agent_yaml)
        metadata = agent.get("metadata") if isinstance(agent.get("metadata"), dict) else {}
        agent_id = str(metadata.get("id") or "")
        if not agent_id:
            continue
        # UI 落位的单一事实源：labels.surface 显式声明该 Agent 属哪种产品对象——
        #   'copilot'  = 嵌在工作流里的副驾（找数副驾等），不进【数据应用】列表；
        #   'data-app' = 独立数据应用，进【数据应用】画廊。
        # 缺省回落 copilot（保守：未声明的不会误入数据应用页）。
        labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
        surface = str(labels.get("surface") or "").strip().lower()
        category = "data-app" if surface == "data-app" else "copilot"
        bindings = load_capability_bindings(agent_yaml.parent)
        allowed_roles = _roles_that_can_use(bindings)
        items.append(
            {
                "agent_id": agent_id,
                "name": metadata.get("name"),
                "version": metadata.get("version"),
                "trust_level": metadata.get("trust_level") or sidecar.get("trust_level"),
                "description": metadata.get("description"),
                "capability_skills": [b["skill_id"] for b in bindings],
                "category": category,
                # 调用方角色须 ∈ allowed_roles 才可用本 Agent（与 task 启动鉴权同口径）。
                # 前端据此过滤卡片（无权不渲染）+ 渲染 403「可切换到」岗位名。
                "allowed_roles": allowed_roles,
                "allowed_role_names": [ROLE_DISPLAY_NAMES_ZH.get(r, r) for r in allowed_roles],
            }
        )
    return items


def _resolve_task_metadata(
    *,
    role: str,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一构建传递给 AgentRuntime 的 task_metadata。"""
    task_metadata = dict(metadata or {})
    if request_id:
        task_metadata["request_id"] = request_id
    task_metadata["caller_role"] = role
    return task_metadata


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

    for binding in bindings:
        skill_id = binding["skill_id"]
        try:
            from zw_brain.capability_registry.runtime import get_manifest

            manifest = get_manifest(skill_id)
        except KeyError as exc:
            raise AgentRuntimeNotFoundError(skill_id) from exc
        try:
            policy.enforce_manifest_policy(skill_id, manifest, role, {})
        except policy.DomainAccessDeniedError as exc:
            raise AccessDeniedError(str(exc)) from exc


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


def _load_agent_files(agent_yaml: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    agent = yaml.safe_load(agent_yaml.read_text(encoding="utf-8")) or {}
    sidecar_path = agent_yaml.parent / "capabilities.json"
    sidecar: dict[str, Any] = {}
    if sidecar_path.is_file():
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    return agent, sidecar
