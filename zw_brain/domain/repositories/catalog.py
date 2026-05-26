from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select

from zw_brain.domain.models import (
    CatalogEntryRecord,
    CatalogEntryVersionRecord,
    CatalogItemRecord,
    CatalogModelFieldRecord,
    CatalogModelRecord,
)
from zw_brain.domain.repositories.legacy_mapping import upsert_legacy_mapping_in_session
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


class CatalogRepository:
    def list_models(self, *, tenant_id: str = "sd-default") -> list[CatalogModelRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(CatalogModelRecord)
                    .where(CatalogModelRecord.tenant_id == tenant_id)
                    .order_by(CatalogModelRecord.model_code)
                ).scalars()
            )

    def upsert_model(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> CatalogModelRecord:
        SessionLocal = create_session_factory()
        model_code = str(payload["model_code"])
        with SessionLocal() as session:
            record = session.execute(
                select(CatalogModelRecord).where(
                    CatalogModelRecord.tenant_id == tenant_id,
                    CatalogModelRecord.model_code == model_code,
                )
            ).scalar_one_or_none()
            if record is None:
                record = CatalogModelRecord(
                    tenant_id=tenant_id,
                    model_code=model_code,
                    title=str(payload.get("title", model_code)),
                    status=str(payload.get("status", "draft")),
                    owner_org_id=payload.get("owner_org_id"),
                    model_schema_json=safe_json(payload.get("model_schema_json") or {}),
                    source_ref=payload.get("source_ref"),
                )
                session.add(record)
            else:
                record.title = str(payload.get("title", record.title))
                record.status = str(payload.get("status", record.status))
                record.owner_org_id = payload.get("owner_org_id", record.owner_org_id)
                record.model_schema_json = safe_json(payload.get("model_schema_json") or record.model_schema_json)
                record.source_ref = payload.get("source_ref", record.source_ref)
            if record.source_ref:
                upsert_legacy_mapping_in_session(
                    session,
                    {
                        "source_ref": record.source_ref,
                        "legacy_object_ref": payload.get("legacy_object_ref") or model_code,
                        "canonical_type": "catalog_model",
                        "canonical_ref": model_code,
                        "evidence_json": {"title": record.title, "status": record.status},
                    },
                    tenant_id=tenant_id,
                )
            session.commit()
            session.refresh(record)
            return record

    def upsert_model_field(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> CatalogModelFieldRecord:
        SessionLocal = create_session_factory()
        model_code = str(payload["model_code"])
        field_code = str(payload["field_code"])
        with SessionLocal() as session:
            record = session.execute(
                select(CatalogModelFieldRecord).where(
                    CatalogModelFieldRecord.tenant_id == tenant_id,
                    CatalogModelFieldRecord.model_code == model_code,
                    CatalogModelFieldRecord.field_code == field_code,
                )
            ).scalar_one_or_none()
            if record is None:
                record = CatalogModelFieldRecord(
                    tenant_id=tenant_id,
                    model_code=model_code,
                    field_code=field_code,
                    title=str(payload.get("title", field_code)),
                    data_type=str(payload.get("data_type", "string")),
                    sensitive_level=payload.get("sensitive_level"),
                    field_policy_json=safe_json(payload.get("field_policy_json") or {}),
                    display_order=int(payload.get("display_order", 0)),
                    source_ref=payload.get("source_ref"),
                )
                session.add(record)
            else:
                record.title = str(payload.get("title", record.title))
                record.data_type = str(payload.get("data_type", record.data_type))
                record.sensitive_level = payload.get("sensitive_level", record.sensitive_level)
                record.field_policy_json = safe_json(payload.get("field_policy_json") or record.field_policy_json)
                record.display_order = int(payload.get("display_order", record.display_order))
                record.source_ref = payload.get("source_ref", record.source_ref)
            if record.source_ref:
                upsert_legacy_mapping_in_session(
                    session,
                    {
                        "source_ref": record.source_ref,
                        "legacy_object_ref": payload.get("legacy_object_ref") or f"{model_code}:{field_code}",
                        "canonical_type": "catalog_model_field",
                        "canonical_ref": f"{model_code}:{field_code}",
                        "evidence_json": {"model_code": model_code, "field_code": field_code},
                    },
                    tenant_id=tenant_id,
                )
            session.commit()
            session.refresh(record)
            return record

    def list_model_fields(self, model_code: str, *, tenant_id: str = "sd-default") -> list[CatalogModelFieldRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(CatalogModelFieldRecord)
                    .where(CatalogModelFieldRecord.tenant_id == tenant_id, CatalogModelFieldRecord.model_code == model_code)
                    .order_by(CatalogModelFieldRecord.display_order, CatalogModelFieldRecord.field_code)
                ).scalars()
            )

    def create_entry_version(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> CatalogEntryVersionRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = CatalogEntryVersionRecord(
                tenant_id=tenant_id,
                catalog_code=str(payload["catalog_code"]),
                version_no=str(payload["version_no"]),
                version_status=str(payload.get("version_status", "draft")),
                snapshot_json=safe_json(payload.get("snapshot_json") or {}),
                audit_ref=payload.get("audit_ref"),
                created_by=payload.get("created_by"),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_entry_versions(self, catalog_code: str, *, tenant_id: str = "sd-default") -> list[CatalogEntryVersionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(CatalogEntryVersionRecord)
                    .where(CatalogEntryVersionRecord.tenant_id == tenant_id, CatalogEntryVersionRecord.catalog_code == catalog_code)
                    .order_by(CatalogEntryVersionRecord.created_at)
                ).scalars()
            )

    def _entry_list_statement(
        self,
        *,
        tenant_id: str,
        lifecycle_status: str | None = None,
        lifecycle_statuses: tuple[str, ...] | None = None,
        owner_org_id: str | None = None,
        catalog_code_prefix: str | None = None,
        exclude_catalog_code_prefix: str | None = None,
        exclude_catalog_code: str | None = None,
    ):
        statement = (
            select(CatalogEntryRecord)
            .where(CatalogEntryRecord.tenant_id == tenant_id)
            .order_by(CatalogEntryRecord.catalog_code)
        )
        if lifecycle_status:
            statement = statement.where(CatalogEntryRecord.lifecycle_status == lifecycle_status)
        if lifecycle_statuses:
            statement = statement.where(CatalogEntryRecord.lifecycle_status.in_(lifecycle_statuses))
        if owner_org_id:
            statement = statement.where(CatalogEntryRecord.owner_org_id == owner_org_id)
        if catalog_code_prefix:
            statement = statement.where(CatalogEntryRecord.catalog_code.like(f"{catalog_code_prefix}%"))
        if exclude_catalog_code_prefix:
            statement = statement.where(~CatalogEntryRecord.catalog_code.like(f"{exclude_catalog_code_prefix}%"))
        if exclude_catalog_code:
            statement = statement.where(CatalogEntryRecord.catalog_code != exclude_catalog_code)
        return statement

    def _entry_filter_kwargs(
        self,
        *,
        lifecycle_status: str | None = None,
        lifecycle_statuses: tuple[str, ...] | None = None,
        owner_org_id: str | None = None,
        catalog_code_prefix: str | None = None,
        exclude_catalog_code_prefix: str | None = None,
        exclude_catalog_code: str | None = None,
    ) -> dict[str, Any]:
        return {
            "lifecycle_status": lifecycle_status,
            "lifecycle_statuses": lifecycle_statuses,
            "owner_org_id": owner_org_id,
            "catalog_code_prefix": catalog_code_prefix,
            "exclude_catalog_code_prefix": exclude_catalog_code_prefix,
            "exclude_catalog_code": exclude_catalog_code,
        }

    def count_entries(
        self,
        *,
        tenant_id: str = "sd-default",
        lifecycle_status: str | None = None,
        lifecycle_statuses: tuple[str, ...] | None = None,
        owner_org_id: str | None = None,
        catalog_code_prefix: str | None = None,
        exclude_catalog_code_prefix: str | None = None,
    ) -> int:
        SessionLocal = create_session_factory()
        filters = self._entry_filter_kwargs(
            lifecycle_status=lifecycle_status,
            lifecycle_statuses=lifecycle_statuses,
            owner_org_id=owner_org_id,
            catalog_code_prefix=catalog_code_prefix,
            exclude_catalog_code_prefix=exclude_catalog_code_prefix,
        )
        with SessionLocal() as session:
            statement = select(func.count()).select_from(CatalogEntryRecord).where(
                CatalogEntryRecord.tenant_id == tenant_id
            )
            if filters["lifecycle_status"]:
                statement = statement.where(CatalogEntryRecord.lifecycle_status == filters["lifecycle_status"])
            if filters["lifecycle_statuses"]:
                statement = statement.where(CatalogEntryRecord.lifecycle_status.in_(filters["lifecycle_statuses"]))
            if filters["owner_org_id"]:
                statement = statement.where(CatalogEntryRecord.owner_org_id == filters["owner_org_id"])
            if filters["catalog_code_prefix"]:
                statement = statement.where(CatalogEntryRecord.catalog_code.like(f"{filters['catalog_code_prefix']}%"))
            if filters["exclude_catalog_code_prefix"]:
                statement = statement.where(
                    ~CatalogEntryRecord.catalog_code.like(f"{filters['exclude_catalog_code_prefix']}%")
                )
            return int(session.execute(statement).scalar_one())

    def list_entries(
        self,
        *,
        tenant_id: str = "sd-default",
        lifecycle_status: str | None = None,
        lifecycle_statuses: tuple[str, ...] | None = None,
        owner_org_id: str | None = None,
        catalog_code_prefix: str | None = None,
        exclude_catalog_code_prefix: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CatalogEntryRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = self._entry_list_statement(
                tenant_id=tenant_id,
                lifecycle_status=lifecycle_status,
                lifecycle_statuses=lifecycle_statuses,
                owner_org_id=owner_org_id,
                catalog_code_prefix=catalog_code_prefix,
                exclude_catalog_code_prefix=exclude_catalog_code_prefix,
            )
            if offset:
                statement = statement.offset(offset)
            if limit is not None:
                statement = statement.limit(limit)
            return list(session.execute(statement).scalars())

    def list_duplicate_candidates(
        self,
        *,
        tenant_id: str = "sd-default",
        exclude_catalog_code: str,
        title: str = "",
        region_code: str = "",
        owner_org_id: str = "",
        lifecycle_statuses: tuple[str, ...],
    ) -> list[CatalogEntryRecord]:
        match_clauses = []
        if title:
            match_clauses.append(CatalogEntryRecord.title == title)
        if region_code and owner_org_id:
            match_clauses.append(
                and_(
                    CatalogEntryRecord.region_code == region_code,
                    CatalogEntryRecord.owner_org_id == owner_org_id,
                )
            )
        if not match_clauses:
            return []
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = (
                select(CatalogEntryRecord)
                .where(
                    CatalogEntryRecord.tenant_id == tenant_id,
                    CatalogEntryRecord.catalog_code != exclude_catalog_code,
                    CatalogEntryRecord.lifecycle_status.in_(lifecycle_statuses),
                    or_(*match_clauses),
                )
                .order_by(CatalogEntryRecord.catalog_code)
            )
            return list(session.execute(statement).scalars())

    def get_entry(self, catalog_code: str, *, tenant_id: str = "sd-default") -> CatalogEntryRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(CatalogEntryRecord).where(
                    CatalogEntryRecord.tenant_id == tenant_id,
                    CatalogEntryRecord.catalog_code == catalog_code,
                )
            ).scalar_one_or_none()

    def search_entries(
        self,
        query: str,
        *,
        tenant_id: str = "sd-default",
        lifecycle_status: str | None = None,
        lifecycle_statuses: tuple[str, ...] | None = None,
        owner_org_id: str | None = None,
        catalog_code_prefix: str | None = None,
        exclude_catalog_code_prefix: str | None = None,
    ) -> list[CatalogEntryRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            records = list(
                session.execute(
                    self._entry_list_statement(
                        tenant_id=tenant_id,
                        lifecycle_status=lifecycle_status,
                        lifecycle_statuses=lifecycle_statuses,
                        owner_org_id=owner_org_id,
                        catalog_code_prefix=catalog_code_prefix,
                        exclude_catalog_code_prefix=exclude_catalog_code_prefix,
                    )
                ).scalars()
            )
            query = query.strip()
            if not query:
                return records
            lowered = query.lower()
            tokens = [token for token in ["法人", "企业", "模板", "复用"] if token in query]
            matched: list[CatalogEntryRecord] = []
            for record in records:
                summary = record.summary_json
                text = " ".join(
                    [
                        record.catalog_code,
                        record.title,
                        record.owner_org_id or "",
                        str(summary.get("desc", "")),
                        str(summary.get("provider", "")),
                        str(summary.get("zone", "")),
                        " ".join(summary.get("fields", [])),
                        " ".join(summary.get("explain", [])),
                    ]
                ).lower()
                if lowered in text or any(token in text for token in tokens):
                    matched.append(record)
            return matched

    def list_items(self, catalog_code: str | None = None, *, tenant_id: str = "sd-default") -> list[CatalogItemRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(CatalogItemRecord).where(CatalogItemRecord.tenant_id == tenant_id)
            if catalog_code:
                statement = statement.where(CatalogItemRecord.catalog_code == catalog_code)
            return list(session.execute(statement.order_by(CatalogItemRecord.catalog_code, CatalogItemRecord.display_order, CatalogItemRecord.item_code)).scalars())

    def list_model_fields_all(self, *, tenant_id: str = "sd-default") -> list[CatalogModelFieldRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(CatalogModelFieldRecord)
                    .where(CatalogModelFieldRecord.tenant_id == tenant_id)
                    .order_by(CatalogModelFieldRecord.model_code, CatalogModelFieldRecord.display_order, CatalogModelFieldRecord.field_code)
                ).scalars()
            )

    def rebind_catalog_code(self, legacy_catalog_code: str, catalog_code: str, *, tenant_id: str = "sd-default") -> int:
        if legacy_catalog_code == catalog_code:
            return 0
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            records = list(
                session.execute(
                    select(CatalogItemRecord).where(
                        CatalogItemRecord.tenant_id == tenant_id,
                        CatalogItemRecord.catalog_code == legacy_catalog_code,
                    )
                ).scalars()
            )
            for record in records:
                record.catalog_code = catalog_code
            session.commit()
            return len(records)

    def upsert_item(self, item: dict[str, Any], *, tenant_id: str = "sd-default") -> CatalogItemRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            item_code = str(item["item_code"])
            record = session.execute(
                select(CatalogItemRecord).where(
                    CatalogItemRecord.tenant_id == tenant_id,
                    CatalogItemRecord.item_code == item_code,
                )
            ).scalar_one_or_none()
            if record is None:
                record = CatalogItemRecord(
                    tenant_id=tenant_id,
                    item_code=item_code,
                    catalog_code=str(item["catalog_code"]),
                    resource_code=item.get("resource_code"),
                    title=str(item.get("title", item_code)),
                    item_kind=str(item.get("item_kind", "group")),
                    display_order=int(item.get("display_order", 0)),
                    summary_json=safe_json(item.get("summary_json") or item),
                    source_ref=item.get("source_ref"),
                )
                session.add(record)
            else:
                record.catalog_code = str(item.get("catalog_code", record.catalog_code))
                record.resource_code = item.get("resource_code", record.resource_code)
                record.title = str(item.get("title", record.title))
                record.item_kind = str(item.get("item_kind", record.item_kind))
                record.display_order = int(item.get("display_order", record.display_order))
                record.summary_json = safe_json(item.get("summary_json") or {**record.summary_json, **item})
                record.source_ref = item.get("source_ref", record.source_ref)
            if record.source_ref:
                upsert_legacy_mapping_in_session(
                    session,
                    {
                        "source_ref": record.source_ref,
                        "legacy_object_ref": item.get("legacy_object_ref") or item_code,
                        "canonical_type": "catalog_item",
                        "canonical_ref": item_code,
                        "evidence_json": {"catalog_code": record.catalog_code, "item_kind": record.item_kind},
                    },
                    tenant_id=tenant_id,
                )
            session.commit()
            session.refresh(record)
            return record

    def upsert_from_resource(self, resource: dict[str, Any], *, tenant_id: str = "sd-default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(CatalogEntryRecord).where(
                    CatalogEntryRecord.tenant_id == tenant_id,
                    CatalogEntryRecord.catalog_code == resource["id"],
                )
            ).scalar_one_or_none()
            if record is None:
                record = CatalogEntryRecord(
                    tenant_id=tenant_id,
                    catalog_code=resource["id"],
                    title=resource["name"],
                    lifecycle_status=resource.get("status", "published"),
                    owner_org_id=resource.get("provider", ""),
                    region_code=resource.get("region_code"),
                    summary_json=safe_json(resource),
                )
                session.add(record)
            else:
                record.title = resource["name"]
                record.lifecycle_status = resource.get("status", "published")
                record.owner_org_id = resource.get("provider", "")
                record.region_code = resource.get("region_code", record.region_code)
                record.summary_json = safe_json(resource)
            if resource.get("source_ref"):
                upsert_legacy_mapping_in_session(
                    session,
                    {
                        "source_ref": resource["source_ref"],
                        "legacy_object_ref": resource.get("legacy_object_ref") or resource["id"],
                        "canonical_type": "catalog_entry",
                        "canonical_ref": resource["id"],
                        "evidence_json": {"title": record.title, "lifecycle_status": record.lifecycle_status},
                    },
                    tenant_id=tenant_id,
                )
            session.commit()
