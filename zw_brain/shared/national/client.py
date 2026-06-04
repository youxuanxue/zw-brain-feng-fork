"""数据直达地方端 client（接口规范 v0.55 §5 + 附录C）。

我们是地方端：``POST {endpoint}/sysapi/{path}``，带 4 个签名头 + 小写 JSON body，
解析 ``{code, message, data}``。传输层经 ``transport`` seam 注入 —— 生产用 stdlib urllib，
测试注入协议合规桩（``tests/national/stub_server``），故 client 全程不依赖真实网络即可验证。

诚实口径：本 client 只在 **已配置接入凭据**（NationalProvisioning）时才会被构造与调用；
是否配置由上层 gate 判定（shared.national.provisioning.resolve_national_channel_state）。
client 不读环境、不判 flag —— 它只忠实地"说协议"。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from zw_brain.shared.national.envelope import build_body, build_headers
from zw_brain.shared.national.provisioning import NationalProvisioning
from zw_brain.shared.national.return_codes import (
    FAILURE_CODE,
    NationalResponse,
    parse_response,
)

# transport(url, headers, body_bytes) -> (http_status, response_bytes)
Transport = Callable[[str, dict[str, str], bytes], "tuple[int, bytes]"]
# clock() -> 毫秒时间戳（int）。文档示例 new Date().getTime()。
Clock = Callable[[], int]


def _urllib_transport(url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
    """默认传输：stdlib urllib（不引第三方依赖）。返回 (status, bytes)。"""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (固定 http(s) 端点)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # 4xx/5xx 仍带 body
        return exc.code, exc.read()


def _default_clock() -> int:
    # time.time() 在测试里可被 monkeypatch；client 默认使用，测试一般注入定值 clock。
    import time

    return int(time.time() * 1000)


@dataclass
class NationalDirectClient:
    """数据直达地方端调用器。"""

    provisioning: NationalProvisioning
    transport: Transport = _urllib_transport
    clock: Clock = _default_clock

    def post(self, interface_name: str, path: str, payload: dict[str, Any]) -> NationalResponse:
        """调用一个上报/查询接口。

        interface_name：用于在 sid_map 取 gjzwfwpt_sid（接口规范每接口一个 sid）。
        path：URL 路径（/sysapi/<path>）。payload：业务字段（出站统一小写化）。
        """
        rtime = str(self.clock())
        headers = build_headers(self.provisioning, interface_name, rtime)
        headers["Content-Type"] = "application/json;charset=utf-8"
        headers["Accept"] = "application/json"
        body = json.dumps(build_body(payload), ensure_ascii=False).encode("utf-8")
        url = f"{self.provisioning.endpoint}/sysapi/{path.lstrip('/')}"
        status, raw_bytes = self.transport(url, headers, body)
        try:
            parsed = json.loads(raw_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return NationalResponse(
                code=FAILURE_CODE,
                message=f"国家平台响应解析失败（HTTP {status}）",
                raw={},
            )
        return parse_response(parsed)
