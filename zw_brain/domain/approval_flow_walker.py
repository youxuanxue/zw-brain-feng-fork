"""E3 Wave-2 三引擎 F2 续 — 自定义 live schema 驱动 J1 审批的走查器。

补 R14 执行层缝：committed 的自定义 approval_flow schema 此前能存却驱动不了真实
J1（`request.py` 只问 baseline seeder）。本模块把一个 live schema 的 payload
（nodes + branches + selection_rules）走查成有序 ApprovalStep 列表，写运行态
ApprovalCase + Step。

边界（本期 deliberately serial）：
- `always` 边 → 直连下一节点（串行多级，覆盖"编制→二级→一级→发布"）。
- `on_decision` 边 → happy-path 直连下一节点；approve→下一步 / reject→终止 的分流由
  决策时的状态机（conditional_approval / append_*）承载，与 baseline 同构。
- `expression` 边 → **本期 fail-closed**：当作 `always` 走默认边 + 收一条 warning。
  **不实现 {field,op,value} 条件求值器**（鞍山反馈 + 所有 feature 场景均纯串行多级、
  零条件路由需求；求值器属镀金，待真有"按金额分流"业务需求再立项）。
- 不可达 / 环 / 无 approval 节点 → 抛 ApprovalFlowWalkError，调用方 fail-closed 回落
  baseline（绝不留半截 case）。

baseline 路径（`approval_flow_baseline.py`）零改动：本模块是并行新增路径。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from zw_brain.domain.approval_flow_baseline import BASELINE_APPLICATION_CODE_SUFFIX
from zw_brain.domain.models import (
    ApprovalCaseRecord,
    ApprovalFlowSchemaRecord,
    ApprovalStepRecord,
)

# 边选择优先级：happy-path 走查时多条出边按此优先级取默认边。
_EDGE_PRIORITY = {"always": 0, "on_decision": 1, "expression": 2}


class ApprovalFlowWalkError(ValueError):
    """schema 走查失败（环 / 不可达 / 无出边 / 无 approval 节点）。调用方应 fail-closed 回落 baseline。"""


def _now() -> datetime:
    return datetime.now(UTC)


def _build_step_spec(
    step_no: int, node: dict[str, Any], rules: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """与 baseline 写法同构的 approver_scope（node_code/node_name + 可选 selection_rule）。"""
    approver_scope: dict[str, Any] = {
        "node_code": node.get("node_code"),
        "node_name": node.get("node_name"),
    }
    rule_code = node.get("selection_rule_code")
    if rule_code and rule_code in rules:
        rule = rules[rule_code]
        approver_scope["selection_rule"] = {
            "rule_code": rule_code,
            "rule_kind": rule.get("rule_kind"),
            "rule_payload_json": rule.get("rule_payload_json", {}),
        }
    return {
        "step_no": step_no,
        "step_name": node.get("node_name", f"步骤{step_no}"),
        "decision_mode": "single",
        "approver_scope_json": approver_scope,
    }


def _pick_next_edge(
    edges: list[dict[str, Any]], warnings: list[str], cur: str
) -> str:
    """从 cur 的出边里取 happy-path 默认边。

    优先级 always > on_decision > expression；expression 边被当默认走时收一条
    fail-closed warning（本期不求值条件，见模块 docstring）。
    """
    ordered = sorted(
        edges, key=lambda b: _EDGE_PRIORITY.get(b.get("condition_kind", "always"), 9)
    )
    chosen = ordered[0]
    if chosen.get("condition_kind") == "expression":
        warnings.append(f"expression-edge-fail-closed:{cur}->{chosen.get('to_node_code')}")
    return str(chosen["to_node_code"])


def instantiate_steps_from_schema(
    payload: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """走查 schema payload → 有序 step 列表（happy-path 串行）。

    返回 {"steps": [step_spec, ...], "warnings": [str, ...]}。
    任何结构问题（无 start / 环 / 无出边 / 无 approval 节点）抛 ApprovalFlowWalkError。
    """
    nodes = {n["node_code"]: n for n in payload.get("nodes", []) if isinstance(n, dict) and n.get("node_code")}
    rules = {r["rule_code"]: r for r in payload.get("selection_rules", []) if isinstance(r, dict) and r.get("rule_code")}

    out_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for branch in payload.get("branches", []):
        if isinstance(branch, dict) and branch.get("from_node_code"):
            out_edges[branch["from_node_code"]].append(branch)

    start = next((c for c, n in nodes.items() if n.get("node_type") == "start"), None)
    if start is None:
        raise ApprovalFlowWalkError("schema has no start node")

    steps: list[dict[str, Any]] = []
    warnings: list[str] = []
    visited: set[str] = set()
    cur = start
    step_no = 0

    while True:
        if cur in visited:
            raise ApprovalFlowWalkError(f"cycle detected at node {cur!r}")
        visited.add(cur)
        node = nodes.get(cur)
        if node is None:
            raise ApprovalFlowWalkError(f"branch points to unknown node {cur!r}")
        node_type = node.get("node_type")
        if node_type == "end":
            break
        if node_type == "approval":
            step_no += 1
            steps.append(_build_step_spec(step_no, node, rules))
        edges = out_edges.get(cur)
        if not edges:
            raise ApprovalFlowWalkError(f"node {cur!r} has no outgoing edge (cannot reach end)")
        cur = _pick_next_edge(edges, warnings, cur)

    if not steps:
        raise ApprovalFlowWalkError("schema produced zero approval steps")
    return {"steps": steps, "warnings": warnings}


def start_approval_workflow_from_schema(
    session: Session,
    *,
    application_code: str,
    tenant_id: str,
    schema: ApprovalFlowSchemaRecord,
    submitted_by: str,
    context: dict[str, Any] | None = None,
) -> ApprovalCaseRecord | None:
    """用自定义 live schema 走查出的 steps 写运行态 ApprovalCase + Step。

    走查在任何 DB 写入前发生（纯函数先行），结构问题直接抛 ApprovalFlowWalkError，
    调用方回落 baseline，不留半截 case。复用 baseline 的 application_code 后缀，使下游
    读侧对 baseline / schema 两条来源一致处理。
    """
    walked = instantiate_steps_from_schema(schema.payload_json or {}, context)
    steps = walked["steps"]
    warnings = walked["warnings"]

    case = ApprovalCaseRecord(
        tenant_id=tenant_id,
        application_code=f"{application_code}{BASELINE_APPLICATION_CODE_SUFFIX}",
        current_status="in_progress",
        current_step=1,
        decision_payload_json={
            "schema_code": schema.schema_code,
            "schema_version": schema.version,
            "schema_id": schema.id,
            "submitted_by": submitted_by,
            "source": "custom_schema",
            "shared_type": (context or {}).get("shared_type"),
            "project_code": (context or {}).get("project_code"),
            "walker_warnings": warnings,
        },
        flow_schema_code=schema.schema_code,
        flow_schema_version=str(schema.version),
    )
    session.add(case)
    session.flush()

    for spec in steps:
        session.add(
            ApprovalStepRecord(
                approval_case_id=case.id,
                step_no=spec["step_no"],
                step_name=spec["step_name"],
                decision_mode=spec["decision_mode"],
                status="pending",
                approver_scope_json=spec["approver_scope_json"],
                started_at=_now() if spec["step_no"] == 1 else None,
            )
        )
    session.commit()
    return case
