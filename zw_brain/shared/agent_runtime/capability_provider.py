"""Agent 清单 sidecar 读取助手（D68 单一模型 · standalone-only）.

历史的 in-process ``ZwBrainCapabilityProvider``（embedded ``dynamic_capability_providers``
注入）已随 embedded 退役移除——单一模型下副驾的能力经 AGENT.yaml ``kind:api`` 工具
回调 zw-brain 已发布认证 API（见 ``agents/*/AGENT.yaml`` + ``*.openapi.yaml``）。
本模块仅保留与 AgentRuntime SDK **无关**的 sidecar 读取助手（供 command 层列出
agent 能力 / 解析 agent 目录用），不 import AgentRuntime SDK。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zw_brain.shared.agent_runtime.config import agents_dir


def agent_directory_for_id(agent_id: str) -> Path:
    folder = agent_id.replace("-", "_")
    return agents_dir() / folder


def load_capability_bindings(agent_dir: Path) -> list[dict[str, Any]]:
    """读 ``capabilities.json`` 的 ``capability_tools``（能力声明，供列出/校验用）。"""
    sidecar = agent_dir / "capabilities.json"
    if not sidecar.is_file():
        return []
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    tools = raw.get("capability_tools") if isinstance(raw, dict) else None
    if not isinstance(tools, list):
        return []
    bindings: list[dict[str, Any]] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        skill_id = str(item.get("skill_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not skill_id or not name:
            continue
        bindings.append(
            {
                "skill_id": skill_id,
                "name": name,
                "description": str(item.get("description") or f"zw-brain skill {skill_id}"),
                "input_schema": item.get("input_schema"),
            }
        )
    return bindings
