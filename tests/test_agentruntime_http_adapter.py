"""Unit tests for the standalone-AgentRuntime HTTP adapter (D68 单一模型 · 独立服务).

CI-safe：mock AgentRuntimeClient，不依赖 live AR（确定性，承 D66 CI 不装 AR wheel）。
覆盖：阻塞模式轮询至终态 + 状态归一（waiting_input→waiting）+ 非阻塞 start +
poll + 404→AgentRuntimeNotFoundError + 纯 HTTP 路径零 SDK 依赖（import 安全）。
真链路（zw-brain REST→独立 AR→agent→结果 + 进程隔离）见 spike 报告 §实测结果。
"""

import base64
import json

import pytest

from zw_brain.shared.agent_runtime import http_client
from zw_brain.shared.agent_runtime.errors import AgentRuntimeNotFoundError


class _FakeClient:
    """模拟 AR REST：start 返回 running，N 次 get 后变 completed。"""

    def __init__(self, *, completes_after: int = 1, terminal: str = "completed", final="OUT"):
        self._n = 0
        self._completes_after = completes_after
        self._terminal = terminal
        self._final = final
        self.created: list[dict] = []
        self.started: list[dict] = []

    def create_session(self, *, agent_id, title, metadata):
        self.created.append({"agent_id": agent_id, "title": title, "metadata": metadata})
        return "sess-1"

    def start_task(self, *, session_id, agent_id, user_input, metadata):
        self.started.append({"session_id": session_id, "agent_id": agent_id, "metadata": metadata})
        return {"task_id": "task-1", "status": "running"}

    def get_task(self, task_id):
        self._n += 1
        if self._n >= self._completes_after:
            return {"session_id": "sess-1", "task_id": task_id, "status": self._terminal, "final_output": self._final}
        return {"session_id": "sess-1", "task_id": task_id, "status": "running", "final_output": None}


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch):
    # 关掉真实 sleep，让轮询循环瞬时跑完
    monkeypatch.setattr(http_client.time, "sleep", lambda *_a, **_k: None)


def _install(monkeypatch, client):
    monkeypatch.setattr(http_client, "get_client", lambda: client)


def test_run_blocking_polls_to_completed(monkeypatch):
    _install(monkeypatch, _FakeClient(completes_after=2, final="推荐结果"))
    r = http_client.run_agent_task_http(agent_id="a-zw-search-helper", user_input="找数", metadata={"caller_role": "ROLE_ORGAN_OPERATER"})
    assert r["status"] == "completed"
    assert r["final_output"] == "推荐结果"
    assert r["session_id"] == "sess-1" and r["task_id"] == "task-1"


def test_status_normalizes_waiting_input(monkeypatch):
    _install(monkeypatch, _FakeClient(completes_after=1, terminal="waiting_input", final=None))
    r = http_client.run_agent_task_http(agent_id="a", user_input="x")
    assert r["status"] == "waiting"  # waiting_input → waiting（保 WebUI resume 流）


def test_blocking_times_out_without_hanging(monkeypatch):
    # 永不终态 → 在 deadline 处返回 timeout（不挂死）
    monkeypatch.setattr(http_client, "_TASK_BLOCK_TIMEOUT_SECONDS", 0.0)
    _install(monkeypatch, _FakeClient(completes_after=10_000))
    r = http_client.run_agent_task_http(agent_id="a", user_input="x")
    assert r["status"] == "timeout"


def test_start_background_returns_immediately(monkeypatch):
    _install(monkeypatch, _FakeClient())
    r = http_client.start_agent_task_background_http(agent_id="a", user_input="x")
    assert r["status"] == "running" and r["task_id"] == "task-1"


def test_poll_maps_and_404_raises(monkeypatch):
    _install(monkeypatch, _FakeClient(completes_after=1, terminal="completed", final="done"))
    assert http_client.poll_agent_task_http("task-1")["status"] == "completed"

    class _NotFound:
        def get_task(self, task_id):
            raise AgentRuntimeNotFoundError("404")

    _install(monkeypatch, _NotFound())
    with pytest.raises(AgentRuntimeNotFoundError):
        http_client.poll_agent_task_http("nope")


def test_http_client_has_no_sdk_dependency():
    """HTTP adapter 零 SDK 依赖：本模块即便 agent_runtime SDK 未安装也可 import（解耦的体现）。"""
    import inspect

    src = inspect.getsource(http_client)
    assert "from agent_runtime" not in src and "import agent_runtime\n" not in src


def test_trusted_gateway_headers_include_admin_runtime(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_GATEWAY_SIGNING_SECRET", "dev-secret")
    headers = http_client._trusted_gateway_headers()  # noqa: SLF001 - guards AR service-to-service auth contract

    assert headers["X-Runtime-Principal-Signature"].startswith("sha256=")
    principal = json.loads(base64.b64decode(headers["X-Runtime-Principal"]).decode("utf-8"))
    assert principal["principal_type"] == "operator"
    assert "admin:runtime" in principal["scopes"]


def test_service_dispatches_to_http(monkeypatch):
    """service.py facade 全部委派到 http_client（单一模型，无 in-process RuntimeService）。"""
    monkeypatch.setenv("ZW_BRAIN_AGENT_RUNTIME_ENABLED", "1")
    from zw_brain.shared.agent_runtime import service

    called = {}
    # service 在模块顶层 `from http_client import run_agent_task_http`，故 patch service 侧绑定。
    monkeypatch.setattr(
        service, "run_agent_task_http",
        lambda **kw: called.update(kw) or {"session_id": "s", "task_id": "t", "status": "completed", "final_output": "ok"},
    )
    out = service.run_agent_task_sync(agent_id="a-zw-search-helper", user_input="hi", metadata={})
    assert out["status"] == "completed" and called["agent_id"] == "a-zw-search-helper"


def test_bridge_task_metadata_does_not_leak_trusted_session_objects():
    from zw_brain.command import agent_runtime_bridge as bridge
    from zw_brain.shared.session_context import (
        TRUSTED_SESSION_CONTEXT_KEY,
        build_trusted_skill_payload,
    )

    trusted = build_trusted_skill_payload(
        {
            "request_id": "UI-AGENT-test",
            "tenant_id": "sd-default",
            "extra_object": object(),
        },
        actor_snapshot={
            "status": "active",
            "tenant_id": "sd-default",
            "org_code": "ORG-A",
            "current_org_code": "ORG-A",
            "current_role": "ROLE_ORGAN_MANAGER",
            "available_contexts": [
                {"org_code": "ORG-A", "role_code": "ROLE_ORGAN_MANAGER", "actor_tags": {}}
            ],
            "actor_tags": {},
        },
    )
    metadata = bridge._resolve_task_metadata(  # noqa: SLF001 - regression guard for HTTP boundary
        role="ROLE_ORGAN_MANAGER",
        request_id=str(trusted["request_id"]),
        metadata={k: v for k, v in trusted.items() if k not in {"agent_id", "input", "role"}},
    )

    json.dumps(metadata)
    assert TRUSTED_SESSION_CONTEXT_KEY not in metadata
    assert "actor_snapshot" not in metadata
    assert "extra_object" not in metadata
    assert metadata == {
        "request_id": "UI-AGENT-test",
        "tenant_id": "sd-default",
        "org_code": "ORG-A",
        "caller_role": "ROLE_ORGAN_MANAGER",
    }
