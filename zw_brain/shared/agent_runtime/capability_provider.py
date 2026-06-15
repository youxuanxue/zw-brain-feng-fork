from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from zw_brain.shared.agent_runtime.config import agents_dir

if TYPE_CHECKING:
    from agent_runtime.runtime.dynamic_capabilities import DynamicCapabilityContext

    # TYPE_CHECKING-only: shared/ must not eager-import command/ at runtime
    # (layer order entry→command→domain→shared; preflight 段 49). The provider
    # only duck-types brain.invoke_skill(), so no runtime symbol is needed.
    from zw_brain.command.brain import BrainService

_LOGGER = logging.getLogger(__name__)
_BUILTIN_ACTOR_ROLE = "ROLE_ORGAN_OPERATER"
# 与 agent_runtime.runtime.dynamic_capabilities.DYNAMIC_PROVIDER_TOOL_CAPABILITY 一致，避免顶层 import agent_runtime
_DYNAMIC_PROVIDER_TOOL_CAPABILITY = "dynamic.provider_tool"


class ZwBrainCapabilityProvider:
    """Maps declared zw-brain Skills to AgentRuntime dynamic provider-backed tools."""

    def __init__(self, brain: BrainService, *, agent_dir: Path) -> None:
        self._brain = brain
        self._agent_dir = agent_dir
        self._bindings = load_capability_bindings(agent_dir)

    def list_tools(self, context: DynamicCapabilityContext) -> list[dict[str, Any]]:
        _ = context
        tools: list[dict[str, Any]] = []
        for binding in self._bindings:
            entry: dict[str, Any] = {
                "kind": "runtime",
                "name": binding["name"],
                "description": binding["description"],
                "capability": _DYNAMIC_PROVIDER_TOOL_CAPABILITY,
            }
            if binding.get("input_schema"):
                entry["config"] = {"input_schema": binding["input_schema"]}
            tools.append(entry)
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any], context: DynamicCapabilityContext) -> Any:
        binding = next((item for item in self._bindings if item["name"] == name), None)
        if binding is None:
            raise ValueError(f"unknown zw-brain capability tool: {name}")

        payload = dict(arguments or {})
        caller_role = (context.task_metadata or {}).get("caller_role")
        payload.setdefault("role", caller_role or _BUILTIN_ACTOR_ROLE)
        payload.setdefault("tenant_id", "sd-default")
        request_id = (context.task_metadata or {}).get("request_id")
        if request_id and "request_id" not in payload:
            payload["request_id"] = request_id

        # 传播 trusted session 标记：当 task_metadata 中包含 _trusted_session_context
        # 和 actor_snapshot 时，将其注入 payload，使 brain._resolve_role 走 trusted
        # session 路径（resolve_trusted_role，从 session actor_snapshot 解析角色），
        # 而不是走 C1/N1 的 resolve_role_from_identity（从 AuthContext / IAF token
        # claims 解析角色）。后者可能因 IAF token 中不包含产品岗位码而报
        # "identity holds no product role"。
        #
        # 这修复了 Agent 内部工具调用（如 platform_docs_search）与 BFF 其他 API
        # 接口角色鉴权逻辑不一致的问题：其他接口通过 build_trusted_skill_payload 打
        # 标记走 trusted session path，而 Agent 工具调用之前丢失了这个标记。
        from zw_brain.shared.session_context import TRUSTED_SESSION_CONTEXT_KEY, build_trusted_skill_payload

        trusted_key = str(TRUSTED_SESSION_CONTEXT_KEY)
        if trusted_key in (context.task_metadata or {}):
            actor_snapshot = (context.task_metadata or {}).get("actor_snapshot")
            if isinstance(actor_snapshot, dict):
                payload = build_trusted_skill_payload(payload, actor_snapshot=actor_snapshot)

        skill_id = binding["skill_id"]
        _LOGGER.info(
            "[AgentRuntime-ToolInvoke] tool=%s skill_id=%s arguments=%s",
            name,
            skill_id,
            json.dumps(payload, ensure_ascii=False, default=str)[:2000],
        )
        result = self._brain.invoke_skill(skill_id, payload)
        _LOGGER.info(
            "[AgentRuntime-ToolInvoke] result tool=%s skill_id=%s result_type=%s result_truncated=%s",
            name,
            skill_id,
            type(result).__name__,
            len(json.dumps(result, ensure_ascii=False, default=str)) > 500 if result else 0,
        )
        return result


def agent_directory_for_id(agent_id: str) -> Path:
    folder = agent_id.replace("-", "_")
    return agents_dir() / folder


def load_capability_bindings(agent_dir: Path) -> list[dict[str, Any]]:
    sidecar = agent_dir / "capabilities.json"
    if not sidecar.is_file():
        return []
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    tools = raw.get("capability_tools") if isinstance(raw, dict) else None
    if not isinstance(tools, list):
        return []
    bindings: list[dict[str, Any]] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        skill_id = str(item.get("skill_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not skill_id or not name:
            continue
        bindings.append(
            {
                "skill_id": skill_id,
                "name": name,
                "description": str(item.get("description") or f"zw-brain skill {skill_id}"),
                "input_schema": item.get("input_schema"),
            }
        )
    return bindings
