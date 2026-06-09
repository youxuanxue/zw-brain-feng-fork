"""form_fill_service — J1 申请表单的字段装配 + 填充编排胶水（应用特定）。

field_derivation 是通用引擎；本模块把它绑到 J1 申请表单的具体字段集上：
  - 定义可编辑字段规格（FORM_FIELD_SPECS：key/label/kind/是否可 AI 建议）
  - create 时：用户在表单里填的=human，空字段经 orchestrate_fill 自动填
    （身份带出/确定性派生=derived，AI 建议=ai_suggested 待确认）
  - assemble_form_fields：把 values+provenance 投影成前端渲染用的字段行（带 source/locked/state）

诚实化：本层不捏造值；空且无源即 empty。AI 建议永不自动提交（人手动提交=担责，承方案口径）。
"""
from __future__ import annotations

from typing import Any

from zw_brain.domain.services.field_derivation import (
    FIELD_ENUM_DICT_TYPE,
    SOURCE_DERIVED,
    SOURCE_EMPTY,
    SOURCE_HUMAN,
    orchestrate_fill,
)

# 字段渲染类型：
#   text   = 自由文本输入
#   org    = 机构选择器（选中触发 organ_code→区划 带出）
#   region = 区划选择器
#   enum   = 字典枚举下拉（dict_type 指明 pub_dict.KIND）
#   derived= 只读（派生权威，不可编辑，体现「自动带出」）
FORM_FIELD_SPECS: tuple[dict[str, Any], ...] = (
    {"key": "organ_code", "label": "责任单位", "kind": "org", "ai_suggestable": False},
    {"key": "organ_name", "label": "责任单位名称", "kind": "derived", "ai_suggestable": False},
    {"key": "region_code", "label": "行政区划", "kind": "region", "ai_suggestable": False},
    {"key": "region_name", "label": "行政区划名称", "kind": "derived", "ai_suggestable": False},
    {"key": "applicant_org", "label": "申请单位", "kind": "derived", "ai_suggestable": False},
    {"key": "purpose", "label": "申请用途", "kind": "text", "ai_suggestable": True},
    {"key": "use_reason", "label": "使用理由", "kind": "text", "ai_suggestable": True},
    {"key": "apply_domain", "label": "申请领域", "kind": "enum", "ai_suggestable": False},
    {"key": "scope", "label": "使用范围", "kind": "text", "ai_suggestable": True},
    {"key": "delivery_expectation", "label": "交付期望", "kind": "text", "ai_suggestable": False},
)

FIELD_KEYS = tuple(spec["key"] for spec in FORM_FIELD_SPECS)
_FIELD_KEYS = FIELD_KEYS
_SPEC_BY_KEY = {spec["key"]: spec for spec in FORM_FIELD_SPECS}

# provenance.source → 前端徽标/状态文案。
_STATE_LABEL = {
    SOURCE_HUMAN: "已填写",
    SOURCE_DERIVED: "自动带出",
    "ai_suggested": "AI建议·待确认",
    SOURCE_EMPTY: "待填写",
}


def build_initial(
    user_values: dict[str, Any],
    *,
    actor_org: dict[str, Any] | None,
    ai_suggestions: dict[str, Any] | None,
    reference: Any,
    tenant_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """草稿创建：用户填的字段标 human，其余经编排自动填。返回 (values, provenance)。"""
    values: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    for key in _FIELD_KEYS:
        v = user_values.get(key)
        values[key] = v if v is not None else ""
        if v not in (None, ""):
            # 用户在表单里实填的字段：human（此后 autofill/AI 不覆盖）。
            provenance[key] = {"source": SOURCE_HUMAN, "locked": True, "modified_by": None, "modified_at": None}
    return orchestrate_fill(
        values,
        provenance,
        reference=reference,
        tenant_id=tenant_id,
        actor_org=actor_org,
        ai_suggestions=ai_suggestions,
    )


def assemble_form_fields(values: dict[str, Any], provenance: dict[str, Any]) -> list[dict[str, Any]]:
    """投影成前端渲染行：每行 {key,label,kind,value,source,locked,state,stateLabel}。"""
    rows: list[dict[str, Any]] = []
    for spec in FORM_FIELD_SPECS:
        key = spec["key"]
        prov = provenance.get(key) or {"source": SOURCE_EMPTY, "locked": False}
        source = prov.get("source", SOURCE_EMPTY)
        # 派生字段恒为只读（kind=derived 或 source=derived）。
        kind = spec["kind"]
        editable = kind != "derived" and source != SOURCE_DERIVED
        rows.append(
            {
                "key": key,
                "label": spec["label"],
                "kind": kind,
                "value": values.get(key, ""),
                "source": source,
                "locked": bool(prov.get("locked")),
                "state": prov.get("state") or source,
                "stateLabel": _STATE_LABEL.get(source, source),
                "editable": editable,
                "aiSuggestable": spec["ai_suggestable"],
                # 枚举字段的字典分组（pub_dict.KIND）单一事实源 = FIELD_ENUM_DICT_TYPE，
                # 前端据此调 reference.dict.options 取下拉选项。
                "dictType": FIELD_ENUM_DICT_TYPE.get(key) if kind == "enum" else None,
            }
        )
    return rows


def provenance_audit_snapshot(provenance: dict[str, Any]) -> dict[str, Any]:
    """提交时审计用：哪些字段是 AI 来源（人手动提交=担责，留可追溯痕迹）。"""
    ai_fields = [k for k, p in provenance.items() if p.get("source") == "ai_suggested"]
    human_fields = [k for k, p in provenance.items() if p.get("source") == SOURCE_HUMAN]
    derived_fields = [k for k, p in provenance.items() if p.get("source") == SOURCE_DERIVED]
    return {
        "ai_suggested_fields": sorted(ai_fields),
        "human_fields": sorted(human_fields),
        "derived_fields": sorted(derived_fields),
        "ai_unconfirmed_count": len(ai_fields),  # 提交时仍为 AI 态=未经人确认（不阻断，仅记录）
    }


def is_known_field(key: str) -> bool:
    return key in _SPEC_BY_KEY
