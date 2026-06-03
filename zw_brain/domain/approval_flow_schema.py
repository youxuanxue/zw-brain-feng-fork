"""E3 Wave-2 三引擎 F1 — 审批流模板状态机 + 仓库 helper。

承接 R14（草稿→预览→入库）/ 设计基线 §10.3 三引擎契约字段：
    config_change_class ∈ {live, preview, draft} 已就位（registered manifest 配 live）。
本仓库只负责模板/定义层，运行态 ApprovalCase* 不变；
NL 草稿生成（F3）和 J1 集成（F2）在后续 F 里接入，本文件只暴露纯结构 API。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zw_brain.domain.models import (
    ApprovalFlowBranchRecord,
    ApprovalFlowNodeRecord,
    ApprovalFlowSchemaRecord,
    ApprovalFlowSelectionRuleRecord,
)

ApprovalFlowStatus = Literal["draft", "preview", "live"]

_VALID_STATUSES: set[str] = {"draft", "preview", "live"}
_VALID_NODE_TYPES: set[str] = {"start", "approval", "notify", "end"}
_VALID_SELECTION_RULE_KINDS: set[str] = {
    "fixed_user",
    "role",
    "org_unit",
    "org_unit_leader",
    "dynamic_expression",
}
_VALID_CONDITION_KINDS: set[str] = {"always", "expression", "on_decision"}


class ApprovalFlowTransitionError(ValueError):
    """draft/preview/live 状态机非法跃迁。"""


class ApprovalFlowPayloadError(ValueError):
    """payload_json 结构校验失败。"""


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ApprovalFlowPayloadError("payload must be a dict")
    for key in ("nodes", "selection_rules", "branches"):
        if key not in payload:
            raise ApprovalFlowPayloadError(f"payload missing required key: {key}")
        if not isinstance(payload[key], list):
            raise ApprovalFlowPayloadError(f"payload[{key!r}] must be a list")

    nodes: list[dict[str, Any]] = payload["nodes"]
    branches: list[dict[str, Any]] = payload["branches"]
    selection_rules: list[dict[str, Any]] = payload["selection_rules"]

    if not nodes:
        raise ApprovalFlowPayloadError("payload.nodes must not be empty")

    node_codes: list[str] = []
    start_count = 0
    end_count = 0
    for node in nodes:
        if not isinstance(node, dict):
            raise ApprovalFlowPayloadError("each node must be a dict")
        code = node.get("node_code")
        node_type = node.get("node_type")
        if not isinstance(code, str) or not code:
            raise ApprovalFlowPayloadError("node.node_code is required")
        if node_type not in _VALID_NODE_TYPES:
            raise ApprovalFlowPayloadError(
                f"node.node_type must be one of {sorted(_VALID_NODE_TYPES)}, got {node_type!r}"
            )
        if code in node_codes:
            raise ApprovalFlowPayloadError(f"duplicate node_code: {code}")
        node_codes.append(code)
        if node_type == "start":
            start_count += 1
        elif node_type == "end":
            end_count += 1

    if start_count != 1 or end_count != 1:
        raise ApprovalFlowPayloadError(
            f"payload must contain exactly 1 start and 1 end node, got start={start_count} end={end_count}"
        )

    node_code_set = set(node_codes)
    for branch in branches:
        if not isinstance(branch, dict):
            raise ApprovalFlowPayloadError("each branch must be a dict")
        from_code = branch.get("from_node_code")
        to_code = branch.get("to_node_code")
        cond_kind = branch.get("condition_kind", "always")
        if from_code not in node_code_set:
            raise ApprovalFlowPayloadError(
                f"branch.from_node_code {from_code!r} not in nodes"
            )
        if to_code not in node_code_set:
            raise ApprovalFlowPayloadError(
                f"branch.to_node_code {to_code!r} not in nodes"
            )
        if cond_kind not in _VALID_CONDITION_KINDS:
            raise ApprovalFlowPayloadError(
                f"branch.condition_kind must be one of {sorted(_VALID_CONDITION_KINDS)}, got {cond_kind!r}"
            )

    for rule in selection_rules:
        if not isinstance(rule, dict):
            raise ApprovalFlowPayloadError("each selection_rule must be a dict")
        kind = rule.get("rule_kind")
        if kind not in _VALID_SELECTION_RULE_KINDS:
            raise ApprovalFlowPayloadError(
                f"selection_rule.rule_kind must be one of {sorted(_VALID_SELECTION_RULE_KINDS)}, got {kind!r}"
            )


def _assert_reachable(payload: dict[str, Any]) -> None:
    """commit_to_live 前的可达性校验：start → ... → end 必须存在路径。"""
    nodes = {node["node_code"]: node for node in payload["nodes"]}
    branches = payload["branches"]
    start = next(code for code, node in nodes.items() if node["node_type"] == "start")
    end = next(code for code, node in nodes.items() if node["node_type"] == "end")

    adjacency: dict[str, list[str]] = {code: [] for code in nodes}
    for branch in branches:
        adjacency[branch["from_node_code"]].append(branch["to_node_code"])

    visited: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur == end:
            return
        if cur in visited:
            continue
        visited.add(cur)
        stack.extend(adjacency.get(cur, []))

    raise ApprovalFlowPayloadError(
        f"end node {end!r} not reachable from start node {start!r}"
    )


class ApprovalFlowSchemaRepo:
    """三态状态机（draft → preview → live）+ payload 结构校验仓库。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ---- mutation ---------------------------------------------------------

    def create_draft(
        self,
        tenant_id: str,
        schema_code: str,
        title: str,
        payload: dict[str, Any],
        *,
        source_kind: str = "manual",
        draft_source_text: str | None = None,
        created_by: str,
    ) -> ApprovalFlowSchemaRecord:
        _validate_payload(payload)
        # 自增 version：同 (tenant, schema_code) 已有记录时新建 v=max+1 草稿，
        # 不与 UNIQUE 约束 (tenant_id, schema_code, version) 冲突。
        existing_max = self._session.execute(
            select(func.max(ApprovalFlowSchemaRecord.version))
            .where(ApprovalFlowSchemaRecord.tenant_id == tenant_id)
            .where(ApprovalFlowSchemaRecord.schema_code == schema_code)
        ).scalar() or 0
        record = ApprovalFlowSchemaRecord(
            tenant_id=tenant_id,
            schema_code=schema_code,
            title=title,
            status="draft",
            version=existing_max + 1,
            source_kind=source_kind,
            draft_source_text=draft_source_text,
            payload_json=payload,
            created_by=created_by,
        )
        self._session.add(record)
        self._session.flush()
        self._project_payload(record, payload)
        self._session.commit()
        return record

    def promote_to_preview(self, schema_id: str) -> ApprovalFlowSchemaRecord:
        record = self._require(schema_id)
        if record.status != "draft":
            raise ApprovalFlowTransitionError(
                f"promote_to_preview requires status=draft, got {record.status!r}"
            )
        _validate_payload(record.payload_json)
        record.status = "preview"
        record.updated_at = _now()
        self._session.commit()
        return record

    def revert_to_draft(self, schema_id: str) -> ApprovalFlowSchemaRecord:
        record = self._require(schema_id)
        if record.status != "preview":
            raise ApprovalFlowTransitionError(
                f"revert_to_draft requires status=preview, got {record.status!r}"
            )
        record.status = "draft"
        record.updated_at = _now()
        self._session.commit()
        return record

    def commit_to_live(self, schema_id: str) -> ApprovalFlowSchemaRecord:
        record = self._require(schema_id)
        if record.status != "preview":
            raise ApprovalFlowTransitionError(
                f"commit_to_live requires status=preview, got {record.status!r}"
            )
        _validate_payload(record.payload_json)
        _assert_reachable(record.payload_json)
        # debt(A方案 2026-05-28): 取同 (tenant, schema_code) 当前最大 version + 1，
        # 避免 commit 时 +1 撞上历史鬼数据。真正的版本语义（A/B/C 三选一）由后续
        # 业务方决策决定；当前为让 demo 反复跑通做的 hack。
        existing_max = self._session.execute(
            select(func.max(ApprovalFlowSchemaRecord.version))
            .where(ApprovalFlowSchemaRecord.tenant_id == record.tenant_id)
            .where(ApprovalFlowSchemaRecord.schema_code == record.schema_code)
        ).scalar() or 0
        now = _now()
        record.status = "live"
        record.version = max(existing_max + 1, (record.version or 1) + 1)
        record.committed_at = now
        record.updated_at = now
        self._session.commit()
        return record

    # ---- read -------------------------------------------------------------

    def get(self, schema_id: str) -> ApprovalFlowSchemaRecord:
        return self._require(schema_id)

    def list_by_tenant(self, tenant_id: str) -> list[ApprovalFlowSchemaRecord]:
        stmt = (
            select(ApprovalFlowSchemaRecord)
            .where(ApprovalFlowSchemaRecord.tenant_id == tenant_id)
            .order_by(ApprovalFlowSchemaRecord.created_at)
        )
        return list(self._session.execute(stmt).scalars())

    def find_live_for_scope(
        self,
        tenant_id: str,
        shared_type: Any,
        project_code: str | None = None,
    ) -> ApprovalFlowSchemaRecord | None:
        """选自定义 live schema 驱动 J1（baseline 之外的项目级覆盖）。

        自定义 schema 在 payload_json["scope"] 携带 {shared_type, project_code?}；
        baseline / 未 scope 的 schema 无该键 → 自然被排除（baseline 路径不受影响，
        golden 回归安全）。匹配语义：
        - scope.project_code 缺省 → 该 shared_type 的所有项目通配；
        - scope.project_code == X → 仅当请求 project_code == X 命中。
        精确项目匹配优先于通配；同档取最高 version。无命中返 None（调用方回落 baseline）。

        live schema 是配置态（数量极小、非热路径），Python 侧过滤可接受，避开
        SQLite JSON-path 查询。
        """
        st = str(shared_type)
        stmt = (
            select(ApprovalFlowSchemaRecord)
            .where(
                ApprovalFlowSchemaRecord.tenant_id == tenant_id,
                ApprovalFlowSchemaRecord.status == "live",
            )
            .order_by(ApprovalFlowSchemaRecord.version.desc())
        )
        exact: ApprovalFlowSchemaRecord | None = None
        wildcard: ApprovalFlowSchemaRecord | None = None
        for record in self._session.execute(stmt).scalars():
            scope = (record.payload_json or {}).get("scope")
            if not isinstance(scope, dict):
                continue  # baseline / unscoped — 不作项目级覆盖
            if str(scope.get("shared_type")) != st:
                continue
            sc_proj = scope.get("project_code")
            if sc_proj is None:
                if wildcard is None:
                    wildcard = record
            elif project_code is not None and sc_proj == project_code:
                if exact is None:
                    exact = record
        return exact or wildcard

    # ---- internal ---------------------------------------------------------

    def _require(self, schema_id: str) -> ApprovalFlowSchemaRecord:
        record = self._session.get(ApprovalFlowSchemaRecord, schema_id)
        if record is None:
            raise ApprovalFlowTransitionError(f"approval flow schema not found: {schema_id}")
        if record.status not in _VALID_STATUSES:
            raise ApprovalFlowTransitionError(
                f"approval flow schema has invalid status {record.status!r}"
            )
        return record

    def _project_payload(
        self, record: ApprovalFlowSchemaRecord, payload: dict[str, Any]
    ) -> None:
        """payload_json 是单一事实源；同时投影到独立表方便后续 NL 草稿 / UI 编辑。"""
        rule_codes_to_ids: dict[str, str] = {}
        for rule in payload.get("selection_rules", []):
            row = ApprovalFlowSelectionRuleRecord(
                schema_id=record.id,
                rule_code=rule["rule_code"],
                rule_kind=rule["rule_kind"],
                rule_payload_json=rule.get("rule_payload_json", {}),
            )
            self._session.add(row)
            self._session.flush()
            rule_codes_to_ids[rule["rule_code"]] = row.id
        for index, node in enumerate(payload.get("nodes", [])):
            rule_code = node.get("selection_rule_code")
            self._session.add(
                ApprovalFlowNodeRecord(
                    schema_id=record.id,
                    node_code=node["node_code"],
                    node_name=node.get("node_name", node["node_code"]),
                    node_type=node["node_type"],
                    order_index=node.get("order_index", index),
                    selection_rule_id=rule_codes_to_ids.get(rule_code) if rule_code else None,
                )
            )
        for branch in payload.get("branches", []):
            self._session.add(
                ApprovalFlowBranchRecord(
                    schema_id=record.id,
                    from_node_code=branch["from_node_code"],
                    to_node_code=branch["to_node_code"],
                    condition_kind=branch.get("condition_kind", "always"),
                    condition_payload_json=branch.get("condition_payload_json", {}),
                )
            )
