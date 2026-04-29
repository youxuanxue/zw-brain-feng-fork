from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import ResourceAssetRecord, ResourceChannelBindingRecord
from zw_brain.domain.repositories.legacy_mapping import upsert_legacy_mapping_in_session
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


def _now() -> datetime:
    return datetime.now(UTC)


class ResourceApiRepository:
    def list_assets(self, *, tenant_id: str = "default") -> list[ResourceAssetRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(ResourceAssetRecord)
                    .where(ResourceAssetRecord.tenant_id == tenant_id)
                    .order_by(ResourceAssetRecord.resource_code)
                ).scalars()
            )

    def has_assets(self, *, tenant_id: str = "default") -> bool:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(ResourceAssetRecord.id).where(ResourceAssetRecord.tenant_id == tenant_id).limit(1)
            ).scalar_one_or_none() is not None

    def get_asset(self, resource_code: str, *, tenant_id: str = "default") -> ResourceAssetRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(ResourceAssetRecord).where(
                    ResourceAssetRecord.tenant_id == tenant_id,
                    ResourceAssetRecord.resource_code == resource_code,
                )
            ).scalar_one_or_none()

    def upsert_asset(self, payload: dict[str, Any], *, tenant_id: str = "default") -> ResourceAssetRecord:
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
                    catalog_code=payload.get("catalog_code"),
                    source_ref=payload.get("source_ref"),
                    summary_json=safe_json(payload.get("summary_json") or payload),
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.title = str(payload.get("title", record.title))
                record.lifecycle_status = str(payload.get("lifecycle_status", record.lifecycle_status))
                record.owner_org_id = payload.get("owner_org_id", record.owner_org_id)
                record.catalog_code = payload.get("catalog_code", record.catalog_code)
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

    def transition_asset(self, resource_code: str, status: str, *, tenant_id: str = "default") -> ResourceAssetRecord | None:
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

    def list_bindings(self, resource_code: str | None = None, *, tenant_id: str = "default") -> list[ResourceChannelBindingRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(ResourceChannelBindingRecord).where(ResourceChannelBindingRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(ResourceChannelBindingRecord.resource_code == resource_code)
            return list(session.execute(statement.order_by(ResourceChannelBindingRecord.binding_code)).scalars())

    def get_binding(self, binding_code: str, *, tenant_id: str = "default") -> ResourceChannelBindingRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(ResourceChannelBindingRecord).where(
                    ResourceChannelBindingRecord.tenant_id == tenant_id,
                    ResourceChannelBindingRecord.binding_code == binding_code,
                )
            ).scalar_one_or_none()

    def upsert_binding(self, payload: dict[str, Any], *, tenant_id: str = "default") -> ResourceChannelBindingRecord:
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
