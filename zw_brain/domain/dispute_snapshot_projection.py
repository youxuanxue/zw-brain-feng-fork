"""Live disputes projection for WebUI snapshot — DB objection cases are the single SoT."""

from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.lifecycle_timeline import objection_sideline_note, objection_timeline
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id


def _case_to_dispute_item(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "topic": record.title,
        "type": record.objection_kind,
        "status": record.status,
        "targetType": record.target_type,
        "targetId": record.target_id,
        "owner": record.provider_org_id or record.complainant_org_id,
        "createdAt": record.created_at.isoformat() if getattr(record, "created_at", None) else "",
        # G 脊柱（申请/复议方侧）：异议办理 timeline（提交→受理→核查→办结→归档）现算，
        # 双侧详情（P3/P5 ObjectionDetail）共用 PhaseTrack 渲「卡在谁桌上」。读侧、不改状态机。
        "statusTimeline": objection_timeline(record.status),
        "lifecycleNote": objection_sideline_note(record.status),
        "repository": {
            "objectionKind": record.objection_kind,
            "targetType": record.target_type,
            "status": record.status,
        },
    }


def enrich_disputes_snapshot(snapshot: dict[str, Any], *, tenant_id: str | None = None) -> dict[str, Any]:
    """Project snapshot['disputes'] from the real objection_case table (DB single SoT).

    **无条件替换**（C-1，去双轨）：空库 → 空列表（不再 append-merge 保留 seed 演示 DSP，
    那会留幻影行）。disputes 与 requests/approvals/discovery 一致，全部以 DB 现算为准。
    """
    out = copy.deepcopy(snapshot)
    repo = ObjectionRepository()
    out["disputes"] = [
        _case_to_dispute_item(record)
        for record in repo.list_cases(tenant_id=tenant_id or get_runtime_tenant_id())
    ]
    return out
