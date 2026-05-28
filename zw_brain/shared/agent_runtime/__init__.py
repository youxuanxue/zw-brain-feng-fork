"""Embedded AgentRuntime integration for zw-brain (architecture §8, Phase 1 SDK)."""

from __future__ import annotations

from typing import Any

from zw_brain.shared.agent_runtime.config import (
    agent_runtime_config_path,
    agents_dir,
    embedded_runtime_env,
    is_agent_runtime_enabled,
    zw_brain_repo_root,
)

_LAZY_EXPORTS = {
    "get_agent_runtime",
    "reset_agent_runtime",
    "run_agent_task_sync",
}

__all__ = [
    "agent_runtime_config_path",
    "agents_dir",
    "embedded_runtime_env",
    "get_agent_runtime",
    "is_agent_runtime_enabled",
    "reset_agent_runtime",
    "run_agent_task_sync",
    "zw_brain_repo_root",
]


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        from zw_brain.shared.agent_runtime import service

        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
