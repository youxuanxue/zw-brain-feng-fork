from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from zw_brain.shared.agent_runtime.capability_provider import (
    ZwBrainCapabilityProvider,
    agent_directory_for_id,
)
from zw_brain.shared.agent_runtime.config import (
    agent_runtime_config_path,
    agent_runtime_profile,
    agent_runtime_schema_env,
    agents_dir,
    apply_embedded_runtime_env_to_process,
    is_agent_runtime_enabled,
    resolve_schema_path,
    zw_brain_repo_root,
)
from zw_brain.shared.agent_runtime.errors import AgentRuntimeNotFoundError

_LOGGER = logging.getLogger(__name__)
_runtime: Any | None = None
_runtime_lock = threading.Lock()

# ---------------------------------------------------------------------------
# 后台事件循环（异步任务持久化）
# 同步 HTTP handler（asyncio.run()）中创建的 asyncio.Task 会在事件循环关闭时
# 被取消。为避免此问题，使用一个专用的后台线程 + 持久事件循环来运行
# 长时间的后台任务。
# ---------------------------------------------------------------------------
_background_loop: asyncio.AbstractEventLoop | None = None
_background_loop_lock = threading.Lock()
_background_loop_thread: threading.Thread | None = None

# in-memory 后台任务注册表（用于状态追踪和清理）
_background_tasks: dict[str, asyncio.Task[None]] = {}


def _ensure_background_loop() -> asyncio.AbstractEventLoop:
    """确保存在一个持久运行的后台事件循环（在独立的守护线程中）。"""
    global _background_loop, _background_loop_thread

    if _background_loop is not None and _background_loop.is_running():
        return _background_loop

    with _background_loop_lock:
        # Double-check after acquiring lock
        if _background_loop is not None and _background_loop.is_running():
            return _background_loop

        loop = asyncio.new_event_loop()

        def _run_loop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=_run_loop, name="agent-bg-loop", daemon=True)
        thread.start()

        _background_loop = loop
        _background_loop_thread = thread
        return loop

# IoC: the command layer registers its BrainService factory here so that shared/
# never imports command/. This keeps the layer order entry→command→domain→shared
# intact (preflight 段 49) — agent_runtime lives in shared/ but needs a BrainService,
# and reaching up via `from zw_brain.command...` (even lazily) is a reverse-dependency.
_brain_provider: Callable[[], Any] | None = None


def register_brain_provider(provider: Callable[[], Any]) -> None:
    """Register the command-layer BrainService factory (e.g. ``get_service``).

    Called at command-layer import time. Lets the embedded agent runtime obtain a
    brain without shared/ importing command/.
    """
    global _brain_provider
    _brain_provider = provider


def _resolve_brain(brain: Any | None) -> Any:
    if brain is not None:
        return brain
    if _brain_provider is not None:
        return _brain_provider()
    raise RuntimeError(
        "no BrainService available for the embedded agent runtime: pass brain= "
        "or ensure the command layer registered a provider via register_brain_provider()"
    )


def _ensure_docs_in_workspace(product: Any) -> None:
    """将 docs/ 目录及文件全部复制到 workspaces 下，使 LLM 可通过 workspace tools 访问。

    AgentRuntime 的 workspace 根目录是 product.workspace_root（宿主机路径
    .data/agent-runtime/workspaces，Docker 映射时需注意地址）。
    此函数在运行时初始化时自动执行，保证 docs 内容对 LLM 可用。
    """
    docs_src = zw_brain_repo_root() / "docs"
    if not docs_src.is_dir():
        _LOGGER.warning(
            "[AgentRuntime-Workspace] docs source not found at %s, skipping workspace copy",
            docs_src,
        )
        return

    workspace_root: Path = product.workspace_root if hasattr(product, "workspace_root") else None
    if workspace_root is None:
        _LOGGER.warning("[AgentRuntime-Workspace] workspace_root not configured, skipping doc copy")
        return

    docs_dst = workspace_root.resolve() / "docs"
    try:
        docs_dst.parent.mkdir(parents=True, exist_ok=True)
        if docs_dst.exists():
            shutil.rmtree(docs_dst)
        shutil.copytree(str(docs_src), str(docs_dst), symlinks=False, ignore_dangling_symlinks=True)
        _LOGGER.info(
            "[AgentRuntime-Workspace] copied docs/ to workspace: src=%s dst=%s",
            docs_src,
            docs_dst,
        )
    except OSError as exc:
        _LOGGER.warning(
            "[AgentRuntime-Workspace] failed to copy docs to workspace: %s", exc,
        )


