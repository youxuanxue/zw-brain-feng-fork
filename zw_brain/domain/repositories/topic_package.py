from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from zw_brain.domain.models import (
    TopicPackageEvidenceRecord,
    TopicPackageItemRecord,
    TopicPackageMetricProjectionRecord,
    TopicPackageRecord,
    TopicPackageReviewRecord,
    TopicPackageVisibilityRecord,
)
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


def _now() -> datetime:
    return datetime.now(UTC)


class TopicPackageStateError(ValueError):
    pass


class TopicPackageRepository:
    TRANSITIONS = {
        "draft": {"configuring", "submitted", "offline"},
        "configuring": {"configured", "submitted", "offline"},
        "configured": {"submitted", "offline"},
        "submitted": {"published", "rejected"},
        "published": {"offline_pending", "offline"},
        "rejected": {"configuring", "submitted"},
        "offline_pending": {"offline", "published"},
        "offline": {"configuring"},
    }

    def create_package(self, payload: dict[str, Any], *, tenant_id: str = "default") -> TopicPackageRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            package_code = str(payload["package_code"])
            existing = session.execute(
                select(TopicPackageRecord).where(TopicPackageRecord.tenant_id == tenant_id, TopicPackageRecord.package_code == package_code)
            ).scalar_one_or_none()
            data = {
                "tenant_id": tenant_id,
                "package_code": package_code,
                "title": str(payload.get("title", package_code)),
                "scenario": str(payload.get("scenario", "一表通 / 基层报表减负")),
                "owner_org_id": payload.get("owner_org_id"),
                "owner_org_snapshot_json": safe_json(payload.get("owner_org_snapshot_json") or {}),
                "status": str(payload.get("status", "draft")),
                "display_snapshot_json": safe_json(payload.get("display_snapshot_json") or payload.get("display_snapshot") or {}),
                "metric_snapshot_json": safe_json(payload.get("metric_snapshot_json") or {}),
                "source_ref": payload.get("source_ref"),
            }
            if existing is None:
                existing = TopicPackageRecord(**data)
                session.add(existing)
                session.flush()
            else:
                for key, value in data.items():
                    setattr(existing, key, value)
            self._add_review_in_session(
                session,
                tenant_id,
                package_code,
                action_type="create",
                action_result="pass",
                from_status=None,
                to_status=existing.status,
                reviewer_snapshot_json=payload.get("actor_snapshot_json") or {},
                opinion=payload.get("description"),
                evidence_json=payload.get("evidence_json") or {},
            )
            session.commit()
            return session.execute(select(TopicPackageRecord).where(TopicPackageRecord.id == existing.id)).scalar_one()

    def configure_package(self, package_code: str, payload: dict[str, Any], *, tenant_id: str = "default") -> TopicPackageRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = self._get_package_in_session(session, tenant_id, package_code)
            if record is None:
                raise KeyError(package_code)
            if record.status == "draft":
                record.status = "configuring"
            if payload.get("title"):
                record.title = str(payload["title"])
            if payload.get("scenario"):
                record.scenario = str(payload["scenario"])
            if payload.get("display_snapshot_json") or payload.get("display_snapshot"):
                record.display_snapshot_json = safe_json(payload.get("display_snapshot_json") or payload.get("display_snapshot") or {})
            for item in payload.get("items") or []:
                self._upsert_item_in_session(session, tenant_id, package_code, item)
            for visibility in payload.get("visibility") or payload.get("visibilities") or []:
                self._upsert_visibility_in_session(session, tenant_id, package_code, visibility)
            self._add_review_in_session(
                session,
                tenant_id,
                package_code,
                action_type="configure",
                action_result="pass",
                from_status=record.status,
                to_status=record.status,
                reviewer_snapshot_json=payload.get("actor_snapshot_json") or {},
                opinion=payload.get("opinion"),
                evidence_json=payload.get("evidence_json") or {},
            )
            session.commit()
            return session.execute(select(TopicPackageRecord).where(TopicPackageRecord.id == record.id)).scalar_one()

    def transition_package(self, package_code: str, next_status: str, payload: dict[str, Any], *, tenant_id: str = "default") -> TopicPackageRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = self._get_package_in_session(session, tenant_id, package_code)
            if record is None:
                raise KeyError(package_code)
            if next_status not in self.TRANSITIONS.get(record.status, set()):
                raise TopicPackageStateError(f"invalid topic package transition: {record.status} -> {next_status}")
            if next_status == "published" and not self._publishable_in_session(session, tenant_id, package_code):
                raise TopicPackageStateError("topic package must have item and approved visibility before publish")
            from_status = record.status
            record.status = next_status
            record.updated_at = _now()
            self._add_review_in_session(
                session,
                tenant_id,
                package_code,
                action_type=str(payload.get("action_type", "transition")),
                action_result=str(payload.get("action_result", "pass")),
                from_status=from_status,
                to_status=next_status,
                reviewer_snapshot_json=payload.get("actor_snapshot_json") or {},
                opinion=payload.get("opinion"),
                evidence_json=payload.get("evidence_json") or {},
            )
            session.commit()
            return session.execute(select(TopicPackageRecord).where(TopicPackageRecord.id == record.id)).scalar_one()

    def update_policy(self, package_code: str, payload: dict[str, Any], *, tenant_id: str = "default") -> list[TopicPackageVisibilityRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            if self._get_package_in_session(session, tenant_id, package_code) is None:
                raise KeyError(package_code)
            records = [self._upsert_visibility_in_session(session, tenant_id, package_code, item) for item in payload.get("visibility", payload.get("visibilities", []))]
            self._add_review_in_session(
                session,
                tenant_id,
                package_code,
                action_type="policy_update",
                action_result="pass",
                from_status=None,
                to_status="policy_updated",
                reviewer_snapshot_json=payload.get("actor_snapshot_json") or {},
                opinion=payload.get("opinion"),
                evidence_json=payload.get("evidence_json") or {},
            )
            session.commit()
            return [session.execute(select(TopicPackageVisibilityRecord).where(TopicPackageVisibilityRecord.id == item.id)).scalar_one() for item in records]

    def attach_evidence(self, package_code: str, payload: dict[str, Any], *, tenant_id: str = "default") -> TopicPackageEvidenceRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            if self._get_package_in_session(session, tenant_id, package_code) is None:
                raise KeyError(package_code)
            record = TopicPackageEvidenceRecord(
                tenant_id=tenant_id,
                package_code=package_code,
                evidence_type=str(payload.get("evidence_type", "case_evidence")),
                title=str(payload.get("title", payload.get("evidence_type", "专题证据"))),
                related_ref_type=payload.get("related_ref_type"),
                related_ref_id=payload.get("related_ref_id"),
                content_json=safe_json(payload.get("content_json") or payload),
                submitted_by_json=safe_json(payload.get("submitted_by_json") or payload.get("actor_snapshot_json") or {}),
            )
            session.add(record)
            session.commit()
            return session.execute(select(TopicPackageEvidenceRecord).where(TopicPackageEvidenceRecord.id == record.id)).scalar_one()

    def upsert_metric(self, package_code: str, payload: dict[str, Any], *, tenant_id: str = "default") -> TopicPackageMetricProjectionRecord:
        metric_key = str(payload["metric_key"])
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(TopicPackageMetricProjectionRecord).where(
                    TopicPackageMetricProjectionRecord.tenant_id == tenant_id,
                    TopicPackageMetricProjectionRecord.package_code == package_code,
                    TopicPackageMetricProjectionRecord.metric_key == metric_key,
                )
            ).scalar_one_or_none()
            data = {
                "tenant_id": tenant_id,
                "package_code": package_code,
                "metric_key": metric_key,
                "metric_value": int(payload.get("metric_value", 0)),
                "metric_json": safe_json(payload.get("metric_json") or {}),
            }
            if record is None:
                record = TopicPackageMetricProjectionRecord(**data)
                session.add(record)
                session.flush()
            else:
                for key, value in data.items():
                    setattr(record, key, value)
                record.updated_at = _now()
            session.commit()
            return session.execute(select(TopicPackageMetricProjectionRecord).where(TopicPackageMetricProjectionRecord.id == record.id)).scalar_one()

    def list_packages(self, *, tenant_id: str = "default", status: str | None = None) -> list[TopicPackageRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(TopicPackageRecord).where(TopicPackageRecord.tenant_id == tenant_id)
            if status:
                statement = statement.where(TopicPackageRecord.status == status)
            return list(session.execute(statement.order_by(TopicPackageRecord.updated_at)).scalars())

    def get_package(self, package_code: str, *, tenant_id: str = "default") -> TopicPackageRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(select(TopicPackageRecord).where(TopicPackageRecord.tenant_id == tenant_id, TopicPackageRecord.package_code == package_code)).scalar_one_or_none()

    def list_items(self, package_code: str, *, tenant_id: str = "default") -> list[TopicPackageItemRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(TopicPackageItemRecord).where(TopicPackageItemRecord.tenant_id == tenant_id, TopicPackageItemRecord.package_code == package_code).order_by(TopicPackageItemRecord.display_order)).scalars())

    def list_visibility(self, package_code: str, *, tenant_id: str = "default") -> list[TopicPackageVisibilityRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(TopicPackageVisibilityRecord).where(TopicPackageVisibilityRecord.tenant_id == tenant_id, TopicPackageVisibilityRecord.package_code == package_code).order_by(TopicPackageVisibilityRecord.visibility_code)).scalars())

    def list_review_records(self, package_code: str, *, tenant_id: str = "default") -> list[TopicPackageReviewRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(TopicPackageReviewRecord).where(TopicPackageReviewRecord.tenant_id == tenant_id, TopicPackageReviewRecord.package_code == package_code).order_by(TopicPackageReviewRecord.created_at)).scalars())

    def list_evidence(self, package_code: str, *, tenant_id: str = "default") -> list[TopicPackageEvidenceRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(TopicPackageEvidenceRecord).where(TopicPackageEvidenceRecord.tenant_id == tenant_id, TopicPackageEvidenceRecord.package_code == package_code).order_by(TopicPackageEvidenceRecord.created_at)).scalars())

    def list_metrics(self, package_code: str, *, tenant_id: str = "default") -> list[TopicPackageMetricProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(TopicPackageMetricProjectionRecord).where(TopicPackageMetricProjectionRecord.tenant_id == tenant_id, TopicPackageMetricProjectionRecord.package_code == package_code).order_by(TopicPackageMetricProjectionRecord.metric_key)).scalars())

    def import_legacy_sharezone(self, payload: dict[str, Any], *, tenant_id: str = "default") -> TopicPackageRecord:
        status_map = {"0": "draft", "1": "configuring", "2": "configured", "3": "submitted", "4": "published", "6": "rejected", "-1": "offline"}
        package = self.create_package(
            {
                "package_code": payload.get("package_code") or f"topic-{payload.get('legacy_id', payload.get('zone_id', 'legacy'))}",
                "title": payload.get("title") or payload.get("name") or "旧共享专区候选",
                "owner_org_id": payload.get("org_code"),
                "owner_org_snapshot_json": {"org_code": payload.get("org_code"), "org_name": payload.get("org_name")},
                "status": status_map.get(str(payload.get("status", "0")), "draft"),
                "display_snapshot_json": safe_json(payload.get("display_snapshot_json") or payload),
                "source_ref": payload.get("source_ref") or "dsp-sharezone:share_zone",
                "actor_snapshot_json": payload.get("actor_snapshot_json") or {},
            },
            tenant_id=tenant_id,
        )
        if payload.get("items") or payload.get("visibility"):
            self.configure_package(package.package_code, payload, tenant_id=tenant_id)
        return self.get_package(package.package_code, tenant_id=tenant_id) or package

    def _get_package_in_session(self, session: Any, tenant_id: str, package_code: str) -> TopicPackageRecord | None:
        return session.execute(select(TopicPackageRecord).where(TopicPackageRecord.tenant_id == tenant_id, TopicPackageRecord.package_code == package_code)).scalar_one_or_none()

    def _publishable_in_session(self, session: Any, tenant_id: str, package_code: str) -> bool:
        has_item = session.execute(select(TopicPackageItemRecord).where(TopicPackageItemRecord.tenant_id == tenant_id, TopicPackageItemRecord.package_code == package_code)).first() is not None
        has_visibility = session.execute(select(TopicPackageVisibilityRecord).where(TopicPackageVisibilityRecord.tenant_id == tenant_id, TopicPackageVisibilityRecord.package_code == package_code, TopicPackageVisibilityRecord.policy_status == "approved")).first() is not None
        return has_item and has_visibility

    def _upsert_item_in_session(self, session: Any, tenant_id: str, package_code: str, item: dict[str, Any]) -> TopicPackageItemRecord:
        item_code = str(item.get("item_code") or f"{item.get('ref_type', 'ref')}:{item.get('ref_id', item.get('id', 'unknown'))}")
        record = session.execute(select(TopicPackageItemRecord).where(TopicPackageItemRecord.tenant_id == tenant_id, TopicPackageItemRecord.package_code == package_code, TopicPackageItemRecord.item_code == item_code)).scalar_one_or_none()
        data = {
            "tenant_id": tenant_id,
            "package_code": package_code,
            "item_code": item_code,
            "ref_type": str(item.get("ref_type", "unresolved")),
            "ref_id": str(item.get("ref_id", item.get("id", "unresolved"))),
            "ref_status": str(item.get("ref_status", "active")),
            "title": str(item.get("title", item_code)),
            "display_order": int(item.get("display_order", 0)),
            "summary_json": safe_json(item.get("summary_json") or item.get("summary") or {}),
        }
        if record is None:
            record = TopicPackageItemRecord(**data)
            session.add(record)
            session.flush()
        else:
            for key, value in data.items():
                setattr(record, key, value)
        return record

    def _upsert_visibility_in_session(self, session: Any, tenant_id: str, package_code: str, item: dict[str, Any]) -> TopicPackageVisibilityRecord:
        visibility_code = str(item.get("visibility_code") or f"{item.get('org_code', '*')}:{item.get('role_code', '*')}:{item.get('surface', 'webui')}:{item.get('intent', 'view')}")
        record = session.execute(select(TopicPackageVisibilityRecord).where(TopicPackageVisibilityRecord.tenant_id == tenant_id, TopicPackageVisibilityRecord.package_code == package_code, TopicPackageVisibilityRecord.visibility_code == visibility_code)).scalar_one_or_none()
        data = {
            "tenant_id": tenant_id,
            "package_code": package_code,
            "visibility_code": visibility_code,
            "org_code": item.get("org_code"),
            "role_code": item.get("role_code"),
            "region_code": item.get("region_code"),
            "surface": str(item.get("surface", "webui")),
            "intent": str(item.get("intent", "view")),
            "policy_status": str(item.get("policy_status", "pending_review")),
            "condition_json": safe_json(item.get("condition_json") or item.get("condition") or {}),
        }
        if record is None:
            record = TopicPackageVisibilityRecord(**data)
            session.add(record)
            session.flush()
        else:
            for key, value in data.items():
                setattr(record, key, value)
        return record

    def _add_review_in_session(
        self,
        session: Any,
        tenant_id: str,
        package_code: str,
        *,
        action_type: str,
        action_result: str,
        from_status: str | None,
        to_status: str,
        reviewer_snapshot_json: dict[str, Any],
        opinion: str | None,
        evidence_json: dict[str, Any],
    ) -> None:
        session.add(
            TopicPackageReviewRecord(
                tenant_id=tenant_id,
                package_code=package_code,
                action_type=action_type,
                action_result=action_result,
                from_status=from_status,
                to_status=to_status,
                reviewer_snapshot_json=safe_json(reviewer_snapshot_json),
                opinion=opinion,
                evidence_json=safe_json(evidence_json),
            )
        )
