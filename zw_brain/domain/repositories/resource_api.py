from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import (
    ResourceApiTestProjectionRecord,
    ResourceAssetRecord,
    ResourceChannelBindingRecord,
)
from zw_brain.domain.repositories.legacy_mapping import upsert_legacy_mapping_in_session
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


def _now() -> datetime:
    return datetime.now(UTC)


class ResourceApiRepository:
    def list_assets(self, *, tenant_id: str = "sd-default") -> list[ResourceAssetRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(ResourceAssetRecord)
                    .where(ResourceAssetRecord.tenant_id == tenant_id)
                    .order_by(ResourceAssetRecord.resource_code)
                ).scalars()
            )

    def has_assets(self, *, tenant_id: str = "sd-default") -> bool:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(ResourceAssetRecord.id).where(ResourceAssetRecord.tenant_id == tenant_id).limit(1)
            ).scalar_one_or_none() is not None

    def get_asset(self, resource_code: str, *, tenant_id: str = "sd-default") -> ResourceAssetRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(ResourceAssetRecord).where(
                    ResourceAssetRecord.tenant_id == tenant_id,
                    ResourceAssetRecord.resource_code == resource_code,
                )
            ).scalar_one_or_none()

    def upsert_asset(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> ResourceAssetRecord:
        SessionLocal = create_session_factory()
        now = _now()
        resource_code = str(payload["resource_code"])
        with SessionLocal() as session:
            record = session.execute(
                select(ResourceAssetRecord).where(
                    ResourceAssetRecord.tenant_id == tenant_id,
                    ResourceAssetRecord.resource_code == resource_code,
                )
            ).scalar_one_or_none()
            if record is None:
                record = ResourceAssetRecord(
                    tenant_id=tenant_id,
                    resource_code=resource_code,
                    resource_kind=str(payload.get("resource_kind", "api")),
                    title=str(payload.get("title", resource_code)),
                    lifecycle_status=str(payload.get("lifecycle_status", "draft")),
                    owner_org_id=payload.get("owner_org_id"),
                    owner_org_snapshot_json=safe_json(payload.get("owner_org_snapshot_json") or {}),
                    region_code=payload.get("region_code"),
                    catalog_code=payload.get("catalog_code"),
                    access_policy_json=safe_json(payload.get("access_policy_json") or {}),
                    qos_policy_json=safe_json(payload.get("qos_policy_json") or {}),
                    source_ref=payload.get("source_ref"),
                    summary_json=safe_json(payload.get("summary_json") or payload),
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.title = str(payload.get("title", record.title))
                record.resource_kind = str(payload.get("resource_kind", record.resource_kind))
                record.lifecycle_status = str(payload.get("lifecycle_status", record.lifecycle_status))
                record.owner_org_id = payload.get("owner_org_id", record.owner_org_id)
                record.owner_org_snapshot_json = safe_json(payload.get("owner_org_snapshot_json") or record.owner_org_snapshot_json)
                record.region_code = payload.get("region_code", record.region_code)
                record.catalog_code = payload.get("catalog_code", record.catalog_code)
                record.access_policy_json = safe_json(payload.get("access_policy_json") or record.access_policy_json)
                record.qos_policy_json = safe_json(payload.get("qos_policy_json") or record.qos_policy_json)
                record.source_ref = payload.get("source_ref", record.source_ref)
                record.summary_json = safe_json(payload.get("summary_json") or {**record.summary_json, **payload})
                record.updated_at = now
            upsert_legacy_mapping_in_session(
                session,
                {
                    "source_ref": record.source_ref,
                    "legacy_object_ref": payload.get("legacy_object_ref") or resource_code,
                    "canonical_type": "resource_asset",
                    "canonical_ref": resource_code,
                    "evidence_json": {"title": record.title, "resource_kind": record.resource_kind},
                },
                tenant_id=tenant_id,
            )
            session.commit()
            session.refresh(record)
            return record

    def transition_asset(self, resource_code: str, status: str, *, tenant_id: str = "sd-default") -> ResourceAssetRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(ResourceAssetRecord).where(
                    ResourceAssetRecord.tenant_id == tenant_id,
                    ResourceAssetRecord.resource_code == resource_code,
                )
            ).scalar_one_or_none()
            if record is None:
                return None
            record.lifecycle_status = status
            record.updated_at = _now()
            session.commit()
            session.refresh(record)
            return record

    def rebind_catalog_code(self, legacy_catalog_code: str, catalog_code: str, *, tenant_id: str = "sd-default") -> int:
        if legacy_catalog_code == catalog_code:
            return 0
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            records = list(
                session.execute(
                    select(ResourceAssetRecord).where(
                        ResourceAssetRecord.tenant_id == tenant_id,
                        ResourceAssetRecord.catalog_code == legacy_catalog_code,
                    )
                ).scalars()
            )
            for record in records:
                record.catalog_code = catalog_code
            session.commit()
            return len(records)

    def list_test_projections(self, resource_code: str | None = None, *, tenant_id: str = "sd-default") -> list[ResourceApiTestProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(ResourceApiTestProjectionRecord).where(ResourceApiTestProjectionRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(ResourceApiTestProjectionRecord.resource_code == resource_code)
            return list(session.execute(statement.order_by(ResourceApiTestProjectionRecord.tested_at)).scalars())

    def upsert_test_projection(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> ResourceApiTestProjectionRecord:
        SessionLocal = create_session_factory()
        now = _now()
        resource_code = str(payload["resource_code"])
        test_ref = str(payload.get("test_ref") or f"{resource_code}:{payload['test_result']}:{now.isoformat()}")
        with SessionLocal() as session:
            record = session.execute(
                select(ResourceApiTestProjectionRecord).where(
                    ResourceApiTestProjectionRecord.tenant_id == tenant_id,
                    ResourceApiTestProjectionRecord.test_ref == test_ref,
                )
            ).scalar_one_or_none()
            if record is None:
                record = ResourceApiTestProjectionRecord(
                    tenant_id=tenant_id,
                    test_ref=test_ref,
                    resource_code=resource_code,
                    binding_code=payload.get("binding_code"),
                    test_result=str(payload["test_result"]),
                    lifecycle_status=str(payload["lifecycle_status"]),
                    source_ref=payload.get("source_ref"),
                    evidence_json=safe_json(payload.get("evidence_json") or {}),
                    tested_by=payload.get("tested_by"),
                    tested_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.binding_code = payload.get("binding_code", record.binding_code)
                record.test_result = str(payload.get("test_result", record.test_result))
                record.lifecycle_status = str(payload.get("lifecycle_status", record.lifecycle_status))
                record.source_ref = payload.get("source_ref", record.source_ref)
                record.evidence_json = safe_json(payload.get("evidence_json") or record.evidence_json)
                record.tested_by = payload.get("tested_by", record.tested_by)
                record.tested_at = now
                record.updated_at = now
            upsert_legacy_mapping_in_session(
                session,
                {
                    "source_ref": record.source_ref or test_ref,
                    "legacy_object_ref": payload.get("legacy_object_ref") or test_ref,
                    "canonical_type": "resource_api_test_projection",
                    "canonical_ref": test_ref,
                    "evidence_json": {"resource_code": resource_code, "test_result": record.test_result},
                },
                tenant_id=tenant_id,
            )
            session.commit()
            session.refresh(record)
            return record

    def list_bindings(self, resource_code: str | None = None, *, tenant_id: str = "sd-default") -> list[ResourceChannelBindingRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(ResourceChannelBindingRecord).where(ResourceChannelBindingRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(ResourceChannelBindingRecord.resource_code == resource_code)
            return list(session.execute(statement.order_by(ResourceChannelBindingRecord.binding_code)).scalars())

    def get_binding(self, binding_code: str, *, tenant_id: str = "sd-default") -> ResourceChannelBindingRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(ResourceChannelBindingRecord).where(
                    ResourceChannelBindingRecord.tenant_id == tenant_id,
                    ResourceChannelBindingRecord.binding_code == binding_code,
                )
            ).scalar_one_or_none()

    def upsert_binding(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> ResourceChannelBindingRecord:
        SessionLocal = create_session_factory()
        now = _now()
        binding_code = str(payload["binding_code"])
        with SessionLocal() as session:
            record = session.execute(
                select(ResourceChannelBindingRecord).where(
                    ResourceChannelBindingRecord.tenant_id == tenant_id,
                    ResourceChannelBindingRecord.binding_code == binding_code,
                )
            ).scalar_one_or_none()
            if record is None:
                record = ResourceChannelBindingRecord(
                    tenant_id=tenant_id,
                    binding_code=binding_code,
                    resource_code=str(payload["resource_code"]),
                    channel_kind=str(payload.get("channel_kind", "api_gateway")),
                    route_ref=payload.get("route_ref"),
                    endpoint_ref=safe_json(payload.get("endpoint_ref") or {}),
                    schema_ref=safe_json(payload.get("schema_ref") or {}),
                    auth_ref=payload.get("auth_ref"),
                    request_schema_json=safe_json(payload.get("request_schema_json")),
                    response_schema_json=safe_json(payload.get("response_schema_json")),
                    gateway_policy_json=safe_json(payload.get("gateway_policy_json")),
                    lifecycle_status=str(payload.get("lifecycle_status", "draft")),
                    source_ref=payload.get("source_ref"),
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.resource_code = str(payload.get("resource_code", record.resource_code))
                record.channel_kind = str(payload.get("channel_kind", record.channel_kind))
                record.route_ref = payload.get("route_ref", record.route_ref)
                record.endpoint_ref = safe_json(payload.get("endpoint_ref") or record.endpoint_ref)
                record.schema_ref = safe_json(payload.get("schema_ref") or record.schema_ref)
                record.auth_ref = payload.get("auth_ref", record.auth_ref)
                record.request_schema_json = safe_json(payload.get("request_schema_json") or record.request_schema_json)
                record.response_schema_json = safe_json(payload.get("response_schema_json") or record.response_schema_json)
                record.gateway_policy_json = safe_json(payload.get("gateway_policy_json") or record.gateway_policy_json)
                record.lifecycle_status = str(payload.get("lifecycle_status", record.lifecycle_status))
                record.source_ref = payload.get("source_ref", record.source_ref)
                record.updated_at = now
            upsert_legacy_mapping_in_session(
                session,
                {
                    "source_ref": record.source_ref,
                    "legacy_object_ref": payload.get("legacy_object_ref") or binding_code,
                    "canonical_type": "resource_channel_binding",
                    "canonical_ref": binding_code,
                    "evidence_json": {"resource_code": record.resource_code, "channel_kind": record.channel_kind},
                },
                tenant_id=tenant_id,
            )
            session.commit()
            session.refresh(record)
            return record
