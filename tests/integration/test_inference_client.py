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
    monkeypatch.delenv("INSPUR_INFERENCE_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("INSPUR_INFERENCE_API_KEY", raising=False)
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
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
