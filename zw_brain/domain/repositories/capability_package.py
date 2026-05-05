from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from zw_brain.domain.models import CapabilityPackageRecord, TenantCapabilityPolicyRecord
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


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

    def get_policy(self, package_slug: str, tenant_id: str = "default") -> TenantCapabilityPolicyRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            return session.execute(
                select(TenantCapabilityPolicyRecord).where(
                    TenantCapabilityPolicyRecord.tenant_id == tenant_id,
                    TenantCapabilityPolicyRecord.package_slug == package_slug,
                )
            ).scalar_one_or_none()

    def upsert_from_package(self, package: dict[str, Any], *, tenant_id: str = "default") -> None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(CapabilityPackageRecord).where(CapabilityPackageRecord.package_slug == package["slug"])).scalar_one_or_none()
            if record is None:
                record = CapabilityPackageRecord(
                    package_slug=package["slug"],
                    review_status=package["status"],
                    source_org=package["source"],
                    manifest_json=safe_json(package),
                )
                session.add(record)
            else:
                record.review_status = package["status"]
                record.source_org = package["source"]
                record.manifest_json = safe_json(package)

            session.execute(delete(TenantCapabilityPolicyRecord).where(TenantCapabilityPolicyRecord.tenant_id == tenant_id, TenantCapabilityPolicyRecord.package_slug == package["slug"]))
            session.add(
                TenantCapabilityPolicyRecord(
                    tenant_id=tenant_id,
                    package_slug=package["slug"],
                    policy_status=self._policy_status(package),
                    policy_json=self._policy_json(package),
                )
            )
            session.commit()

    def upsert_tenant_policy(self, package: dict[str, Any], *, tenant_id: str = "default") -> TenantCapabilityPolicyRecord:
        self.upsert_from_package(package, tenant_id=tenant_id)
        policy = self.get_policy(str(package["slug"]), tenant_id=tenant_id)
        if policy is None:
            raise KeyError(package["slug"])
        return policy

    def set_tenant_policy_status(
        self,
        package: dict[str, Any],
        *,
        tenant_id: str = "default",
        policy_status: str,
        enabled: bool,
        exposed_surfaces: list[str] | None = None,
    ) -> TenantCapabilityPolicyRecord:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(select(CapabilityPackageRecord).where(CapabilityPackageRecord.package_slug == package["slug"])).scalar_one_or_none()
            if record is None:
                record = CapabilityPackageRecord(
                    package_slug=package["slug"],
                    review_status=package["status"],
                    source_org=package["source"],
                    manifest_json=safe_json(package),
                )
                session.add(record)
            else:
                record.review_status = package["status"]
                record.source_org = package["source"]
                record.manifest_json = safe_json(package)
            session.execute(delete(TenantCapabilityPolicyRecord).where(TenantCapabilityPolicyRecord.tenant_id == tenant_id, TenantCapabilityPolicyRecord.package_slug == package["slug"]))
            session.add(
                TenantCapabilityPolicyRecord(
                    tenant_id=tenant_id,
                    package_slug=package["slug"],
                    policy_status=policy_status,
                    policy_json=safe_json(
                        {
                            **self._policy_json(package),
                            "enabled": enabled,
                            "exposedSurfaces": exposed_surfaces if exposed_surfaces is not None else package.get("exposure", []),
                        }
                    ),
                )
            )
            session.commit()
        policy = self.get_policy(str(package["slug"]), tenant_id=tenant_id)
        if policy is None:
            raise KeyError(package["slug"])
        return policy

    def _policy_json(self, package: dict[str, Any]) -> dict[str, Any]:
        return safe_json(
            {
                "enabled": package.get("status") == "approved",
                "exposedSurfaces": package.get("exposure", []),
                "requiresHuman": package.get("requiresHuman", False),
                "auditClass": package.get("auditClass"),
                "tenantPolicy": package.get("tenantPolicy", {}),
                "failureWriteback": package.get("failureWriteback", {}),
            }
        )

    def _policy_status(self, package: dict[str, Any]) -> str:
        if package["status"] == "approved":
            return "enabled"
        if package["status"] in {"pending", "pending-fix"}:
            return "reviewing"
        return "disabled"
