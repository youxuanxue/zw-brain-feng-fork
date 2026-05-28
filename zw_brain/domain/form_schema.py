"""E3 Wave-2 三引擎 F4 — 表单 schema 化引擎状态机 + 仓库 helper。

承接 R14（草稿→预览→入库）/ 设计基线 §10.3 三引擎契约字段；与
[[approval-flow-schema]] 同形，本仓库只负责模板/定义层，业务表单实例提交不在本组。
to_json_schema 提供 draft-07 兼容投影，供 J1/J2 表单页消费（消费端集成不在本期 F4）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zw_brain.domain.models import (
    FormFieldRecord,
    FormSchemaRecord,
    FormSectionRecord,
    FormValidatorRecord,
)

FormSchemaStatus = Literal["draft", "preview", "live"]

_VALID_STATUSES: set[str] = {"draft", "preview", "live"}
_VALID_FIELD_TYPES: set[str] = {
    "text",
    "textarea",
    "number",
    "date",
    "datetime",
    "select",
    "multiselect",
    "checkbox",
    "file",
    "user_picker",
    "org_picker",
}
_VALID_VALIDATOR_KINDS: set[str] = {
    "regex",
    "range",
    "length",
    "enum",
    "file_size",
    "file_type",
    "custom_expression",
}

# field_type → JSON Schema 基础 type 映射（用于 to_json_schema）
_FIELD_TYPE_TO_JSON_TYPE: dict[str, str] = {
    "text": "string",
    "textarea": "string",
    "number": "number",
    "date": "string",
    "datetime": "string",
    "select": "string",
    "multiselect": "array",
    "checkbox": "boolean",
    "file": "string",
    "user_picker": "string",
    "org_picker": "string",
}
_FIELD_TYPE_TO_JSON_FORMAT: dict[str, str] = {
    "date": "date",
    "datetime": "date-time",
}


class FormSchemaTransitionError(ValueError):
    """draft/preview/live 状态机非法跃迁。"""


class FormSchemaPayloadError(ValueError):
    """payload_json 结构校验失败。"""


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise FormSchemaPayloadError("payload must be a dict")
    for key in ("sections", "fields", "validators"):
        if key not in payload:
            raise FormSchemaPayloadError(f"payload missing required key: {key}")
        if not isinstance(payload[key], list):
            raise FormSchemaPayloadError(f"payload[{key!r}] must be a list")

    sections: list[dict[str, Any]] = payload["sections"]
    fields: list[dict[str, Any]] = payload["fields"]
    validators: list[dict[str, Any]] = payload["validators"]

    if not sections:
        raise FormSchemaPayloadError("payload.sections must not be empty")
    if not fields:
        raise FormSchemaPayloadError("payload.fields must not be empty")

    section_codes: list[str] = []
    for section in sections:
        if not isinstance(section, dict):
            raise FormSchemaPayloadError("each section must be a dict")
        code = section.get("section_code")
        if not isinstance(code, str) or not code:
            raise FormSchemaPayloadError("section.section_code is required")
        if code in section_codes:
            raise FormSchemaPayloadError(f"duplicate section_code: {code}")
        section_codes.append(code)

    section_code_set = set(section_codes)
    field_codes: list[str] = []
    for field in fields:
        if not isinstance(field, dict):
            raise FormSchemaPayloadError("each field must be a dict")
        code = field.get("field_code")
        section_code = field.get("section_code")
        field_type = field.get("field_type")
        if not isinstance(code, str) or not code:
            raise FormSchemaPayloadError("field.field_code is required")
        if code in field_codes:
            raise FormSchemaPayloadError(f"duplicate field_code: {code}")
        field_codes.append(code)
        if section_code not in section_code_set:
            raise FormSchemaPayloadError(
                f"field.section_code {section_code!r} not in sections"
            )
        if field_type not in _VALID_FIELD_TYPES:
            raise FormSchemaPayloadError(
                f"field.field_type must be one of {sorted(_VALID_FIELD_TYPES)}, got {field_type!r}"
            )

    field_code_set = set(field_codes)
    validator_codes: list[str] = []
    for validator in validators:
        if not isinstance(validator, dict):
            raise FormSchemaPayloadError("each validator must be a dict")
        code = validator.get("validator_code")
        applies_to = validator.get("applies_to_field_code")
        kind = validator.get("validator_kind")
        if not isinstance(code, str) or not code:
            raise FormSchemaPayloadError("validator.validator_code is required")
        if code in validator_codes:
            raise FormSchemaPayloadError(f"duplicate validator_code: {code}")
        validator_codes.append(code)
        if applies_to not in field_code_set:
            raise FormSchemaPayloadError(
                f"validator.applies_to_field_code {applies_to!r} not in fields"
            )
        if kind not in _VALID_VALIDATOR_KINDS:
            raise FormSchemaPayloadError(
                f"validator.validator_kind must be one of {sorted(_VALID_VALIDATOR_KINDS)}, got {kind!r}"
            )


class FormSchemaRepo:
    """三态状态机（draft → preview → live）+ payload 结构校验仓库。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ---- mutation ---------------------------------------------------------

    def create_draft(
        self,
        tenant_id: str,
        form_code: str,
        title: str,
        payload: dict[str, Any],
        *,
        source_kind: str = "manual",
        draft_source_text: str | None = None,
        created_by: str,
    ) -> FormSchemaRecord:
        _validate_payload(payload)
        # 自增 version：同 (tenant, form_code) 已有记录时新建 v=max+1 草稿。
        existing_max = self._session.execute(
            select(func.max(FormSchemaRecord.version))
            .where(FormSchemaRecord.tenant_id == tenant_id)
            .where(FormSchemaRecord.form_code == form_code)
        ).scalar() or 0
        record = FormSchemaRecord(
            tenant_id=tenant_id,
            form_code=form_code,
            title=title,
            status="draft",
            version=existing_max + 1,
            source_kind=source_kind,
            draft_source_text=draft_source_text,
            payload_json=payload,
            created_by=created_by,
        )
        self._session.add(record)
        self._session.flush()
        self._project_payload(record, payload)
        self._session.commit()
        return record

    def promote_to_preview(self, schema_id: str) -> FormSchemaRecord:
        record = self._require(schema_id)
        if record.status != "draft":
            raise FormSchemaTransitionError(
                f"promote_to_preview requires status=draft, got {record.status!r}"
            )
        _validate_payload(record.payload_json)
        record.status = "preview"
        record.updated_at = _now()
        self._session.commit()
        return record

    def revert_to_draft(self, schema_id: str) -> FormSchemaRecord:
        record = self._require(schema_id)
        if record.status != "preview":
            raise FormSchemaTransitionError(
                f"revert_to_draft requires status=preview, got {record.status!r}"
            )
        record.status = "draft"
        record.updated_at = _now()
        self._session.commit()
        return record

    def commit_to_live(self, schema_id: str) -> FormSchemaRecord:
        record = self._require(schema_id)
        if record.status != "preview":
            raise FormSchemaTransitionError(
                f"commit_to_live requires status=preview, got {record.status!r}"
            )
        _validate_payload(record.payload_json)
        # debt(A方案 2026-05-28): 同 approval_flow_schema — 取 max+1 避免历史鬼数据撞 UNIQUE。
        existing_max = self._session.execute(
            select(func.max(FormSchemaRecord.version))
            .where(FormSchemaRecord.tenant_id == record.tenant_id)
            .where(FormSchemaRecord.form_code == record.form_code)
        ).scalar() or 0
        now = _now()
        record.status = "live"
        record.version = max(existing_max + 1, (record.version or 1) + 1)
        record.committed_at = now
        record.updated_at = now
        self._session.commit()
        return record

    # ---- read -------------------------------------------------------------

    def get(self, schema_id: str) -> FormSchemaRecord:
        return self._require(schema_id)

    def list_by_tenant(self, tenant_id: str) -> list[FormSchemaRecord]:
        stmt = (
            select(FormSchemaRecord)
            .where(FormSchemaRecord.tenant_id == tenant_id)
            .order_by(FormSchemaRecord.created_at)
        )
        return list(self._session.execute(stmt).scalars())

    # ---- JSON Schema 投影 -------------------------------------------------

    @staticmethod
    def to_json_schema(record: FormSchemaRecord) -> dict[str, Any]:
        """payload → draft-07 JSON Schema（J1/J2 表单页消费契约）。

        - type=object
        - properties 按 field_type 映射（multiselect → array of string；checkbox → boolean）
        - required 按 field.required=True 聚合
        - regex/range/length/enum/file_size 等 validator 注入到对应 field
        """
        payload = record.payload_json or {}
        fields: list[dict[str, Any]] = payload.get("fields", [])
        validators: list[dict[str, Any]] = payload.get("validators", [])

        validators_by_field: dict[str, list[dict[str, Any]]] = {}
        for validator in validators:
            validators_by_field.setdefault(validator["applies_to_field_code"], []).append(validator)

        properties: dict[str, Any] = {}
        required: list[str] = []
        for field in fields:
            field_code = field["field_code"]
            field_type = field["field_type"]
            json_type = _FIELD_TYPE_TO_JSON_TYPE[field_type]
            prop: dict[str, Any] = {
                "type": json_type,
                "title": field.get("field_name", field_code),
            }
            json_format = _FIELD_TYPE_TO_JSON_FORMAT.get(field_type)
            if json_format:
                prop["format"] = json_format
            if field_type == "multiselect":
                prop["items"] = {"type": "string"}
            if field.get("required"):
                required.append(field_code)
            for validator in validators_by_field.get(field_code, []):
                _apply_validator_to_prop(prop, validator)
            properties[field_code] = prop

        schema: dict[str, Any] = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": record.title,
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema

    # ---- internal ---------------------------------------------------------

    def _require(self, schema_id: str) -> FormSchemaRecord:
        record = self._session.get(FormSchemaRecord, schema_id)
        if record is None:
            raise FormSchemaTransitionError(f"form schema not found: {schema_id}")
        if record.status not in _VALID_STATUSES:
            raise FormSchemaTransitionError(
                f"form schema has invalid status {record.status!r}"
            )
        return record

    def _project_payload(self, record: FormSchemaRecord, payload: dict[str, Any]) -> None:
        """payload_json 是单一事实源；同时投影到独立表方便 UI 编辑与 NL 草稿 (F5)。"""
        for index, section in enumerate(payload.get("sections", [])):
            self._session.add(
                FormSectionRecord(
                    form_schema_id=record.id,
                    section_code=section["section_code"],
                    title=section.get("title", section["section_code"]),
                    order_index=section.get("order_index", index),
                    collapsible=bool(section.get("collapsible", False)),
                )
            )
        for index, field in enumerate(payload.get("fields", [])):
            self._session.add(
                FormFieldRecord(
                    form_schema_id=record.id,
                    section_code=field["section_code"],
                    field_code=field["field_code"],
                    field_name=field.get("field_name", field["field_code"]),
                    field_type=field["field_type"],
                    order_index=field.get("order_index", index),
                    required=bool(field.get("required", False)),
                    placeholder=field.get("placeholder"),
                    default_value_json=field.get("default_value_json"),
                    layout_hints_json=field.get("layout_hints_json", {}),
                )
            )
        for validator in payload.get("validators", []):
            self._session.add(
                FormValidatorRecord(
                    form_schema_id=record.id,
                    validator_code=validator["validator_code"],
                    applies_to_field_code=validator["applies_to_field_code"],
                    validator_kind=validator["validator_kind"],
                    validator_payload_json=validator.get("validator_payload_json", {}),
                    error_message_template=validator.get("error_message_template"),
                )
            )


def _apply_validator_to_prop(prop: dict[str, Any], validator: dict[str, Any]) -> None:
    """单个 validator 投影到 JSON Schema 属性上。"""
    kind = validator["validator_kind"]
    payload = validator.get("validator_payload_json", {}) or {}
    if kind == "regex":
        pattern = payload.get("pattern")
        if pattern:
            prop["pattern"] = pattern
    elif kind == "range":
        if "minimum" in payload:
            prop["minimum"] = payload["minimum"]
        if "maximum" in payload:
            prop["maximum"] = payload["maximum"]
    elif kind == "length":
        if "minLength" in payload:
            prop["minLength"] = payload["minLength"]
        if "maxLength" in payload:
            prop["maxLength"] = payload["maxLength"]
    elif kind == "enum":
        values = payload.get("values")
        if isinstance(values, list):
            prop["enum"] = values
    elif kind == "file_size":
        if "maxBytes" in payload:
            prop["x-file-max-bytes"] = payload["maxBytes"]
    elif kind == "file_type":
        types = payload.get("acceptedTypes")
        if isinstance(types, list):
            prop["x-file-accepted-types"] = types
    elif kind == "custom_expression":
        expression = payload.get("expression")
        if expression:
            prop["x-custom-expression"] = expression
