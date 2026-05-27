"""J1 P4 状态解释助手 — delivery.status.explain (F8 减摩组件).

§5.4.4 反约束：
- 仅解释当前阶段 / 异常原因 / 影响范围 / 责任归属，不替代 P4 时间线组件 / 回执界面
- 不返回 events 列表 / 不评价进度 / 不打分 / 不调任何写 cap
- audit_class=read；audit_required=true
- 推理走 shared/inference/client；三层降级 (推理失败 / JSON 解析失败 / enabled=false)
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

# 真实 sd-default delivery_task.state 分布：draft / pending / granted / stopped
_PHASE_DESCRIPTIONS: dict[str, str] = {
    "draft": "交付任务草稿阶段，资源准备中尚未开始处理。",
    "pending": "已生成交付任务，等待提供方部门完成数据准备或授权决策。",
    "granted": "已授权使用方访问资源；凭据通常已签发。",
    "stopped": "交付任务已停止，可能因申请人撤回、提供方下线资源或合规干预。",
    "revoked": "凭据/授权已撤销；该交付任务后续调用将被网关拒绝。",
    "completed": "交付任务已完成；如为单次任务即终态。",
}

_PHASE_LABELS: dict[str, str] = {
    "draft": "草稿",
    "pending": "待处理",
    "granted": "已授权",
    "stopped": "已停止",
    "revoked": "已撤销",
    "completed": "已完成",
}

_RESPONSIBLE_ROLE_BY_PHASE: dict[str, str] = {
    "draft": "申请方部门操作员（补齐草稿）",
    "pending": "提供方部门管理员（数据准备 / 授权决策）",
    "granted": "申请方部门操作员（按配额使用凭据）",
    "stopped": "需联系提供方或合规审计员确认停止原因",
    "revoked": "申请方部门操作员（重新提交申请或申诉）",
    "completed": "无（终态）",
}


def _do_explain_fallback(task: dict[str, Any]) -> dict[str, Any]:
    state = str(task.get("state") or "")
    phase_label = _PHASE_LABELS.get(state, state or "未知")
    description = _PHASE_DESCRIPTIONS.get(state, "状态未在已知阶段列表中，建议人工核查。")
    responsible = _RESPONSIBLE_ROLE_BY_PHASE.get(state, "未识别责任方")

    exception_reasons: list[str] = []
    if state == "pending":
        exception_reasons.append("如长期处于 pending，建议提供方核查数据准备进度或授权决策卡点。")
    elif state == "stopped":
        exception_reasons.append("stopped 通常由申请方撤回 / 提供方下线 / 合规干预触发；需结合 audit_event 定位。")
    elif state == "revoked":
        exception_reasons.append("revoked 多由配额超限、合规事件或申请方主动收回凭据触发。")
    elif state == "draft":
        exception_reasons.append("草稿阶段不应长期停留；超 7 天未提交建议补齐或撤销。")
    if not exception_reasons:
        exception_reasons.append("当前阶段无典型异常模式。")

    impact_scope: list[str] = []
    if state in ("stopped", "revoked"):
        impact_scope.append("该交付任务对应的凭据将不再可用；下游调用方需切换路径或申诉。")
    elif state == "pending":
        impact_scope.append("申请方暂无法启动调用；下游业务流程可能延期。")
    elif state == "granted":
        impact_scope.append("调用受配额与有效期限制；超额或过期将自动转 revoked。")
    if not impact_scope:
        impact_scope.append("无显著下游影响。")

    evidence_sources = [
        f"delivery_task.state={state}",
        f"delivery_task.channel={task.get('channel')}",
    ]
    if task.get("resource_name"):
        evidence_sources.append(f"delivery_task.payload.resource_name={task['resource_name']}")
    if task.get("application_code"):
        evidence_sources.append(f"delivery_task.application_code={task['application_code']}")

    return {
        "delivery_code": task.get("delivery_code"),
        "application_code": task.get("application_code"),
        "phase": state,
        "phase_label": phase_label,
        "phase_description": description,
        "exception_reasons": exception_reasons,
        "impact_scope": impact_scope,
        "responsible_role": responsible,
        "evidence_sources": evidence_sources,
        "source": "fallback_rule",
    }


def _do_explain_inference(task: dict[str, Any], *, request_id: str) -> dict[str, Any] | None:
    prompt = (
        "你是政务数据共享平台 P4 交付任务状态解释助手。基于交付任务字段，输出严格 JSON："
        "{\"phase\":\"\",\"phase_label\":\"\",\"phase_description\":\"\","
        "\"exception_reasons\":[],\"impact_scope\":[],\"responsible_role\":\"\","
        "\"evidence_sources\":[]}。"
        "仅解释，不评价进度，不返时间线，不调写接口。证据必须基于输入字段。"
    )
    user = f"交付任务字段：{_json.dumps(task, ensure_ascii=False)}"
    result = _inference_chat(
        [ChatMessage(role="system", content=prompt), ChatMessage(role="user", content=user)],
        model="", request_id=request_id, temperature=0.0,
    )
    raw = (result.text or "").strip()
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
    return {
        "delivery_code": task.get("delivery_code"),
        "application_code": task.get("application_code"),
        "phase": str(parsed.get("phase") or task.get("state") or ""),
        "phase_label": str(parsed.get("phase_label") or _PHASE_LABELS.get(str(task.get("state") or ""), "")),
        "phase_description": str(parsed.get("phase_description") or ""),
        "exception_reasons": [str(x) for x in (parsed.get("exception_reasons") or []) if x][:6],
        "impact_scope": [str(x) for x in (parsed.get("impact_scope") or []) if x][:6],
        "responsible_role": str(parsed.get("responsible_role") or ""),
        "evidence_sources": [str(x) for x in (parsed.get("evidence_sources") or []) if x][:6],
        "source": "inference",
    }


def _load_delivery_task(brain, deps, ctx, *, delivery_code: str | None, application_code: str | None) -> dict[str, Any] | None:
    """从 DeliveryRepository 取真实 sd-default 交付任务."""
    from sqlalchemy import select

    from zw_brain.domain.models import DeliveryTaskRecord
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        stmt = select(DeliveryTaskRecord).where(DeliveryTaskRecord.tenant_id == "sd-default")
        if delivery_code:
            stmt = stmt.where(DeliveryTaskRecord.delivery_code == delivery_code)
        elif application_code:
            stmt = stmt.where(DeliveryTaskRecord.application_code == application_code)
        else:
            return None
        # 同 application_code 可能对应多个 delivery_task；按 created_at 倒序取最新一条
        # （稳定 UX：解释「当前」状态必须指向最新交付）
        stmt = stmt.order_by(DeliveryTaskRecord.created_at.desc()).limit(1)
        record = session.execute(stmt).scalars().first()
    if record is None:
        return None
    payload = record.payload_json if isinstance(record.payload_json, dict) else {}
    return {
        "delivery_code": record.delivery_code,
        "application_code": record.application_code,
        "state": record.state,
        "channel": record.channel,
        "resource_id": payload.get("resource_id"),
        "resource_name": payload.get("resource_name"),
        "kind": payload.get("kind"),
    }


def _do_explain(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    delivery_code = (payload.get("delivery_code") or "").strip() or None
    application_code = (payload.get("application_code") or "").strip() or None
    if not delivery_code and not application_code:
        raise ValueError("delivery_code or application_code is required")
    enabled = bool(payload.get("enabled", True))
    request_id = str(payload.get("request_id") or f"delivery-explain-{abs(hash(delivery_code or application_code)) & 0xFFFFFFFF:08x}")
    actor = ctx.actor or "system"

    task = _load_delivery_task(brain, deps, ctx, delivery_code=delivery_code, application_code=application_code)
    if task is None:
        return {
            "delivery_code": delivery_code,
            "application_code": application_code,
            "status": "not_found",
            "hint": "交付任务不存在或不属于 sd-default tenant",
            "source": "fallback_rule",
            "enabled": enabled,
        }

    if not enabled:
        result = _do_explain_fallback(task)
        deps.append_audit_feed("delivery.status.explain", task["delivery_code"] or "", "ok", actor)
        result["enabled"] = False
        return result

    inf: dict[str, Any] | None = None
    try:
        inf = _do_explain_inference(task, request_id=request_id)
    except InferenceError:
        inf = None
    if inf is not None:
        deps.append_audit_feed("delivery.status.explain", task["delivery_code"] or "", "ok", actor)
        inf["enabled"] = True
        return inf

    fallback = _do_explain_fallback(task)
    deps.append_audit_feed("delivery.status.explain", task["delivery_code"] or "", "warning", actor)
    fallback["enabled"] = True
    fallback["degraded"] = True
    return fallback


def handler_delivery_status_explain(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _do_explain(brain, deps, ctx, payload)
