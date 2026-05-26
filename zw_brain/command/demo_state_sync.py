"""Demo-seed state cascades, extracted out of BrainService core (Commit 2).

These blocks react to the `sd-default` demo seed entities (the parking-lot
reuse journey: `REQ-2026-04-25-0011` / `DLV-2026-04-25-0011` / `PKG-2026-04-25-001`
/ `res-jbxx-ledger` / ...) and project their confirmation state onto provider /
discovery / zone snapshot slices for the WebUI demo.

They used to live inline in `BrainService._sync_state_views` and ran on every
mutation. The behavior is unchanged — under a real customer seed these IDs don't
exist, so each `_maybe_*` lookup returns None and the cascade is a no-op. Keeping
them in a clearly-named module (rather than the core state machine) is the point:
`scripts/check_no_demo_id_literals.py` forbids these literals from leaking back
into `brain.py` / handlers, and this file is the single allow-listed home.

Signature mirrors the handler convention (`fn(brain, ...)`); brain.py calls this
via a lazy import to avoid a module-level import cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


def sync_demo_state_views(brain: BrainService) -> None:
    request0011 = brain._maybe_request("REQ-2026-04-25-0011")
    request0007 = brain._maybe_request("REQ-2026-04-24-0007")
    task0011 = brain._maybe_delivery("DLV-2026-04-25-0011")
    package001 = brain._maybe_package("PKG-2026-04-25-001")

    if request0011:
        # R-005 fix: 每条待办按 (role, item_id, category) 唯一；同一 REQ ID 在同一 role 下可承载多语境
        brain._set_todo_status("ROLE_ORGAN_OPERATER", "REQ-2026-04-25-0011", brain._request_status_text(request0011, "applicant"), category="apply-progress")
        brain._set_todo_status("ROLE_ORGAN_MANAGER", "REQ-2026-04-25-0011", brain._request_status_text(request0011, "reviewer"), category="review")
        brain._set_todo_status("ROLE_ORGAN_OPERATER", "REQ-2026-04-25-0011", brain._request_status_text(request0011, "filler"), category="supplement-township")
        brain._set_todo_status("ROLE_ORGAN_OPERATER", "REQ-2026-04-25-0011", brain._request_status_text(request0011, "filler"), category="supplement-village")
        brain._set_todo_status("ROLE_ORGAN_MANAGER", "REQ-2026-04-25-0011", brain._request_status_text(request0011, "summarizer"), category="summary")
    if request0007:
        brain._set_todo_status("ROLE_ORGAN_MANAGER", "REQ-2026-04-24-0007", brain._request_status_text(request0007, "reviewer"), category="review")
        brain._set_todo_status("ROLE_ORGAN_OPERATER", "REQ-2026-04-24-0007", brain._request_status_text(request0007, "filler"), category="supplement-township")

    if task0011:
        confirmed = task0011["backflow"]["status"] == "已确认"
        brain._set_todo_status("ROLE_ORGAN_MANAGER", "LEDGER-parking-v1.3", "已发布" if confirmed else "待发布")
        brain._set_todo_status("ROLE_BUSIAUDIT", "ZONE-business-ledger", "已上线" if confirmed else "待更新")
        provider = brain._snapshot["provider"]
        provider["overview"][0]["value"] = "v1.3" if confirmed else "v1.2 → v1.3"
        provider["overview"][2]["value"] = "0" if confirmed else str(len(task0011["backflow"]["candidateFields"]))
        provider["catalogs"][0]["issue"] = "v1.3 版本说明已同步" if confirmed else "需补充 v1.3 版本说明"
        if not provider["catalogs"][1].get("governanceLocked"):
            provider["catalogs"][1]["status"] = "已发布" if confirmed else "待质检"
            provider["catalogs"][1]["issue"] = "默认复用入口已更新" if confirmed else "需更新默认复用入口说明"
        provider["resources"][0]["updatedAt"] = brain._now_date() if confirmed else "2026-04-25"
        if not provider["resources"][1].get("governanceLocked"):
            provider["resources"][1]["status"] = "可共享" if confirmed else "待审核"
        provider["aiGovernance"]["summary"] = (
            "停车场信息共享目录已确认吸收高频差异字段，下一步重点转为持续监测补录热区和维护专题入口一致性。"
            if confirmed
            else "建议优先发布停车场信息共享目录回流候选，并把“本地泊位开放状态”“最新开放时间”纳入目录说明；其次更新城市运行专题目录中的默认复用入口说明。"
        )
        discovery = brain._resource_by_id("res-jbxx-ledger")
        discovery["coverage"] = "89%" if confirmed else "82%"
        discovery["updatedAt"] = brain._now_date() if confirmed else "2026-04-25"
        discovery["explain"] = [
            "当前需求可直接复用 v1.3 模板，基层补录字段进一步收缩",
            "经营状态与最近走访时间已纳入正式字段",
            "专题入口与模板版本已同步更新",
        ] if confirmed else [
            "当前需求首先应复用该模板，而不是重新发起整表采集",
            "模板已覆盖多数企业基础字段",
            "仅需补少量现场差异字段即可形成任务",
        ]
        zone = brain._zone_by_id("business")
        zone["trust"] = [
            "来源等级：高",
            "模板版本：v1.3，默认入口已同步",
            "责任方：区政数局 / 市场监管局",
        ] if confirmed else [
            "来源等级：高",
            "模板版本：v1.2，v1.3 待发布",
            "责任方：区政数局 / 市场监管局",
        ]
        # K12 dashboard 块已退役（详见 D15 二次反转）；toggle 副作用不再更新大屏 burden/suggestions

    if package001:
        brain._set_todo_status("ROLE_BUSIAUDIT", "PKG-2026-04-25-001", brain._package_status_text(package001))
