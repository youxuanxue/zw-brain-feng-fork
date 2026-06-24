"""snapshot.webui.nationalChannel 三态投影（C5b / D50 §二运行门）.

核实后端把国家通道运行三态诚实投影到 webui 配置块：
  - OFF → enabled=false（前端据此让 P5 入口不渲染）、notice 人话；
  - ON_UNPROVISIONED → enabled=true / provisioned=false（草拟可用、发布置灰）；
  - ON_PROVISIONED → provisioned=true；
  - notice 不含工程术语（R12），不含任何密钥。
"""

from __future__ import annotations

import json

import pytest

from zw_brain.command.brain import _national_channel_webui_state
from zw_brain.shared.national.provisioning import (
    ENV_APPKEY,
    ENV_APPSECRET,
    ENV_BASIC_ELEM_TEMPLATE_READY,
    ENV_CREDENTIAL_LIFECYCLE_READY,
    ENV_ENABLED,
    ENV_ENDPOINT,
    ENV_RECEIPT_RECONCILIATION_READY,
    ENV_RID,
    ENV_SID_MAP,
)

pytestmark = pytest.mark.no_db


@pytest.fixture()
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        ENV_ENABLED,
        ENV_ENDPOINT,
        ENV_RID,
        ENV_APPKEY,
        ENV_APPSECRET,
        ENV_SID_MAP,
        ENV_BASIC_ELEM_TEMPLATE_READY,
        ENV_RECEIPT_RECONCILIATION_READY,
        ENV_CREDENTIAL_LIFECYCLE_READY,
    ):
        monkeypatch.delenv(var, raising=False)


def _provision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_ENABLED, "1")
    monkeypatch.setenv(ENV_ENDPOINT, "https://national.example")
    monkeypatch.setenv(ENV_RID, "RID-1")
    monkeypatch.setenv(ENV_APPKEY, "AK")
    monkeypatch.setenv(ENV_APPSECRET, "SK")
    monkeypatch.setenv(ENV_SID_MAP, json.dumps({"adapter.national.application.submit": "SID-1"}))


def test_off_state(_clean_env: None) -> None:
    st = _national_channel_webui_state()
    assert st["enabled"] is False
    assert st["provisioned"] is False
    assert st["status"] == "off"
    assert st["notice"]


def test_unprovisioned_state(_clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_ENABLED, "1")  # 开关开但凭据未配齐
    st = _national_channel_webui_state()
    assert st["enabled"] is True
    assert st["provisioned"] is False
    assert st["syncReady"] is False
    assert st["status"] == "unprovisioned"
    assert st["notice"] == "国家通道待配置接入信息"
    assert st["operatorSummary"] == "草拟与审核可用，发布同步需平台运维员补齐接入信息"
    config = {item["key"]: item["ready"] for item in st["configItems"]}
    assert config == {
        "channel_enabled": True,
        "platform_address": False,
        "requester_identity": False,
        "access_account": False,
        "access_secret": False,
        "interface_service_map": False,
    }
    assert {item["label"]: item["ready"] for item in st["externalReadinessItems"]} == {
        "国家下发基本要素目录与模板数据": False,
        "国家平台真实回执与对账口径": False,
        "国家平台凭据签发与撤销规则": False,
    }
    assert [item["key"] for item in st["missingConfigItems"]] == [
        "platform_address",
        "requester_identity",
        "access_account",
        "access_secret",
        "interface_service_map",
    ]
    assert [item["key"] for item in st["missingExternalReadinessItems"]] == [
        "basic_elem_template",
        "receipt_reconciliation",
        "credential_lifecycle",
    ]
    assert st["opsRoute"] == "#/integration-admin"
    assert st["nationalQueueRoute"] == "#/workbench"
    checklist = {item["key"]: item for item in st["opsChecklist"]}
    assert checklist["env_config"]["blocked"] is True
    assert checklist["external_material"]["blocked"] is True
    assert checklist["apply_effect"]["blocked"] is True


def test_provisioned_state(_clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _provision(monkeypatch)
    st = _national_channel_webui_state()
    assert st["enabled"] is True
    assert st["provisioned"] is True
    assert st["syncReady"] is False
    assert st["status"] == "provisioned"
    assert st["notice"] == "国家通道待确认上线资料"
    assert st["operatorSummary"] == "接入信息已配齐，发布同步仍需确认上线资料"
    config = {item["key"]: item["ready"] for item in st["configItems"]}
    assert all(config.values())
    assert st["missingConfigItems"] == []
    assert not any(item["ready"] for item in st["externalReadinessItems"])
    assert [item["key"] for item in st["missingExternalReadinessItems"]] == [
        "basic_elem_template",
        "receipt_reconciliation",
        "credential_lifecycle",
    ]


def test_sync_ready_requires_external_readiness(_clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _provision(monkeypatch)
    monkeypatch.setenv(ENV_BASIC_ELEM_TEMPLATE_READY, "1")
    monkeypatch.setenv(ENV_RECEIPT_RECONCILIATION_READY, "1")
    monkeypatch.setenv(ENV_CREDENTIAL_LIFECYCLE_READY, "1")
    st = _national_channel_webui_state()
    assert st["syncReady"] is True
    assert st["notice"] == "国家通道已满足发布同步条件"
    assert st["operatorSummary"] == "国家通道已满足发布同步条件"
    assert all(item["ready"] for item in st["externalReadinessItems"])
    assert st["missingConfigItems"] == []
    assert st["missingExternalReadinessItems"] == []
    assert all(item["blocked"] is False for item in st["opsChecklist"])


def test_notice_no_engineering_terms_and_no_secret_values(
    _clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    for setup in (lambda: None, lambda: monkeypatch.setenv(ENV_ENABLED, "1"), lambda: _provision(monkeypatch)):
        setup()
        st = _national_channel_webui_state()
        # 用户可见 notice 文案不得含工程术语（R12）。
        notice = str(st["notice"]).lower()
        for term in ("flag", "binding", "provision", "endpoint", "appkey", "appsecret", "secret", "sid", "env"):
            assert term not in notice, f"notice 文案泄漏工程术语：{term}"
        # 整块绝不含任何密钥**值**（appkey/appsecret/rid/sid_map 的字面值）。
        blob = json.dumps(st, ensure_ascii=False)
        for secret_value in ("AK", "SK", "RID-1", "SID-1", "national.example"):
            assert secret_value not in blob, f"snapshot.webui.nationalChannel 泄漏接入凭据值：{secret_value}"
