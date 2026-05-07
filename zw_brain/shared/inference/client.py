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

import base64
import json
import os
from dataclasses import dataclass, field
from typing import Any
from urllib import error, request

DEFAULT_INFERENCE_MODEL = "claude-sonnet-4-7"


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
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = (base_url or os.getenv("INSPUR_INFERENCE_BASE_URL") or os.getenv("BASE_URL") or "").rstrip("/")
        self._api_key = api_key or os.getenv("INSPUR_INFERENCE_API_KEY") or os.getenv("AUTH_TOKEN")
        self._model = model or os.getenv("INSPUR_INFERENCE_MODEL") or os.getenv("MODEL") or DEFAULT_INFERENCE_MODEL
        self._timeout_seconds = timeout_seconds

    def _require_platform_config(self) -> None:
        if not self._base_url:
            raise InferenceError("inference base_url is required")
        if not self._api_key:
            raise InferenceError("inference auth token is required")

    def _resolve_model(self, model: str | None) -> str:
        resolved = model or self._model
        if not resolved:
            raise InferenceError("inference model is required")
        return resolved

    def _post_json(self, path: str, payload: dict[str, Any], *, request_id: str | None = None) -> dict[str, Any]:
        self._require_platform_config()
        req = request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                **({"X-Request-ID": request_id} if request_id else {}),
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                detail = ""
            raise InferenceError(f"inference http {exc.code}: {detail or exc.reason}") from exc
        except error.URLError as exc:
            raise InferenceError(f"inference network error: {exc.reason}") from exc

        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise InferenceError("inference response is not valid json") from exc
        if not isinstance(parsed, dict):
            raise InferenceError("inference response must be a json object")
        return parsed

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
        resolved_model = self._resolve_model(model)
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        response = self._post_json("/v1/chat/completions", payload, request_id=request_id)
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise InferenceError("inference response missing choices")
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        if not isinstance(content, str):
            content = str(content)
        usage_raw = response.get("usage")
        usage: dict[str, int] = {}
        if isinstance(usage_raw, dict):
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage_raw.get(key)
                if isinstance(value, int):
                    usage[key] = value

        finish_reason = first.get("finish_reason") if isinstance(first, dict) else None
        return ChatResult(
            text=content,
            model=str(response.get("model") or resolved_model),
            usage=usage,
            finish_reason=finish_reason if isinstance(finish_reason, str) and finish_reason else "stop",
        )

    def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        resolved_model = self._resolve_model(model)
        response = self._post_json("/v1/embeddings", {"model": resolved_model, "input": texts})
        rows = response.get("data")
        if not isinstance(rows, list):
            raise InferenceError("inference embeddings response missing data")
        vectors: list[list[float]] = []
        for row in rows:
            embedding = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(embedding, list) or not all(isinstance(v, (int, float)) for v in embedding):
                raise InferenceError("inference embeddings response has invalid embedding")
            vectors.append([float(v) for v in embedding])
        return vectors

    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        model: str,
        top_n: int | None = None,
    ) -> list[RerankHit]:
        embeddings = self.embed([query, *documents], model=model)
        if len(embeddings) < 2:
            return []
        query_vec = embeddings[0]

        def _score(vec: list[float]) -> float:
            return float(sum(a * b for a, b in zip(query_vec, vec, strict=False)))

        hits = [RerankHit(index=i, score=_score(vec), document=documents[i]) for i, vec in enumerate(embeddings[1:])]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[: top_n or len(hits)]

    def asr(self, audio_bytes: bytes, *, model: str, language: str | None = None) -> AsrResult:
        resolved_model = self._resolve_model(model)
        payload: dict[str, Any] = {
            "model": resolved_model,
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
        }
        if language:
            payload["language"] = language
        response = self._post_json("/v1/audio/transcriptions", payload)
        text = response.get("text")
        if not isinstance(text, str):
            raise InferenceError("inference asr response missing text")
        language_value = response.get("language")
        duration_value = response.get("duration_seconds")
        return AsrResult(
            text=text,
            language=language_value if isinstance(language_value, str) and language_value else (language or "zh-CN"),
            duration_seconds=float(duration_value) if isinstance(duration_value, (int, float)) else 0.0,
        )

    def ocr(self, image_bytes: bytes, *, model: str) -> OcrResult:
        resolved_model = self._resolve_model(model)
        response = self._post_json(
            "/v1/chat/completions",
            {
                "model": resolved_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract all visible text from this image."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}"
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0.0,
            },
        )
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise InferenceError("inference ocr response missing choices")
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, list):
            text = "\n".join(
                str(part.get("text") or "") for part in content if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        else:
            text = str(content or "")
        return OcrResult(text=text, blocks=[])


_default_client: InferenceClient | None = None


def get_client() -> InferenceClient:
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
