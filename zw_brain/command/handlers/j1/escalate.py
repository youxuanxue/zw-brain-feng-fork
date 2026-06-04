"""J1 国家直达转报 handler（D50/C6，national-direct 子旅程）。

业务运营员把本级已审核通过的申请**转报国家平台**。核心硬约束（D50 §三 + SPEC 场景4）：
**绝不污染 J1 主链路**——

  - 不新增 application 主 status 枚举值（``conditional_approval.CONDITIONAL_TRANSITIONS`` 零改动）；
  - 不调用 application_repo.update_status —— 本 handler **完全不写 application 聚合**；
  - 「国家通道转报中 / 撤销中」是**读侧计算态**（overlay），由 ``national_channel_display`` 纯函数
    从 stage 派生，绝不落主状态机。

转报经 C4 国家通道 gate 调 adapter.national.application.submit：provisioned→真实出站(C3 client)+
受理回执；未配置→记意图 + 诚实「待国家平台回执」，**不伪造回流**（本期无真实端点）。
审计 capability_call=application.escalate_national（由 pipeline 用 ctx.skill_id 记）。
"""

from __future__ import annotations

from typing import Any

from zw_brain.command.deps import HandlerDeps, SkillContext

# 计算态 overlay 值（**绝不写入 application 主 status**；仅读侧派生展示）。
STAGE_ESCALATING = "escalating"
STAGE_REVOKING = "revoking"

# 国家通道出站适配能力（经 C4 national_channel_gate 出站）。
_NATIONAL_SUBMIT_CAP = "adapter.national.application.submit"

_STAGE_DISPLAY = {
    STAGE_ESCALATING: "国家通道转报中",
    STAGE_REVOKING: "国家通道撤销中",
}


def national_channel_display(stage: str | None) -> str | None:
    """读侧计算态 → 展示文案（R12 人话）。stage 为空 → None（主链路展示不受影响）。

    纯函数、无副作用：这是「计算态不入主状态机」的单一事实源——UI 读 application 主 status
    照常，再叠加本 overlay；不存在「escalating」这个主 status 值。
    """
    return _STAGE_DISPLAY.get(stage or "")


def handler_application_escalate_national(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A 兼容别名
    application_code = str(payload.get("application_code", ""))
    stage = STAGE_REVOKING if str(payload.get("action", "")) == "revoke" else STAGE_ESCALATING

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        from zw_brain.command.handlers.infra import national_channel_gate as gate

        decision = gate.evaluate()
        result: dict[str, Any] = {
            "application_code": application_code,
            "national_channel_stage": stage,  # 计算态 overlay（不入主状态机）
            "display_status": national_channel_display(stage),
            "audit_id": audit_id,
        }
        if not decision.provisioned:
            # 记意图 + 诚实 pending：零对外、不伪造回流、不动 application 主 status。
            result["national_channel"] = decision.pending
            return result
        # provisioned：经 C4 client 真实出站，受理回执取真实响应（不伪造）。
        response = gate.outbound(
            _NATIONAL_SUBMIT_CAP,
            {
                "application_code": application_code,
                "action": payload.get("action", "escalate"),
                "reason": payload.get("reason", ""),
            },
        )
        result["national_channel"] = {
            "status": "submitted" if response.ok else "rejected",
            "reason": "已转报国家平台，待回执" if response.ok else response.message,
            "code": response.code,
        }
        return result

    return deps.write(ctx, payload, mutation)