def _require_agent_runtime():
    try:
        from agent_runtime import RuntimeService
        from agent_runtime.runtime.product_config import ProductRuntimeConfig, load_product_runtime_config
    except ImportError as exc:  # pragma: no cover - optional extra
        raise RuntimeError(
            "agent-runtime package is not installed; install offline package from "
            "vendor/agent-runtime/release/v0.1/ (see vendor/agent-runtime/README.md)"
        ) from exc
    return RuntimeService, ProductRuntimeConfig, load_product_runtime_config


async def get_agent_runtime(brain: Any | None = None):
    """Lazy singleton Embedded RuntimeService (in-process, no HTTP server).

    使用 threading.Lock 确保线程安全（可在主线程和后台事件循环线程中并行访问）。

    ``brain`` is the BrainService to bridge capabilities from; when omitted it is
    resolved from the command-layer provider registered via ``register_brain_provider``.
    """
    global _runtime
    if _runtime is not None:
        return _runtime

    # threading.Lock 不能直接 await，使用 loop.run_in_executor 或直接 acquire
    # 由于这里初始化很快（只是检查和赋值），在单独的线程中阻塞无所谓
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _runtime_lock.acquire)
    try:
        if _runtime is not None:
            return _runtime
        RuntimeService, ProductRuntimeConfig, load_product_runtime_config = _require_agent_runtime()

        config_path = agent_runtime_config_path()
        if config_path.is_file():
            product = load_product_runtime_config(config_path)
            overrides: dict[str, Any] = {
                "profile": agent_runtime_profile(),
                "agents_dir": agents_dir(),
            }
            schema_env = agent_runtime_schema_env()
            if schema_env is not None and schema_env.is_file():
                overrides["schema_path"] = schema_env
            if agent_runtime_profile() == "local_dev":
                overrides["auth_mode"] = "none"
            product = product.model_copy(update=overrides)
        else:
            product = ProductRuntimeConfig(
                product_name="zw-brain",
                profile=agent_runtime_profile(),  # type: ignore[arg-type]
                agents_dir=agents_dir(),
                schema_path=resolve_schema_path(None),
                workspace_root=zw_brain_repo_root() / ".data/agent-runtime/workspaces",
                log_dir=zw_brain_repo_root() / ".data/agent-runtime/logs",
                auth_mode="none" if agent_runtime_profile() == "local_dev" else "trusted_gateway",
                context_mode="minimal",
                tenant_mode="single",
            )

        resolved_brain = _resolve_brain(brain)
        providers: dict[str, ZwBrainCapabilityProvider] = {}
        for agent_yaml in sorted(agents_dir().glob("*/AGENT.yaml")):
            agent_id = _agent_id_from_yaml(agent_yaml)
            if not agent_id:
                continue
            providers[agent_id] = ZwBrainCapabilityProvider(
                resolved_brain,
                agent_dir=agent_directory_for_id(agent_id),
            )

        repo_root = zw_brain_repo_root()
        runtime_env = apply_embedded_runtime_env_to_process()

        # 自动将 docs/ 目录复制到 workspaces 目录，使 LLM 能够通过 workspace tools 访问文档
        _ensure_docs_in_workspace(product)

        runtime = RuntimeService.for_product(
            product,
            repo_root=repo_root,
            env=runtime_env,
            dynamic_capability_providers=providers,
        )
        await runtime.initialize()
        _runtime = runtime
        _LOGGER.info(
            "AgentRuntime embedded SDK ready profile=%s agents=%s",
            agent_runtime_profile(),
            sorted(providers),
        )
        return _runtime
    finally:
        _runtime_lock.release()


def reset_agent_runtime() -> None:
    global _runtime
    _runtime = None


