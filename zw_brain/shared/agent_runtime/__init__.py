"""AgentRuntime 接入（D68 单一模型 · standalone-only）。

embedded（in-process SDK）已退役：zw-brain 经 HTTP 驱动独立 AgentRuntime 服务，
本进程内不 import AgentRuntime SDK。facade 见 ``service`` / ``http_client``。
"""

from __future__ import annotations

from typing import Any

from zw_brain.shared.agent_runtime.config import (
    agents_dir,
    is_agent_runtime_enabled,
    zw_brain_repo_root,
)

_LAZY_EXPORTS = {
    "reset_agent_runtime",
    "run_agent_task_sync",
}

__all__ = [
    "agents_dir",
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
