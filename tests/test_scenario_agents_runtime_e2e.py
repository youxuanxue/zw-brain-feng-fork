# Wave: 1
# Journey: J1 (A① 数据发现副驾) + B 试点 (法人信用画像研判, embedded)
# Pages: P2 资源发现 / 用数方研判
# Consumer-faces: AgentRuntime embedded SDK (RuntimeService Task 生命周期)
# Roles: ROLE_ORGAN_MANAGER
# Trace:
#   docs/scenario-agents/wave1-pilot-acceptance.md §2 tier-3b
#   agents/zw_search_helper/{AGENT.yaml,capabilities.json}
#   agents/legal_person_credit_profiler/{AGENT.yaml,capabilities.json}
#   zw_brain/shared/agent_runtime/service.py (run_agent_task)
"""端到端运行时生命周期验收：两个场景智能体经**真实 AgentRuntime SDK** 的完整
Task 生命周期（create_session → start_task → drain → terminal）跑到 ``completed``，
并验证 runtime 加载的是升级后的 manifest（A① 4 工具 / B 试点 3 工具）。

这覆盖承载栈最上层（agent → AgentRuntime → Task → 终态）。与 tool 执行层
（``test_scenario_agents_pilot_e2e.py``：provider→brain→handler→真实数据）合起来，
两个 agent 的承载链端到端全覆盖。

注意（诚实边界）：本机 runtime_core=fake（local_dev profile），fake 核驱动 Task 到
``completed`` 但不做 LLM 工具编排；「LLM 自主串工具」需 live 集团推理 gateway，见
wave1-pilot-acceptance.md §4。SDK 缺席的环境（如 CI）按既有 importorskip 语义整体 skip。
"""
from __future__ import annotations

import pytest

pytest.importorskip("agent_runtime")


@pytest.fixture(autouse=True)
def _agent_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_TEST_MODE", "1")
    monkeypatch.setenv("ZW_BRAIN_AGENT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("ZW_BRAIN_AGENT_RUNTIME_PROFILE", "local_dev")
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_GATEWAY_URL", "http://inspur-inference-gateway.local/v1")
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_MODEL", "claude-sonnet-4-7")


_EXPECTED_TOOLS = {
    "zw-search-helper": {"search_intent_parse", "data_search", "catalog_browse", "catalog_entry_query"},
    "legal-person-credit-profiler": {"data_search", "catalog_entry_query", "catalog_item_query"},
}


@pytest.mark.anyio
@pytest.mark.parametrize("agent_id", list(_EXPECTED_TOOLS))
async def test_agent_runs_through_runtime_to_completed(agent_id: str) -> None:
    """经真实 AgentRuntime SDK 跑完整 Task：到 completed 终态，且 manifest 快照含升级后工具集。"""
    from zw_brain.command.runtime import reset_service
    from zw_brain.shared.agent_runtime.service import (
        get_agent_runtime,
        reset_agent_runtime,
        run_agent_task,
    )

    reset_service()
    reset_agent_runtime()
    runtime = await get_agent_runtime()
    assert runtime.settings.runtime_core == "fake"  # local_dev：确定性核，不连 live 推理

    result = await run_agent_task(
        agent_id=agent_id,
        user_input="查询法人信用画像XZ9 的企业登记信息",
        metadata={"request_id": f"rt-e2e-{agent_id}", "caller_role": "ROLE_ORGAN_MANAGER"},
    )

    # 1) 经真实 runtime 跑到终态 completed（agent 加载 + Task 生命周期端到端）
    assert result["status"] == "completed", result
    assert result["final_output"]  # 产出非空

    # 2) runtime 加载的是升级后的 manifest：Task 快照携带该 agent 声明的工具集
    stored = await runtime._task_store.get(result["task_id"])  # noqa: SLF001
    snapshot = stored.agent_manifest_snapshot or {}
    tool_names = {e["name"] for e in (snapshot.get("tools") or []) if isinstance(e, dict)}
    assert _EXPECTED_TOOLS[agent_id] <= tool_names, (agent_id, sorted(tool_names))

    reset_agent_runtime()
    reset_service()
