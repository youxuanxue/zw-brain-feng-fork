"""Standalone AgentRuntime HTTP client (D68 单一模型 · http 形态).

zw-brain 作为调用方，通过 AR 原生 REST 驱动一个**独立进程**的 AgentRuntime
服务（``agent-runtime serve``）。本模块**不 import AgentRuntime SDK** —— 这正是
单一模型解耦的体现：zw-brain 只依赖 AR 的 JSON 路由形状，不依赖其 Python 符号 /
py3.12.12 pyc / langchain 依赖闭包（接缝守卫 段77 因此对本文件零命中）。

facade 签名与历史一致；service.py 全部委派到这里（embedded 已退役，无 mode 分支）。
能力回调（AR 内 agent → zw-brain 已发布认证 API）由 AGENT.yaml 的工具声明承载，
不在本驱动路径内。
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from zw_brain.shared.agent_runtime.config import agent_runtime_base_url
from zw_brain.shared.agent_runtime.errors import AgentRuntimeNotFoundError

_LOGGER = logging.getLogger(__name__)

# 与 embedded 形态 service.py 的阻塞超时一致（HTTP 客户端可容忍 ~25s 等待）。
_TASK_BLOCK_TIMEOUT_SECONDS = 25.0
_POLL_INTERVAL_SECONDS = 1.0
_HTTP_TIMEOUT_SECONDS = 30.0

# AR TaskRecord.status → zw-brain 既有 facade 状态串（与 embedded drain 语义对齐）。
_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "waiting_input"}


def _map_status(ar_status: str) -> str:
    """AR 状态归一到 facade 既有语义：waiting_input→waiting（保 WebUI resume 流）。"""
    return "waiting" if ar_status == "waiting_input" else ar_status


class AgentRuntimeClient:
    """独立 AgentRuntime 服务的薄 HTTP 客户端（stdlib urllib，localhost 绕代理）。"""

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")
        # localhost 调用绕过 http(s)_proxy（与 start-local/curl --noproxy 一致）。
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            f"{self._base}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with self._opener.open(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            if exc.code == 404:
                raise AgentRuntimeNotFoundError(f"AgentRuntime 404 at {path}: {raw[:200]!r}") from exc
            raise RuntimeError(
                f"AgentRuntime HTTP {exc.code} at {method} {path}: {raw.decode('utf-8', 'replace')[:400]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"AgentRuntime unreachable at {self._base}{path}: {exc} "
                f"(独立 agent-runtime serve 未起?见 docs/agent-runtime/copilot-out-of-process-spike.md)"
            ) from exc
        return json.loads(raw) if raw else {}

    def create_session(self, *, agent_id: str, title: str, metadata: dict[str, Any]) -> str:
        resp = self._request("POST", "/sessions", {"agent_id": agent_id, "title": title, "metadata": metadata})
        return str(resp["session_id"])

    def start_task(
        self, *, session_id: str, agent_id: str, user_input: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        # subject_user_id（on-behalf-of）需 tasks:start:any_user scope；dev principal 暂无，
        # 故 per-user 身份走 metadata + 能力回调侧凭据（${user_credential:}）, 见 spike 报告 §4。
        return self._request(
            "POST",
            "/tasks",
            {"session_id": session_id, "agent_id": agent_id, "input": user_input, "metadata": metadata},
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/tasks/{task_id}")

    def resume_task(self, *, task_id: str, input_data: str | dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/tasks/{task_id}/resume", {"input": input_data})


_client: AgentRuntimeClient | None = None


def get_client() -> AgentRuntimeClient:
    global _client
    if _client is not None:
        return _client
    base = agent_runtime_base_url()
    if not base:
        raise RuntimeError(
            "未设 ZW_BRAIN_AGENT_RUNTIME_URL（独立 AR 服务地址；http 形态须指向 agent-runtime serve）"
        )
    _client = AgentRuntimeClient(base)
    return _client


def reset_client() -> None:
    global _client
    _client = None


def _session_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    sm: dict[str, Any] = {"tenant_id": "sd-default"}
    if metadata:
        for k in ("caller_role", "request_id"):
            if metadata.get(k):
                sm[k] = metadata[k]
    return sm


def run_agent_task_http(
    *,
    agent_id: str,
    user_input: str,
    session_title: str | None = None,
    metadata: dict[str, Any] | None = None,
    brain: Any | None = None,  # noqa: ARG001 — facade 形参对齐；http 形态不需 in-process brain
) -> dict[str, Any]:
    """阻塞模式：起 session+task，轮询至终态（最长 ~25s），返回 facade dict。"""
    client = get_client()
    session_id = client.create_session(
        agent_id=agent_id,
        title=session_title or f"zw-brain:{agent_id}",
        metadata=_session_metadata(metadata),
    )
    task = client.start_task(
        session_id=session_id, agent_id=agent_id, user_input=user_input, metadata=metadata or {}
    )
    task_id = str(task["task_id"])
    _LOGGER.info("[AR-HTTP] started session=%s task=%s agent=%s", session_id, task_id, agent_id)

    status = str(task.get("status") or "pending")
    final_output = task.get("final_output")
    deadline = time.monotonic() + _TASK_BLOCK_TIMEOUT_SECONDS
    while status not in _TERMINAL_STATUSES:
        if time.monotonic() >= deadline:
            status = "timeout"
            break
        time.sleep(_POLL_INTERVAL_SECONDS)
        rec = client.get_task(task_id)
        status = str(rec.get("status") or status)
        final_output = rec.get("final_output", final_output)

    return {
        "session_id": session_id,
        "task_id": task_id,
        "status": _map_status(status),
        "final_output": final_output,
    }


def start_agent_task_background_http(
    *,
    agent_id: str,
    user_input: str,
    session_title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """非阻塞模式：起 session+task 立即返回；独立 AR 进程自管生命周期（无需后台线程）。"""
    client = get_client()
    session_id = client.create_session(
        agent_id=agent_id,
        title=session_title or f"zw-brain:{agent_id}",
        metadata=_session_metadata(metadata),
    )
    task = client.start_task(
        session_id=session_id, agent_id=agent_id, user_input=user_input, metadata=metadata or {}
    )
    return {
        "session_id": session_id,
        "task_id": str(task["task_id"]),
        "status": _map_status(str(task.get("status") or "pending")),
    }


def poll_agent_task_http(task_id: str) -> dict[str, Any]:
    """轮询单个任务（GET /tasks/{id}）；404 → AgentRuntimeNotFoundError。"""
    rec = get_client().get_task(task_id)
    return {
        "session_id": str(rec.get("session_id") or ""),
        "task_id": str(rec.get("task_id") or task_id),
        "status": _map_status(str(rec.get("status") or "")),
        "final_output": rec.get("final_output"),
    }


def resume_agent_task_http(
    *,
    task_id: str,
    input_data: str | dict[str, Any],
    brain: Any | None = None,  # noqa: ARG001 — facade 形参对齐
) -> dict[str, Any]:
    """恢复 waiting 任务（POST /tasks/{id}/resume）；后续状态走 poll。"""
    rec = get_client().resume_task(task_id=task_id, input_data=input_data)
    return {"task_id": str(task_id), "status": _map_status(str(rec.get("status") or "resumed"))}