def _agent_id_from_yaml(path) -> str | None:
    try:
        import yaml
    except ImportError:
        _LOGGER.warning("PyYAML missing; cannot parse %s", path)
        return None
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        _LOGGER.warning("invalid AGENT.yaml at %s: %s", path, exc)
        return None
    metadata = parsed.get("metadata") if isinstance(parsed, dict) else None
    if isinstance(metadata, dict) and metadata.get("id"):
        return str(metadata["id"])
    return None


_TASK_STREAM_TIMEOUT_SECONDS = float(os.environ.get("ZW_BRAIN_AGENT_TASK_TIMEOUT_SECONDS") or 25)


# ---------------------------------------------------------------------------
# 阻塞模式（原有语义）—— 同步等待任务完成，最多等待 _TASK_STREAM_TIMEOUT_SECONDS
# ---------------------------------------------------------------------------

async def _drain_until_terminal(
    runtime: Any,
    task_id: str,
    *,
    initial_status: str,
    initial_output: Any,
    timeout: float,
) -> tuple[str, Any]:
    """流式消费 task 事件直到终端状态，返回 (final_status, final_output)。

    识别以下事件类型：
    - ``task_completed`` → status="completed"
    - ``task_failed`` → status="failed"
    - ``task_cancelled`` → status="cancelled"
    - ``task_waiting`` → status="waiting"（Agent 等待用户输入/授权，不再阻塞）
    """
    final_status: str = str(initial_status)
    final_output: Any = initial_output
    event_count = 0

    async def _drain() -> None:
        nonlocal final_status, final_output, event_count
        async for event in runtime._task_runner.stream_task(task_id):  # noqa: SLF001
            event_count += 1

            # 增强日志：记录每个事件的 payload 详细信息
            payload_preview = event.payload if event.payload else {}
            if isinstance(payload_preview, dict):
                if "final_output" in payload_preview:
                    payload_preview = {
                        k: (str(v)[:500] + "…" if isinstance(v, str) and len(v) > 500 else v)
                        for k, v in payload_preview.items()
                    }
            _LOGGER.info(
                "[AgentRuntime-Drain] task_id=%s event=%s (#%d) payload_summary=%s",
                task_id,
                event.event,
                event_count,
                json.dumps(payload_preview, ensure_ascii=False, default=str)[:1000],
            )

            if event.event == "task_completed":
                final_output = (event.payload or {}).get("final_output", final_output)
                final_status = "completed"
                _LOGGER.info(
                    "[AgentRuntime-Drain] task_id=%s completed (events=%d) final_output_present=%s",
                    task_id,
                    event_count,
                    "yes" if final_output else "no",
                )
                break
            if event.event == "task_failed":
                final_status = "failed"
                error_detail = (event.payload or {}).get("error") if event.payload else None
                _LOGGER.warning(
                    "[AgentRuntime-Drain] task_id=%s failed (events=%d) error=%s",
                    task_id,
                    event_count,
                    error_detail,
                )
                break
            if event.event == "task_cancelled":
                final_status = "cancelled"
                _LOGGER.info(
                    "[AgentRuntime-Drain] task_id=%s cancelled (events=%d)",
                    task_id,
                    event_count,
                )
                break
            if event.event == "task_waiting":
                final_status = "waiting"
                wait_reason = (event.payload or {}).get("reason", "ask_user") if event.payload else "ask_user"
                _LOGGER.info(
                    "[AgentRuntime-Drain] task_id=%s waiting (events=%d) reason=%s — break to avoid blocking on ask_user",
                    task_id,
                    event_count,
                    wait_reason,
                )
                break
            # 记录 llm_call 事件（模型返回/回调信息）
            if event.event == "llm_call":
                payload = event.payload or {}
                if isinstance(payload, dict):
                    llm_model = payload.get("model", "unknown")
                    llm_response = payload.get("response", "")
                    _LOGGER.info(
                        "[AgentRuntime-LLMCall] task_id=%s event=llm_call (#%d) model=%s response_summary=%s",
                        task_id,
                        event_count,
                        llm_model,
                        str(llm_response)[:300] if llm_response else "empty",
                    )
            # 记录 tool_invoke 事件
            if event.event == "tool_invoke":
                payload = event.payload or {}
                if isinstance(payload, dict):
                    tool_name = payload.get("name", "unknown")
                    tool_args = payload.get("arguments", {})
                    _LOGGER.info(
                        "[AgentRuntime-ToolInvoke] task_id=%s event=tool_invoke (#%d) tool=%s arguments=%s",
                        task_id,
                        event_count,
                        tool_name,
                        json.dumps(tool_args, ensure_ascii=False, default=str)[:2000],
                    )

    try:
        await asyncio.wait_for(_drain(), timeout=timeout)
    except TimeoutError:
        _LOGGER.warning(
            "[AgentRuntime-Drain] task_id=%s drain timeout after %.1fs (events=%d, last_status=%s)",
            task_id,
            timeout,
            event_count,
            final_status,
        )
        final_status = "timeout"

    _LOGGER.debug(
        "[AgentRuntime-Drain] done task_id=%s final_status=%s final_output=%s events=%d",
        task_id,
        final_status,
        "present" if final_output is not None else "none",
        event_count,
    )
    return final_status, final_output


