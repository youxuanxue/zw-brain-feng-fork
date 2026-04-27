from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from zw_brain.domain.models import CapabilityPackageRecord, TenantCapabilityPolicyRecord
from zw_brain.shared.db import create_session_factory


class CapabilityPackageRepository:
    def list_packages(self) -> list[CapabilityPackageRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(CapabilityPackageRecord).order_by(CapabilityPackageRecord.package_slug)).scalars())

    def list_policies(self, tenant_id: str = "default") -> list[TenantCapabilityPolicyRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(TenantCapabilityPolicyRecord)
                    .where(TenantCapabilityPolicyRecord.tenant_id == tenant_id)
                    .order_by(TenantCapabilityPolicyRecord.package_slug)
                ).scalars()
            )

    def upsert_from_package(self, package: dict[str, Any], *, tenant_id: str = "default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(CapabilityPackageRecord).where(CapabilityPackageRecord.package_slug == package["slug"])).scalar_one_or_none()
            if record is None:
                record = CapabilityPackageRecord(
                    package_slug=package["slug"],
                    review_status=package["status"],
                    source_org=package["source"],
                    manifest_json=package,
                )
                session.add(record)
            else:
                record.review_status = package["status"]
                record.source_org = package["source"]
                record.manifest_json = package

            session.execute(delete(TenantCapabilityPolicyRecord).where(TenantCapabilityPolicyRecord.tenant_id == tenant_id, TenantCapabilityPolicyRecord.package_slug == package["slug"]))
            session.add(
                TenantCapabilityPolicyRecord(
                    tenant_id=tenant_id,
                    package_slug=package["slug"],
                    policy_status=self._policy_status(package),
                    policy_json={
                        "enabled": package["status"] == "approved",
                        "exposedSurfaces": package.get("exposure", []),
                        "requiresHuman": package.get("requiresHuman", False),
                        "auditClass": package.get("auditClass"),
                    },
                )
            )
            session.commit()

    def _policy_status(self, package: dict[str, Any]) -> str:
        if package["status"] == "approved":
            return "enabled"
        if package["status"] in {"pending", "pending-fix"}:
            return "reviewing"
        return "disabled"
