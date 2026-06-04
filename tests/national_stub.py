"""协议合规桩（数据直达国家端模拟）—— 测试夹具，**非业务数据 mock**（D50 / 承 D11）。

国家平台是外部基础设施（架构 §3.4「保持外部依赖」），本期无真实端点可联调。本桩只校验
**我方 client 是否会说协议**：4 个签名头齐全、签名可被相同算法复算命中、body 是合法小写 JSON、
URL 走 /sysapi/。校验通过则返回 canned ``{code,message,data}``（返回码取自附录B）。它**不持有、
不返回任何业务行**（无目录/资源/申请数据），故不触 no-mock 红线。

经 client 的 transport seam 注入，无需真实 socket，全程确定性。
"""

from __future__ import annotations

import json
from typing import Any

from zw_brain.shared.national.envelope import (
    HEADER_RID,
    HEADER_RTIME,
    HEADER_SID,
    HEADER_SIGN,
)
from zw_brain.shared.national.signing import sign_request


class ProtocolViolation(AssertionError):
    """我方 client 发出的请求不符合协议（桩用断言暴露，测试即失败）。"""


def make_stub_transport(
    appsecret: str,
    *,
    canned: dict[str, Any] | None = None,
    captured: list[dict[str, Any]] | None = None,
):
    """构造一个 transport，校验协议合规后返回 canned 响应。

    appsecret：桩用它复算签名，验证 client 的 gjzwfwpt_sign 正确。
    canned：要返回的 ``{code,message,data}``（默认成功 200）。
    captured：若传入 list，会把每次 (url, headers, body) 追加进去供断言。
    """
    response = canned if canned is not None else {"code": "200", "message": "成功", "data": {}}

    def transport(url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
        # URL 形态
        if "/sysapi/" not in url:
            raise ProtocolViolation(f"URL 未走 /sysapi/：{url}")
        # 4 头齐全
        for h in (HEADER_RID, HEADER_SID, HEADER_RTIME, HEADER_SIGN):
            if not headers.get(h):
                raise ProtocolViolation(f"缺签名头 {h}")
        # 签名可复算命中（sid+rid+rtime, appsecret）
        expect = sign_request(
            sid=headers[HEADER_SID],
            rid=headers[HEADER_RID],
            rtime=headers[HEADER_RTIME],
            appsecret=appsecret,
        )
        if headers[HEADER_SIGN] != expect:
            raise ProtocolViolation("gjzwfwpt_sign 验签失败（client 签名与桩复算不一致）")
        # body 是合法小写 JSON
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProtocolViolation(f"body 非合法 UTF-8 JSON：{exc}") from exc
        _assert_lowercase_keys(parsed)
        if captured is not None:
            captured.append({"url": url, "headers": dict(headers), "body": parsed})
        return 200, json.dumps(response, ensure_ascii=False).encode("utf-8")

    return transport


def _assert_lowercase_keys(value: Any) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and k != k.lower():
                raise ProtocolViolation(f"body key 未小写：{k!r}")
            _assert_lowercase_keys(v)
    elif isinstance(value, list):
        for v in value:
            _assert_lowercase_keys(v)
