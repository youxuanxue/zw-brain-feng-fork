from __future__ import annotations

import os

import pytest

from zw_brain.shared import runtime_config


def test_runtime_config_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_REST_HOST", raising=False)
    monkeypatch.delenv("ZW_BRAIN_REST_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("ZW_BRAIN_REST_BASE_URL", raising=False)
    monkeypatch.delenv("ZW_BRAIN_DASHBOARD_BFF_HOST", raising=False)
    monkeypatch.delenv("ZW_BRAIN_DASHBOARD_BFF_PORT", raising=False)

    assert runtime_config.get_rest_host() == "0.0.0.0"
    assert runtime_config.get_rest_port() == 8800
    assert runtime_config.get_rest_base_url() == "http://127.0.0.1:8800"
    assert runtime_config.get_rest_api_skills_endpoint() == "http://127.0.0.1:8800/api/skills"
    assert runtime_config.get_dashboard_bff_host() == "0.0.0.0"
    assert runtime_config.get_dashboard_bff_port() == 8801


def test_runtime_config_reads_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_REST_HOST", "0.0.0.0")
    monkeypatch.setenv("ZW_BRAIN_REST_PORT", "18800")
    monkeypatch.setenv("ZW_BRAIN_DASHBOARD_BFF_HOST", "127.0.0.2")
    monkeypatch.setenv("ZW_BRAIN_DASHBOARD_BFF_PORT", "18801")

    assert runtime_config.get_rest_host() == "0.0.0.0"
    assert runtime_config.get_rest_port() == 18800
    assert runtime_config.get_rest_base_url() == "http://127.0.0.1:18800"
    assert runtime_config.get_rest_api_skills_endpoint() == "http://127.0.0.1:18800/api/skills"
    assert runtime_config.get_dashboard_bff_host() == "127.0.0.2"
    assert runtime_config.get_dashboard_bff_port() == 18801


def test_runtime_config_reads_explicit_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_REST_PORT", "18800")
    monkeypatch.setenv("ZW_BRAIN_REST_BASE_URL", "https://brain.example.internal:9443/")

    assert runtime_config.get_rest_base_url() == "https://brain.example.internal:9443"
    assert runtime_config.get_rest_api_skills_endpoint() == "https://brain.example.internal:9443/api/skills"


def test_runtime_config_port_env_maps_rest_and_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_REST_PORT", raising=False)
    monkeypatch.delenv("ZW_BRAIN_DASHBOARD_BFF_PORT", raising=False)
    monkeypatch.setenv("PORT", "3000")

    assert runtime_config.get_rest_port() == 3000
    assert runtime_config.get_dashboard_bff_port() == 3001


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ZW_BRAIN_REST_PORT", "abc"),
        ("ZW_BRAIN_REST_PORT", "0"),
        ("ZW_BRAIN_DASHBOARD_BFF_PORT", "70000"),
    ],
)
def test_runtime_config_rejects_invalid_ports(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)

    getter = runtime_config.get_rest_port if name == "ZW_BRAIN_REST_PORT" else runtime_config.get_dashboard_bff_port
    with pytest.raises(ValueError):
        getter()
