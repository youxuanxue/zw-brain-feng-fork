from __future__ import annotations

import os

import pytest

from zw_brain.shared.inference.client import ChatMessage, InferenceClient


def _required_env() -> tuple[str, str, str]:
    base_url = os.getenv("BASE_URL") or os.getenv("INSPUR_INFERENCE_BASE_URL")
    auth_token = os.getenv("AUTH_TOKEN") or os.getenv("INSPUR_INFERENCE_API_KEY")
    model = os.getenv("MODEL") or os.getenv("INSPUR_INFERENCE_MODEL")
    if not base_url or not auth_token or not model:
        pytest.skip("smoke test requires BASE_URL/AUTH_TOKEN/MODEL (or INSPUR_INFERENCE_* aliases)")
    return base_url, auth_token, model


def test_inference_gateway_smoke_chat() -> None:
    base_url, auth_token, model = _required_env()
    client = InferenceClient(base_url=base_url, api_key=auth_token, model=model, timeout_seconds=30.0)

    chat = client.chat(
        [ChatMessage(role="user", content="smoke ping")],
        model=model,
        request_id="smoke-chat-request-id",
    )
    assert isinstance(chat.text, str)
    assert chat.text.strip()
    assert isinstance(chat.model, str)
    assert chat.model.strip()


