"""B1 investigation assistant handler — assistant.investigation_summary (F3-backend).

把 B1.1 statistics / anomaly / accountability panel 输出脱敏后生成调查摘要。
约束（架构 D68 + D14）：

- zw-brain 主进程不持有推理平台 SDK / env；复杂模型能力由独立 AgentRuntime 服务承载。
- panel_payload 在摘要前做强脱敏：actor / skill_id / tenant_id 等定向字段 hash 化；
  其他字段保留聚合特征但不外泄业务原文。
- 输出 summary 不包含原始 actor/skill_id 字面值；handler 自身写一条 read-sensitive
  meta-audit（与 audit.event.* 同 pattern）。
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import zw_brain.shared.audit as audit_bus
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.handlers.b1._meta import enforce_tenant_scope

_SENSITIVE_KEYS = (
    "actor",
    "actor_snapshot",
    "skill_id",
    "tenant_id",
    "credential",
    "secret",
    "token",
    "password",
    "api_key",
    "request_id",
    "legacy_role_ref",
    "target_role_code",
)

def _sanitize_value(value: Any) -> Any:
    """递归脱敏：dict 内匹配 _SENSITIVE_KEYS 的字段统一 hash 化；list 递归。"""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            low = str(k).lower()
            if any(needle in low for needle in _SENSITIVE_KEYS):
                digest = hashlib.sha1(
                    json.dumps(v, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()[:16]
                out[k] = f"sha1:{digest}"
            else:
                out[k] = _sanitize_value(v)
        return out
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        # 防御性：碰到形如 user:gov:ROLE_*:名字 / 长 request_id / skill 命名空间字符串也脱敏
        if value.startswith("user:") or value.startswith("REQ-") or value.startswith("AUDIT-META-"):
            return "sha1:" + hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
        return value
    return value


def _emit_meta_audit(
    *,
    skill_id: str,
    payload: dict[str, Any],
    tenant_id: str,
    param_hash: str,
    summary_length: int,
) -> None:
    role = str(payload.get("role") or "ROLE_SECURITY_AUDIT")
    actor = f"user:gov:{role}:investigation-meta"
    request_id = str(payload.get("request_id") or "AUDIT-META-INV")
    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id=request_id,
            actor=actor,
            skill_id=skill_id,
            phase="commit",
            payload={
                "param_hash": param_hash,
                "summary_length": int(summary_length),
                "skill_id": skill_id,
                "panel": str(payload.get("panel") or ""),
            },
            tenant_id=tenant_id,
            audit_class="read-sensitive",
            event_type="audit_assist",
        )
    )


def _fallback_investigation_summary(panel: str, sanitized: dict[str, Any], digest: str) -> dict[str, Any]:
    """规则摘要：推理平台不可用时仍给出可演示的调查结论（不调用第三方 LLM）。"""
    if panel == "statistics":
        scanned = int(sanitized.get("scanned") or 0)
        totals = sanitized.get("totals") or {}
        top = ", ".join(f"{k} {v}" for k, v in list(totals.items())[:3]) if totals else "暂无分布"
        text = (
            f"统计视图共扫描 {scanned} 条审计事件；累计分布：{top}。"
            "建议关注 write-critical 占比是否异常升高，并抽样核对高频 skill。"
        )
    elif panel == "anomaly":
        anomalies = sanitized.get("anomalies") or []
        n = len(anomalies) if isinstance(anomalies, list) else 0
        text = (
            f"异常视图命中 {n} 项规则告警。"
            "优先处理 high-severity 且重复出现的 actor/skill 组合，并关联 request 回放原始证据。"
        )
    else:
        total = int(sanitized.get("total") or 0)
        text = (
            f"追责视图共 {total} 条拒绝链路。"
            "建议从 denied 次数最高的 request 入手，核对策略匹配与岗位授权是否一致。"
        )
    return {
        "summary": text,
        "model": "rule-fallback",
        "sanitized_input_digest": digest,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def handler_assistant_investigation_summary(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    """F3 assistant.investigation_summary —— 脱敏 panel + 本地摘要 + meta-audit。

    成功路径：返回 {summary, model, sanitized_input_digest, usage}。
    """
    tenant_id = enforce_tenant_scope(payload, capability="assistant.investigation_summary")
    panel = str(payload["panel"]).strip()
    if panel not in {"statistics", "anomaly", "accountability"}:
        raise ValueError(f"unknown panel kind: {panel!r}")
    panel_payload = payload.get("panel_payload") or {}
    if not isinstance(panel_payload, dict):
        raise ValueError("panel_payload must be a dict")
    request_id = str(payload["request_id"]).strip()
    if not request_id:
        raise ValueError("assistant.investigation_summary requires non-empty request_id")

    sanitized = _sanitize_value(panel_payload)
    sanitized_text = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, default=str)
    sanitized_digest = hashlib.sha1(sanitized_text.encode("utf-8")).hexdigest()

    fallback = _fallback_investigation_summary(panel, sanitized, sanitized_digest)
    summary_text = fallback["summary"]
    model_name = fallback["model"]
    usage = fallback["usage"]

    fingerprint = hashlib.sha1(
        json.dumps(
            {"panel": panel, "tenant_id": tenant_id, "digest": sanitized_digest},
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    _emit_meta_audit(
        skill_id=skill_id,
        payload=payload,
        tenant_id=tenant_id,
        param_hash=fingerprint,
        summary_length=len(summary_text or ""),
    )

    return {
        "summary": summary_text,
        "model": model_name,
        "sanitized_input_digest": sanitized_digest,
        "usage": usage,
    }


__all__ = ("handler_assistant_investigation_summary",)
