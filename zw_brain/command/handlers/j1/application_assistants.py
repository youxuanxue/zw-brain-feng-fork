"""J1 P3 申请双助手 — application.draft.suggest + approval.evidence.summarize.

F7 减摩组件（plan e1-j1-journey F7 + §5.4.4 反约束）:
- application.draft.suggest：申请草拟助手。基于资源 schema + 申请人上下文 + 历史相似
  申请，预填 purpose / use_item / use_reason / service_times 等字段 + 风险预估。
  绝不调用 application.resource.submit / application.create —— 仅输出建议。
- approval.evidence.summarize：审批依据助手。基于待审申请 + 历史同源审批，归纳依据
  + 反事实分析 + 推荐 decision，但绝不调用 approval.decide / request.approve / reject。

两 cap 均走 zw_brain.shared.inference.client.chat（D6 硬约束），三层降级：
推理失败 / JSON 解析失败 / enabled=false 三种情况都回落本地规则。
"""

from __future__ import annotations

import json as _json
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

# ──────────────────────────────────────────────────────────────────────
# Common helpers
# ──────────────────────────────────────────────────────────────────────


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        parsed = _json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


# ──────────────────────────────────────────────────────────────────────
# application.draft.suggest
# ──────────────────────────────────────────────────────────────────────

_RISK_HIGH_TRIGGERS = ("敏感", "公安", "个人信息", "身份证", "手机号", "户籍")
_USE_REASONS = ("行政依据", "审批办理", "信用核查", "其他")


def _draft_fallback(resource_name: str, applicant_org: str, use_case: str) -> dict[str, Any]:
    """fallback 规则草拟：基于 keyword 命中 + 默认值."""
    high_risk_hits = [t for t in _RISK_HIGH_TRIGGERS if t in resource_name or t in (use_case or "")]
    risk_score = 80 if high_risk_hits else 40
    risk_factors = [
        f"资源/用途含敏感关键词：{', '.join(high_risk_hits)}"
        if high_risk_hits else "未识别到敏感关键词；默认低风险评估"
    ]
    suggested = {
        "purpose": (use_case or f"{applicant_org} 业务办理需要").strip(),
        "use_reason": "行政依据",
        "use_item": "1",
        "service_times": 1000,
        "service_times_unit": "次/日",
        "use_region": "山东省",
    }
    missing: list[str] = []
    if not use_case:
        missing.append("具体使用场景（如行政审批 / 信用核查 / 内部统计）")
    missing.append("数据返回字段子集（最小可用原则）")
    if high_risk_hits:
        missing.append("加密传输方案与脱敏策略")
    return {
        "suggested_fields": suggested,
        "risk_score": risk_score,
        "risk_band": "high" if risk_score >= 70 else "medium" if risk_score >= 40 else "low",
        "risk_factors": risk_factors,
        "missing_fields": missing,
        "recommended_use_reasons": list(_USE_REASONS),
        "reasoning": (
            f"基于资源「{resource_name}」与申请方「{applicant_org}」推断业务场景；"
            f"实际提交前请补充具体用途与字段子集。"
        ),
        "source": "fallback_rule",
    }


def _draft_inference(
    resource_name: str, applicant_org: str, use_case: str, *, historical_examples: list[dict], request_id: str
) -> dict[str, Any] | None:
    examples_snippet = _json.dumps(historical_examples[:3], ensure_ascii=False)
    prompt = (
        "你是政务数据共享平台 P3 申请草拟助手。基于资源名称、申请方、使用场景与历史相似申请，"
        "输出严格 JSON：{\"suggested_fields\":{\"purpose\":\"\",\"use_reason\":\"\","
        "\"use_item\":\"\",\"service_times\":0,\"service_times_unit\":\"\",\"use_region\":\"\"},"
        "\"risk_score\":0,\"risk_band\":\"low|medium|high\",\"risk_factors\":[],\"missing_fields\":[],"
        "\"recommended_use_reasons\":[],\"reasoning\":\"\"}。仅给建议不替人提交。"
    )
    user = (
        f"资源：{resource_name}\n申请方：{applicant_org}\n使用场景：{use_case or '未填'}\n"
        f"历史相似申请样例：{examples_snippet}"
    )
    result = _inference_chat(
        [ChatMessage(role="system", content=prompt), ChatMessage(role="user", content=user)],
        model="", request_id=request_id, temperature=0.0,
    )
    parsed = _try_parse_json(result.text)
    if parsed is None:
        return None
    suggested = parsed.get("suggested_fields") or {}
    if not isinstance(suggested, dict):
        suggested = {}
    risk_score = parsed.get("risk_score")
    if not isinstance(risk_score, (int, float)):
        risk_score = 0
    return {
        "suggested_fields": {k: suggested.get(k) for k in (
            "purpose", "use_reason", "use_item", "service_times",
            "service_times_unit", "use_region",
        )},
        "risk_score": int(risk_score),
        "risk_band": str(parsed.get("risk_band") or "medium"),
        "risk_factors": [str(x) for x in (parsed.get("risk_factors") or []) if x][:6],
        "missing_fields": [str(x) for x in (parsed.get("missing_fields") or []) if x][:6],
        "recommended_use_reasons": [str(x) for x in (parsed.get("recommended_use_reasons") or []) if x][:6],
        "reasoning": str(parsed.get("reasoning") or ""),
        "source": "inference",
    }


