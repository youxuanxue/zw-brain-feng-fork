"""REST surface for Embedded AgentRuntime."""
from __future__ import annotations

from pathlib import Path

import pytest

from zw_brain.command.agent_runtime_bridge import (
    AgentRuntimeNotEnabledError,
    list_builtin_agents,
    runtime_status,
    start_agent_task,
)
from zw_brain.command.runtime import get_service, reset_service

pytest.importorskip("agent_runtime")

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_AGENT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("ZW_BRAIN_TEST_MODE", "1")
    monkeypatch.setenv("INSPUR_INFERENCE_BASE_URL", "http://inspur-inference-gateway.local/v1")
    monkeypatch.setenv("INSPUR_INFERENCE_MODEL", "claude-sonnet-4-7")


def test_runtime_status_only_exposes_enable_bit() -> None:
    # /health 与 /api/agent-runtime/status 公开返回 runtime_status()，所以它只暴露开关位；
    # Agent topology 详情走 /api/agent-runtime/agents 鉴权 endpoint（test_list_builtin_agents_*）
    status = runtime_status()
    assert status == {"enabled": True}


def test_list_builtin_agents_includes_capabilities() -> None:
    agents = list_builtin_agents()
    helper = next(a for a in agents if a["agent_id"] == "zw-search-helper")
    assert "search.intent.parse" in helper["capability_skills"]
    assert "data.search" in helper["capability_skills"]
    guide = next(a for a in agents if a["agent_id"] == "zw-platform-guide")
    assert "platform.docs.search" in guide["capability_skills"]
    assert "platform.docs.read" in guide["capability_skills"]


def test_start_agent_task_requires_enable_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_AGENT_RUNTIME_ENABLED", raising=False)
    reset_service()
    brain = get_service()
    with pytest.raises(AgentRuntimeNotEnabledError):
        start_agent_task(
            brain=brain,
            role="ROLE_ORGAN_OPERATER",
            agent_id="zw-search-helper",
            user_input="test",
        )


def test_start_agent_task_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from zw_brain.shared.agent_runtime.service import reset_agent_runtime

    db_path = tmp_path / "brain.db"
    monkeypatch.setenv("ZW_BRAIN_DATABASE_URL", f"sqlite:///{db_path}")
    reset_service()
    reset_agent_runtime()
    brain = get_service()
    result = start_agent_task(
        brain=brain,
        role="ROLE_ORGAN_OPERATER",
        agent_id="zw-search-helper",
        user_input="停车场",
        request_id="req-rest-smoke",
        metadata={},
    )
    assert result["task_id"]
    assert result["status"] in {"completed", "failed", "running", "pending"}
    reset_agent_runtime()
    reset_service()
