"""E3 Wave-2 三引擎 F2 — 审批流引擎内置基线 + J1 集成。

承接 plan.yaml F2 停止条件：J1 申请按 shared_type=1/2 自动选择对应基线流程。
基线两条：
- baseline_shared_conditional (shared_type=1)：start → 业务管理员审 → 数据管理员审
  → 部门负责人终审 → end，4 个 approval；选人规则覆盖 role / org_unit / org_unit_leader。
- baseline_shared_unconditional (shared_type=2)：start → 数据管理员快速审 → end，
  1 个 approval。

Seeder idempotent；start_approval_workflow_from_baseline 拿 baseline 后写
ApprovalCaseRecord + ApprovalStepRecord（运行态表，F1 之前已存在）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo
from zw_brain.domain.models import (
    ApprovalCaseRecord,
    ApprovalFlowSchemaRecord,
    ApprovalStepRecord,
)

BASELINE_CONDITIONAL_CODE = "baseline_shared_conditional"
BASELINE_UNCONDITIONAL_CODE = "baseline_shared_unconditional"
SHARED_TYPE_CONDITIONAL = 1
SHARED_TYPE_UNCONDITIONAL = 2


def _now() -> datetime:
    return datetime.now(UTC)


def _conditional_baseline_payload() -> dict[str, Any]:
    """有条件共享：业务管理员 → 数据管理员 → 部门负责人 三审 + 终审 4 级。

    选人规则覆盖 role / org_unit / org_unit_leader 三种。
    """
    return {
        "nodes": [
            {"node_code": "start", "node_type": "start", "node_name": "开始", "order_index": 0},
            {
                "node_code": "biz_review",
                "node_type": "approval",
                "node_name": "业务管理员审核",
                "selection_rule_code": "biz_operator_role",
                "order_index": 1,
            },
            {
                "node_code": "data_review",
                "node_type": "approval",
                "node_name": "数据管理员审核",
                "selection_rule_code": "data_manager_role",
                "order_index": 2,
            },
            {
                "node_code": "org_unit_review",
                "node_type": "approval",
                "node_name": "申请单位部门审",
                "selection_rule_code": "applicant_org_unit",
                "order_index": 3,
            },
            {
                "node_code": "leader_final",
                "node_type": "approval",
                "node_name": "部门负责人终审",
                "selection_rule_code": "org_unit_leader",
                "order_index": 4,
            },
            {"node_code": "end", "node_type": "end", "node_name": "结束", "order_index": 5},
        ],
        "selection_rules": [
            {
                "rule_code": "biz_operator_role",
                "rule_kind": "role",
                "rule_payload_json": {"role_code": "ROLE_ORGAN_OPERATER"},
            },
            {
                "rule_code": "data_manager_role",
                "rule_kind": "role",
                "rule_payload_json": {"role_code": "ROLE_ORGAN_MANAGER"},
            },
            {
                "rule_code": "applicant_org_unit",
                "rule_kind": "org_unit",
                "rule_payload_json": {"scope": "applicant_org"},
            },
            {
                "rule_code": "org_unit_leader",
                "rule_kind": "org_unit_leader",
                "rule_payload_json": {"scope": "applicant_org"},
            },
        ],
        "branches": [
            {"from_node_code": "start", "to_node_code": "biz_review", "condition_kind": "always", "condition_payload_json": {}},
            {"from_node_code": "biz_review", "to_node_code": "data_review", "condition_kind": "on_decision", "condition_payload_json": {}},
            {"from_node_code": "data_review", "to_node_code": "org_unit_review", "condition_kind": "on_decision", "condition_payload_json": {}},
            {"from_node_code": "org_unit_review", "to_node_code": "leader_final", "condition_kind": "on_decision", "condition_payload_json": {}},
            {"from_node_code": "leader_final", "to_node_code": "end", "condition_kind": "on_decision", "condition_payload_json": {}},
        ],
    }


def _unconditional_baseline_payload() -> dict[str, Any]:
    """无条件共享：1 级数据管理员快速审。"""
    return {
        "nodes": [
            {"node_code": "start", "node_type": "start", "node_name": "开始", "order_index": 0},
            {
                "node_code": "fast_review",
                "node_type": "approval",
                "node_name": "数据管理员快速审核",
                "selection_rule_code": "data_manager_role",
                "order_index": 1,
            },
            {"node_code": "end", "node_type": "end", "node_name": "结束", "order_index": 2},
        ],
        "selection_rules": [
            {
                "rule_code": "data_manager_role",
                "rule_kind": "role",
                "rule_payload_json": {"role_code": "ROLE_ORGAN_MANAGER"},
            },
        ],
        "branches": [
            {"from_node_code": "start", "to_node_code": "fast_review", "condition_kind": "always", "condition_payload_json": {}},
            {"from_node_code": "fast_review", "to_node_code": "end", "condition_kind": "on_decision", "condition_payload_json": {}},
        ],
    }


_BASELINE_BY_SHARED_TYPE: dict[int, tuple[str, str, str]] = {
    SHARED_TYPE_CONDITIONAL: (BASELINE_CONDITIONAL_CODE, "有条件共享基线流程", "conditional"),
    SHARED_TYPE_UNCONDITIONAL: (BASELINE_UNCONDITIONAL_CODE, "无条件共享基线流程", "unconditional"),
}


def _baseline_payload_for(code: str) -> dict[str, Any]:
    if code == BASELINE_CONDITIONAL_CODE:
        return _conditional_baseline_payload()
    return _unconditional_baseline_payload()


class ApprovalFlowBaselineSeeder:
    """Idempotent seeder：commit_to_live 入库 2 条 baseline schema。"""

    SEEDER_CREATED_BY = "system:bootstrap:approval_flow_baseline"

    def __init__(self, session: Session) -> None:
        self._session = session

    def seed_all(self, tenant_id: str = "sd-default") -> dict[str, ApprovalFlowSchemaRecord]:
        result: dict[str, ApprovalFlowSchemaRecord] = {}
        for _code, (rule_code, title, _kind) in [
            (BASELINE_CONDITIONAL_CODE, (BASELINE_CONDITIONAL_CODE, "有条件共享基线流程", "conditional")),
            (BASELINE_UNCONDITIONAL_CODE, (BASELINE_UNCONDITIONAL_CODE, "无条件共享基线流程", "unconditional")),
        ]:
            schema_code = rule_code
            title_str = title
            existing_live = self._find_live(tenant_id, schema_code)
            if existing_live is not None:
                result[schema_code] = existing_live
                continue
            repo = ApprovalFlowSchemaRepo(self._session)
            record = repo.create_draft(
                tenant_id=tenant_id,
                schema_code=schema_code,
                title=title_str,
                payload=_baseline_payload_for(schema_code),
                source_kind="manual",
                draft_source_text=f"baseline {_kind}",
                created_by=self.SEEDER_CREATED_BY,
            )
            repo.promote_to_preview(record.id)
            live = repo.commit_to_live(record.id)
            result[schema_code] = live
        return result

    def get_baseline_for_shared_type(
        self, tenant_id: str, shared_type: Any
    ) -> ApprovalFlowSchemaRecord | None:
        try:
            shared_type_int = int(shared_type)
        except (TypeError, ValueError):
            return None
        mapping = _BASELINE_BY_SHARED_TYPE.get(shared_type_int)
        if mapping is None:
            return None
        schema_code, _title, _kind = mapping
        return self._find_live(tenant_id, schema_code)

    def _find_live(self, tenant_id: str, schema_code: str) -> ApprovalFlowSchemaRecord | None:
        stmt = (
            select(ApprovalFlowSchemaRecord)
            .where(
                ApprovalFlowSchemaRecord.tenant_id == tenant_id,
                ApprovalFlowSchemaRecord.schema_code == schema_code,
                ApprovalFlowSchemaRecord.status == "live",
            )
            .order_by(ApprovalFlowSchemaRecord.version.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalar_one_or_none()


BASELINE_APPLICATION_CODE_SUFFIX = "#baseline"


def start_approval_workflow_from_baseline(
    session: Session,
    *,
    application_code: str,
    tenant_id: str,
    shared_type: Any,
    submitted_by: str,
) -> ApprovalCaseRecord | None:
    """按 shared_type 拿 baseline，写运行态 ApprovalCase + Step。

    缺失 / 未知 shared_type / baseline 未入库 → 返 None（防御性，不抛）。

    实现注：application_code 加 BASELINE_APPLICATION_CODE_SUFFIX 后缀避免与 legacy
    `upsert_from_request_and_approval` 的 ApprovalCase 行（每次 _persist 时按
    application_code 覆盖 + 删 step）冲突。Wave 2 baseline 是新路径，与 legacy
    单步审批投影并行存在。
    """
    seeder = ApprovalFlowBaselineSeeder(session)
    baseline = seeder.get_baseline_for_shared_type(tenant_id, shared_type)
    if baseline is None:
        return None

    payload = baseline.payload_json or {}
    nodes = payload.get("nodes", [])
    selection_rules = {r["rule_code"]: r for r in payload.get("selection_rules", [])}
    approval_nodes = [n for n in nodes if n.get("node_type") == "approval"]

    case = ApprovalCaseRecord(
        tenant_id=tenant_id,
        application_code=f"{application_code}{BASELINE_APPLICATION_CODE_SUFFIX}",
        current_status="in_progress",
        current_step=1,
        decision_payload_json={
            "baseline_code": baseline.schema_code,
            "baseline_version": baseline.version,
            "schema_id": baseline.id,
            "submitted_by": submitted_by,
            "shared_type": int(shared_type) if shared_type is not None else None,
        },
    )
    session.add(case)
    session.flush()

    for index, node in enumerate(approval_nodes, start=1):
        rule_code = node.get("selection_rule_code")
        approver_scope: dict[str, Any] = {"node_code": node.get("node_code"), "node_name": node.get("node_name")}
        if rule_code and rule_code in selection_rules:
            rule = selection_rules[rule_code]
            approver_scope["selection_rule"] = {
                "rule_code": rule_code,
                "rule_kind": rule.get("rule_kind"),
                "rule_payload_json": rule.get("rule_payload_json", {}),
            }
        session.add(
            ApprovalStepRecord(
                approval_case_id=case.id,
                step_no=index,
                step_name=node.get("node_name", f"步骤{index}"),
                decision_mode="single",
                status="pending",
                approver_scope_json=approver_scope,
                started_at=_now() if index == 1 else None,
            )
        )
    session.commit()
    return case


def seed_runtime_data(session: Session, tenant_id: str = "sd-default") -> dict[str, ApprovalFlowSchemaRecord]:
    """Service 启动可调用的显式 seeder 入口；idempotent。"""
    return ApprovalFlowBaselineSeeder(session).seed_all(tenant_id=tenant_id)
