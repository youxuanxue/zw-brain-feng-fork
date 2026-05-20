from __future__ import annotations

import pytest

from zw_brain.shared import runtime_config


def test_runtime_config_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_REST_HOST", raising=False)
    monkeypatch.delenv("ZW_BRAIN_REST_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("ZW_BRAIN_REST_BASE_URL", raising=False)
    monkeypatch.delenv("ZW_BRAIN_DEV_IAM_BYPASS", raising=False)

    assert runtime_config.get_rest_host() == "0.0.0.0"
    assert runtime_config.get_rest_port() == 8800
    assert runtime_config.get_rest_base_url() == "http://127.0.0.1:8800"
    assert runtime_config.get_rest_api_skills_endpoint() == "http://127.0.0.1:8800/api/skills"
    assert runtime_config.get_dev_iam_bypass_enabled() is False


def test_runtime_config_dev_iam_bypass_requires_two_envs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_DEV_IAM_BYPASS", raising=False)
    monkeypatch.delenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", raising=False)
    assert runtime_config.get_dev_iam_bypass_enabled() is False

    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    assert runtime_config.get_dev_iam_bypass_enabled() is False, "ack flag missing must keep bypass off"

    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    assert runtime_config.get_dev_iam_bypass_enabled() is True

    for value in ("true", "0", "", "yes"):
        monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", value)
        assert runtime_config.get_dev_iam_bypass_enabled() is False, f"main flag value {value!r} must not enable bypass"

    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    for value in ("yes", "true", "", "production"):
        monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", value)
        assert runtime_config.get_dev_iam_bypass_enabled() is False, f"ack flag value {value!r} must not enable bypass"


def test_runtime_config_iaf_insecure_tls_requires_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_IAF_VERIFY_SSL", raising=False)
    monkeypatch.delenv("ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK", raising=False)
    assert runtime_config.get_iaf_verify_ssl() is True
    assert runtime_config.get_iaf_insecure_tls_dev_ack() is False

    monkeypatch.setenv("ZW_BRAIN_IAF_VERIFY_SSL", "false")
    assert runtime_config.get_iaf_verify_ssl() is False
    assert runtime_config.get_iaf_insecure_tls_dev_ack() is False

    monkeypatch.setenv("ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK", "yes")
    assert runtime_config.get_iaf_insecure_tls_dev_ack() is False

    monkeypatch.setenv("ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK", "development-only")
    assert runtime_config.get_iaf_insecure_tls_dev_ack() is True


def test_runtime_config_reads_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_REST_HOST", "0.0.0.0")
    monkeypatch.setenv("ZW_BRAIN_REST_PORT", "18800")

    assert runtime_config.get_rest_host() == "0.0.0.0"
    assert runtime_config.get_rest_port() == 18800
    assert runtime_config.get_rest_base_url() == "http://127.0.0.1:18800"
    assert runtime_config.get_rest_api_skills_endpoint() == "http://127.0.0.1:18800/api/skills"


def test_runtime_config_reads_explicit_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_REST_PORT", "18800")
    monkeypatch.setenv("ZW_BRAIN_REST_BASE_URL", "https://brain.example.internal:9443/")

    assert runtime_config.get_rest_base_url() == "https://brain.example.internal:9443"
    assert runtime_config.get_rest_api_skills_endpoint() == "https://brain.example.internal:9443/api/skills"


def test_runtime_config_port_env_maps_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_REST_PORT", raising=False)
    monkeypatch.setenv("PORT", "3000")

    assert runtime_config.get_rest_port() == 3000


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ZW_BRAIN_REST_PORT", "abc"),
        ("ZW_BRAIN_REST_PORT", "0"),
    ],
)
def test_runtime_config_rejects_invalid_ports(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError):
        runtime_config.get_rest_port()
