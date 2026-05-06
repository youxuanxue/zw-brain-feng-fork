from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import (
    ComplianceCaseRecord,
    ComplianceRuleRecord,
    HealthSignalProjectionRecord,
    MetricDefinitionProjectionRecord,
    RiskEventProjectionRecord,
    StandardAssetProjectionRecord,
)
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


def _now() -> datetime:
    return datetime.now(UTC)


class ComplianceOpsRepository:
    """Compliance/ops projections (M1–M6).

    Read paths are eventually consumed by Dashboard / P6 surfaces; write paths come from
    the legacy importer (mappers/projections.py) and from the `compliance.*`,
    `risk.event.ingest`, `adapter.health.probe`, `standard.asset.sync` skills.
    """

    def upsert_case(self, payload: dict[str, Any], *, tenant_id: str) -> ComplianceCaseRecord:
        data = {
            "tenant_id": tenant_id,
            "case_code": str(payload["case_code"]),
            "case_kind": str(payload.get("case_kind", "timeout")),
            "target_type": str(payload.get("target_type", "unknown")),
            "target_ref": str(payload.get("target_ref", "")),
            "severity": str(payload.get("severity", "medium")),
            "status": str(payload.get("status", "detected")),
            "assignee_org_id": payload.get("assignee_org_id"),
            "assignee_snapshot_json": safe_json(payload.get("assignee_snapshot_json") or {}),
            "detected_summary": str(payload.get("detected_summary", "")),
            "resolved_summary": payload.get("resolved_summary"),
            "evidence_json": safe_json(payload.get("evidence_json") or {}),
            "source_ref": payload.get("source_ref"),
            "closed_at": payload.get("closed_at"),
        }
        return self._upsert(
            ComplianceCaseRecord,
            [
                ComplianceCaseRecord.tenant_id == tenant_id,
                ComplianceCaseRecord.case_code == data["case_code"],
            ],
            data,
        )

    def upsert_rule(self, payload: dict[str, Any], *, tenant_id: str) -> ComplianceRuleRecord:
        data = {
            "tenant_id": tenant_id,
            "rule_code": str(payload["rule_code"]),
            "rule_kind": str(payload.get("rule_kind", "timeout")),
            "target_scope": str(payload.get("target_scope", "all")),
            "title": str(payload.get("title", payload["rule_code"])),
            "threshold_json": safe_json(payload.get("threshold_json") or {}),
            "review_status": str(payload.get("review_status", "pending_review")),
            "source_ref": payload.get("source_ref"),
        }
        return self._upsert(
            ComplianceRuleRecord,
            [
                ComplianceRuleRecord.tenant_id == tenant_id,
                ComplianceRuleRecord.rule_code == data["rule_code"],
            ],
            data,
        )

    def upsert_risk_event(self, payload: dict[str, Any], *, tenant_id: str) -> RiskEventProjectionRecord:
        data = {
            "tenant_id": tenant_id,
            "event_kind": str(payload.get("event_kind", "abnormal")),
            "severity": str(payload.get("severity", "medium")),
            "source_system": str(payload["source_system"]),
            "source_ref": str(payload["source_ref"]),
            "target_type": payload.get("target_type"),
            "target_ref": payload.get("target_ref"),
            "detected_at": payload.get("detected_at") or _now(),
            "summary_json": safe_json(payload.get("summary_json") or {}),
        }
        return self._upsert(
            RiskEventProjectionRecord,
            [
                RiskEventProjectionRecord.tenant_id == tenant_id,
                RiskEventProjectionRecord.source_system == data["source_system"],
                RiskEventProjectionRecord.source_ref == data["source_ref"],
            ],
            data,
            updated_field="generated_at",
        )

    def upsert_health_signal(self, payload: dict[str, Any], *, tenant_id: str) -> HealthSignalProjectionRecord:
        data = {
            "tenant_id": tenant_id,
            "subject_kind": str(payload["subject_kind"]),
            "subject_ref": str(payload["subject_ref"]),
            "status": str(payload.get("status", "unknown")),
            "metric_json": safe_json(payload.get("metric_json") or {}),
            "last_observed_at": payload.get("last_observed_at"),
            "source_ref": payload.get("source_ref"),
        }
        return self._upsert(
            HealthSignalProjectionRecord,
            [
                HealthSignalProjectionRecord.tenant_id == tenant_id,
                HealthSignalProjectionRecord.subject_kind == data["subject_kind"],
                HealthSignalProjectionRecord.subject_ref == data["subject_ref"],
            ],
            data,
            updated_field="generated_at",
        )

    def upsert_standard_asset(self, payload: dict[str, Any], *, tenant_id: str) -> StandardAssetProjectionRecord:
        data = {
            "tenant_id": tenant_id,
            "asset_kind": str(payload["asset_kind"]),
            "asset_ref": str(payload["asset_ref"]),
            "title": str(payload.get("title", payload["asset_ref"])),
            "status": str(payload.get("status", "candidate")),
            "source_system": str(payload.get("source_system", "legacy")),
            "source_ref": payload.get("source_ref"),
            "evidence_json": safe_json(payload.get("evidence_json") or {}),
        }
        return self._upsert(
            StandardAssetProjectionRecord,
            [
                StandardAssetProjectionRecord.tenant_id == tenant_id,
                StandardAssetProjectionRecord.asset_kind == data["asset_kind"],
                StandardAssetProjectionRecord.asset_ref == data["asset_ref"],
            ],
            data,
            updated_field="generated_at",
        )

    def upsert_metric_definition(self, payload: dict[str, Any], *, tenant_id: str) -> MetricDefinitionProjectionRecord:
        data = {
            "tenant_id": tenant_id,
            "metric_code": str(payload["metric_code"]),
            "title": str(payload.get("title", payload["metric_code"])),
            "metric_kind": str(payload.get("metric_kind", "count")),
            "target_aggregate": str(payload.get("target_aggregate", "unknown")),
            "dimension_json": safe_json(payload.get("dimension_json") or {}),
            "formula_ref": payload.get("formula_ref"),
            "owner_org_id": payload.get("owner_org_id"),
            "source_ref": payload.get("source_ref"),
        }
        return self._upsert(
            MetricDefinitionProjectionRecord,
            [
                MetricDefinitionProjectionRecord.tenant_id == tenant_id,
                MetricDefinitionProjectionRecord.metric_code == data["metric_code"],
            ],
            data,
            updated_field="generated_at",
        )

    def list_cases(self, *, tenant_id: str, status: str | None = None) -> list[ComplianceCaseRecord]:
        statement = select(ComplianceCaseRecord).where(ComplianceCaseRecord.tenant_id == tenant_id)
        if status:
            statement = statement.where(ComplianceCaseRecord.status == status)
        return self._list(statement.order_by(ComplianceCaseRecord.created_at.desc()))

    def list_rules(self, *, tenant_id: str, review_status: str | None = None) -> list[ComplianceRuleRecord]:
        statement = select(ComplianceRuleRecord).where(ComplianceRuleRecord.tenant_id == tenant_id)
        if review_status:
            statement = statement.where(ComplianceRuleRecord.review_status == review_status)
        return self._list(statement.order_by(ComplianceRuleRecord.rule_code))

    def list_risk_events(self, *, tenant_id: str, event_kind: str | None = None) -> list[RiskEventProjectionRecord]:
        statement = select(RiskEventProjectionRecord).where(RiskEventProjectionRecord.tenant_id == tenant_id)
        if event_kind:
            statement = statement.where(RiskEventProjectionRecord.event_kind == event_kind)
        return self._list(statement.order_by(RiskEventProjectionRecord.detected_at.desc()))

    def list_health_signals(self, *, tenant_id: str, subject_kind: str | None = None) -> list[HealthSignalProjectionRecord]:
        statement = select(HealthSignalProjectionRecord).where(HealthSignalProjectionRecord.tenant_id == tenant_id)
        if subject_kind:
            statement = statement.where(HealthSignalProjectionRecord.subject_kind == subject_kind)
        return self._list(statement.order_by(HealthSignalProjectionRecord.subject_ref))

    def list_standard_assets(self, *, tenant_id: str, asset_kind: str | None = None) -> list[StandardAssetProjectionRecord]:
        statement = select(StandardAssetProjectionRecord).where(StandardAssetProjectionRecord.tenant_id == tenant_id)
        if asset_kind:
            statement = statement.where(StandardAssetProjectionRecord.asset_kind == asset_kind)
        return self._list(statement.order_by(StandardAssetProjectionRecord.asset_ref))

    def list_metric_definitions(self, *, tenant_id: str) -> list[MetricDefinitionProjectionRecord]:
        return self._list(
            select(MetricDefinitionProjectionRecord)
            .where(MetricDefinitionProjectionRecord.tenant_id == tenant_id)
            .order_by(MetricDefinitionProjectionRecord.metric_code)
        )

    def _upsert(self, model: Any, where: list[Any], data: dict[str, Any], *, updated_field: str = "updated_at") -> Any:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(model).where(*where)).scalar_one_or_none()
            if record is None:
                if updated_field == "generated_at" and "generated_at" not in data:
                    data = {**data, "generated_at": _now()}
                record = model(**data)
                session.add(record)
                session.flush()
            else:
                for key, value in data.items():
                    setattr(record, key, value)
                setattr(record, updated_field, _now())
            session.commit()
            return session.execute(select(model).where(model.id == record.id)).scalar_one()

    def _list(self, statement: Any) -> list[Any]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(statement).scalars())
