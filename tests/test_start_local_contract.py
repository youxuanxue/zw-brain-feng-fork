from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_start_local_fails_closed_when_independent_agent_runtime_lacks_inference_env():
    """启用独立 AgentRuntime 服务时必须启动期校验 AR 模型配置，不能到 UI 对话时才失败。"""
    script = (REPO_ROOT / "scripts" / "start-local.sh").read_text(encoding="utf-8")
    assert "ensure_agent_runtime_inference_ready" in script
    assert "AGENT_RUNTIME_DEFAULT_MODEL" in script
    assert "OPENAI_COMPATIBLE_BASE_URL" in script
    assert "OPENAI_COMPATIBLE_API_KEY" in script
    assert "AGENT_RUNTIME_GATEWAY_SIGNING_SECRET" in script
    assert "OPENAI_API_KEY" not in script
    assert "ZW_BRAIN_INFERENCE_" not in script
    service_block = script.find('if [[ "$AR_LOCAL_SWITCH" == "http" ]]; then')
    guard_call = script.find("\n    ensure_agent_runtime_inference_ready\n", service_block)
    ar_start = script.find("\n    start_agent_runtime\n", service_block)
    assert guard_call != -1 and ar_start != -1 and guard_call < ar_start
    assert 'exec env \\' in script
    assert "clear_rest_model_env" in script
    clear_call = script.find("\nclear_rest_model_env\n", service_block)
    rest_start = script.find("\nstart_rest\n", service_block)
    assert clear_call != -1 and rest_start != -1 and clear_call < rest_start


def test_start_local_does_not_describe_agent_runtime_as_http_mode():
    """本地启动脚本只能把 ZW_BRAIN_AGENT_RUNTIME_MODE=http 说成兼容开关，不能说成运行形态。"""
    script = (REPO_ROOT / "scripts" / "start-local.sh").read_text(encoding="utf-8")
    assert "历史兼容启动开关" in script
    for phrase in ("AgentRuntime http 模式", "http 模式", "http 形态", "AgentRuntime 形态=http"):
        assert phrase not in script
