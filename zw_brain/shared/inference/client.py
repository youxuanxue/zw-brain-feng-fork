"""Inference client.

This is the **only** allowed module-level egress for model service calls. The
real implementation will wrap the Group Inference Platform SDK once the
contract is finalized; the public surface declared here is intentionally
minimal so swapping implementations later is mechanical.

Public API:

    chat(messages, *, model, max_tokens=None, temperature=0.0, request_id=None) -> ChatResult
    embed(texts, *, model) -> list[list[float]]

All callers MUST pass `request_id` so the audit bus can correlate the
inference call with the originating Skill invocation (D4 audit trail).

Returning structured dataclasses (not raw dicts) lets static type checkers
catch incompatible upgrades when the Group SDK lands.
"""
from __future__ import annotations

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
        # Legacy evidence: standardservice `/syncModel2Vector` writes vectors via RecommendAgentService
        # (`/add` and `/query`) to an external Python vector service.
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


