from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_gateway_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "mock-agent-llm-gateway.py"
    spec = importlib.util.spec_from_file_location("mock_agent_llm_gateway", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_business_mock_answer_is_agent_specific() -> None:
    gateway = _load_gateway_module()
    answer = gateway._answer(  # noqa: SLF001 - executable contract for local acceptance gateway
        [{"role": "system", "content": "你是 zw-brain 的法人信用画像核验，服务对象是授权用数方信用尽调人员。"}]
    )

    assert "法人信用画像核验" in answer
    assert "授权用数方信用尽调人员" in answer
    assert "本地调试回答" not in answer
    assert "AgentRuntime" not in answer
    assert "网关" not in answer
    assert "本地" not in answer


def test_business_mock_supports_openai_compatible_streaming() -> None:
    gateway = _load_gateway_module()
    chunks: list[bytes] = []

    class Handler(gateway.Handler):
        def send_response(self, _status: int) -> None:
            return None

        def send_header(self, _name: str, _value: str) -> None:
            return None

        def end_headers(self) -> None:
            return None

    handler = object.__new__(Handler)
    handler.wfile = type("Writer", (), {"write": lambda _self, data: chunks.append(data)})()

    handler._stream_chat_completion(model="mock-chat", content="法人信用画像核验回答")

    raw = b"".join(chunks).decode("utf-8")
    assert "chat.completion.chunk" in raw
    assert "法人信用画像核验回答" in raw
    assert "data: [DONE]" in raw