async def _create_session_and_task(
    *,
    agent_id: str,
    user_input: str,
    session_title: str | None = None,
    metadata: dict[str, Any] | None = None,
    brain: Any | None = None,
) -> tuple[Any, Any, Any]:
    """创建 Session 并启动 Task，返回 (runtime, session, task)。"""
    from agent_runtime.runtime.models import CreateSessionRequest, StartTaskRequest

    runtime = await get_agent_runtime(brain=brain)

    session_metadata: dict[str, Any] = {"tenant_id": "sd-default"}
    if metadata:
        # 将 task 级别的 metadata 同步到 session 级别，便于后续追踪
        caller_role = metadata.get("caller_role")
        if caller_role:
            session_metadata["caller_role"] = caller_role
        request_id = metadata.get("request_id")
        if request_id:
            session_metadata["request_id"] = request_id

    session = await runtime.create_session(
        CreateSessionRequest(
            agent_id=agent_id,
            title=session_title or f"zw-brain:{agent_id}",
            metadata=session_metadata,
        )
    )
    task = await runtime.start_task(
        StartTaskRequest(
            session_id=session.session_id,
            agent_id=agent_id,
            input=user_input,
            metadata=metadata or {},
        )
    )
    _LOGGER.info(
        "[AgentRuntime-Session] created session_id=%s task_id=%s agent_id=%s input_summary=%s",
        session.session_id,
        task.task_id,
        agent_id,
        user_input.strip().replace("\n", " ")[:200],
    )
    return runtime, session, task


async def run_agent_task(
    *,
    agent_id: str,
    user_input: str,
    session_title: str | None = None,
    metadata: dict[str, Any] | None = None,
    brain: Any | None = None,
) -> dict[str, Any]:
    """阻塞模式：等待任务完成（最长 _TASK_STREAM_TIMEOUT_SECONDS 秒）。

    适用于 HTTP 客户端能容忍 ~25 秒等待的场景。若需避免长时间阻塞，
    请使用 start_agent_task_background() + poll_agent_task() 非阻塞模式。
    """
    runtime, session, task = await _create_session_and_task(
        agent_id=agent_id,
        user_input=user_input,
        session_title=session_title,
        metadata=metadata,
        brain=brain,
    )

    final_status, final_output = await _drain_until_terminal(
        runtime,
        str(task.task_id),
        initial_status=str(task.status),
        initial_output=task.final_output,
        timeout=_TASK_STREAM_TIMEOUT_SECONDS,
    )

    # 记录 session 的输入输出信息（通过 update_session 更新 metadata）
    try:
        from agent_runtime.runtime.models import UpdateSessionRequest

        session_metadata = dict(session.metadata or {})
        session_metadata["last_task_status"] = final_status
        session_metadata["last_input_summary"] = user_input.strip().replace("\n", " ")[:200]
        if final_output is not None:
            session_metadata["has_output"] = True
            # 记录输出的摘要（避免存完整大文本到 metadata）
            if isinstance(final_output, str):
                session_metadata["output_summary"] = final_output.strip().replace("\n", " ")[:200]
            elif isinstance(final_output, dict):
                session_metadata["output_summary"] = json.dumps(final_output, ensure_ascii=False, default=str)[:200]
        await runtime.update_session(
            str(session.session_id),
            UpdateSessionRequest(
                metadata=session_metadata,
            ),
        )
        _LOGGER.info(
            "[AgentRuntime-Session] recorded session_id=%s task_id=%s status=%s",
            session.session_id,
            task.task_id,
            final_status,
        )
    except Exception as exc:
        _LOGGER.warning(
            "[AgentRuntime-Session] failed to update session metadata session_id=%s: %s",
            session.session_id,
            exc,
        )

    return {
        "session_id": str(session.session_id),
        "task_id": str(task.task_id),
        "status": str(final_status),
        "final_output": final_output,
    }


