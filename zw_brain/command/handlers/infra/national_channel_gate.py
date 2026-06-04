"""国家通道运行门（D50 §二运行门，复用 shared.national 三态单一事实源）。

清单门（status=live + binding=external_capability）让 10 个 adapter.national.* 在 5 消费面
（api/cli/a2a；webui 由子旅程 escalate/compile 编排，不直挂）可见、require_surface 放行。
**能否对外是运行时事实**，由本运行门判定：

  - OFF / ON_UNPROVISIONED → 返回诚实 pending（人话、零对外、**非 404**）。能力存在，
    只是通道未开 / 接入信息未配齐。
  - ON_PROVISIONED → 经 NationalDirectClient 真实出站（记录受理回执，**不伪造回流**）。

R12 纪律：对外 reason 文案不含 flag / binding / provision / endpoint 等工程术语。
诚实纪律（承 D47/D50）：本期无真实国家端点可联调；provisioned 仅在 operator 真实配齐
接入凭据时成立，client 忠实“说协议”，回执取其真实响应，不造假成功回流。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zw_brain.shared.national import (
    NationalChannelState,
    NationalDirectClient,
    NationalResponse,
    load_national_provisioning,
    resolve_national_channel_state,
)

# 运行门 pending 文案（R12 人话；OFF 与未配齐区分，但都不暴露工程术语）。
_PENDING_REASON: dict[NationalChannelState, str] = {
    NationalChannelState.OFF: "国家通道暂不可用，请稍后",
    NationalChannelState.ON_UNPROVISIONED: "国家通道待配置接入信息",
}

# 测试注入点：协议合规桩 transport（tests/national 桩）。生产为 None → client 默认 urllib。
# 不喂任何业务数据，仅验“我方 client 是否会说协议”（承 D11 桩≠业务 mock 口径）。
OUTBOUND_TRANSPORT: Any = None


@dataclass(frozen=True)
class NationalChannelDecision:
    """运行门裁决。``pending`` 非 None 即诚实待定（零对外）；None 即 provisioned 可出站。"""

    state: NationalChannelState
    pending: dict[str, Any] | None

    @property
    def provisioned(self) -> bool:
        return self.state is NationalChannelState.ON_PROVISIONED


def evaluate() -> NationalChannelDecision:
    """派生当前通道运行态裁决（纯函数，读 env 三态）。"""
    state = resolve_national_channel_state()
    if state is NationalChannelState.ON_PROVISIONED:
        return NationalChannelDecision(state=state, pending=None)
    return NationalChannelDecision(
        state=state,
        pending={"status": "pending", "reason": _PENDING_REASON[state]},
    )


def _interface_and_path(skill_id: str) -> tuple[str, str]:
    """skill_id → (interface_name, url_path)。

    interface_name = 完整 slug：**不发明接口名**，operator 在 ZW_BRAIN_NATIONAL_SID_MAP
    以 slug 为 key 映射 gjzwfwpt_sid（附录C 客户上线时下发）。path 为占位（dots→slash），
    客户上线时按附录C 接口 NAME 校准 —— 本期无真实端点，记 HONESTLY-PENDING。
    """
    path = skill_id.removeprefix("adapter.national.").replace(".", "/")
    return skill_id, path


def outbound(skill_id: str, payload: dict[str, Any]) -> NationalResponse:
    """provisioned 态真实出站；调用方须已确认 ``evaluate().provisioned``。

    fail-closed：若凭据竟未配齐（理论上 evaluate 已挡）→ 抛错，绝不发未签名请求。
    """
    prov = load_national_provisioning()
    if prov is None:
        raise RuntimeError("national channel not provisioned (outbound called without credentials)")
    client = (
        NationalDirectClient(provisioning=prov, transport=OUTBOUND_TRANSPORT)
        if OUTBOUND_TRANSPORT is not None
        else NationalDirectClient(provisioning=prov)
    )
    interface_name, path = _interface_and_path(skill_id)
    return client.post(interface_name, path, payload)
