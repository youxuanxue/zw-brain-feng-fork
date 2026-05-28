from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from zw_brain.command.runtime import get_service
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

_LOGGER = logging.getLogger(__name__)
_runtime: Any | None = None
_runtime_lock = asyncio.Lock()


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


async def get_agent_runtime():
    """Lazy singleton Embedded RuntimeService (in-process, no HTTP server)."""
    global _runtime
    if _runtime is not None:
        return _runtime

    async with _runtime_lock:
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

        brain = get_service()
        providers: dict[str, ZwBrainCapabilityProvider] = {}
        for agent_yaml in sorted(agents_dir().glob("*/AGENT.yaml")):
            agent_id = _agent_id_from_yaml(agent_yaml)
            if not agent_id:
                continue
            providers[agent_id] = ZwBrainCapabilityProvider(
                brain,
                agent_dir=agent_directory_for_id(agent_id),
            )

        repo_root = zw_brain_repo_root()
        runtime_env = apply_embedded_runtime_env_to_process()
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


_TASK_STREAM_TIMEOUT_SECONDS = float(os.environ.get("ZW_BRAIN_AGENT_TASK_TIMEOUT_SECONDS") or 300)


async def run_agent_task(
    *,
    agent_id: str,
    user_input: str,
    session_title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from agent_runtime.runtime.models import CreateSessionRequest, StartTaskRequest

    runtime = await get_agent_runtime()
    session = await runtime.create_session(
        CreateSessionRequest(
            agent_id=agent_id,
            title=session_title or f"zw-brain:{agent_id}",
            metadata={"tenant_id": "sd-default"},
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
    final_status = task.status
    final_output = task.final_output

    async def _drain_until_terminal() -> None:
        nonlocal final_status, final_output
        async for event in runtime._task_runner.stream_task(task.task_id):  # noqa: SLF001
            if event.event == "task_completed":
                final_output = (event.payload or {}).get("final_output", final_output)
                final_status = "completed"
                break
            if event.event == "task_failed":
                final_status = "failed"
                break

    try:
        await asyncio.wait_for(_drain_until_terminal(), timeout=_TASK_STREAM_TIMEOUT_SECONDS)
    except TimeoutError:
        final_status = "timeout"

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
