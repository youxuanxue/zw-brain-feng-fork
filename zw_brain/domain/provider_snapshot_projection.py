"""Live provider inbox projection for WebUI P5.

P5Provider.vue reads ``provider.field_decisions`` / ``hookup_reviews`` /
``demand_matches`` for todo counts. Canonical DB state is projected here on
each ``system.snapshot`` call — not stored in seed_snapshot.json.
"""

from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.repositories.topic_package import TopicPackageRepository
from zw_brain.domain.supply_demand_phase import (
    PHASE_MANUAL_REGISTERED,
    PHASE_RECOMMEND_FAILED,
    PHASE_REGISTERED,
)
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEMAND_PROVIDER_PHASES = frozenset(
    {PHASE_REGISTERED, PHASE_MANUAL_REGISTERED, PHASE_RECOMMEND_FAILED}
)


def _entry_to_field_decision(record: Any) -> dict[str, Any]:
    return {
        "id": record.catalog_code,
        "title": record.title,
        "status": record.lifecycle_status,
        "owner_org_id": record.owner_org_id,
    }


def _asset_to_hookup_review(record: Any) -> dict[str, Any]:
    return {
        "id": record.resource_code,
        "title": record.title,
        "status": record.lifecycle_status,
        "catalog_code": record.catalog_code,
    }


def _demand_to_match(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "title": str(payload.get("title") or ""),
        "status": str(payload.get("demand_phase") or payload.get("status") or ""),
        "applicant_dept": str(payload.get("applicantDept") or ""),
    }


def _case_to_objection_inbox(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "status": record.status,
        "target_type": record.target_type,
        "target_id": record.target_id,
    }


def project_provider_inbox(*, tenant_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    tenant_id = tenant_id or get_runtime_tenant_id()
    catalog_repo = CatalogRepository()
    resource_repo = ResourceApiRepository()
    supply_repo = SupplyDemandRepository()
    objection_repo = ObjectionRepository()

    field_decisions = [
        _entry_to_field_decision(record)
        for record in catalog_repo.list_entries(tenant_id=tenant_id, lifecycle_status="pending_review")
    ]
    hookup_reviews = [
        _asset_to_hookup_review(record)
        for record in resource_repo.list_assets(tenant_id=tenant_id, lifecycle_status="pending_review")
    ]
    demand_matches = [
        _demand_to_match(item)
        for item in supply_repo.list_demands(tenant_id=tenant_id)
        if item.get("demand_phase") in _DEMAND_PROVIDER_PHASES
    ]
    objection_cases = [
        _case_to_objection_inbox(record)
        for record in objection_repo.list_cases(tenant_id=tenant_id, status="provider_investigating")
    ]
    return {
        "field_decisions": field_decisions,
        "hookup_reviews": hookup_reviews,
        "demand_matches": demand_matches,
        "objection_cases": objection_cases,
    }


def _attach_reverse_catalog_fields(catalog: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    """Ensure P5 反向编目 wizard 能拿到 catalog_code / schema_ref。"""
    out = copy.deepcopy(catalog)
    out.setdefault("catalog_code", out.get("legacy_object_ref") or out.get("id"))
    if out.get("schema_ref"):
        return out
    metadata_repo = MetadataEvidenceRepository()
    resource_code = out.get("canonical_resource_id") or out.get("id")
    if resource_code:
        snaps = metadata_repo.list_schema_snapshots(resource_code=str(resource_code), tenant_id=tenant_id)
        table_ref = next((snap.snapshot_ref for snap in snaps if ":db_meta_table:" in snap.snapshot_ref), None)
        if table_ref:
            out["schema_ref"] = table_ref
            return out
        if snaps:
            out["schema_ref"] = snaps[0].snapshot_ref
            return out
    legacy = out.get("legacy_object_ref")
    canonical = out.get("canonical_resource_id")
    if canonical and legacy:
        out["schema_ref"] = f"{canonical}:legacy:{legacy}"
    elif out.get("source_ref"):
        out["schema_ref"] = str(out["source_ref"])
    return out


def enrich_zones_snapshot(snapshot: dict[str, Any], *, tenant_id: str | None = None) -> dict[str, Any]:
    """Attach subscribe-ready package_code to P7 zone cards."""
    tenant_id = tenant_id or get_runtime_tenant_id()
    out = copy.deepcopy(snapshot)
    zones = out.get("zones")
    if not isinstance(zones, list):
        return out
    repo = TopicPackageRepository()
    published = [p for p in repo.list_packages(tenant_id=tenant_id) if p.status == "published"]
    fallback = published[0].package_code if published else None
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        zid = str(zone.get("id") or "")
        if repo.get_package(zid, tenant_id=tenant_id) is not None:
            zone["package_code"] = zid
        elif fallback:
            zone["package_code"] = fallback
    return out


def enrich_provider_snapshot(snapshot: dict[str, Any], *, tenant_id: str | None = None) -> dict[str, Any]:
    """Merge live inbox projection into *snapshot*['provider'] (deep copy)."""
    tenant_id = tenant_id or get_runtime_tenant_id()
    out = copy.deepcopy(snapshot)
    provider = out.setdefault("provider", {})
    inbox = project_provider_inbox(tenant_id=tenant_id)
    provider["field_decisions"] = inbox["field_decisions"]
    provider["hookup_reviews"] = inbox["hookup_reviews"]
    provider["demand_matches"] = inbox["demand_matches"]
    provider["objection_cases"] = inbox["objection_cases"]
    catalogs = provider.get("catalogs")
    if isinstance(catalogs, list):
        provider["catalogs"] = [
            _attach_reverse_catalog_fields(item, tenant_id=tenant_id) if isinstance(item, dict) else item
            for item in catalogs
        ]
    return out
