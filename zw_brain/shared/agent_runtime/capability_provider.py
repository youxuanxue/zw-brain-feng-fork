from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from zw_brain.command.brain import BrainService
from zw_brain.shared.agent_runtime.config import agents_dir

if TYPE_CHECKING:
    from agent_runtime.runtime.dynamic_capabilities import DynamicCapabilityContext

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
        payload.setdefault("role", _BUILTIN_ACTOR_ROLE)
        payload.setdefault("tenant_id", "sd-default")
        request_id = (context.task_metadata or {}).get("request_id")
        if request_id and "request_id" not in payload:
            payload["request_id"] = request_id

        skill_id = binding["skill_id"]
        _LOGGER.debug("agent_runtime capability invoke skill_id=%s tool=%s", skill_id, name)
        return self._brain.invoke_skill(skill_id, payload)


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
