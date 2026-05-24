"""E3 Wave-2 三引擎 F5 — 表单 schema NL 草稿生成。

3-tier 策略（与 [[approval-flow-nl-draft]] 同形）：
- Tier 1 deterministic：识别 "N 字段 / N 个字段" 模板 + 常见字段名 patterns
  （姓名 / 身份证号 / 联系电话 / 单位 / 申请事由 / 申请日期 / 附件 / 备注 ...），
  生成 1 个 section（默认"基本信息"）+ N 个 FormField + 自动绑定 validator。
- Tier 2 LLM：经 zw_brain.shared.inference.client.chat，约束 strict JSON；
  含「四川 7 字段」few-shot。
- Tier 3 fallback：InferenceError / JSON 解析失败 / payload 校验失败 → deterministic 兜底。
- 输出二次过 FormSchemaRepo 的 _validate_payload。
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from zw_brain.domain.form_schema import FormSchemaRepo, _validate_payload
from zw_brain.domain.models import FormSchemaRecord
from zw_brain.shared.inference.client import ChatMessage, InferenceError
from zw_brain.shared.inference.client import chat as _inference_chat

_CN_DIGIT_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_COUNT_PATTERN = re.compile(
    r"(\d+|一|二|三|四|五|六|七|八|九|十)\s*(?:个)?\s*字段"
)

_DEFAULT_MAX_FIELDS = 20

# 常见政务表单字段模板：字段名（含中文别名）→ (field_code, field_type, default validators[])
_FIELD_TEMPLATES: list[dict[str, Any]] = [
    {
        "aliases": ["姓名", "申请人姓名", "姓名/申请人"],
        "field_code": "applicant_name",
        "field_name": "申请人姓名",
        "field_type": "text",
        "required": True,
        "validators": [
            {
                "validator_code": "name_len",
                "validator_kind": "length",
                "validator_payload_json": {"minLength": 2, "maxLength": 32},
                "error_message_template": "姓名长度需在 2-32 之间",
            }
        ],
    },
    {
        "aliases": ["身份证号", "身份证", "身份证号码"],
        "field_code": "id_card",
        "field_name": "身份证号",
        "field_type": "text",
        "required": True,
        "validators": [
            {
                "validator_code": "id_card_pattern",
                "validator_kind": "regex",
                "validator_payload_json": {"pattern": r"^\d{17}[\dXx]$"},
                "error_message_template": "身份证号格式错误",
            }
        ],
    },
    {
        "aliases": ["联系电话", "电话", "手机号", "手机", "联系方式"],
        "field_code": "phone",
        "field_name": "联系电话",
        "field_type": "text",
        "required": True,
        "validators": [
            {
                "validator_code": "phone_len",
                "validator_kind": "length",
                "validator_payload_json": {"minLength": 7, "maxLength": 20},
                "error_message_template": "联系电话长度需在 7-20 之间",
            }
        ],
    },
    {
        "aliases": ["单位", "工作单位", "申请单位", "所属单位", "机构"],
        "field_code": "applicant_org",
        "field_name": "申请单位",
        "field_type": "text",
        "required": True,
        "validators": [],
    },
    {
        "aliases": ["申请事由", "事由", "申请原因", "用途"],
        "field_code": "apply_reason",
        "field_name": "申请事由",
        "field_type": "textarea",
        "required": True,
        "validators": [
            {
                "validator_code": "reason_len",
                "validator_kind": "length",
                "validator_payload_json": {"minLength": 5, "maxLength": 500},
                "error_message_template": "申请事由 5-500 字",
            }
        ],
    },
    {
        "aliases": ["申请日期", "日期"],
        "field_code": "apply_date",
        "field_name": "申请日期",
        "field_type": "date",
        "required": True,
        "validators": [],
    },
    {
        "aliases": ["附件", "证明材料", "上传附件", "材料"],
        "field_code": "attachment",
        "field_name": "附件",
        "field_type": "file",
        "required": False,
        "validators": [
            {
                "validator_code": "attachment_size",
                "validator_kind": "file_size",
                "validator_payload_json": {"maxBytes": 20 * 1024 * 1024},
                "error_message_template": "单个附件不超过 20MB",
            }
        ],
    },
    {
        "aliases": ["备注", "其他说明", "补充说明"],
        "field_code": "remark",
        "field_name": "备注",
        "field_type": "textarea",
        "required": False,
        "validators": [],
    },
    {
        "aliases": ["邮箱", "电子邮箱", "email"],
        "field_code": "email",
        "field_name": "电子邮箱",
        "field_type": "text",
        "required": False,
        "validators": [
            {
                "validator_code": "email_pattern",
                "validator_kind": "regex",
                "validator_payload_json": {"pattern": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"},
                "error_message_template": "邮箱格式错误",
            }
        ],
    },
    {
        "aliases": ["地址", "联系地址", "通讯地址"],
        "field_code": "address",
        "field_name": "联系地址",
        "field_type": "text",
        "required": False,
        "validators": [],
    },
]


FORM_SCHEMA_PROMPT = """你是政务大脑表单 schema 配置助手。

