"""Embedded AgentRuntime 配置：Inspur 网关环境变量桥接。"""

from __future__ import annotations

import os

import pytest

from zw_brain.shared.agent_runtime.config import (
    apply_embedded_runtime_env_to_process,
    embedded_runtime_env,
)


@pytest.fixture(autouse=True)
def _clear_openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "OPENAI_COMPATIBLE_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_COMPATIBLE_BASE_URL",
        "OPENAI_BASE_URL",
        "INSPUR_INFERENCE_API_KEY",
        "INSPUR_INFERENCE_BASE_URL",
        "AUTH_TOKEN",
        "BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_embedded_runtime_env_bridges_inspur_api_key_and_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INSPUR_INFERENCE_API_KEY", "inspur-secret")
    monkeypatch.setenv("INSPUR_INFERENCE_BASE_URL", "http://inspur-gateway.local/v1")

    env = embedded_runtime_env()

    assert env["OPENAI_COMPATIBLE_API_KEY"] == "inspur-secret"
    assert env["OPENAI_COMPATIBLE_BASE_URL"] == "http://inspur-gateway.local/v1"


def test_embedded_runtime_env_bridges_auth_token_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_TOKEN", "token-from-auth")
    monkeypatch.setenv("BASE_URL", "http://legacy-base/v1")

    env = embedded_runtime_env()

    assert env["OPENAI_COMPATIBLE_API_KEY"] == "token-from-auth"
    assert env["OPENAI_COMPATIBLE_BASE_URL"] == "http://legacy-base/v1"


def test_embedded_runtime_env_does_not_override_explicit_openai_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INSPUR_INFERENCE_API_KEY", "inspur-secret")
    monkeypatch.setenv("INSPUR_INFERENCE_BASE_URL", "http://inspur-gateway.local/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "explicit-key")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://explicit/v1")

    env = embedded_runtime_env()

    assert env["OPENAI_COMPATIBLE_API_KEY"] == "explicit-key"
    assert env["OPENAI_COMPATIBLE_BASE_URL"] == "http://explicit/v1"


def test_apply_embedded_runtime_env_writes_openai_keys_to_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_COMPATIBLE_BASE_URL", raising=False)
    monkeypatch.setenv("INSPUR_INFERENCE_API_KEY", "Bear")
    monkeypatch.setenv("INSPUR_INFERENCE_BASE_URL", "http://inspur-gateway.local/v1")

    apply_embedded_runtime_env_to_process()

    assert os.environ.get("OPENAI_COMPATIBLE_API_KEY") == "Bear"
    assert os.environ.get("OPENAI_COMPATIBLE_BASE_URL") == "http://inspur-gateway.local/v1"


def test_embedded_runtime_env_optional_api_key_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_API_KEY_OPTIONAL", "1")
    monkeypatch.setenv("INSPUR_INFERENCE_BASE_URL", "http://inspur-gateway.local/v1")

    env = embedded_runtime_env()

    assert env["OPENAI_COMPATIBLE_API_KEY"] == "unused"
    assert env["OPENAI_COMPATIBLE_BASE_URL"] == "http://inspur-gateway.local/v1"
