"""国家平台接入凭据与通道开关（provisioning + flag）。

诚实口径（D50 / 承 D47 凭据诚实化）：
  - 通道默认 **关闭**。`ZW_BRAIN_NATIONAL_CHANNEL_ENABLED=1` 才打开（单值即可，因为打开本身
    不授予任何对外能力 —— 真正能对外取决于是否已配置接入凭据）。
  - 接入凭据由国家平台在客户上线时下发（接口规范 v0.55 附录C：rid / appkey / appsecret /
    每接口 sid + 端点）。**全部经环境变量注入、禁硬编码**（架构约束 §所有配置通过环境变量注入）。
    任一缺失 → 视为"未配置"，连接器静默、对外零请求。
  - 三态：OFF（开关关）/ ON_UNPROVISIONED（开关开但凭据未配齐）/ ON_PROVISIONED（开关开 + 凭据齐）。
    只有 ON_PROVISIONED 才会真正构造对外请求；其余两态由 handler 返回诚实 pending、不 404。

密钥安全：appsecret/appkey 标 ``repr=False``，不进 ``repr()`` / 日志 / snapshot / manifest。
"""

from __future__ import annotations

import enum
import json
import os
from dataclasses import dataclass, field


class NationalChannelState(enum.Enum):
    """国家通道运行态（由 env 纯函数派生，gate 与 webui 投影共用单一事实源）。"""

    OFF = "off"
    ON_UNPROVISIONED = "unprovisioned"
    ON_PROVISIONED = "provisioned"


# 环境变量名（单一事实源 —— 测试与文档引用此处，禁散落字面量）。
ENV_ENABLED = "ZW_BRAIN_NATIONAL_CHANNEL_ENABLED"
ENV_ENDPOINT = "ZW_BRAIN_NATIONAL_ENDPOINT"
ENV_RID = "ZW_BRAIN_NATIONAL_RID"
ENV_APPKEY = "ZW_BRAIN_NATIONAL_APPKEY"
ENV_APPSECRET = "ZW_BRAIN_NATIONAL_APPSECRET"
ENV_SID_MAP = "ZW_BRAIN_NATIONAL_SID_MAP"


@dataclass(frozen=True)
class NationalProvisioning:
    """一套已配齐的国家平台接入凭据（附录C）。

    ``sid_map``：接口名 → 服务接口标识（gjzwfwpt_sid），每接口一个，由国家平台逐个下发。
    """

    endpoint: str
    rid: str
    appkey: str = field(repr=False)
    appsecret: str = field(repr=False)
    sid_map: dict[str, str]

    def sid_for(self, interface_name: str) -> str | None:
        """取某接口的服务接口标识；未配置该接口 → None（调用方 fail-closed）。"""
        return self.sid_map.get(interface_name)


def get_national_channel_enabled() -> bool:
    """通道开关是否打开（默认 False）。打开 ≠ 可对外，仅放开"尝试"。"""
    return os.environ.get(ENV_ENABLED, "").strip() == "1"


def _parse_sid_map(raw: str | None) -> dict[str, str]:
    """解析 ``ZW_BRAIN_NATIONAL_SID_MAP``（JSON: 接口名→sid）。非法/空 → 空 dict（fail-closed）。"""
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    # 只保留双侧均为非空字符串的条目。
    return {
        str(k): str(v)
        for k, v in parsed.items()
        if isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
    }


def load_national_provisioning() -> NationalProvisioning | None:
    """从环境读取接入凭据；任一必填项缺失 → None（未配置）。

    必填：endpoint / rid / appkey / appsecret 且 sid_map 至少一项。任一为空即未配齐。
    """
    endpoint = (os.environ.get(ENV_ENDPOINT) or "").strip().rstrip("/")
    rid = (os.environ.get(ENV_RID) or "").strip()
    appkey = (os.environ.get(ENV_APPKEY) or "").strip()
    appsecret = (os.environ.get(ENV_APPSECRET) or "").strip()
    sid_map = _parse_sid_map(os.environ.get(ENV_SID_MAP))
    if not (endpoint and rid and appkey and appsecret and sid_map):
        return None
    return NationalProvisioning(
        endpoint=endpoint,
        rid=rid,
        appkey=appkey,
        appsecret=appsecret,
        sid_map=sid_map,
    )


def is_national_provisioned() -> bool:
    """接入凭据是否已配齐。"""
    return load_national_provisioning() is not None


def resolve_national_channel_state() -> NationalChannelState:
    """派生当前通道三态（gate + webui 投影单一事实源）。"""
    if not get_national_channel_enabled():
        return NationalChannelState.OFF
    if not is_national_provisioned():
        return NationalChannelState.ON_UNPROVISIONED
    return NationalChannelState.ON_PROVISIONED
