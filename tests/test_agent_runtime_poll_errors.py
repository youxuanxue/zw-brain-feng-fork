"""回归：poll_agent_task 对未知 task_id 必须抛 AgentRuntimeNotFoundError。

修复前 service.py 直接 `raise AgentRuntimeNotFoundError(...)` 但该类未导入
（定义在 command 层、service 在 shared 层不得反向 import），运行时这条 not-found
分支会抛 NameError 而非预期异常 —— 即非阻塞轮询「任务不存在」直接崩。
本测试钉死：异常类住 shared.errors、service 抛得出、command 重导出同一对象。
"""

from __future__ import annotations

import pytest

from zw_brain.command import agent_runtime_bridge as bridge
from zw_brain.shared.agent_runtime import service
from zw_brain.shared.agent_runtime.errors import AgentRuntimeNotFoundError


def test_exception_class_is_single_object_across_layers() -> None:
    # service raise 的与 command 重导出的、与 shared 定义的必须是同一个类对象，
    # 否则 server.py 的 `except bridge.AgentRuntimeNotFoundError` 接不住。
    assert service.AgentRuntimeNotFoundError is AgentRuntimeNotFoundError
    assert bridge.AgentRuntimeNotFoundError is AgentRuntimeNotFoundError


def test_poll_unknown_task_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    # 模拟后台事件循环对未知 task_id 抛 KeyError（即 _poll_agent_task_impl 内未命中）。
    def _boom(coro: object) -> None:
        close = getattr(coro, "close", None)
        if callable(close):
            close()  # 关闭未 await 的协程，避免 RuntimeWarning
        raise KeyError("task")

    monkeypatch.setattr(service, "_run_async_in_background_loop", _boom)

    # 修复前：NameError（AgentRuntimeNotFoundError 未定义）→ 此断言失败。
    with pytest.raises(AgentRuntimeNotFoundError):
        service.poll_agent_task("nonexistent-task-id")
