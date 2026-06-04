"""数据直达响应返回码（接口规范 v0.55 附录B）。

通用：``200`` 调用成功 / ``300`` 调用失败。失败时 ``data``/``message`` 带分域错误码：
  - ``catalog-NNN`` 目录返回码（catalog-001 无效目录编码 … catalog-033 缺资源平台名称）
  - ``res-NNN``     资源基础返回码
  - ``api-NNN``     API 资源返回码
  - ``db-NNN``      库表资源返回码

本模块把国家平台原始响应 ``{code, message, data}`` 归一为 ``NationalResponse``，
只判成功/失败 + 透传域错误码（不硬编码全部码表 —— 码表会演进，硬编码即漂移源；
我们诚实透传 message/code 给上层与审计）。纯函数、可单测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SUCCESS_CODE = "200"
FAILURE_CODE = "300"

# 分域错误码前缀（仅用于诊断归类，不做穷举校验）。
DOMAIN_PREFIXES = ("catalog-", "res-", "api-", "db-")


@dataclass(frozen=True)
class NationalResponse:
    """国家平台一次调用的归一化结果。

    ``ok`` = code 为成功码（"200"）。``error_domain`` 在失败且 message/code 命中分域前缀时给出
    （catalog/res/api/db），否则 None。``raw`` 保留原始响应供审计回溯。
    """

    code: str
    message: str
    data: Any = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def ok(self) -> bool:
        return self.code == SUCCESS_CODE

    @property
    def error_domain(self) -> str | None:
        if self.ok:
            return None
        probe = f"{self.code} {self.message}".lower()
        for pfx in DOMAIN_PREFIXES:
            if pfx in probe:
                return pfx.rstrip("-")
        return None


def parse_response(raw: dict[str, Any]) -> NationalResponse:
    """把国家平台 JSON 响应解析为 NationalResponse。缺字段 fail-closed 为失败。"""
    if not isinstance(raw, dict):
        return NationalResponse(code=FAILURE_CODE, message="国家平台响应非法（非 JSON 对象）", raw={})
    code = str(raw.get("code", FAILURE_CODE)).strip() or FAILURE_CODE
    message = str(raw.get("message", "")).strip()
    return NationalResponse(code=code, message=message, data=raw.get("data"), raw=raw)
