from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from zw_brain.command.brain import AccessDeniedError, BrainService
from zw_brain.domain import policy
from zw_brain.shared.agent_runtime.capability_provider import (
    agent_directory_for_id,
    load_capability_bindings,
)
from zw_brain.shared.agent_runtime.config import agents_dir, is_agent_runtime_enabled


class AgentRuntimeNotEnabledError(RuntimeError):
    pass


class AgentRuntimeNotFoundError(LookupError):
    pass


def runtime_status() -> dict[str, Any]:
    # 仅暴露 enable bit；Agent topology（agent_id / capability_skills）属敏感信息，
    # 仅通过 /api/agent-runtime/agents 在鉴权后返回。
    return {"enabled": is_agent_runtime_enabled()}


def list_builtin_agents() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for agent_yaml in sorted(agents_dir().glob("*/AGENT.yaml")):
        agent, sidecar = _load_agent_files(agent_yaml)
        metadata = agent.get("metadata") if isinstance(agent.get("metadata"), dict) else {}
        agent_id = str(metadata.get("id") or "")
        if not agent_id:
            continue
        bindings = load_capability_bindings(agent_yaml.parent)
        items.append(
            {
                "agent_id": agent_id,
                "name": metadata.get("name"),
                "version": metadata.get("version"),
                "trust_level": metadata.get("trust_level") or sidecar.get("trust_level"),
                "description": metadata.get("description"),
                "capability_skills": [b["skill_id"] for b in bindings],
            }
        )
    return items


def start_agent_task(
    *,
    brain: BrainService,
    role: str,
    agent_id: str,
    user_input: str,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not is_agent_runtime_enabled():
        raise AgentRuntimeNotEnabledError("ZW_BRAIN_AGENT_RUNTIME_ENABLED is not set")

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

    task_metadata = dict(metadata or {})
    if request_id:
        task_metadata["request_id"] = request_id
    task_metadata["caller_role"] = role

    from zw_brain.shared.agent_runtime.service import run_agent_task_sync

    return run_agent_task_sync(
        agent_id=agent_id,
        user_input=user_input,
        metadata=task_metadata,
    )


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