任务：根据用户一句话需求，生成严格 JSON 的表单模板 payload。

输出必须是单个 JSON 对象，字段：
- sections: list, 每项 {section_code, title, order_index?, collapsible?}
  - 至少 1 个 section
- fields: list, 每项 {field_code, section_code, field_name, field_type, required?, order_index?, placeholder?, default_value_json?, layout_hints_json?}
  - field_type ∈ {text, textarea, number, date, datetime, select, multiselect, checkbox, file, user_picker, org_picker}
  - section_code 必须存在于 sections
- validators: list, 每项 {validator_code, applies_to_field_code, validator_kind, validator_payload_json, error_message_template?}
  - validator_kind ∈ {regex, range, length, enum, file_size, file_type, custom_expression}

输出示例（四川 7 字段表单：姓名/身份证/联系电话/单位/事由/日期/附件）：
{
  "sections": [{"section_code": "basic", "title": "基本信息", "order_index": 0}],
  "fields": [
    {"field_code": "applicant_name", "section_code": "basic", "field_name": "申请人姓名", "field_type": "text", "required": true, "order_index": 0},
    {"field_code": "id_card", "section_code": "basic", "field_name": "身份证号", "field_type": "text", "required": true, "order_index": 1},
    {"field_code": "phone", "section_code": "basic", "field_name": "联系电话", "field_type": "text", "required": true, "order_index": 2},
    {"field_code": "applicant_org", "section_code": "basic", "field_name": "申请单位", "field_type": "text", "required": true, "order_index": 3},
    {"field_code": "apply_reason", "section_code": "basic", "field_name": "申请事由", "field_type": "textarea", "required": true, "order_index": 4},
    {"field_code": "apply_date", "section_code": "basic", "field_name": "申请日期", "field_type": "date", "required": true, "order_index": 5},
    {"field_code": "attachment", "section_code": "basic", "field_name": "附件", "field_type": "file", "required": false, "order_index": 6}
  ],
  "validators": [
    {"validator_code": "id_card_pattern", "applies_to_field_code": "id_card", "validator_kind": "regex", "validator_payload_json": {"pattern": "^\\\\d{17}[\\\\dXx]$"}},
    {"validator_code": "phone_len", "applies_to_field_code": "phone", "validator_kind": "length", "validator_payload_json": {"minLength": 7, "maxLength": 20}},
    {"validator_code": "attachment_size", "applies_to_field_code": "attachment", "validator_kind": "file_size", "validator_payload_json": {"maxBytes": 20971520}}
  ]
}

