"""Reverse-cataloging 三档智能预填.

Tier 1 (deterministic, ships now):
    - `column.comment` / `column.remark` (legacy data center notes)
    - `meta_standard_cn` (legacy 数据标准 mapping)
    → green confidence "comment"

Tier 2 (deterministic, ships now):
    - PII pattern match (mobile / phone / id_card / email / addr / secret …)
      reusing the redaction rule patterns from W0.1
    → yellow confidence "pii-pattern"; also flips sensitive_level to 3
      so R6 doesn't accidentally ship a leaky catalog

Tier 3 (stub, swap to inference gateway in W5):
    - placeholder "字段_<en_name>" with low confidence "llm-stub"
    - the LLM call will go through `zw_brain.shared.inference.client`
      per D6 (no third-party LLM SDKs). For now we just emit a
      placeholder so the UI flow is complete end-to-end.

Output shape is stable and stored under `summary_json.draft_field_suggestions`
when the user accepts the suggestion, so R7 can later see exactly which
suggestion source each field came from.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# Built-in Chinese mapping for common PII column patterns. These are the
# names R7 will see when no comment is available — chosen to match the
# vocabulary used in old/12-datastructure XML schemas.
_PII_PATTERN_MAPPING: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"(^|_)(mobile|cellphone|手机)(_|$)", re.IGNORECASE), "手机号", "3"),
    (re.compile(r"(^|_)(phone|tel|telephone|telphone)(_|$)", re.IGNORECASE), "联系电话", "3"),
    (re.compile(r"(^|_)id_?card(_|$|no)", re.IGNORECASE), "身份证号", "4"),
    (re.compile(r"(^|_)(idno|certno|cert_no|certificate_no)(_|$)", re.IGNORECASE), "证件号", "4"),
    (re.compile(r"(^|_)(email|mail)(_|$|addr)", re.IGNORECASE), "电子邮箱", "3"),
    (re.compile(r"(^|_)(password|passwd|pwd|secret|token|api_?key|app_?key|app_?secret)(_|$)", re.IGNORECASE), "凭据（脱敏）", "4"),
    (re.compile(r"(^|_)(home_addr|reg_addr|contact_addr)(_|$)", re.IGNORECASE), "联系地址", "3"),
    (re.compile(r"(^|_)(address|addr)(_|$)", re.IGNORECASE), "地址", "3"),
    (re.compile(r"(^|_)(bank_?card|card_?no|account_?no|bank_?account)(_|$)", re.IGNORECASE), "银行账号", "4"),
    (re.compile(r"(^|_)(ip_addr|ip_address|server_ip|host_ip|client_ip)(_|$)", re.IGNORECASE), "IP 地址", "3"),
    (re.compile(r"(^|_)(name_cn|name)(_|$)", re.IGNORECASE), "姓名", "3"),
    (re.compile(r"(^|_)(org_code|org_name|department|dept_name)(_|$)", re.IGNORECASE), "组织信息", "2"),
    (re.compile(r"(^|_)(region_code|region_name|area_code|area_name)(_|$)", re.IGNORECASE), "区划", "1"),
    (re.compile(r"(^|_)(create_time|update_time|gmt_create|gmt_update|created_at|updated_at)(_|$)", re.IGNORECASE), "时间戳", "1"),
)

# Likely keys carrying the column name across legacy schemas / db_meta tables.
_COLUMN_KEYS_FIELD_NAME = ("column_name", "field_name", "name", "name_en", "column_code")
_COLUMN_KEYS_COMMENT = ("comment", "remark", "column_comment", "name_cn", "title")
_COLUMN_KEYS_STANDARD_CN = ("meta_standard_cn", "standard_cn", "data_standard_cn")
_COLUMN_KEYS_SENSITIVE = ("sensitive_level",)
_COLUMN_KEYS_TYPE = ("data_type", "type", "format", "column_type")


def build_field_suggestions(schema_json: dict[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return suggestions for every column found in `schema_json`.

    `schema_json` shapes seen in the wild:
        {"columns": [{"column_name": ..., "comment": ...}, ...]}     (CatalogMetadataMapper)
        {"fields":  [{"name": ..., "type": ...}, ...]}               (some adapter outputs)
        {"meta_id": ..., "column_name": ..., "comment": ...}         (single-row meta)
    The helper handles all three shapes by always coercing into a flat
    list of column dicts before running the three-tier suggestion logic.
    """
    if not isinstance(schema_json, dict):
        return [], {"green": 0, "yellow": 0, "orange": 0, "total": 0}
    raw_fields = _flatten_field_list(schema_json)
    suggestions = [_suggest_for_column(col) for col in raw_fields]
    coverage = {
        "green": sum(1 for s in suggestions if s["confidence"] == "green"),
        "yellow": sum(1 for s in suggestions if s["confidence"] == "yellow"),
        "orange": sum(1 for s in suggestions if s["confidence"] == "orange"),
        "total": len(suggestions),
    }
    return suggestions, coverage


