"""AgentRuntime 懒加载：未启用或未调用任务时不必加载 agent_runtime 包。"""
from __future__ import annotations

import importlib.util

import pytest


def test_capability_provider_has_no_top_level_agent_runtime_import() -> None:
    import zw_brain.shared.agent_runtime.capability_provider as mod

    source = importlib.util.find_spec(mod.__name__)
    assert source is not None and source.origin
    text = open(source.origin, encoding="utf-8").read()
    in_type_checking = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("if TYPE_CHECKING:"):
            in_type_checking = True
            continue
        if in_type_checking and stripped and not stripped.startswith("#") and not stripped.startswith("from "):
            in_type_checking = False
        if in_type_checking:
            continue
        if stripped.startswith("from agent_runtime") or stripped.startswith("import agent_runtime"):
            pytest.fail(f"runtime agent_runtime import in capability_provider: {stripped}")


def test_bridge_defers_service_import() -> None:
    import zw_brain.command.agent_runtime_bridge as bridge

    assert "run_agent_task_sync" not in bridge.__dict__


def test_runtime_status_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_AGENT_RUNTIME_ENABLED", raising=False)
    from zw_brain.command.agent_runtime_bridge import runtime_status

    status = runtime_status()
    assert status["enabled"] is False
    assert status["ready"] is False


def test_rest_server_health_agent_runtime_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_AGENT_RUNTIME_ENABLED", raising=False)
    from zw_brain.entry.rest.server import _agent_runtime_bridge

    status = _agent_runtime_bridge().runtime_status()
    assert status["enabled"] is False
    assert status["ready"] is False