只输出 JSON，不要 markdown 代码块、不要解释。"""


class FormSchemaDraftError(ValueError):
    pass


class FormSchemaDraftSourceError(ValueError):
    pass


def _chinese_to_int(token: str) -> int | None:
    if token.isdigit():
        try:
            return int(token)
        except ValueError:
            return None
    return _CN_DIGIT_MAP.get(token)


def _match_field_templates(intent_text: str) -> list[dict[str, Any]]:
    """按出现顺序抽取已知字段模板。"""
    hits: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    # 按 alias 在 intent_text 中第一次出现的位置排序
    positioned: list[tuple[int, dict[str, Any]]] = []
    for tpl in _FIELD_TEMPLATES:
        best_pos: int | None = None
        for alias in tpl["aliases"]:
            pos = intent_text.find(alias)
            if pos >= 0 and (best_pos is None or pos < best_pos):
                best_pos = pos
        if best_pos is not None:
            positioned.append((best_pos, tpl))
    positioned.sort(key=lambda x: x[0])
    for _, tpl in positioned:
        if tpl["field_code"] in seen_codes:
            continue
        seen_codes.add(tpl["field_code"])
        hits.append(tpl)
    return hits


def _build_payload_from_templates(templates: list[dict[str, Any]]) -> dict[str, Any]:
    if not templates:
        # 最小可达 schema：1 个文本字段
        templates = [
            {
                "field_code": "applicant_name",
                "field_name": "申请人姓名",
                "field_type": "text",
                "required": True,
                "validators": [],
            }
        ]
    sections = [{"section_code": "basic", "title": "基本信息", "order_index": 0}]
    fields: list[dict[str, Any]] = []
    validators: list[dict[str, Any]] = []
    for idx, tpl in enumerate(templates):
        fields.append(
            {
                "field_code": tpl["field_code"],
                "section_code": "basic",
                "field_name": tpl["field_name"],
                "field_type": tpl["field_type"],
                "required": bool(tpl.get("required", False)),
                "order_index": idx,
            }
        )
        for v in tpl.get("validators", []):
            validators.append({**v, "applies_to_field_code": tpl["field_code"]})
    return {"sections": sections, "fields": fields, "validators": validators}


def _deterministic_payload(intent_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    templates = _match_field_templates(intent_text)
    if templates:
        payload = _build_payload_from_templates(templates)
        return payload, {
            "tier": "deterministic",
            "matched_pattern": "field_aliases",
            "field_count": len(templates),
        }
    # 没匹配到字段名 → 尝试数量推断（fallback 不知字段名，建 N 个通用文本字段）
    match = _COUNT_PATTERN.search(intent_text)
    if match:
        count = _chinese_to_int(match.group(1))
        if count and 1 <= count <= _DEFAULT_MAX_FIELDS:
            generic_templates = [
                {
                    "field_code": f"field_{i + 1}",
                    "field_name": f"字段{i + 1}",
                    "field_type": "text",
                    "required": False,
                    "validators": [],
                }
                for i in range(count)
            ]
            payload = _build_payload_from_templates(generic_templates)
            return payload, {
                "tier": "deterministic",
                "matched_pattern": "field_count_only",
                "field_count": count,
            }
    # 最小可达：1 个文本字段
    payload = _build_payload_from_templates([])
    return payload, {
        "tier": "deterministic",
        "matched_pattern": "fallback_min",
        "field_count": 1,
    }


def _try_llm_payload(intent_text: str, *, request_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        result = _inference_chat(
            [
                ChatMessage(role="system", content=FORM_SCHEMA_PROMPT),
                ChatMessage(role="user", content=intent_text),
            ],
            model="claude-sonnet-4-7",
            temperature=0.0,
            max_tokens=1500,
            request_id=request_id,
        )
    except InferenceError as exc:
        return None, {"tier": "llm-fallback", "fallback_reason": f"InferenceError: {exc}"}
    text = (result.text or "").strip()
    if not text:
        return None, {"tier": "llm-fallback", "fallback_reason": "empty_llm_response"}
    cleaned = text
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
    if not isinstance(intent_text, str) or not intent_text.strip():
        raise FormSchemaDraftSourceError("intent_text must be a non-empty string")

    deterministic_payload, deterministic_meta = _deterministic_payload(intent_text)
    _validate_payload(deterministic_payload)

    if deterministic_only:
        return deterministic_payload, deterministic_meta

    rid = request_id or f"FORM-NL-{uuid.uuid4()}"
    payload, meta = _try_llm_payload(intent_text, request_id=rid)
    if payload is None:
        return deterministic_payload, {**deterministic_meta, **meta}
    return payload, {**meta, "deterministic_baseline": deterministic_meta}


def generate_draft(
    repo: FormSchemaRepo,
    *,
    tenant_id: str,
    form_code: str,
    title: str,
    intent_text: str,
    created_by: str,
    deterministic_only: bool = False,
    request_id: str | None = None,
) -> tuple[FormSchemaRecord, dict[str, Any]]:
    payload, source_meta = generate_draft_payload(
        intent_text,
        tenant_id=tenant_id,
        deterministic_only=deterministic_only,
        request_id=request_id,
    )
    record = repo.create_draft(
        tenant_id=tenant_id,
        form_code=form_code,
        title=title,
        payload=payload,
        source_kind="nl_draft",
        draft_source_text=intent_text,
        created_by=created_by,
    )
    return record, source_meta
