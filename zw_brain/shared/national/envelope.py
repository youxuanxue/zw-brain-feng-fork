"""数据直达报文 envelope（接口规范 v0.55 §5）。

Message Header（HTTP 头，4 个必填）：
  - ``gjzwfwpt_rid``  请求者身份标识（国家平台向各省下发）
  - ``gjzwfwpt_sid``  服务接口标识（每接口唯一）
  - ``gjzwfwpt_rtime`` 服务调用时间（毫秒时间戳字符串，文档示例 new Date().getTime()）
  - ``gjzwfwpt_sign`` 签名（见 signing.py）

Message Body：JSON，**所有字段 key 小写**、UTF-8（文档明确：模板可能大写，但下发报文一律小写）。
本模块只构造 header/body（纯函数），不发请求；rtime 由调用方注入（client 用可注入时钟，测试可定值）。
"""

from __future__ import annotations

from typing import Any

from zw_brain.shared.national.provisioning import NationalProvisioning
from zw_brain.shared.national.signing import sign_request

HEADER_RID = "gjzwfwpt_rid"
HEADER_SID = "gjzwfwpt_sid"
HEADER_RTIME = "gjzwfwpt_rtime"
HEADER_SIGN = "gjzwfwpt_sign"


class MissingInterfaceSidError(KeyError):
    """provisioning.sid_map 未配置该接口的 sid —— fail-closed，不对外发未签名/错签名请求。"""


def build_headers(prov: NationalProvisioning, interface_name: str, rtime: str) -> dict[str, str]:
    """构造 4 个必填 HTTP 头。接口 sid 缺失 → 抛错（不静默发请求）。"""
    sid = prov.sid_for(interface_name)
    if not sid:
        raise MissingInterfaceSidError(
            f"接口 {interface_name!r} 未配置 gjzwfwpt_sid（ZW_BRAIN_NATIONAL_SID_MAP 缺该项）"
        )
    return {
        HEADER_RID: prov.rid,
        HEADER_SID: sid,
        HEADER_RTIME: rtime,
        HEADER_SIGN: sign_request(sid=sid, rid=prov.rid, rtime=rtime, appsecret=prov.appsecret),
    }


def _lower_keys(value: Any) -> Any:
    """递归把 dict 的 key 全转小写（数组元素逐个处理）。

    文档规则：报文 JSON 字段一律小写。我们在出站统一规范化，避免上游 payload 大小写不一致。
    """
    if isinstance(value, dict):
        return {str(k).lower(): _lower_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_lower_keys(v) for v in value]
    return value


def build_body(payload: dict[str, Any]) -> dict[str, Any]:
    """规范化 Message Body：key 全小写。"""
    return _lower_keys(payload)
