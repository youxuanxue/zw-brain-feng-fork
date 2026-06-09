"""field_derivation — 表单字段确定性派生引擎（声明式规则，前向兼容 D26 表单引擎）。

治理口径（form-autofill-provenance 方案，业务方拍板）：
  - **派生层是权威、只读、不可被人锁死**：源（trigger）字段一变，派生（target）字段
    就重算，**不受「保持人锁值」约束**——事实/逻辑的确定性优先于人工值。
  - 派生 ≠ AI 建议：派生只写它声明的 target 字段，标 source="derived"；AI 建议/人填
    走另一条编排路径（Phase 3）。
  - 空 trigger：清理「曾被派生」的 target（回 empty），但**绝不动 human/ai_suggested**
    字段（保护人手动直选的值，如不经机构直接选区划）。

本期为最小声明式规则表（非 DB 驱动通用规则引擎，不做条件求值器——属 D26 延后）。
规则按依赖顺序声明，引擎做有界定点迭代以支持级联（机构→区划码→区划名）。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import zw_brain.shared.clock as _clock

# ---- 字段来源（provenance.source）枚举 ----
SOURCE_HUMAN = "human"
SOURCE_DERIVED = "derived"
SOURCE_AI = "ai_suggested"
SOURCE_EMPTY = "empty"

_MAX_PASSES = 5  # 级联定点迭代上限（机构→区划码→区划名 仅需 2 趟，留余量）


@dataclass(frozen=True)
class DerivationRule:
    """一条确定性派生规则：trigger 一变 → 重算 targets。

    resolve(trigger_value, reference, tenant_id) → {target_field: value} | None。
    返回 None 视同「无法带出」→ 引擎把 targets 清空（诚实，不留陈旧/不捏造）。
    """

    trigger: str
    targets: tuple[str, ...]
    resolve: Callable[[str, Any, str], dict[str, Any] | None]


def _resolve_organ(value: str, reference: Any, tenant_id: str) -> dict[str, Any] | None:
    organ = reference.organ(value, tenant_id=tenant_id)
    if not organ:
        return None
    return {
        "organ_name": organ.get("org_name") or "",
        "region_code": organ.get("region_code") or "",
        "region_name": organ.get("region_name") or "",
    }


def _resolve_region(value: str, reference: Any, tenant_id: str) -> dict[str, Any] | None:
    region = reference.region(value, tenant_id=tenant_id)
    if not region:
        return None
    return {"region_name": region.get("region_name") or ""}


# 依赖顺序：organ 先（产出 region_code），region 后（消费 region_code 产出 region_name）。
DERIVATION_RULES: tuple[DerivationRule, ...] = (
    DerivationRule(trigger="organ_code", targets=("organ_name", "region_code", "region_name"), resolve=_resolve_organ),
    DerivationRule(trigger="region_code", targets=("region_name",), resolve=_resolve_region),
)

# 枚举字段 → 字典分组（pub_dict.KIND）。供前端选择器取 options（reference.dict_options）。
# 仅声明已确认有真字典源的字段；未列字段不强凑 options。
FIELD_ENUM_DICT_TYPE: dict[str, str] = {
    "sensitive_level": "data_sensity_level",
    "data_level": "data_level",
    "supply_way": "catalog_data_supply_way",
    # 申请领域取 data_apply_field（健康保障/行政依据/工作参考/业务协同… 13 项），
    # 比 data_apply_domain（仅 2 项）覆盖全、更贴合「申请用于哪个领域」。
    "apply_domain": "data_apply_field",
    "organ_line": "organLine",
}


def _provenance_for_derived(trigger: str) -> dict[str, Any]:
    return {"source": SOURCE_DERIVED, "locked": False, "modified_by": None, "modified_at": None, "derived_from": trigger}


def _provenance_empty() -> dict[str, Any]:
    return {"source": SOURCE_EMPTY, "locked": False, "modified_by": None, "modified_at": None}


# AI 建议层只填这些自由文本字段（application.draft.suggest 产出域）；派生字段不在此列。
AI_SUGGESTABLE_FIELDS: frozenset[str] = frozenset(
    {"purpose", "use_reason", "use_item", "service_times", "service_times_unit", "use_region", "scope"}
)

# AI 建议态的 provenance.state（前端据此渲染「AI建议·待确认」异色 + 提交担责）。
STATE_AI_PENDING = "ai_pending_confirm"


def _provenance_for_human(actor: str) -> dict[str, Any]:
    return {"source": SOURCE_HUMAN, "locked": True, "modified_by": actor or None, "modified_at": _clock.now_datetime()}


def _provenance_for_ai() -> dict[str, Any]:
    return {"source": SOURCE_AI, "locked": False, "modified_by": None, "modified_at": None, "state": STATE_AI_PENDING}


def orchestrate_fill(
    values: dict[str, Any],
    provenance: dict[str, Any] | None = None,
    *,
    reference: Any,
    tenant_id: str,
    actor_org: dict[str, Any] | None = None,
    ai_suggestions: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """草稿创建时的填充编排：身份带出 + 确定性派生 + AI 建议（只填空、不覆盖人填）。

    顺序与优先级（高→低）：human(locked) > derived(权威) > ai_suggested > empty。
      1. 身份带出（derived）：actor_org → applicant_org/applicant_dept（登录身份确定性带出）。
      2. 确定性派生（derived）：field_derivation.derive（机构→区划 等，权威覆盖）。
      3. AI 建议（ai_suggested）：仅对 AI_SUGGESTABLE_FIELDS 中**当前为空且非 human/derived** 的字段
         填建议值，标「待确认」；永不覆盖人填/派生（人手动提交=担责，承方案口径）。
      4. 其余空字段标 empty。
    """
    values = dict(values)
    provenance = {k: dict(v) for k, v in (provenance or {}).items()}

    # 1. 身份带出（derived）：把登录身份的组织确定性写入申请方字段。
    if actor_org:
        for field, key in (("applicant_org", "org_name"), ("applicant_dept", "org_name"), ("applicant_org_code", "org_code")):
            val = actor_org.get(key)
            if val and provenance.get(field, {}).get("source") != SOURCE_HUMAN:
                values[field] = val
                provenance[field] = {**_provenance_for_derived("actor.identity"), "derived_from": "actor.identity"}

    # 2. 确定性派生（权威）。
    values, provenance = derive(values, provenance, reference=reference, tenant_id=tenant_id)

    # 3. AI 建议：只填空，不碰 human/derived/locked。
    for field, suggestion in (ai_suggestions or {}).items():
        if field not in AI_SUGGESTABLE_FIELDS:
            continue
        cur = provenance.get(field, {})
        if cur.get("locked") or cur.get("source") in (SOURCE_HUMAN, SOURCE_DERIVED):
            continue
        if values.get(field) in (None, "") and suggestion not in (None, ""):
            values[field] = suggestion
            provenance[field] = _provenance_for_ai()

    # 4. 其余空字段标 empty（无 provenance 的）。
    for field in list(values.keys()):
        if field not in provenance:
            provenance[field] = _provenance_empty() if values.get(field) in (None, "") else {"source": SOURCE_HUMAN, "locked": False, "modified_by": None, "modified_at": None}

    return values, provenance


def apply_human_edit(
    values: dict[str, Any],
    provenance: dict[str, Any] | None,
    field: str,
    new_value: Any,
    *,
    actor: str,
    reference: Any,
    tenant_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """人原地修订一个字段 → 标 human+locked（此后 autofill/AI 不再覆盖），随后重跑派生。

    注：派生字段（derived target）由派生权威拥有、不可被人锁死——若人试图改派生字段，
    重跑派生会按 trigger 还原（承方案口径，前端应把派生字段渲染为只读）。
    非派生字段（如 purpose）人改后锁定，重跑派生不动它。
    """
    values = dict(values)
    provenance = {k: dict(v) for k, v in (provenance or {}).items()}
    values[field] = new_value
    provenance[field] = _provenance_for_human(actor)
    # 重跑派生：trigger 变了就重算 dependents；human 锁定的非派生字段不受影响。
    return derive(values, provenance, reference=reference, tenant_id=tenant_id)


def derive(
    values: dict[str, Any],
    provenance: dict[str, Any] | None = None,
    *,
    reference: Any,
    tenant_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """对 values 应用所有派生规则，返回 (新 values, 新 provenance)。

    - trigger 非空 → 重算 targets，写 source=derived（**覆盖一切，含 human/locked**，派生权威）。
    - trigger 为空 → 仅清理「当前 source==derived」的 targets（保护 human/ai 直选值）。
    - 输入不被原地修改（返回浅拷贝）。
    """
    values = dict(values)
    provenance = {k: dict(v) for k, v in (provenance or {}).items()}

    for _ in range(_MAX_PASSES):
        changed = False
        for rule in DERIVATION_RULES:
            trig = values.get(rule.trigger)
            if trig not in (None, ""):
                result = rule.resolve(str(trig), reference, tenant_id) or {}
                for tgt in rule.targets:
                    new_val = result.get(tgt, "")
                    if values.get(tgt) != new_val or provenance.get(tgt, {}).get("source") != SOURCE_DERIVED:
                        values[tgt] = new_val
                        provenance[tgt] = _provenance_for_derived(rule.trigger)
                        changed = True
            else:
                # 空 trigger：回收曾派生的 target；human/ai/empty 一律不动。
                for tgt in rule.targets:
                    if provenance.get(tgt, {}).get("source") == SOURCE_DERIVED:
                        values[tgt] = ""
                        provenance[tgt] = _provenance_empty()
                        changed = True
        if not changed:
            break

    return values, provenance
