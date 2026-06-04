"""C1 — 国家通道 flag/provisioning 基建单测（无网络、无 seed）。

守住诚实口径：默认 OFF；打开但凭据未配齐 → ON_UNPROVISIONED；配齐 → ON_PROVISIONED；
appsecret 不进 repr；sid_map 非法 JSON fail-closed。
"""

from __future__ import annotations

import pytest

from zw_brain.shared.national import provisioning as prov
from zw_brain.shared.national.provisioning import NationalChannelState


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        prov.ENV_ENABLED,
        prov.ENV_ENDPOINT,
        prov.ENV_RID,
        prov.ENV_APPKEY,
        prov.ENV_APPSECRET,
        prov.ENV_SID_MAP,
    ):
        monkeypatch.delenv(name, raising=False)


def _provision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(prov.ENV_ENDPOINT, "http://10.0.0.1:8080/")
    monkeypatch.setenv(prov.ENV_RID, "rid-shandong")
    monkeypatch.setenv(prov.ENV_APPKEY, "appkey-xxx")
    monkeypatch.setenv(prov.ENV_APPSECRET, "appsecret-xxx")
    monkeypatch.setenv(prov.ENV_SID_MAP, '{"catalog.report": "sid-001"}')


def test_flag_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    assert prov.get_national_channel_enabled() is False
    assert prov.resolve_national_channel_state() is NationalChannelState.OFF


def test_enabled_but_unprovisioned(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv(prov.ENV_ENABLED, "1")
    assert prov.is_national_provisioned() is False
    assert prov.resolve_national_channel_state() is NationalChannelState.ON_UNPROVISIONED


def test_enabled_and_provisioned(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv(prov.ENV_ENABLED, "1")
    _provision(monkeypatch)
    assert prov.is_national_provisioned() is True
    state = prov.resolve_national_channel_state()
    assert state is NationalChannelState.ON_PROVISIONED
    cfg = prov.load_national_provisioning()
    assert cfg is not None
    # 端点末尾 / 被裁掉；sid 按接口名解析。
    assert cfg.endpoint == "http://10.0.0.1:8080"
    assert cfg.sid_for("catalog.report") == "sid-001"
    assert cfg.sid_for("unknown.interface") is None


def test_provisioned_requires_all_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv(prov.ENV_ENABLED, "1")
    _provision(monkeypatch)
    # 抽掉任一必填项 → 回落未配置。
    monkeypatch.delenv(prov.ENV_APPSECRET, raising=False)
    assert prov.is_national_provisioned() is False
    assert prov.resolve_national_channel_state() is NationalChannelState.ON_UNPROVISIONED


def test_sid_map_malformed_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    _provision(monkeypatch)
    monkeypatch.setenv(prov.ENV_SID_MAP, "not-json{")
    assert prov.load_national_provisioning() is None  # 空 sid_map → 未配齐


def test_appsecret_not_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    _provision(monkeypatch)
    cfg = prov.load_national_provisioning()
    assert cfg is not None
    text = repr(cfg)
    assert "appsecret-xxx" not in text
    assert "appkey-xxx" not in text
    # 非密钥字段仍可见，便于排障。
    assert "rid-shandong" in text
