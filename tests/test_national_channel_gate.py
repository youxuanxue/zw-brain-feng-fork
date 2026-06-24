"""国家通道运行门 gate（D50）.

权威：docs/decisions/national-platform-access-D50.md §二（两道正交门）。
gate 纯函数三态 + outbound 真实出站（协议合规桩）；其消费方是 escalate(j1)/compile(j2)
handler（见 test_national_escalate.py 覆盖 off→pending / provisioned→submitted 的 live 路径）。
核实诚实纪律：
  - OFF / 未配齐 → 诚实 pending（人话、非 404、非抛错），记意图、零对外；
  - provisioned（env + 协议合规桩 transport）→ 经 NationalDirectClient 真实出站，
    带 4 个签名头 + 小写 body，受理回执取真实响应（不伪造回流）；
  - pending 文案不含工程术语（R12）。
"""

from __future__ import annotations

import json

import pytest

from zw_brain.command.handlers.infra import national_channel_gate as gate
from zw_brain.shared.national.provisioning import (
    ENV_APPKEY,
    ENV_APPSECRET,
    ENV_ENABLED,
    ENV_ENDPOINT,
    ENV_RID,
    ENV_SID_MAP,
    NationalChannelState,
)

pytestmark = pytest.mark.no_db

_SKILL = "adapter.national.application.submit"


@pytest.fixture()
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (ENV_ENABLED, ENV_ENDPOINT, ENV_RID, ENV_APPKEY, ENV_APPSECRET, ENV_SID_MAP):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(gate, "OUTBOUND_TRANSPORT", None)


def _provision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_ENABLED, "1")
    monkeypatch.setenv(ENV_ENDPOINT, "https://national.example")
    monkeypatch.setenv(ENV_RID, "RID-1")
    monkeypatch.setenv(ENV_APPKEY, "AK-test")
    monkeypatch.setenv(ENV_APPSECRET, "SK-test")
    monkeypatch.setenv(ENV_SID_MAP, json.dumps({_SKILL: "SID-1"}))


# ---- gate 纯函数三态 --------------------------------------------------------


def test_gate_off_is_pending(_clean_env: None) -> None:
    decision = gate.evaluate()
    assert decision.state is NationalChannelState.OFF
    assert not decision.provisioned
    assert decision.pending == {"status": "pending", "reason": "国家通道暂不可用，请稍后"}


def test_gate_enabled_but_unprovisioned_is_pending(
    _clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_ENABLED, "1")  # 开关开但凭据未配齐
    decision = gate.evaluate()
    assert decision.state is NationalChannelState.ON_UNPROVISIONED
    assert not decision.provisioned
    assert decision.pending["reason"] == "国家通道待配置接入信息"


def test_gate_pending_reason_has_no_engineering_terms(
    _clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    for setup in (lambda: None, lambda: monkeypatch.setenv(ENV_ENABLED, "1")):
        setup()
        reason = gate.evaluate().pending["reason"]
        for term in ("flag", "binding", "provision", "endpoint", "env", "404"):
            assert term not in reason.lower()


def test_gate_provisioned_allows_outbound(_clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _provision(monkeypatch)
    assert gate.evaluate().provisioned is True


# ---- outbound 真实出站（协议合规桩，零网络）--------------------------------


def test_outbound_speaks_protocol_with_stub(_clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _provision(monkeypatch)
    sent: dict = {}

    def stub(url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
        sent["url"] = url
        sent["headers"] = headers
        sent["body"] = body
        return 200, json.dumps({"code": "200", "message": "ok", "data": {}}).encode("utf-8")

    monkeypatch.setattr(gate, "OUTBOUND_TRANSPORT", stub)
    resp = gate.outbound(_SKILL, {"ApplyId": "A-1", "Note": "X"})

    assert resp.ok and resp.code == "200"
    # 4 个必填签名头齐全 + sid 取自 sid_map（slug→sid）。
    assert sent["headers"]["gjzwfwpt_rid"] == "RID-1"
    assert sent["headers"]["gjzwfwpt_sid"] == "SID-1"
    assert sent["headers"]["gjzwfwpt_rtime"]
    assert sent["headers"]["gjzwfwpt_sign"]
    # body key 全小写（applyid/note），值不动；URL 走 /sysapi/<path>。
    body = json.loads(sent["body"].decode("utf-8"))
    assert body == {"applyid": "A-1", "note": "X"}
    assert sent["url"] == "https://national.example/sysapi/application/submit"


# 注：off→pending / provisioned→submitted 的 handler 级 live 路径覆盖在 test_national_escalate.py
# （escalate(j1) 经 gate 出站）；国家通道不再经 adapter_passthrough 分流（10 adapter 回 deferred
# scaffolding，require_surface 拒非 live），故此处只守 gate 本体三态 + outbound 协议。
