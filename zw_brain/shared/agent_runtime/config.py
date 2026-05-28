from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

ZW_BRAIN_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = ZW_BRAIN_REPO_ROOT / "agent-runtime.yaml"
DEFAULT_AGENTS_DIR = ZW_BRAIN_REPO_ROOT / "agents"
DEFAULT_AGENT_RUNTIME_SCHEMA = ZW_BRAIN_REPO_ROOT / "schemas" / "agent.schema.json"


def zw_brain_repo_root() -> Path:
    return ZW_BRAIN_REPO_ROOT


def agent_runtime_config_path() -> Path:
    override = (os.environ.get("ZW_BRAIN_AGENT_RUNTIME_CONFIG") or "").strip()
    return Path(override) if override else DEFAULT_CONFIG_PATH


def agents_dir() -> Path:
    override = (os.environ.get("ZW_BRAIN_AGENTS_DIR") or "").strip()
    if override:
        return Path(override)
    if DEFAULT_AGENTS_DIR.is_dir():
        return DEFAULT_AGENTS_DIR
    installed = _installed_agents_dir()
    if installed is not None:
        return installed
    return DEFAULT_AGENTS_DIR


def agent_runtime_schema_env() -> Path | None:
    override = (os.environ.get("ZW_BRAIN_AGENT_RUNTIME_SCHEMA") or "").strip()
    return Path(override) if override else None


def _installed_agents_dir() -> Path | None:
    try:
        import zw_brain

        pkg_root = Path(zw_brain.__file__).resolve().parent
        for candidate in (pkg_root.parent / "agents", pkg_root / "agents"):
            if candidate.is_dir():
                return candidate
    except Exception:  # noqa: BLE001
        return None
    return None


def is_agent_runtime_enabled() -> bool:
    return (os.environ.get("ZW_BRAIN_AGENT_RUNTIME_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def embedded_runtime_env() -> dict[str, str]:
    """构建 Embedded SDK 用的环境变量，避免旧 agent-runtime/.env.local 里的路径覆盖 zw-brain 配置。

    若 shell 中曾 `source` 过旧环境的 ``AGENT_RUNTIME_*``（指向 /data/xuanzhaofeng/...），
    直接传入 ``os.environ`` 会让 Runtime 加载错误 agents 目录或 schema。此处剔除路径类
    覆盖项，保留模型网关（OPENAI_* / INSPUR_*）等仍可能需要的项。
    """
    blocked_prefixes = (
        "AGENT_RUNTIME_AGENTS_DIR",
        "AGENT_RUNTIME_SCHEMA_PATH",
        "AGENT_RUNTIME_WORKSPACE_ROOT",
        "AGENT_RUNTIME_CONFIG_PATH",
        "AGENT_RUNTIME_LOG_DIR",
        "AGENT_RUNTIME_DATABASE_URL",
    )
    env = dict(os.environ)
    for key in list(env):
        if key in blocked_prefixes or key.startswith("AGENT_RUNTIME_AGENTS_DIR"):
            env.pop(key, None)
    return env


def agent_runtime_profile() -> str:
    """local_dev → fake core for tests; embedded_single_tenant for production embed."""
    explicit = (os.environ.get("ZW_BRAIN_AGENT_RUNTIME_PROFILE") or "").strip()
    if explicit:
        return explicit
    if (os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("ZW_BRAIN_TEST_MODE") or "").strip():
        return "local_dev"
    return "embedded_single_tenant"


@lru_cache(maxsize=1)
def sibling_agent_runtime_repo() -> Path | None:
    candidate = ZW_BRAIN_REPO_ROOT.parent / "agent-runtime"
    if (candidate / "src" / "agent_runtime").is_dir():
        return candidate
    return None


def resolve_schema_path(config_schema: Path | None) -> Path:
    env_schema = agent_runtime_schema_env()
    if env_schema is not None and env_schema.is_file():
        return env_schema
    if config_schema is not None:
        path = config_schema if config_schema.is_absolute() else ZW_BRAIN_REPO_ROOT / config_schema
        if path.is_file():
            return path
    if DEFAULT_AGENT_RUNTIME_SCHEMA.is_file():
        return DEFAULT_AGENT_RUNTIME_SCHEMA
    sibling = sibling_agent_runtime_repo()
    if sibling is not None:
        schema = sibling / "schemas" / "agent.schema.json"
        if schema.is_file():
            return schema
    packaged = _schema_from_installed_agent_runtime()
    if packaged is not None:
        return packaged
    raise FileNotFoundError(
        "AgentRuntime schema not found; install agent-runtime, set ZW_BRAIN_AGENT_RUNTIME_SCHEMA, "
        "or set schema_path in agent-runtime.yaml"
    )


def _schema_from_installed_agent_runtime() -> Path | None:
    try:
        import importlib.util

        spec = importlib.util.find_spec("agent_runtime")
        if spec is None:
            return None
        roots: list[Path] = []
        if spec.submodule_search_locations:
            roots.extend(Path(p) for p in spec.submodule_search_locations)
        elif spec.origin:
            roots.append(Path(spec.origin).resolve().parent)
        for root in roots:
            for candidate in (
                root.parent / "schemas" / "agent.schema.json",
                root / "schemas" / "agent.schema.json",
            ):
                if candidate.is_file():
                    return candidate
    except Exception:  # noqa: BLE001
        return None
    return None
