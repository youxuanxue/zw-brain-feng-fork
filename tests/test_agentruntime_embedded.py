"""Embedded AgentRuntime integration (architecture §8 / wave-0 infra-agentruntime-embedded)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("agent_runtime")

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_YAML = REPO_ROOT / "agents" / "zw_search_helper" / "AGENT.yaml"


@pytest.fixture(autouse=True)
def _agent_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_TEST_MODE", "1")
    monkeypatch.setenv("ZW_BRAIN_AGENT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("INSPUR_INFERENCE_BASE_URL", "http://inspur-inference-gateway.local/v1")
    monkeypatch.setenv("INSPUR_INFERENCE_MODEL", "claude-sonnet-4-7")


def test_agentruntime_validate_zw_search_helper() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "agentruntime_validate.py"), str(AGENT_YAML)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_agentruntime_doctor_dev_target() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "agentruntime_doctor.py"),
            str(AGENT_YAML.parent),
            "--target",
            "dev",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "FAIL" not in proc.stdout


def test_agentruntime_validate_rejects_wrong_spec_version(tmp_path: Path) -> None:
    bad = tmp_path / "AGENT.yaml"
    bad.write_text(
        "schema_version: anp-agent/v1.0\nkind: Agent\nmetadata:\n  id: bad\n  name: bad\n  version: 0.0.1\n  trust_level: untrusted\nmodel:\n  provider: openai_compatible\n  model: test\ninstructions: test\n",
        encoding="utf-8",
    )
    (tmp_path / "capabilities.json").write_text(
        json.dumps({"runtime_spec_version": "anp-agent/v1.0", "auth_mode": "trusted_gateway"}),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "agentruntime_validate.py"), str(bad)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "anp-agent/v1.2" in (proc.stderr + proc.stdout)


def test_zw_brain_capability_provider_invokes_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from zw_brain.command.runtime import get_service, reset_service
    from zw_brain.shared.agent_runtime.capability_provider import ZwBrainCapabilityProvider

    db_path = tmp_path / "brain.db"
    monkeypatch.setenv("ZW_BRAIN_DATABASE_URL", f"sqlite:///{db_path}")
    reset_service()
    brain = get_service()
    provider = ZwBrainCapabilityProvider(brain, agent_dir=AGENT_YAML.parent)
    tools = provider.list_tools(
        type(
            "Ctx",
            (),
            {
                "agent_config": {},
                "agent_identity": {"id": "zw-search-helper"},
                "task_metadata": {"request_id": "req-agentruntime-1"},
                "extensions": {},
            },
        )()
    )
    names = {item["name"] for item in tools}
    assert "search_intent_parse" in names
    assert "data_search" in names

    result = provider.call_tool(
        "search_intent_parse",
        {"query": "户籍信息", "enabled": False},
        type(
            "Ctx",
            (),
            {
                "agent_config": {},
                "agent_identity": {"id": "zw-search-helper"},
                "task_metadata": {"request_id": "req-agentruntime-1"},
                "extensions": {},
            },
        )(),
    )
    assert isinstance(result, dict)
    assert "intent" in result or "keywords" in result or "source" in result
    reset_service()


@pytest.mark.asyncio
async def test_embedded_sdk_task_with_fake_core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from zw_brain.command.runtime import reset_service
    from zw_brain.shared.agent_runtime.config import zw_brain_repo_root
    from zw_brain.shared.agent_runtime.service import get_agent_runtime, reset_agent_runtime

    db_path = tmp_path / "brain.db"
    monkeypatch.setenv("ZW_BRAIN_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ZW_BRAIN_AGENT_RUNTIME_PROFILE", "local_dev")
    reset_service()
    reset_agent_runtime()

    workspace = tmp_path / "workspaces"
    workspace.mkdir()
    monkeypatch.setenv("ZW_BRAIN_AGENT_RUNTIME_CONFIG", "")
    # Point product config paths at repo via default agent-runtime.yaml + local_dev profile

    runtime = await get_agent_runtime()
    assert runtime.settings.runtime_core == "fake"
    # exposes_chat=false 的内置 Agent 不会出现在 list_agents()（仅 chat 发现面）
    agent_ids = {m.agent_id for m in runtime._registry.list_manifests()}  # noqa: SLF001
    assert "zw-search-helper" in agent_ids

    from agent_runtime.runtime.models import CreateSessionRequest, StartTaskRequest

    session = await runtime.create_session(
        CreateSessionRequest(agent_id="zw-search-helper", title="embedded-test")
    )
    task = await runtime.start_task(
        StartTaskRequest(
            session_id=session.session_id,
            agent_id="zw-search-helper",
            input="解析搜索意图：停车场数据",
            metadata={"request_id": "req-embedded-sdk-1"},
        )
    )
    assert task.task_id
    stored = await runtime._task_store.get(task.task_id)  # noqa: SLF001
    manifest = stored.agent_manifest_snapshot
    tool_names = {entry["name"] for entry in manifest.get("tools") or [] if isinstance(entry, dict)}
    assert "search_intent_parse" in tool_names

    reset_agent_runtime()
    reset_service()
    _ = zw_brain_repo_root()  # silence unused in refactor paths
