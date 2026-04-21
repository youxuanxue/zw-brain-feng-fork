"""Group Inference Platform SDK gateway.

Per design baseline D6 + D14, every model-service call (LLM / Embedding / ASR /
Rerank / OCR / ...) MUST go through `zw_brain.shared.inference.client` —
direct calls to OpenAI / Anthropic / 百川 / 智谱 / 通义 / DeepSeek / etc. are
forbidden and mechanically blocked by `scripts/check_no_direct_llm.py`
(preflight section 10).

Phase-0 ships a mock implementation; the real SDK contract is pending from
the Group platform team.
"""