def build_title_suggestion(snapshot_payload: dict[str, Any] | None) -> dict[str, Any]:
    """Suggest a catalog title from snapshot metadata.

    Picks (in order): explicit title / table comment / resource title /
    table name → fallback to schema_ref. Confidence escalates from high
    (explicit) to low (placeholder).
    """
    if not isinstance(snapshot_payload, dict):
        return {"title": "", "confidence": "orange", "source": "placeholder"}
    for key in ("title", "name_cn", "table_comment", "comment", "resource_title"):
        value = snapshot_payload.get(key)
        if isinstance(value, str) and value.strip():
            return {"title": value.strip(), "confidence": "green", "source": key}
    for key in ("table_name", "resource_code", "schema_ref"):
        value = snapshot_payload.get(key)
        if isinstance(value, str) and value.strip():
            return {"title": _humanize_identifier(value), "confidence": "yellow", "source": f"derived:{key}"}
    return {"title": "新建反向编目目录", "confidence": "orange", "source": "placeholder"}


def _flatten_field_list(schema_json: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("columns", "fields", "column_list", "field_list"):
        value = schema_json.get(key)
        if isinstance(value, list):
            return [col for col in value if isinstance(col, dict)]
    # Single-row shape: treat the whole dict as one column entry.
    if any(k in schema_json for k in _COLUMN_KEYS_FIELD_NAME):
        return [schema_json]
    return []


def _suggest_for_column(column: dict[str, Any]) -> dict[str, Any]:
    field_en = _pick(column, _COLUMN_KEYS_FIELD_NAME) or "<unknown>"
    data_type = _pick(column, _COLUMN_KEYS_TYPE)
    sensitive_legacy = _pick(column, _COLUMN_KEYS_SENSITIVE)
    # Tier 1a: explicit data standard Chinese name
    standard_cn = _pick(column, _COLUMN_KEYS_STANDARD_CN)
    if standard_cn:
        return _row(field_en, standard_cn, "green", "data-standard", data_type, sensitive_legacy)
    # Tier 1b: column.comment / remark
    comment = _pick(column, _COLUMN_KEYS_COMMENT)
    if comment and comment != field_en:
        return _row(field_en, comment, "green", "comment", data_type, sensitive_legacy)
    # Tier 2: PII pattern match
    for pattern, mapping_cn, suggested_level in _PII_PATTERN_MAPPING:
        if pattern.search(field_en):
            level = sensitive_legacy if sensitive_legacy in {"3", "4"} else suggested_level
            return _row(field_en, mapping_cn, "yellow", "pii-pattern", data_type, level)
    # Tier 3: LLM stub (W5 will swap this for an inference-gateway call)
    return _row(field_en, f"字段_{field_en}", "orange", "llm-stub", data_type, sensitive_legacy or "1")


def _row(
    field_en: str,
    field_cn: str,
    confidence: str,
    source: str,
    data_type: str | None,
    sensitive_level: str | None,
) -> dict[str, Any]:
    return {
        "field_en": field_en,
        "field_cn": field_cn,
        "confidence": confidence,
        "source": source,
        "data_type": data_type or "",
        "sensitive_level": sensitive_level or "1",
    }


def _pick(column: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = column.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and value != 0:
            return str(value)
    return None


def _humanize_identifier(ident: str) -> str:
    if not ident:
        return ident
    parts = [p for p in re.split(r"[_\-:]+", ident) if p]
    return " ".join(parts) or ident
