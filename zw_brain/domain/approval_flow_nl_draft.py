"""E3 Wave-2 三引擎 F3 — 审批流 NL 草稿生成。

3-tier 策略（与 [[reverse-draft-suggest]] 一致）：
- Tier 1 deterministic：识别 "N 级审批 / N 级会签 / N 级审核 / 编制→A→B→发布" 等模板，
  产出 N+2 节点 schema（start + N approval + end）+ 默认 SelectionRule（每节点 role=ROLE_ORGAN_MANAGER）+ 线性 branches。
- Tier 2 LLM：经 zw_brain.shared.inference.client.chat，约束输出 strict JSON；
  失败回退 Tier 1。**禁止直连任何第三方 LLM SDK**（preflight 段 10）。
- Tier 3 fallback：min 可达 schema（start→approval→end）+ source_metadata.fallback_reason。

输出的 payload 经 ApprovalFlowSchemaRepo 的 _validate_payload 二次校验（写入前），
保证草稿和 commit 阶段共享同一规则。
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from zw_brain.domain.approval_flow_schema import (
    ApprovalFlowSchemaRepo,
    _validate_payload,
)
from zw_brain.domain.models import ApprovalFlowSchemaRecord
from zw_brain.shared.inference.client import ChatMessage, InferenceError
from zw_brain.shared.inference.client import chat as _inference_chat

_CN_DIGIT_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_LEVEL_PATTERN = re.compile(
    r"(\d+|一|二|三|四|五|六|七|八|九|十)\s*级.{0,8}?(审批|会签|审核)"
)
_DEFAULT_TENANT_DEFAULT_LEVEL = 1
_DEFAULT_MAX_LEVEL = 8

APPROVAL_FLOW_PROMPT = """你是政务大脑审批流配置助手。

任务：根据用户一句话需求，生成严格 JSON 的审批流模板 payload。

输出必须是单个 JSON 对象，字段：
- nodes: list, 每项 {node_code, node_type, node_name, selection_rule_code?, order_index?}
  - node_type ∈ {start, approval, notify, end}
  - 必须且仅有 1 个 start 节点和 1 个 end 节点
  - approval 节点必须引用 selection_rules 中已有的 rule_code
- selection_rules: list, 每项 {rule_code, rule_kind, rule_payload_json}
  - rule_kind ∈ {fixed_user, role, org_unit, org_unit_leader, dynamic_expression}
- branches: list, 每项 {from_node_code, to_node_code, condition_kind, condition_payload_json?}
  - condition_kind ∈ {always, expression, on_decision}
  - 必须能从 start 通过 branches 到达 end

输出示例（4 级审批）：
{
  "nodes": [
    {"node_code": "start", "node_type": "start", "node_name": "开始"},
    {"node_code": "level1", "node_type": "approval", "node_name": "1 级审批", "selection_rule_code": "default_manager"},
    {"node_code": "level2", "node_type": "approval", "node_name": "2 级审批", "selection_rule_code": "default_manager"},
    {"node_code": "level3", "node_type": "approval", "node_name": "3 级审批", "selection_rule_code": "default_manager"},
    {"node_code": "level4", "node_type": "approval", "node_name": "4 级审批", "selection_rule_code": "default_manager"},
    {"node_code": "end", "node_type": "end", "node_name": "结束"}
  ],
  "selection_rules": [
    {"rule_code": "default_manager", "rule_kind": "role", "rule_payload_json": {"role_code": "ROLE_ORGAN_MANAGER"}}
  ],
  "branches": [
    {"from_node_code": "start", "to_node_code": "level1", "condition_kind": "always"},
    {"from_node_code": "level1", "to_node_code": "level2", "condition_kind": "on_decision"},
    {"from_node_code": "level2", "to_node_code": "level3", "condition_kind": "on_decision"},
    {"from_node_code": "level3", "to_node_code": "level4", "condition_kind": "on_decision"},
    {"from_node_code": "level4", "to_node_code": "end", "condition_kind": "on_decision"}
  ]
}

