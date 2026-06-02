"""平台指南 Web 消费面：提问请求体须序列化岗位字符串，而非 Vue Ref。

zw-brain-web 暂无 Vitest 基础设施，无法 mock fetch 跑行为断言；本测试改为定位
``ask()`` 内 ``authFetch(..., { body: JSON.stringify({...}) })`` 的真实 body，
在该 body 范围内校验 ``role:`` 取的是 ``.value`` 解包后的字符串而不是裸 Ref。
比裸子串匹配强：移到文件其它位置（注释 / 文档字符串）不再误判通过。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _extract_ask_fetch_body(src: str) -> str:
    """从 usePlatformGuideChat.ts 抽出 ``ask()`` 中 ``authFetch`` 调用的 JSON body。"""
    # URL 经 apiUrl() 单一前缀源包裹（authFetch(apiUrl('/api/agent-runtime/tasks'), {...})），
    # 故 url 后允许可选 `apiUrl(` 包装 + 闭合括号，再定位到同一 fetch 选项里的 body。
    match = re.search(
        r"authFetch\(\s*(?:apiUrl\(\s*)?['\"]/api/agent-runtime/tasks['\"].*?"
        r"body:\s*JSON\.stringify\(\s*(\{.*?\})\s*\)",
        src,
        re.DOTALL,
    )
    assert match, "could not locate /api/agent-runtime/tasks fetch JSON body in usePlatformGuideChat.ts"
    return match.group(1)


def test_platform_guide_ask_serializes_product_role_value() -> None:
    src = (REPO / "zw-brain-web" / "src" / "composables" / "usePlatformGuideChat.ts").read_text(
        encoding="utf-8",
    )
    body = _extract_ask_fetch_body(src)
    assert re.search(r"role:\s*getProductRole\(\)\.value", body), (
        f"role must serialize unwrapped Ref value, got body: {body!r}"
    )
    assert not re.search(r"role:\s*getProductRole\(\)\s*,", body), (
        f"role must not be set to the Ref object itself, got body: {body!r}"
    )
