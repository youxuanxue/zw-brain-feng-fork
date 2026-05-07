from __future__ import annotations

import json
from urllib import error

import pytest

from zw_brain.shared.inference.client import DEFAULT_INFERENCE_MODEL, ChatMessage, InferenceClient, InferenceError


class _DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_chat_uses_openai_compatible_payload_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def _fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization")
        seen["request_id"] = req.headers.get("X-request-id")
        seen["body"] = json.loads(req.data.decode("utf-8"))
        seen["timeout"] = timeout
        return _DummyResponse(
            {
                "model": "xx",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    client = InferenceClient(base_url="https://api.tokenkey.dev", api_key="xxxx", model="xx")
    out = client.chat([ChatMessage(role="user", content="hi")], model="xx", request_id="REQ-1")

    assert out.text == "ok"
    assert out.model == "xx"
    assert out.usage["total_tokens"] == 6
    assert seen["url"] == "https://api.tokenkey.dev/v1/chat/completions"
    assert seen["auth"] == "Bearer xxxx"
    assert seen["request_id"] == "REQ-1"
    assert seen["body"]["model"] == "xx"
    assert seen["body"]["messages"][0]["content"] == "hi"


def test_chat_requires_request_id() -> None:
    client = InferenceClient(base_url="https://api.tokenkey.dev", api_key="xxxx", model="xx")
    with pytest.raises(InferenceError, match="request_id is required"):
        client.chat([ChatMessage(role="user", content="hi")], model="xx")


def test_chat_maps_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(req, timeout):
        raise error.HTTPError(req.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    client = InferenceClient(base_url="https://api.tokenkey.dev", api_key="xxxx", model="xx")
    with pytest.raises(InferenceError, match="inference http 401"):
        client.chat([ChatMessage(role="user", content="hi")], model="xx", request_id="REQ-1")


def test_default_model_is_claude_sonnet_4_7() -> None:
    client = InferenceClient(base_url="https://api.tokenkey.dev", api_key="xxxx")
    assert client._resolve_model(None) == DEFAULT_INFERENCE_MODEL
