"""AgentRuntime 异常类（住 shared 层，供 shared 的 service.py 与 command 的
agent_runtime_bridge.py 共用）。

放这里而非 command/agent_runtime_bridge.py 的原因：service.py 在 shared 层，
按分层 entry→command→domain→shared 不得反向 import command。异常类下沉到 shared
后，service.py 可直接 raise，command 层再导入并重导出（同一个类对象，
`except bridge.AgentRuntimeNotFoundError` 仍能接住 service.py 抛出的实例）。
"""

from __future__ import annotations


class AgentRuntimeNotEnabledError(RuntimeError):
    """ZW_BRAIN_AGENT_RUNTIME_ENABLED 未开启时调用 runtime 能力。"""


class AgentRuntimeNotFoundError(LookupError):
    """请求的 agent / 任务 / 能力不存在。"""
