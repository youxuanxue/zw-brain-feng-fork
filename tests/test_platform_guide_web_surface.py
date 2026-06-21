"""Agent 对话 Web 消费面：提问请求体须序列化岗位字符串，而非 Vue Ref。

PR #313 后 ``usePlatformGuideChat`` 收敛为通用 ``useAgentChat`` 的薄包装（单一对话
引擎），``ask()`` 的 ``authFetch(..., { body: JSON.stringify({...}) })`` 实体移到了
``useAgentChat.ts``——平台指南副驾、数据应用、找数副驾共用同一 POST body。本测试随之
定位 ``useAgentChat.ts`` 内该 body，在其范围内校验 ``role:`` 取 ``.value`` 解包后的
字符串而不是裸 Ref（一处守卫覆盖所有走该引擎的内置 Agent，含平台指南）。
比裸子串匹配强：移到文件其它位置（注释 / 文档字符串）不再误判通过。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _extract_ask_fetch_body(src: str) -> str:
    """从 useAgentChat.ts 抽出 ``ask()`` 中 ``authFetch`` 调用的 JSON body。"""
    # URL 经 apiUrl() 单一前缀源包裹（authFetch(apiUrl('/api/agent-runtime/tasks'), {...})），
    # 故 url 后允许可选 `apiUrl(` 包装 + 闭合括号，再定位到同一 fetch 选项里的 body。
    match = re.search(
        r"authFetch\(\s*(?:apiUrl\(\s*)?['\"]/api/agent-runtime/tasks['\"].*?"
        r"body:\s*JSON\.stringify\(\s*(\{.*?\})\s*\)",
        src,
        re.DOTALL,
    )
    assert match, "could not locate /api/agent-runtime/tasks fetch JSON body in useAgentChat.ts"
    return match.group(1)


def test_platform_guide_ask_serializes_product_role_value() -> None:
    src = (REPO / "zw-brain-web" / "src" / "composables" / "useAgentChat.ts").read_text(
        encoding="utf-8",
    )
    body = _extract_ask_fetch_body(src)
    assert re.search(r"role:\s*getProductRole\(\)\.value", body), (
        f"role must serialize unwrapped Ref value, got body: {body!r}"
    )
    assert not re.search(r"role:\s*getProductRole\(\)\s*,", body), (
        f"role must not be set to the Ref object itself, got body: {body!r}"
    )