def run_agent_task_sync(**kwargs: Any) -> dict[str, Any]:
    if not is_agent_runtime_enabled():
        raise RuntimeError("ZW_BRAIN_AGENT_RUNTIME_ENABLED is not set")
    return asyncio.run(run_agent_task(**kwargs))


# ---------------------------------------------------------------------------
# Resume（恢复等待中的任务）
# ---------------------------------------------------------------------------

async def resume_agent_task(
    *,
    task_id: str,
    input_data: str | dict[str, Any],
    brain: Any | None = None,
) -> dict[str, Any]:
    """恢复一个处于 waiting 状态的任务（例如 ask_user 等待用户输入后继续）。

    调用 RuntimeService.resume_task() 将用户输入传递给等待中的 Agent，
    返回 ``{"status": "resumed"}``。任务的后续状态需要通过
    ``poll_agent_task(task_id)`` 轮询获取。

    resume 后会自动启动一个新的后台 stream 消费者，以确保 Agent
    完成后能通过 poll 获取最终状态。

    Args:
        task_id: 要恢复的任务 ID。
        input_data: 用户提供的输入（字符串或字典），作为 resume 的 input 字段。
        brain: BrainService 实例（可选，默认自动解析）。
    """
    from agent_runtime.runtime.models import ResumeTaskRequest

    runtime = await get_agent_runtime(brain=brain)
    resume_req = ResumeTaskRequest(input=input_data)
    await runtime.resume_task(task_id=task_id, request=resume_req)
    _LOGGER.info("[AgentRuntime-Resume] task_id=%s resumed", task_id)

    # resume 后启动新的后台 stream 消费者，确保后续事件被消费
    # 避免 task 完成后 poll 不到最终状态
    bg_task = asyncio.create_task(
        _background_task_runner(
            runtime,
            task_id,
            initial_status="resumed",
            initial_output=None,
        )
    )
    _background_tasks[task_id] = bg_task

    return {
        "task_id": str(task_id),
        "status": "resumed",
    }


__all__ = [
    "get_agent_runtime",
    "register_brain_provider",
    "reset_agent_runtime",
    "run_agent_task",
    "run_agent_task_sync",
    "resume_agent_task",
]


# ---------------------------------------------------------------------------
# 非阻塞模式（推荐）：start → 立即返回 task_id → 客户端轮询结果
# ---------------------------------------------------------------------------

async def _background_task_runner(
    runtime: Any,
    task_id: str,
    *,
    initial_status: str,
    initial_output: Any,
) -> None:
    """在后台消费 stream_task 事件，更新 AgentRuntime 内部状态。

    AgentRuntime 的 get_task() 会返回最终状态，即使我们不显式保存结果。
    此函数仅确保 stream 被消费完，否则 AgentRuntime 内部可能有未处理事件。
    """
    _LOGGER.info("[AgentRuntime-BGRunner] start task_id=%s initial_status=%s", task_id, initial_status)
    bg_start = time.monotonic()
    try:
        final_status, final_output = await _drain_until_terminal(
            runtime,
            task_id,
            initial_status=initial_status,
            initial_output=initial_output,
            timeout=300.0,  # 后台任务给足够长的时间
        )
        elapsed = time.monotonic() - bg_start
        _LOGGER.info(
            "[AgentRuntime-BGRunner] done task_id=%s final_status=%s elapsed=%.1fs",
            task_id,
            final_status,
            elapsed,
        )
    except Exception:
        elapsed = time.monotonic() - bg_start
        _LOGGER.exception("[AgentRuntime-BGRunner] drain failed task_id=%s elapsed=%.1fs", task_id, elapsed)
    finally:
        _background_tasks.pop(task_id, None)


