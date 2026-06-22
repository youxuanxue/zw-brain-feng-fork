"""AgentRuntime 接入 facade（D68 单一模型 · standalone-only）.

zw-brain **不再内置/嵌入** AgentRuntime —— embedded（in-process SDK）已退役。
AgentRuntime 作为**独立进程服务**被 zw-brain 经 HTTP 驱动（见 ``http_client``）；
本进程内**不 import AgentRuntime SDK**（接缝守卫 段77：zw_brain/ 下零 ``from agent_runtime``）。

本模块只保留历史 facade（签名不变，command 层无感），全部委派到 ``http_client``。
能力回调（AR 内 agent → zw-brain）走 AGENT.yaml 声明的 ``kind:api`` 工具回调
zw-brain 已发布认证 API，不经本进程。
"""

from __future__ import annotations

import logging
from typing import Any

from zw_brain.shared.agent_runtime.config import is_agent_runtime_enabled
from zw_brain.shared.agent_runtime.http_client import (
    poll_agent_task_http,
    reset_client,
    resume_agent_task_http,
    run_agent_task_http,
    start_agent_task_background_http,
)

_LOGGER = logging.getLogger(__name__)

# 单一模型下 AR 是独立进程、能力经已发布 API 回调，本进程**不需要 in-process brain**——
# 历史的 register_brain_provider IoC 注入（embedded in-process 回调用）已随 embedded 退役移除。


def reset_agent_runtime() -> None:
    """重置独立 AR HTTP 客户端单例（mode 切换/测试隔离）。"""
    reset_client()


def run_agent_task_sync(**kwargs: Any) -> dict[str, Any]:
    """阻塞模式：经 HTTP 驱动独立 AR 跑任务、轮询至终态，返回 facade dict。"""
    if not is_agent_runtime_enabled():
        raise RuntimeError("ZW_BRAIN_AGENT_RUNTIME_ENABLED is not set")
    return run_agent_task_http(**kwargs)


def start_agent_task_background(
    *,
    agent_id: str,
    user_input: str,
    session_title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """非阻塞模式：经 HTTP 起任务后立即返回；独立 AR 自管生命周期。"""
    return start_agent_task_background_http(
        agent_id=agent_id,
        user_input=user_input,
        session_title=session_title,
        metadata=metadata,
    )


def poll_agent_task(task_id: str) -> dict[str, Any]:
    """轮询任务状态（GET /tasks/{id}）；404 → AgentRuntimeNotFoundError。"""
    return poll_agent_task_http(task_id)


def resume_agent_task(
    *,
    task_id: str,
    input_data: str | dict[str, Any],
    brain: Any | None = None,
) -> dict[str, Any]:
    """恢复 waiting 任务（POST /tasks/{id}/resume）；后续状态走 poll。"""
    return resume_agent_task_http(task_id=task_id, input_data=input_data, brain=brain)


__all__ = [
    "reset_agent_runtime",
    "run_agent_task_sync",
    "start_agent_task_background",
    "poll_agent_task",
    "resume_agent_task",
]
