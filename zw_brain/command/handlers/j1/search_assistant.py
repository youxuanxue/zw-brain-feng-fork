"""J1 P2 搜索上下文助手 (语义入口 / 缺口追问 / 推荐理由) — F6 减摩组件.

设计取舍（plan e1-j1-journey F6 + §5.4.4 反约束）:
- 这是减摩组件：输出结构化辅助字段 (intent / keywords / missing_fields / 推荐理由 /
  追问列表)，**不替代** P2 目录树 / 筛选器 / 资源详情页。
- 推理走 shared/inference/client.chat（唯一 LLM 出口，D6 硬约束 + preflight 段 10）。
- 可降级：推理失败 (InferenceError) 时回落 generic 规则解析，source 标 fallback_rule。
- 可关闭：调用方传 enabled=false → 直接返回 fallback_rule，绕过推理。
- 不存储输出（每次按需渲染，避免缓存导致的语义漂移）。
"""

from __future__ import annotations

import json as _json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.shared.inference.client import (
    ChatMessage,
    InferenceError,
)
from zw_brain.shared.inference.client import (
    chat as _inference_chat,
)

# 业务意图枚举（与 P2/P3 旅程对齐）
INTENT_DISCOVER_RESOURCE = "discover_resource"
INTENT_REGISTER_DEMAND = "register_demand"
INTENT_QUERY_APPLICATION = "query_application"
INTENT_UNKNOWN = "unknown"

ALL_INTENTS = (
    INTENT_DISCOVER_RESOURCE,
    INTENT_REGISTER_DEMAND,
    INTENT_QUERY_APPLICATION,
    INTENT_UNKNOWN,
)

# 关键词 → intent 的本地规则字典（fallback 路径用）
_INTENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (INTENT_REGISTER_DEMAND, ("找不到", "没有", "缺", "没数据", "需要数据", "登记需求")),
    (INTENT_QUERY_APPLICATION, ("申请单", "审批进度", "我的申请", "我提交")),
    (INTENT_DISCOVER_RESOURCE, ("查", "找", "搜", "需要", "想要", "数据", "资源", "目录")),
)

_REGION_PATTERN = re.compile(r"(全省|跨省|省内|济南|青岛|烟台|淄博|潍坊|临沂|济宁|泰安|聊城|滨州|菏泽|枣庄|日照|东营|威海|德州)")


_QUERY_PREFIXES = ("帮我", "我要", "想要", "搜索", "查", "找", "搜")
_QUERY_SUFFIXES = ("相关数据", "相关资源", "相关", "数据", "资源", "信息", "目录")
_TOPIC_VOCAB = (
    "营商环境",
    "停车场",
    "医保码",
    "医保",
    "户籍",
    "不动产",
    "教育",
    "水电气",
    "一表通",
    "民政",
    "出生",
    "婚姻登记",
    "行政审批",
    "房地产",
    "医疗救助",
    "跨省",
)


def _split_keywords(query: str) -> list[str]:
    """简单中文分词 (Wave 1 stub)：按空格 / 标点 拆，过滤短词."""
    parts = re.split(r"[\s,，。;；:：、\-——()（）\[\]【】\"'""'']+", query.strip())
    return [p for p in parts if len(p) >= 2]


def _strip_query_noise(text: str) -> str:
    q = text.strip()
    for prefix in _QUERY_PREFIXES:
        if q.startswith(prefix):
            q = q[len(prefix) :]
    for suffix in _QUERY_SUFFIXES:
        if q.endswith(suffix) and len(q) > len(suffix) + 1:
            q = q[: -len(suffix)]
    return q.lstrip("省市区县").strip()


def _extract_search_terms(query: str) -> list[str]:
    """从整句 NL 输入提取可检索主题词，避免整句落进搜索框导致 0 命中。"""
    query_clean = query.strip()
    if not query_clean:
        return []
    terms: list[str] = []
    for topic in sorted(_TOPIC_VOCAB, key=len, reverse=True):
        if topic not in query_clean:
            continue
        if any(topic in existing or existing in topic for existing in terms):
            continue
        terms.append(topic)
    if terms:
        return terms[:8]
    stripped = _strip_query_noise(query_clean)
    parts = _split_keywords(stripped)
    if parts:
        return parts[:8]
    if len(stripped) >= 2:
        return [stripped]
    return _split_keywords(query_clean)[:8]


def _normalize_keywords(query: str, keywords: list[str]) -> list[str]:
    cleaned = [str(k).strip() for k in keywords if str(k).strip()]
    extracted = _extract_search_terms(query)
    merged: list[str] = []
    for k in cleaned + extracted:
        if not k or k in merged:
            continue
        if any(k in existing or existing in k for existing in merged):
            continue
        merged.append(k)
    if not merged:
        return extracted[:8]
    if len(merged) == 1 and merged[0] == query.strip():
        return extracted[:8] or merged
    return merged[:8]


