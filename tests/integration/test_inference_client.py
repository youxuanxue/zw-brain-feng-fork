"""F2: inference client mock/platform modes — local dev without gateway credentials."""

from __future__ import annotations

import pytest

from zw_brain.shared.inference.client import (
    ChatMessage,
    InferenceClient,
    InferenceError,
    reset_default_client,
)


@pytest.fixture(autouse=True)
def _reset_inference_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_INFERENCE_GATEWAY_URL", raising=False)
    monkeypatch.delenv("ZW_BRAIN_INFERENCE_API_KEY", raising=False)
    monkeypatch.delenv("ZW_BRAIN_INFERENCE_MODEL", raising=False)
    reset_default_client()


def test_mock_mode_chat_works_without_gateway_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_MODE", "mock")
    client = InferenceClient(base_url="", api_key="", model="qwen-7b")
    assert client.mode == "mock"

    result = client.chat(
        [ChatMessage(role="user", content="医疗救助目录")],
        model="qwen-7b",
        request_id="REQ-MOCK-1",
    )
    assert result.text.startswith("[mock-inference:qwen-7b]")
    assert "医疗救助目录" in result.text
    assert result.usage["total_tokens"] == 2


def test_mock_mode_embed_returns_fixed_dimension_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_MODE", "mock")
    client = InferenceClient(mode="mock")
    vectors = client.embed(["a", "b"], model="embed-v1")
    assert len(vectors) == 2
    assert all(len(row) == 8 for row in vectors)
    assert vectors[0][0] == 0.125


def test_platform_mode_requires_gateway_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_MODE", "platform")
    client = InferenceClient(base_url="", api_key="", model="qwen-7b")
    with pytest.raises(InferenceError, match="base_url is required"):
        client.chat(
            [ChatMessage(role="user", content="hi")],
            model="qwen-7b",
            request_id="REQ-PLATFORM-1",
        )


def test_mock_mode_still_requires_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_MODE", "mock")
    client = InferenceClient(mode="mock")
    with pytest.raises(InferenceError, match="request_id is required"):
        client.chat([ChatMessage(role="user", content="hi")], model="qwen-7b", request_id=None)


def test_client_ignores_legacy_base_url_env_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    """D36 负向守卫：InferenceClient 的 base_url 只认 ZW_BRAIN_INFERENCE_GATEWAY_URL；
    旧 INSPUR_INFERENCE_BASE_URL / 裸 BASE_URL 一律不兜底 → 平台模式缺 base_url 即报错。"""
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_MODE", "platform")
    monkeypatch.setenv("INSPUR_INFERENCE_BASE_URL", "http://legacy-gw/v1")
    monkeypatch.setenv("BASE_URL", "http://legacy-base/v1")
    client = InferenceClient()
    with pytest.raises(InferenceError, match="base_url is required"):
        client.chat([ChatMessage(role="user", content="hi")], model="m", request_id="REQ-D36-BASE")


def test_client_ignores_legacy_api_key_env_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    """D36 负向守卫：base_url 由 ZW_BRAIN_INFERENCE_GATEWAY_URL 提供时，api_key 只认
    ZW_BRAIN_INFERENCE_API_KEY；旧 INSPUR_INFERENCE_API_KEY / AUTH_TOKEN 不兜底 → 缺 auth token 报错。"""
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_MODE", "platform")
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_GATEWAY_URL", "http://gw/v1")
    monkeypatch.setenv("INSPUR_INFERENCE_API_KEY", "legacy-key")
    monkeypatch.setenv("AUTH_TOKEN", "legacy-token")
    client = InferenceClient()
    with pytest.raises(InferenceError, match="auth token is required"):
        client.chat([ChatMessage(role="user", content="hi")], model="m", request_id="REQ-D36-KEY")


def test_connection_values_stripped_of_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """F2 live-probe 实测：env/.env/docker --env-file 值常带尾随空白/换行；
    base_url/api_key/model 必须 strip，否则 URL 含控制字符 → InvalidURL（2026-05-29）。"""
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_MODE", "platform")
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_GATEWAY_URL", "https://gw.example/v1   ")
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_API_KEY", " sk-abc \n")
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_MODEL", "  qwen-7b  ")
    client = InferenceClient()
    assert client._base_url == "https://gw.example/v1"
    assert client._api_key == "sk-abc"
    assert client._model == "qwen-7b"