def _load_historical_examples(brain, deps, ctx, resource_name: str, limit: int = 5) -> list[dict[str, Any]]:
    """从真实 application_record 找历史相似申请（同 resource_name），脱敏后返回."""
    examples: list[dict[str, Any]] = []
    if deps.state_store.database_store is None:
        return examples
    try:
        from zw_brain.domain.repositories.application import ApplicationRepository
        repo = ApplicationRepository()
        records = repo.list_records(tenant_id="sd-default")
    except Exception:
        return examples
    for r in records:
        payload = r.payload_json if isinstance(r.payload_json, dict) else {}
        if payload.get("kind") != "apply":
            continue
        if resource_name and resource_name not in str(payload.get("resource_name") or ""):
            continue
        examples.append({
            "purpose": str(payload.get("purpose") or payload.get("use_reason") or "")[:60],
            "use_reason": str(payload.get("use_reason") or "")[:40],
            "use_item": str(payload.get("use_item") or "")[:20],
            "service_times": payload.get("service_times"),
            "status": r.status,
        })
        if len(examples) >= limit:
            break
    return examples


def _do_draft_suggest(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    resource_name = str(payload.get("resource_name") or "").strip()
    applicant_org = str(payload.get("applicant_org") or "").strip()
    use_case = str(payload.get("use_case") or "").strip()
    enabled = bool(payload.get("enabled", True))
    request_id = str(payload.get("request_id") or f"app-draft-{abs(hash(resource_name + applicant_org)) & 0xFFFFFFFF:08x}")
    actor = ctx.actor or "system"
    audit_target = f"{resource_name[:40]}|{applicant_org[:20]}"

    if not enabled:
        result = _draft_fallback(resource_name, applicant_org, use_case)
        deps.append_audit_feed("application.draft.suggest", audit_target, "ok", actor)
        result["enabled"] = False
        return result

    examples = _load_historical_examples(brain, deps, ctx, resource_name)
    inf: dict[str, Any] | None = None
    try:
        inf = _draft_inference(resource_name, applicant_org, use_case, historical_examples=examples, request_id=request_id)
    except InferenceError:
        inf = None
    if inf is not None:
        deps.append_audit_feed("application.draft.suggest", audit_target, "ok", actor)
        inf["enabled"] = True
        inf["historical_examples_count"] = len(examples)
        return inf

    fallback = _draft_fallback(resource_name, applicant_org, use_case)
    deps.append_audit_feed("application.draft.suggest", audit_target, "warning", actor)
    fallback["enabled"] = True
    fallback["degraded"] = True
    fallback["historical_examples_count"] = len(examples)
    return fallback


def handler_application_draft_suggest(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _do_draft_suggest(brain, deps, ctx, payload)


# ──────────────────────────────────────────────────────────────────────
# approval.evidence.summarize
# ──────────────────────────────────────────────────────────────────────

_APPROVE_HINT_REASONS = ("行政依据", "审批办理", "信用核查")
_RECOMMEND_VALUES = ("approve", "return_for_fix", "reject")


def _evidence_fallback(application: dict[str, Any], historical: list[dict[str, Any]]) -> dict[str, Any]:
    use_reason = str(application.get("use_reason") or "")
    resource_name = str(application.get("resource_name") or "")
    purpose = str(application.get("purpose") or "")
    high_risk = any(t in resource_name for t in _RISK_HIGH_TRIGGERS)
    has_evidence = use_reason in _APPROVE_HINT_REASONS and bool(purpose)
    recommendation = "approve" if has_evidence and not high_risk else (
        "return_for_fix" if not purpose else "reject"
    )
    bases = []
    if use_reason in _APPROVE_HINT_REASONS:
        bases.append(f"use_reason='{use_reason}' 属预设合规口径")
    if purpose:
        bases.append("purpose 字段已填，业务场景可追溯")
    if not bases:
        bases.append("依据字段缺失：建议申请人补充用途说明")

    counter = []
    if high_risk:
        counter.append(f"资源「{resource_name}」含敏感信息，应启用加密传输 + 脱敏字段")
    if not application.get("service_times"):
        counter.append("未声明调用频次，建议补 service_times 字段")
    if not counter:
        counter.append("未识别明显反事实因素；维持现有结论")

    history_summary = (
        f"历史 {len(historical)} 条同源申请，{sum(1 for h in historical if h.get('status') == 'approved')} 条 approved"
        if historical else "无历史同源申请样本"
    )
    return {
        "bases": bases,
        "counter_factuals": counter,
        "recommendation": recommendation,
        "recommended_decision_reason": (
            f"基于 use_reason='{use_reason}' + purpose 完整度 + 资源敏感度评估，建议 {recommendation}。"
        ),
        "historical_summary": history_summary,
        "source": "fallback_rule",
    }


def _evidence_inference(
    application: dict[str, Any], historical: list[dict[str, Any]], *, request_id: str
) -> dict[str, Any] | None:
    prompt = (
        "你是政务数据共享平台 P3 审批依据助手。基于待审申请字段与历史同源申请，输出严格 JSON："
        "{\"bases\":[],\"counter_factuals\":[],\"recommendation\":\"approve|return_for_fix|reject\","
        "\"recommended_decision_reason\":\"\",\"historical_summary\":\"\"}。"
        "仅给归纳与建议，绝不替人点决策。"
    )
    user = (
        f"待审申请：{_json.dumps(application, ensure_ascii=False)}\n"
        f"历史同源 (最多 5 条)：{_json.dumps(historical[:5], ensure_ascii=False)}"
    )
    result = _inference_chat(
        [ChatMessage(role="system", content=prompt), ChatMessage(role="user", content=user)],
        model="", request_id=request_id, temperature=0.0,
    )
    parsed = _try_parse_json(result.text)
    if parsed is None:
        return None
    recommendation = str(parsed.get("recommendation") or "")
    if recommendation not in _RECOMMEND_VALUES:
        recommendation = "return_for_fix"
    return {
        "bases": [str(x) for x in (parsed.get("bases") or []) if x][:6],
        "counter_factuals": [str(x) for x in (parsed.get("counter_factuals") or []) if x][:6],
        "recommendation": recommendation,
        "recommended_decision_reason": str(parsed.get("recommended_decision_reason") or ""),
        "historical_summary": str(parsed.get("historical_summary") or ""),
        "source": "inference",
    }


def _load_application(brain, deps, ctx, application_id: str) -> dict[str, Any] | None:
    from zw_brain.domain.repositories.application import ApplicationRepository
    repo = ApplicationRepository()
    record = repo.get_record(application_id, tenant_id="sd-default")
    if record is None:
        return None
    payload = record.payload_json if isinstance(record.payload_json, dict) else {}
    return {
        "application_code": record.application_code,
        "status": record.status,
        "resource_name": payload.get("resource_name") or payload.get("resourceName"),
        "purpose": payload.get("purpose") or payload.get("use_reason"),
        "use_reason": payload.get("use_reason"),
        "use_item": payload.get("use_item"),
        "service_times": payload.get("service_times"),
        "applicant_org_name": payload.get("applicant_org_name"),
    }


def _load_historical_for_review(brain, deps, ctx, resource_name: str, exclude_id: str, limit: int = 5) -> list[dict[str, Any]]:
    from zw_brain.domain.repositories.application import ApplicationRepository
    repo = ApplicationRepository()
    out: list[dict[str, Any]] = []
    for r in repo.list_records(tenant_id="sd-default"):
        if r.application_code == exclude_id:
            continue
        payload = r.payload_json if isinstance(r.payload_json, dict) else {}
        if payload.get("kind") != "apply":
            continue
        if resource_name and resource_name not in str(payload.get("resource_name") or ""):
            continue
        out.append({
            "application_code": r.application_code,
            "status": r.status,
            "use_reason": payload.get("use_reason"),
            "purpose": str(payload.get("purpose") or "")[:60],
        })
        if len(out) >= limit:
            break
    return out


def _do_evidence_summarize(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    application_id = str(payload.get("application_id") or "").strip()
    if not application_id:
        raise ValueError("application_id is required")
    enabled = bool(payload.get("enabled", True))
    request_id = str(payload.get("request_id") or f"app-evidence-{abs(hash(application_id)) & 0xFFFFFFFF:08x}")
    actor = ctx.actor or "system"

    application = _load_application(brain, deps, ctx, application_id)
    if application is None:
        return {
            "application_id": application_id,
            "status": "not_found",
            "hint": "申请单不存在或不属于 sd-default tenant",
            "source": "fallback_rule",
            "enabled": enabled,
        }
    historical = _load_historical_for_review(brain, deps, ctx, str(application.get("resource_name") or ""), exclude_id=application_id)

    if not enabled:
        result = _evidence_fallback(application, historical)
        deps.append_audit_feed("approval.evidence.summarize", application_id, "ok", actor)
        result["application_id"] = application_id
        result["application_status"] = application["status"]
        result["enabled"] = False
        return result

    inf: dict[str, Any] | None = None
    try:
        inf = _evidence_inference(application, historical, request_id=request_id)
    except InferenceError:
        inf = None
    if inf is not None:
        deps.append_audit_feed("approval.evidence.summarize", application_id, "ok", actor)
        inf["application_id"] = application_id
        inf["application_status"] = application["status"]
        inf["enabled"] = True
        return inf

    fallback = _evidence_fallback(application, historical)
    deps.append_audit_feed("approval.evidence.summarize", application_id, "warning", actor)
    fallback["application_id"] = application_id
    fallback["application_status"] = application["status"]
    fallback["enabled"] = True
    fallback["degraded"] = True
    return fallback


def handler_approval_evidence_summarize(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _do_evidence_summarize(brain, deps, ctx, payload)
