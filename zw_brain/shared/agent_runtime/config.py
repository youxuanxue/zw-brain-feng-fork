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


# AgentRuntime openai_compatible 适配器在任务执行期读 os.environ，不只读 for_product(env=...) 入参。
_OPENAI_BRIDGE_ENV_KEYS = (
    "OPENAI_COMPATIBLE_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_COMPATIBLE_BASE_URL",
    "OPENAI_BASE_URL",
)

# 网关不要求鉴权时，占位 Bearer（须非空字符串才能通过 AgentRuntime 校验）。
_DEFAULT_OPTIONAL_INFERENCE_API_KEY = "unused"


def embedded_runtime_env() -> dict[str, str]:
    """构建 Embedded SDK 用的环境变量，避免旧 agent-runtime/.env.local 里的路径覆盖 zw-brain 配置。

    若 shell 中曾 `source` 过旧环境的 ``AGENT_RUNTIME_*``（指向 /data/xuanzhaofeng/...），
    直接传入 ``os.environ`` 会让 Runtime 加载错误 agents 目录或 schema。此处剔除路径类
    覆盖项，保留模型网关（OPENAI_* / INSPUR_*）等仍可能需要的项。

    AgentRuntime ``openai_compatible`` 适配器只认 ``OPENAI_COMPATIBLE_*`` / ``OPENAI_*``；
    zw-brain 统一使用 ``INSPUR_INFERENCE_*``（D6）。在显式未设置 OPENAI 变量时，从 Inspur
    网关变量桥接，避免平台指南等 Embedded 任务在真实 LLM 路径下缺 key/base_url。
    """
    # 精确匹配（不是 prefix）—— 这些 key 在旧 agent-runtime/.env.local 里指向其他工作区，
    # 误漂到 zw-brain 进程会让 Runtime 加载错 agents 目录 / schema。
    blocked_env_keys = frozenset(
        (
            "AGENT_RUNTIME_AGENTS_DIR",
            "AGENT_RUNTIME_SCHEMA_PATH",
            "AGENT_RUNTIME_WORKSPACE_ROOT",
            "AGENT_RUNTIME_CONFIG_PATH",
            "AGENT_RUNTIME_LOG_DIR",
            "AGENT_RUNTIME_DATABASE_URL",
        )
    )
    env = dict(os.environ)
    for key in list(env):
        if key in blocked_env_keys:
            env.pop(key, None)
    _bridge_inspur_inference_to_openai_compatible(env)
    return env


def apply_embedded_runtime_env_to_process() -> dict[str, str]:
    """构建 Embedded 环境并写入进程 os.environ（供 AgentRuntime 模型适配器读取）。"""
    env = embedded_runtime_env()
    for key in _OPENAI_BRIDGE_ENV_KEYS:
        bridged = (env.get(key) or "").strip()
        if not bridged:
            continue
        current = (os.environ.get(key) or "").strip()
        if not current:
            os.environ[key] = bridged
    return env


def _env_str(env: dict[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _inference_api_key_optional(env: dict[str, str]) -> bool:
    flag = _env_str(env, "ZW_BRAIN_INFERENCE_API_KEY_OPTIONAL").lower()
    return flag in {"1", "true", "yes", "on"}


def _bridge_inspur_inference_to_openai_compatible(env: dict[str, str]) -> None:
    """Map zw-brain Inspur gateway env → AgentRuntime openai_compatible adapter env."""
    if not _env_str(env, "OPENAI_COMPATIBLE_API_KEY") and not _env_str(env, "OPENAI_API_KEY"):
        api_key = _env_str(env, "INSPUR_INFERENCE_API_KEY") or _env_str(env, "AUTH_TOKEN") or _env_str(
            env, "ZW_BRAIN_INFERENCE_API_KEY"
        )
        if not api_key and _inference_api_key_optional(env):
            placeholder = _env_str(env, "ZW_BRAIN_INFERENCE_API_KEY_PLACEHOLDER")
            api_key = placeholder or _DEFAULT_OPTIONAL_INFERENCE_API_KEY
        if api_key:
            env["OPENAI_COMPATIBLE_API_KEY"] = api_key
            if not _env_str(env, "OPENAI_API_KEY"):
                env["OPENAI_API_KEY"] = api_key

    if not _env_str(env, "OPENAI_COMPATIBLE_BASE_URL") and not _env_str(env, "OPENAI_BASE_URL"):
        base_url = _env_str(env, "INSPUR_INFERENCE_BASE_URL") or _env_str(env, "BASE_URL")
        if base_url:
            env["OPENAI_COMPATIBLE_BASE_URL"] = base_url
            if not _env_str(env, "OPENAI_BASE_URL"):
                env["OPENAI_BASE_URL"] = base_url


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
