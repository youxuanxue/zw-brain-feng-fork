"""GovernanceService — governance actor filter / import issues / audit events.

Owns: governance actor filtering, import-time issue collection,
governance-scoped audit event query, M0 work-queue card projection.

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


# Fixed whitelist of governance-scoped skill_ids surfaced by the audit view. Kept as a
# module constant so it can be pushed to SQL (list_audit_events_for_capabilities) — the LIMIT then
# applies AFTER this filter, instead of a 500-row cap silently dropping older matches.
_GOVERNANCE_AUDIT_SKILL_IDS = (
    "tenant.policy.evaluate",
    "legacy.bsp.mapping.import",
    "org.projection.sync",
    "actor.projection.sync",
    "governance.iam_overview",
    "governance.policy_candidate.list",
    "governance.policy_candidate.review",
)
_IMPORT_ISSUES_SKILL_ID = "legacy.bsp.mapping.import"


@dataclass(frozen=True)
class GovernanceService:
    """Governance helpers (B1 audit / J2 governance / M0 work queue)."""

    brain: BrainService

    def filter_actor(
        self,
        item: dict[str, Any],
        *,
        status_filter: str,
        role_filter: str,
        actor_filter: str,
    ) -> bool:
        """Filter governance actor projection rows by status/role/actor."""
        profile = item.get("profile_json") if isinstance(item.get("profile_json"), dict) else {}
        if status_filter and item.get("status") != status_filter and profile.get("binding_status") != status_filter:
            return False
        if role_filter and role_filter not in (item.get("role_codes_json") or []):
            return False
        if actor_filter and item.get("external_actor_id") != actor_filter:
            return False
        return True

    def import_issues(self, adapter_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Collect import-time issues from adapter run receipts + capability_calls."""
        issues: list[dict[str, Any]] = []
        for run in adapter_runs:
            receipt = run.get("receipt_json") if isinstance(run.get("receipt_json"), dict) else {}
            for issue in receipt.get("issues") or []:
                if not isinstance(issue, dict):
                    continue
                issues.append(copy.deepcopy(issue) | {"adapter_run_id": run.get("id"), "adapter_status": run.get("status"), "source_ref": run.get("source_ref")})
        store = self.brain._state_store.database_store
        if store is not None:
            # P1-2: push the skill_id filter to SQL instead of hydrating the whole
            # unbounded capability_call table then filtering one skill_id in Python.
            for call in store.list_capability_calls_for_capability(_IMPORT_ISSUES_SKILL_ID):
                for item in call.output_json.get("items") or []:
                    if isinstance(item, dict) and item.get("reason"):
                        issues.append({"type": item["reason"], "table": "legacy.bsp.mapping.import", "legacy_ref": item.get("legacy_permission_ref"), "detail": {"legacy_role_ref": item.get("legacy_role_ref"), "capability_id": item.get("capability_id")}, "capability_call_ref": call.call_ref})
        return issues

    def audit_events(
        self,
        *,
        tenant_id: str,
        capability_filter: str = "",
        actor_filter: str = "",
    ) -> list[dict[str, Any]]:
        """Governance-scoped audit events filtered by capability/actor."""
        store = self.brain._state_store.database_store
        if store is None:
            return []
        events = []
        # P1-2 completeness fix: push the governance skill_id whitelist to SQL so the LIMIT
        # applies AFTER it. The old code capped the table at 500 *then* filtered to the
        # whitelist in Python — once audit_event exceeded 500 rows, a matching older
        # governance event was silently truncated away. Response shape is unchanged.
        for item in store.list_audit_events_for_capabilities(list(_GOVERNANCE_AUDIT_SKILL_IDS)):
            payload = item.payload_json if isinstance(item.payload_json, dict) else {}
            if payload.get("tenant_id") not in {None, "", tenant_id}:
                continue
            if capability_filter and payload.get("capability_id") != capability_filter and payload.get("capability_slug") != capability_filter:
                continue
            if actor_filter and actor_filter not in {str(payload.get("external_actor_id", "")), str(payload.get("actor_id", "")), str(payload.get("actor_snapshot", {}).get("subject", "")) if isinstance(payload.get("actor_snapshot"), dict) else ""}:
                continue
            events.append({"id": item.request_id, "skill_id": item.skill_id, "phase": item.phase, "actor": item.actor, "occurred_at": item.occurred_at.isoformat(), "payload_json": copy.deepcopy(payload)})
        return events

    def build_m0_work_queue_cards(
        self,
        *,
        totals: dict[str, int],
        by_canonical: dict[str, dict[str, int]],
        adapter_runs: list[dict[str, Any]],
        rollbacks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build the 11 M0 work-queue cards from import telemetry.

        Each card has a deterministic status (ready / partial / pending / failed)
        derived only from what we already loaded — no extra queries.
        """
        succeeded_runs = sum(1 for r in adapter_runs if r["status"] == "succeeded")
        failed_runs = sum(1 for r in adapter_runs if r["status"] == "failed")
        has_runs = bool(adapter_runs)
        has_mappings = totals["mappings"] > 0
        any_conflicted = totals.get("conflicted", 0) > 0
        any_rolled_back = totals.get("rolled_back", 0) > 0
        catalog_count = by_canonical.get("catalog_entry", {}).get("total", 0)
        resource_count = (
            by_canonical.get("ResourceAssetRecord", {}).get("total", 0)
            + by_canonical.get("resource_asset", {}).get("total", 0)
        )
        application_count = by_canonical.get("application_record", {}).get("total", 0)
        topic_count = by_canonical.get("TopicPackageRecord", {}).get("total", 0)
        objection_count = by_canonical.get("ObjectionCaseRecord", {}).get("total", 0)
        delivery_count = by_canonical.get("DeliveryTaskRecord", {}).get("total", 0)

        def status(condition_ready: bool, condition_partial: bool = False) -> str:
            if condition_ready:
                return "ready"
            if condition_partial:
                return "partial"
            return "pending"

        return [
            {
                "id": "export",
                "title": "一键导出",
                "owner": "M0 + 客户授权",
                "status": "ready" if has_runs else "pending",
                "summary": f"已识别 {len(adapter_runs)} 次最近导入运行" if has_runs else "等待客户现场导出",
            },
            {
                "id": "import",
                "title": "批量导入",
                "owner": "M0 实施人",
                "status": status(succeeded_runs >= 5, has_runs),
                "summary": f"{succeeded_runs} 个 adapter 已成功，{failed_runs} 个失败",
            },
            {
                "id": "mapping_verify",
                "title": "对象映射核验",
                "owner": "M0 + 数据提供方 / 业务运营员 抽样",
                "status": status(has_mappings and not any_conflicted, has_mappings),
                "summary": f"映射 {totals['mappings']} 条；冲突 {totals.get('conflicted', 0)}",
            },
            {
                "id": "catalog_migration_review",
                "title": "目录迁移审核",
                "owner": "M0 + 业务运营员 抽样",
                "status": status(catalog_count > 0, False),
                "summary": f"catalog_entry 映射 {catalog_count} 条",
            },
            {
                "id": "schema_mapping",
                "title": "schema 快照与挂接核验",
                "owner": "M0 + 数据提供方 抽样",
                "status": status(resource_count > 0, False),
                "summary": f"resource_asset 映射 {resource_count} 条",
            },
            {
                "id": "application_history",
                "title": "申请审批授权历史核验",
                "owner": "M0 + 审批人 抽样",
                "status": status(application_count > 0 and delivery_count > 0, application_count > 0),
                "summary": f"application_record {application_count} / delivery_task {delivery_count}",
            },
            {
                "id": "projection",
                "title": "投影生成",
                "owner": "M0 自动 + 失败摘要",
                "status": status((topic_count + objection_count) > 0, has_runs),
                "summary": f"topic_package {topic_count} / objection_case {objection_count}",
            },
            {
                "id": "compliance_sample",
                "title": "合规与断链抽查",
                "owner": "安全审计员 抽样",
                "status": status(objection_count > 0, has_mappings),
                "summary": f"已建立 objection_case {objection_count} 条样本" if objection_count else "等待 安全审计员 抽查",
            },
            {
                "id": "handover",
                "title": "验收移交",
                "owner": "客户验收人 + M0 实施人",
                "status": status(
                    has_mappings and not any_conflicted and succeeded_runs >= 5,
                    has_mappings,
                ),
                "summary": "等待客户验收签字" if not has_mappings else "可移交（缺口请检查冲突映射）",
            },
            {
                "id": "gap_reimport",
                "title": "缺口补迁",
                "owner": "M0 + 客户授权",
                "status": "ready" if has_runs else "pending",
                "summary": "支持按 schema 递增追加，回指旧对象",
            },
            {
                "id": "rollback",
                "title": "回滚",
                "owner": "M0 + 客户授权",
                "status": "ready" if any_rolled_back or has_runs else "pending",
                "summary": (
                    f"已记录 {len(rollbacks)} 次 rollback；最近 actor={rollbacks[0]['actor']}"
                    if rollbacks
                    else "尚未触发"
                ),
            },
        ]
