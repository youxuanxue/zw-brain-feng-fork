"""Inference client.

This is the **only** allowed module-level egress for model service calls. The
real implementation will wrap the Group Inference Platform SDK once the
contract is finalized; the public surface declared here is intentionally
minimal so swapping implementations later is mechanical.

Public API:

    chat(messages, *, model, max_tokens=None, temperature=0.0, request_id=None) -> ChatResult
    embed(texts, *, model) -> list[list[float]]
    rerank(query, documents, *, model, top_n=None) -> list[RerankHit]
    asr(audio_bytes, *, model, language=None) -> AsrResult
    ocr(image_bytes, *, model) -> OcrResult

All callers MUST pass `request_id` so the audit bus can correlate the
inference call with the originating Skill invocation (D4 audit trail).

Returning structured dataclasses (not raw dicts) lets static type checkers
catch incompatible upgrades when the Group SDK lands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ChatResult:
    text: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"


@dataclass(frozen=True)
class RerankHit:
    index: int
    score: float
    document: str


@dataclass(frozen=True)
class AsrResult:
    text: str
    language: str
    duration_seconds: float


@dataclass(frozen=True)
class OcrResult:
    text: str
    blocks: list[dict[str, Any]] = field(default_factory=list)


class InferenceError(RuntimeError):
    """Raised when the inference platform refuses the call (auth / quota / model unknown)."""


class InferenceClient:
    """Thin facade.

    The current implementation is deterministic and local so tests do not need
    network access. When the Group SDK lands, it should replace the internals
    behind the same surface.

    The local adapter honors `request_id` as the audit correlation key but
    performs no real I/O.
    """

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None) -> None:
        # Real deployment reads from env (`INSPUR_INFERENCE_BASE_URL`, `INSPUR_INFERENCE_API_KEY`).
        # The local adapter simply records what was passed for assertion in tests.
        self._base_url = base_url
        self._api_key = api_key

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        request_id: str | None = None,
    ) -> ChatResult:
        if not request_id:
            raise InferenceError("request_id is required (D4 audit trail)")
        # Local adapter: echo back the last user message reversed, plus model tag.
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return ChatResult(
            text=f"[mock:{model}] {last_user[::-1]}",
            model=model,
            usage={"prompt_tokens": sum(len(m.content) for m in messages), "completion_tokens": len(last_user)},
        )

    def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        return [[float(len(t) % 7) / 7.0] * 8 for t in texts]

    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        model: str,
        top_n: int | None = None,
    ) -> list[RerankHit]:
        scored = sorted(
            (RerankHit(index=i, score=1.0 / (1 + abs(len(d) - len(query))), document=d) for i, d in enumerate(documents)),
            key=lambda h: h.score,
            reverse=True,
        )
        return scored[: top_n or len(scored)]

    def asr(self, audio_bytes: bytes, *, model: str, language: str | None = None) -> AsrResult:
        return AsrResult(text="[mock asr]", language=language or "zh-CN", duration_seconds=float(len(audio_bytes)) / 16000.0)

    def ocr(self, image_bytes: bytes, *, model: str) -> OcrResult:
        return OcrResult(text="[mock ocr]", blocks=[])


_default_client: InferenceClient | None = None


def get_client() -> InferenceClient:
    """Process-wide singleton accessor. Tests can monkeypatch
    `zw_brain.shared.inference.client._default_client` to inject a fixture.
    """
    global _default_client
    if _default_client is None:
        _default_client = InferenceClient()
    return _default_client


def chat(messages: list[ChatMessage], **kwargs: Any) -> ChatResult:
    return get_client().chat(messages, **kwargs)


def embed(texts: list[str], **kwargs: Any) -> list[list[float]]:
    return get_client().embed(texts, **kwargs)


def rerank(query: str, documents: list[str], **kwargs: Any) -> list[RerankHit]:
    return get_client().rerank(query, documents, **kwargs)


def asr(audio_bytes: bytes, **kwargs: Any) -> AsrResult:
    return get_client().asr(audio_bytes, **kwargs)


def ocr(image_bytes: bytes, **kwargs: Any) -> OcrResult:
    return get_client().ocr(image_bytes, **kwargs)
