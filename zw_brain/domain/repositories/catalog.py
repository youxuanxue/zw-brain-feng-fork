from __future__ import annotations

from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import CatalogEntryRecord
from zw_brain.shared.db import create_session_factory


class CatalogRepository:
    def list_entries(self) -> list[CatalogEntryRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(CatalogEntryRecord).order_by(CatalogEntryRecord.catalog_code)).scalars())

    def get_entry(self, catalog_code: str) -> CatalogEntryRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(CatalogEntryRecord).where(CatalogEntryRecord.catalog_code == catalog_code)
            ).scalar_one_or_none()

    def search_entries(self, query: str) -> list[CatalogEntryRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            records = list(session.execute(select(CatalogEntryRecord).order_by(CatalogEntryRecord.catalog_code)).scalars())
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

    def upsert_from_resource(self, resource: dict[str, Any], *, tenant_id: str = "default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(CatalogEntryRecord).where(CatalogEntryRecord.catalog_code == resource["id"])).scalar_one_or_none()
            if record is None:
                record = CatalogEntryRecord(
                    tenant_id=tenant_id,
                    catalog_code=resource["id"],
                    title=resource["name"],
                    lifecycle_status=resource.get("status", "published"),
                    owner_org_id=resource.get("provider", ""),
                    summary_json=resource,
                )
                session.add(record)
            else:
                record.title = resource["name"]
                record.lifecycle_status = resource.get("status", "published")
                record.owner_org_id = resource.get("provider", "")
                record.summary_json = resource
            session.commit()