只输出 JSON，不要包裹 markdown 代码块、不要解释文本。"""


class ApprovalFlowDraftError(ValueError):
    """LLM 输出非法 JSON 或不能通过 payload 校验。"""


class ApprovalFlowDraftSourceError(ValueError):
    """intent_text 无效或缺失。"""


def _chinese_to_int(token: str) -> int | None:
    if token.isdigit():
        try:
            return int(token)
        except ValueError:
            return None
    return _CN_DIGIT_MAP.get(token)


def _build_linear_payload(level_count: int, *, title_prefix: str = "审批") -> dict[str, Any]:
    level_count = max(1, min(level_count, _DEFAULT_MAX_LEVEL))
    nodes: list[dict[str, Any]] = [
        {"node_code": "start", "node_type": "start", "node_name": "开始", "order_index": 0}
    ]
    branches: list[dict[str, Any]] = []
    prev = "start"
    for idx in range(1, level_count + 1):
        node_code = f"level{idx}"
        nodes.append(
            {
                "node_code": node_code,
                "node_type": "approval",
                "node_name": f"{idx} 级{title_prefix}",
                "selection_rule_code": "default_manager",
                "order_index": idx,
            }
        )
        branches.append(
            {
                "from_node_code": prev,
                "to_node_code": node_code,
                "condition_kind": "always" if prev == "start" else "on_decision",
                "condition_payload_json": {},
            }
        )
        prev = node_code
    nodes.append(
        {"node_code": "end", "node_type": "end", "node_name": "结束", "order_index": level_count + 1}
    )
    branches.append(
        {
            "from_node_code": prev,
            "to_node_code": "end",
            "condition_kind": "on_decision",
            "condition_payload_json": {},
        }
    )
    selection_rules = [
        {
            "rule_code": "default_manager",
            "rule_kind": "role",
            "rule_payload_json": {"role_code": "ROLE_ORGAN_MANAGER"},
        }
    ]
    return {
        "nodes": nodes,
        "selection_rules": selection_rules,
        "branches": branches,
    }


def _deterministic_payload(intent_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """从 intent_text 抽取级数；命中模板时给精确 schema，否则返回最小可达 schema。"""
    match = _LEVEL_PATTERN.search(intent_text)
    if match:
        level = _chinese_to_int(match.group(1))
        kind = match.group(2)
        if level and 1 <= level <= _DEFAULT_MAX_LEVEL:
            payload = _build_linear_payload(level, title_prefix=kind)
            return payload, {"tier": "deterministic", "matched_pattern": "level_count", "level": level, "kind": kind}
    # 关键词→粗略级数
    if "编制" in intent_text and "发布" in intent_text:
        # "编制→二级部门审→一级部门审→发布" 模式
        approve_terms = re.findall(r"([一二三四五六七八九十]级\s*[部门]*\s*审|审[核批]|会签)", intent_text)
        level = max(1, min(len(approve_terms), _DEFAULT_MAX_LEVEL))
        payload = _build_linear_payload(level, title_prefix="审批")
        return payload, {"tier": "deterministic", "matched_pattern": "draft_release", "level": level}
    payload = _build_linear_payload(_DEFAULT_TENANT_DEFAULT_LEVEL, title_prefix="审批")
    return payload, {"tier": "deterministic", "matched_pattern": "fallback_min", "level": _DEFAULT_TENANT_DEFAULT_LEVEL}


def _try_llm_payload(intent_text: str, *, request_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Tier 2：经集团推理平台生成 JSON payload；任意失败 → None 让上层降级。"""
    try:
        result = _inference_chat(
            [
                ChatMessage(role="system", content=APPROVAL_FLOW_PROMPT),
                ChatMessage(role="user", content=intent_text),
            ],
            model="claude-sonnet-4-7",
            temperature=0.0,
            max_tokens=1024,
            request_id=request_id,
        )
    except InferenceError as exc:
        return None, {"tier": "llm-fallback", "fallback_reason": f"InferenceError: {exc}"}
    text = (result.text or "").strip()
    if not text:
        return None, {"tier": "llm-fallback", "fallback_reason": "empty_llm_response"}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
        cleaned = cleaned.rstrip("`").strip()
    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, {"tier": "llm-fallback", "fallback_reason": f"json_decode_error: {exc}"}
    if not isinstance(payload, dict):
        return None, {"tier": "llm-fallback", "fallback_reason": "llm_response_not_object"}
    try:
        _validate_payload(payload)
    except Exception as exc:  # noqa: BLE001
        return None, {"tier": "llm-fallback", "fallback_reason": f"payload_validation: {exc}"}
    return payload, {"tier": "llm", "model": result.model}


def generate_draft_payload(
    intent_text: str,
    *,
    tenant_id: str,
    deterministic_only: bool = False,
    request_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (payload, source_metadata)。

    source_metadata.tier ∈ {deterministic, llm, llm-fallback}；
    payload 必然通过 _validate_payload。
    """
    if not isinstance(intent_text, str) or not intent_text.strip():
        raise ApprovalFlowDraftSourceError("intent_text must be a non-empty string")

    deterministic_payload, deterministic_meta = _deterministic_payload(intent_text)
    _validate_payload(deterministic_payload)

    if deterministic_only:
        return deterministic_payload, deterministic_meta

    rid = request_id or f"AF-NL-{uuid.uuid4()}"
    attempt = _try_llm_payload(intent_text, request_id=rid)
    if attempt is None:
        # 推理客户端模块出口异常（不应发生）— 走 fallback
        return deterministic_payload, {
            **deterministic_meta,
            "tier": "llm-fallback",
            "fallback_reason": "llm_attempt_returned_none",
        }
    payload, meta = attempt
    if payload is None:
        # Tier 2 失败 → Tier 3 fallback：用 deterministic 兜底，但元数据保留 LLM 失败原因。
        return deterministic_payload, {**deterministic_meta, **meta}
    return payload, {**meta, "deterministic_baseline": deterministic_meta}


def generate_draft(
    repo: ApprovalFlowSchemaRepo,
    *,
    tenant_id: str,
    schema_code: str,
    title: str,
    intent_text: str,
    created_by: str,
    deterministic_only: bool = False,
    request_id: str | None = None,
) -> tuple[ApprovalFlowSchemaRecord, dict[str, Any]]:
    payload, source_meta = generate_draft_payload(
        intent_text,
        tenant_id=tenant_id,
        deterministic_only=deterministic_only,
        request_id=request_id,
    )
    record = repo.create_draft(
        tenant_id=tenant_id,
        schema_code=schema_code,
        title=title,
        payload=payload,
        source_kind="nl_draft",
        draft_source_text=intent_text,
        created_by=created_by,
    )
    return record, source_meta
