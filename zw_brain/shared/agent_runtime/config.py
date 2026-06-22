"""AgentRuntime 接入配置（D68 单一模型 · standalone-only）.

embedded（in-process SDK）退役后，本模块只留：①是否启用 AR 接入；②独立 AR 服务地址；
③agents 目录解析（供 command 层列出/校验 agent 清单）；④仓库根。
**不再**含 in-process 运行时的 env 桥接 / schema 解析 / profile / ProductRuntimeConfig 路径
等 embedded-only 配置（已随 embedded 移除）。AR 独立进程自读其 ``agent-runtime*.yaml``
并由启动脚本桥接 ``OPENAI_COMPATIBLE_*``。
"""

from __future__ import annotations

import os
from pathlib import Path

ZW_BRAIN_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AGENTS_DIR = ZW_BRAIN_REPO_ROOT / "agents"


def zw_brain_repo_root() -> Path:
    return ZW_BRAIN_REPO_ROOT


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


def agent_runtime_base_url() -> str | None:
    """独立 AgentRuntime 服务的 base URL（http_client 用；zw-brain 经此 HTTP 驱动 AR）。"""
    url = (os.environ.get("ZW_BRAIN_AGENT_RUNTIME_URL") or "").strip()
    return url or None
