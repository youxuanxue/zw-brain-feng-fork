"""国家数据平台接入（数据直达）共享层 — 纯协议，无 DB、无反向引用。

我们是 **地方端（省级平台）**：调用国家平台（国家端）暴露的查询 / 上报 / 消息同步接口。
本包只承载协议事实（报文 envelope、HMAC-SHA256 签名、返回码映射、传输 client、接入凭据
读取），不持有任何业务数据、不写库。接入凭据（rid/appkey/appsecret/sid）由国家平台在客户
上线时下发（接口规范 v0.55 附录C），未接入客户前天然缺失 —— 缺失即"未配置"，通道静默。

权威协议源：old/2024-06-28全国一体化政务数据共享数据直达接口规范v0.55.docx
"""

from zw_brain.shared.national.client import NationalDirectClient
from zw_brain.shared.national.envelope import build_body, build_headers
from zw_brain.shared.national.provisioning import (
    NationalChannelState,
    NationalProvisioning,
    is_national_provisioned,
    is_national_sync_ready,
    load_national_provisioning,
    national_channel_config_presence,
    national_external_readiness_presence,
    resolve_national_channel_state,
)
from zw_brain.shared.national.return_codes import NationalResponse, parse_response
from zw_brain.shared.national.signing import sign_request

__all__ = [
    "NationalChannelState",
    "NationalDirectClient",
    "NationalProvisioning",
    "NationalResponse",
    "build_body",
    "build_headers",
    "is_national_provisioned",
    "is_national_sync_ready",
    "load_national_provisioning",
    "national_channel_config_presence",
    "national_external_readiness_presence",
    "parse_response",
    "resolve_national_channel_state",
    "sign_request",
]