def _rule_based_parse(query: str) -> dict[str, Any]:
    query_clean = query.strip()
    if not query_clean:
        return {
            "intent": INTENT_UNKNOWN,
            "keywords": [],
            "dimension": {"keyword": [], "target_resource_hint": None, "region": None},
            "missing_fields": ["query"],
            "recommendation_reason": "未输入搜索关键词。",
            "follow_up_questions": ["想找哪类政务数据？", "数据涉及哪些部门？"],
            "source": "fallback_rule",
        }
    keywords = _extract_search_terms(query_clean)
    intent = INTENT_UNKNOWN
    for candidate_intent, markers in _INTENT_RULES:
        if any(m in query_clean for m in markers):
            intent = candidate_intent
            break
    if intent == INTENT_UNKNOWN and keywords:
        intent = INTENT_DISCOVER_RESOURCE

    region_match = _REGION_PATTERN.search(query_clean)
    region = region_match.group(1) if region_match else None
    target_hint = keywords[0] if keywords else None

    missing_fields: list[str] = []
    if not region:
        missing_fields.append("覆盖范围（如省 / 市 / 跨省）")
    if intent == INTENT_REGISTER_DEMAND:
        missing_fields.append("期望提供方部门")
    if intent == INTENT_QUERY_APPLICATION:
        missing_fields.append("申请单提交时间窗")

    reason = (
        f"基于关键词 {keywords[:3]} 推断为「{intent}」；"
        f"如想看其他主题数据，可在搜索框追加更多关键词。"
    )
    follow_ups = []
    if intent == INTENT_DISCOVER_RESOURCE:
        follow_ups = [
            f"是否限定为 {region or '某省 / 市'}？",
            "需要原始库表还是接口服务？",
            "数据更新频率要求多高？",
        ]
    elif intent == INTENT_REGISTER_DEMAND:
        follow_ups = [
            "希望由哪个部门提供？",
            "本需求是否已与提供方部门沟通过？",
        ]
    elif intent == INTENT_QUERY_APPLICATION:
        follow_ups = [
            "查最近 7 天 / 30 天 / 全部？",
            "限定为审批中 / 已通过 / 已驳回？",
        ]

    return {
        "intent": intent,
        "keywords": keywords[:8],
        "dimension": {
            "keyword": keywords[:5],
            "target_resource_hint": target_hint,
            "region": region,
        },
        "missing_fields": missing_fields,
        "recommendation_reason": reason,
        "follow_up_questions": follow_ups,
        "source": "fallback_rule",
    }


def _inference_based_parse(query: str, request_id: str) -> dict[str, Any] | None:
    """走 shared/inference/client.chat；推理返回 JSON 解析失败时回 None 让 caller 走 fallback."""
    prompt = (
        "你是政务数据平台 P2 资源发现页的搜索助手。请把用户的一句话搜索拆成结构化字段，"
        "输出严格 JSON：{"
        "\"intent\":\"discover_resource|register_demand|query_application|unknown\","
        "\"keywords\":[],\"dimension\":{\"keyword\":[],\"target_resource_hint\":null,\"region\":null},"
        "\"missing_fields\":[],\"recommendation_reason\":\"\",\"follow_up_questions\":[]}"
        "。不要输出其他文字。"
    )
    messages = [
        ChatMessage(role="system", content=prompt),
        ChatMessage(role="user", content=query),
    ]
    result = _inference_chat(messages, model="", request_id=request_id, temperature=0.0)
    raw = (result.text or "").strip()
    # 尝试剥掉 markdown 围栏
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        parsed = _json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    intent = str(parsed.get("intent", INTENT_UNKNOWN))
    if intent not in ALL_INTENTS:
        intent = INTENT_UNKNOWN
    keywords = parsed.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    dim_raw = parsed.get("dimension") or {}
    if not isinstance(dim_raw, dict):
        dim_raw = {}
    return {
        "intent": intent,
        "keywords": [str(k) for k in keywords if k][:8],
        "dimension": {
            "keyword": [str(k) for k in (dim_raw.get("keyword") or []) if k][:5],
            "target_resource_hint": str(dim_raw["target_resource_hint"]) if dim_raw.get("target_resource_hint") else None,
            "region": str(dim_raw["region"]) if dim_raw.get("region") else None,
        },
        "missing_fields": [str(m) for m in (parsed.get("missing_fields") or []) if m][:6],
        "recommendation_reason": str(parsed.get("recommendation_reason") or ""),
        "follow_up_questions": [str(q) for q in (parsed.get("follow_up_questions") or []) if q][:6],
        "source": "inference",
    }


def _parse_search_intent(brain, deps, ctx, query: str, role: str, *, enabled: bool, request_id: str) -> dict[str, Any]:
    actor = ctx.actor or "system"
    audit_target = query[:80] if query else "<empty>"

    if not enabled:
        result = _rule_based_parse(query)
        deps.append_audit_feed("search.intent.parse", audit_target, "ok", actor)
        result["enabled"] = False
        return result

    inference_result: dict[str, Any] | None = None
    try:
        inference_result = _inference_based_parse(query, request_id=request_id)
    except InferenceError:
        inference_result = None

    if inference_result is not None:
        deps.append_audit_feed("search.intent.parse", audit_target, "ok", actor)
        inference_result["enabled"] = True
        inference_result["keywords"] = _normalize_keywords(query, inference_result.get("keywords") or [])
        dim = inference_result.get("dimension") or {}
        if isinstance(dim, dict):
            dim["keyword"] = inference_result["keywords"][:5]
            if inference_result["keywords"] and not dim.get("target_resource_hint"):
                dim["target_resource_hint"] = inference_result["keywords"][0]
            inference_result["dimension"] = dim
        return inference_result

    # 推理失败 / JSON 解析失败 → 降级
    fallback = _rule_based_parse(query)
    deps.append_audit_feed("search.intent.parse", audit_target, "warning", actor)
    fallback["enabled"] = True
    fallback["degraded"] = True
    return fallback


def handler_search_intent_parse(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    query = str(payload.get("query") or "")
    role = str(payload.get("role", ctx.role))
    enabled = bool(payload.get("enabled", True))
    request_id = str(payload.get("request_id") or f"search-intent-{abs(hash(query)) & 0xFFFFFFFF:08x}")
    return _parse_search_intent(brain, deps, ctx, query, role, enabled=enabled, request_id=request_id)
