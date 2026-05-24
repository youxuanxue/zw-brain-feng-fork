"""E3 Wave-2 三引擎 F6 — 推荐规则模板状态机 + 仓库 helper。

承接 R14（草稿→预览→入库）；与 [[approval-flow-schema]] / [[form-schema]] 同形。
本仓库只管规则模板（项目级管理员配置物）；执行引擎在 [[recommendation-engine]]。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from zw_brain.domain.models import (
    RecommendationRuleClauseRecord,
    RecommendationRuleRecord,
)

RecommendationRuleStatus = Literal["draft", "preview", "live"]

_VALID_STATUSES: set[str] = {"draft", "preview", "live"}
_VALID_CLAUSE_KINDS: set[str] = {
    "keyword_match",
    "category_match",
    "org_affinity",
    "usage_frequency",
    "fuzzy_text",
    "negative_filter",
}


class RecommendationRuleTransitionError(ValueError):
    """draft/preview/live 状态机非法跃迁。"""


class RecommendationRulePayloadError(ValueError):
    """payload_json 结构校验失败。"""


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise RecommendationRulePayloadError("payload must be a dict")
    if "clauses" not in payload:
        raise RecommendationRulePayloadError("payload missing required key: clauses")
    clauses = payload["clauses"]
    if not isinstance(clauses, list) or not clauses:
        raise RecommendationRulePayloadError("payload.clauses must be a non-empty list")

    clause_codes: list[str] = []
    for clause in clauses:
        if not isinstance(clause, dict):
            raise RecommendationRulePayloadError("each clause must be a dict")
        code = clause.get("clause_code")
        kind = clause.get("clause_kind")
        weight = clause.get("weight", 1.0)
        if not isinstance(code, str) or not code:
            raise RecommendationRulePayloadError("clause.clause_code is required")
        if code in clause_codes:
            raise RecommendationRulePayloadError(f"duplicate clause_code: {code}")
        clause_codes.append(code)
        if kind not in _VALID_CLAUSE_KINDS:
            raise RecommendationRulePayloadError(
                f"clause.clause_kind must be one of {sorted(_VALID_CLAUSE_KINDS)}, got {kind!r}"
            )
        try:
            if float(weight) <= 0:
                raise RecommendationRulePayloadError(
                    f"clause.weight must be > 0, got {weight!r}"
                )
        except (TypeError, ValueError) as exc:
            raise RecommendationRulePayloadError(
                f"clause.weight must be numeric, got {weight!r}"
            ) from exc


class RecommendationRuleRepo:
    """三态状态机（draft → preview → live）+ payload 结构校验仓库。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ---- mutation ---------------------------------------------------------

    def create_draft(
        self,
        tenant_id: str,
        rule_code: str,
        title: str,
        payload: dict[str, Any],
        *,
        source_kind: str = "manual",
        draft_source_text: str | None = None,
        created_by: str,
    ) -> RecommendationRuleRecord:
        _validate_payload(payload)
        record = RecommendationRuleRecord(
            tenant_id=tenant_id,
            rule_code=rule_code,
            title=title,
            status="draft",
            version=1,
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

    def promote_to_preview(self, rule_id: str) -> RecommendationRuleRecord:
        record = self._require(rule_id)
        if record.status != "draft":
            raise RecommendationRuleTransitionError(
                f"promote_to_preview requires status=draft, got {record.status!r}"
            )
        _validate_payload(record.payload_json)
        record.status = "preview"
        record.updated_at = _now()
        self._session.commit()
        return record

    def revert_to_draft(self, rule_id: str) -> RecommendationRuleRecord:
        record = self._require(rule_id)
        if record.status != "preview":
            raise RecommendationRuleTransitionError(
                f"revert_to_draft requires status=preview, got {record.status!r}"
            )
        record.status = "draft"
        record.updated_at = _now()
        self._session.commit()
        return record

    def commit_to_live(self, rule_id: str) -> RecommendationRuleRecord:
        record = self._require(rule_id)
        if record.status != "preview":
            raise RecommendationRuleTransitionError(
                f"commit_to_live requires status=preview, got {record.status!r}"
            )
        _validate_payload(record.payload_json)
        now = _now()
        record.status = "live"
        record.version = (record.version or 1) + 1
        record.committed_at = now
        record.updated_at = now
        self._session.commit()
        return record

    # ---- read -------------------------------------------------------------

    def get(self, rule_id: str) -> RecommendationRuleRecord:
        return self._require(rule_id)

    def list_by_tenant(self, tenant_id: str) -> list[RecommendationRuleRecord]:
        stmt = (
            select(RecommendationRuleRecord)
            .where(RecommendationRuleRecord.tenant_id == tenant_id)
            .order_by(RecommendationRuleRecord.created_at)
        )
        return list(self._session.execute(stmt).scalars())

    def list_live(self, tenant_id: str) -> list[RecommendationRuleRecord]:
        stmt = (
            select(RecommendationRuleRecord)
            .where(
                RecommendationRuleRecord.tenant_id == tenant_id,
                RecommendationRuleRecord.status == "live",
            )
            .order_by(RecommendationRuleRecord.created_at)
        )
        return list(self._session.execute(stmt).scalars())

    # ---- internal ---------------------------------------------------------

    def _require(self, rule_id: str) -> RecommendationRuleRecord:
        record = self._session.get(RecommendationRuleRecord, rule_id)
        if record is None:
            raise RecommendationRuleTransitionError(
                f"recommendation rule not found: {rule_id}"
            )
        if record.status not in _VALID_STATUSES:
            raise RecommendationRuleTransitionError(
                f"recommendation rule has invalid status {record.status!r}"
            )
        return record

    def _project_payload(
        self, record: RecommendationRuleRecord, payload: dict[str, Any]
    ) -> None:
        for index, clause in enumerate(payload.get("clauses", [])):
            self._session.add(
                RecommendationRuleClauseRecord(
                    rule_id=record.id,
                    clause_code=clause["clause_code"],
                    clause_kind=clause["clause_kind"],
                    clause_payload_json=clause.get("clause_payload_json", {}),
                    weight=float(clause.get("weight", 1.0)),
                    order_index=clause.get("order_index", index),
                )
            )