def _run_async_in_background_loop(coro: Any) -> Any:
    """在后台事件循环中执行协程，返回结果。

    用于同步上下文中调用异步函数，同时确保 asyncio.create_task()
    创建的后台任务不会被销毁。
    """
    loop = _ensure_background_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def start_agent_task_background(
    *,
    agent_id: str,
    user_input: str,
    session_title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """非阻塞模式：启动任务后立即返回，客户端通过 poll_agent_task() 轮询结果。

    同步函数（可在同步 HTTP handler 中直接调用）。
    返回 ``{"task_id": ..., "status": "pending"}``，
    调用方应用 ``poll_agent_task(task_id)`` 轮询最终结果。

    使用场景：HTTP 客户端超时短（浏览器 ~15 秒），但 Agent 多轮工具调用可能更长。
    AgentRuntime SDK 的 create_session / start_task 内部使用异步事件循环，
    因此需要在后台事件循环中执行。
    """
    _LOGGER.info("[AgentRuntime-Start] starting background task agent_id=%s", agent_id)
    start = time.monotonic()
    try:
        result = _run_async_in_background_loop(
            _start_agent_task_background_impl(
                agent_id=agent_id,
                user_input=user_input,
                session_title=session_title,
                metadata=metadata,
            )
        )
        elapsed = time.monotonic() - start
        _LOGGER.info(
            "[AgentRuntime-Start] task_id=%s status=%s elapsed=%.3fs",
            result.get("task_id", "unknown"),
            result.get("status", "unknown"),
            elapsed,
        )
        return result
    except Exception:
        elapsed = time.monotonic() - start
        _LOGGER.exception("[AgentRuntime-Start] failed agent_id=%s elapsed=%.3fs", agent_id, elapsed)
        raise


async def _start_agent_task_background_impl(
    *,
    agent_id: str,
    user_input: str,
    session_title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """非阻塞模式的异步实现。"""
    runtime, session, task = await _create_session_and_task(
        agent_id=agent_id,
        user_input=user_input,
        session_title=session_title,
        metadata=metadata,
    )

    task_id = str(task.task_id)

    # 在后台事件循环中启动后台协程消费 stream_task 事件
    bg_task = asyncio.create_task(
        _background_task_runner(
            runtime,
            task_id,
            initial_status=str(task.status),
            initial_output=task.final_output,
        )
    )
    _background_tasks[task_id] = bg_task

    return {
        "session_id": str(session.session_id),
        "task_id": task_id,
        "status": "pending",
    }


def poll_agent_task(task_id: str) -> dict[str, Any]:
    """轮询任务状态。返回与 run_agent_task() 相同的结构。

    同步函数（可在同步 HTTP handler 中直接调用）。
    使用后台事件循环避免阻塞主线程。
    """
    _LOGGER.debug("[AgentRuntime-Poll] polling task_id=%s", task_id)
    start = time.monotonic()
    try:
        result = _run_async_in_background_loop(_poll_agent_task_impl(task_id))
        elapsed = time.monotonic() - start
        _LOGGER.debug(
            "[AgentRuntime-Poll] task_id=%s status=%s elapsed=%.3fs",
            task_id,
            result.get("status", "unknown"),
            elapsed,
        )
        return result
    except KeyError:
        # task_id 不存在
        elapsed = time.monotonic() - start
        _LOGGER.warning("[AgentRuntime-Poll] task_id=%s not found (elapsed=%.3fs)", task_id, elapsed)
        raise AgentRuntimeNotFoundError(f"task {task_id} not found") from None
    except Exception:
        elapsed = time.monotonic() - start
        _LOGGER.exception("[AgentRuntime-Poll] task_id=%s poll failed (elapsed=%.3fs)", task_id, elapsed)
        raise


async def _poll_agent_task_impl(task_id: str) -> dict[str, Any]:
    """轮询的异步实现。"""
    runtime = await get_agent_runtime()
    record = await runtime.get_task(task_id)

    status = str(record.status.value) if hasattr(record.status, "value") else str(record.status)
    has_output = record.final_output is not None

    _LOGGER.debug(
        "[AgentRuntime-Poll-Impl] task_id=%s status=%s has_output=%s",
        task_id,
        status,
        has_output,
    )

    return {
        "session_id": str(record.session_id),
        "task_id": str(record.task_id),
        "status": status,
        "final_output": record.final_output,
    }
