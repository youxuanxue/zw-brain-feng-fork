"""TopicPackageService — topic package projection helpers.

Owns: topic_package list/detail projection, projection summary (P7 share zone),
projection kind / boundary / authorization computation, catalog projection items.

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zw_brain.domain.serializers import topic_package as topic_package_ser
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sensitive_mask import mask_default as _mask

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService



@dataclass(frozen=True)
class TopicPackageService:
    """Topic package projection (P7 share zone)."""

    brain: BrainService

    def list_projection(self, item: Any) -> dict[str, Any]:
        """Topic package record → list view dict (with projection summary)."""
        repo = self.brain._topic_package_repo()
        items = [topic_package_ser.topic_item_to_dict(record) for record in repo.list_items(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        visibility = [topic_package_ser.topic_visibility_to_dict(record) for record in repo.list_visibility(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        return topic_package_ser.topic_package_to_dict(item) | self.projection_summary(item, items, visibility)

    def detail_to_dict(self, item: Any) -> dict[str, Any]:
        """Topic package record → detail view dict."""
        repo = self.brain._topic_package_repo()
        items = [topic_package_ser.topic_item_to_dict(record) for record in repo.list_items(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        visibility = [topic_package_ser.topic_visibility_to_dict(record) for record in repo.list_visibility(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        return topic_package_ser.topic_package_to_dict(item) | self.projection_summary(item, items, visibility) | {
            "items": items,
            "visibility": visibility,
            "catalogProjectionItems": self.catalog_projection_items(items),
            "reviews": [topic_package_ser.topic_review_to_dict(record) for record in repo.list_review_records(item.package_code, tenant_id=_DEFAULT_TENANT_ID)],
            "evidence": [topic_package_ser.topic_evidence_to_dict(record) for record in repo.list_evidence(item.package_code, tenant_id=_DEFAULT_TENANT_ID)],
            "metrics": [topic_package_ser.topic_metric_to_dict(record) for record in repo.list_metrics(item.package_code, tenant_id=_DEFAULT_TENANT_ID)],
        }

    def projection_summary(
        self,
        item: Any,
        items: list[dict[str, Any]],
        visibility: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute projection status / failure reasons / authorization summary."""
        approved_visibility = [record for record in visibility if record.get("policy_status") == "approved"]
        catalog_items = [record for record in items if record.get("ref_type") == "catalog_entry"]
        catalog_projection_items = self.catalog_projection_items(catalog_items)
        visible_catalog_items = [record for record in catalog_projection_items if record.get("visible")]
        active_catalog_items = [record for record in catalog_projection_items if record.get("lifecycle_status") == "active"]
        authorization = self.authorization_summary(catalog_items)
        failure_reasons: list[str] = []
        if item.status != "published":
            failure_reasons.append(f"topic_status:{item.status}")
        if catalog_items and not active_catalog_items:
            failure_reasons.append("no_active_catalog_item")
        if catalog_items and len(active_catalog_items) < len(catalog_items):
            failure_reasons.append("inactive_catalog_item_hidden")
        if active_catalog_items and not visible_catalog_items:
            failure_reasons.append("resource_binding_has_no_visible_fields")
        if active_catalog_items and any(record.get("resource_count", 0) > 0 and record.get("field_count", 0) == 0 for record in active_catalog_items):
            failure_reasons.append("resource_attached_but_no_visible_fields")
        if not approved_visibility:
            failure_reasons.append("no_approved_visibility")
        if authorization["effectiveGrantCount"] == 0:
            failure_reasons.append("authorization_not_effective")
        projection_status = "projected" if item.status == "published" and visible_catalog_items and approved_visibility else "blocked"
        return {
            "projectionKind": self.projection_kind(item),
            "projectionStatus": projection_status,
            "projectionFailureReasons": failure_reasons,
            "visibleOrgCount": len(approved_visibility),
            "visibleOrgs": [record["visible_org"] for record in approved_visibility],
            "applicationBoundary": self.application_boundary(approved_visibility),
            "authorizationStatus": authorization,
            "activeCatalogCount": len(active_catalog_items),
            "hiddenCatalogCount": max(0, len(catalog_items) - len(visible_catalog_items)),
            "sourceFact": "share_zone/share_group legacy tables are empty; this projection is derived from data_catalog_group/data_group_permission only.",
        }

    def projection_kind(self, item: Any) -> str:
        """Extract projection_kind from display_snapshot_json."""
        display = item.display_snapshot_json if isinstance(item.display_snapshot_json, dict) else {}
        return str(display.get("projection_kind") or display.get("source") or "topic_package")

    def application_boundary(self, visibility: list[dict[str, Any]]) -> dict[str, Any]:
        """Application boundary derived from visibility records."""
        sources = sorted({str(record.get("source")) for record in visibility if record.get("source")})
        return {
            "visibilitySource": sources or ["none"],
            "approvedViewPolicyCount": sum(1 for record in visibility if record.get("policy_status") == "approved" and record.get("intent") == "view"),
            "conditions": [record.get("condition_json") or {} for record in visibility],
            "rule": "目录专题只解释可见与申请边界；实际资源申请仍走 application.resource.submit/application.resource.review。",
        }

    def catalog_projection_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """For each catalog_entry item, compute field/resource counts and visibility."""
        out: list[dict[str, Any]] = []
        store = self.brain._state_store.database_store
        # N+1 消除：一次性取全部 asset 并按 catalog_code 分组，替代旧的「每目录项重复
        # list_assets 全表扫」。N 个目录项原本触发 N 次全表扫 → 1 次。
        assets_by_catalog: dict[str, list[Any]] = {}
        if store is not None:
            for asset in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID):
                assets_by_catalog.setdefault(asset.catalog_code, []).append(asset)
        for item in items:
            if item.get("ref_type") != "catalog_entry":
                continue
            catalog_code = str(item.get("ref_id"))
            status = self.brain._get_handler_deps().services.catalog.entry_status(catalog_code)
            field_count = 0
            resource_count = 0
            if store is not None:
                assets = assets_by_catalog.get(catalog_code, [])
                resource_codes = {asset.resource_code for asset in assets}
                catalog_field_count = len(store.catalog_repo.list_items(catalog_code, tenant_id=_DEFAULT_TENANT_ID))
                mapping_field_count = len(store.metadata_evidence_repo.list_schema_mappings(catalog_code=catalog_code, tenant_id=_DEFAULT_TENANT_ID))
                snapshot_field_count = sum(
                    len(store.metadata_evidence_repo.list_schema_snapshots(resource_code=resource_code, tenant_id=_DEFAULT_TENANT_ID))
                    for resource_code in resource_codes
                )
                field_count = catalog_field_count + mapping_field_count + snapshot_field_count
                resource_count = len(assets)
            out.append(
                item | {
                    "catalog_code": catalog_code,
                    "lifecycle_status": status,
                    "visible": status == "active" and field_count > 0,
                    "field_count": field_count,
                    "resource_count": resource_count,
                    "hidden_reason": None if status == "active" and field_count > 0 else ("catalog_not_active" if status != "active" else "resource_binding_has_no_visible_fields"),
                }
            )
        return out

    def authorization_summary(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Authorization status summary (effective grants vs pending)."""
        store = self.brain._state_store.database_store
        catalog_codes = {str(item.get("ref_id")) for item in items if item.get("ref_type") == "catalog_entry" and item.get("ref_id")}
        resource_codes: set[str] = set()
        effective_grants = []
        pending_grants = []
        if store is not None:
            for asset in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID):
                if asset.catalog_code in catalog_codes:
                    resource_codes.add(asset.resource_code)
            for delivery in store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID):
                payload = delivery.payload_json if isinstance(delivery.payload_json, dict) else {}
                if payload.get("resource_id") not in resource_codes:
                    continue
                grant = payload.get("access_grant") or {}
                row = {
                    "delivery_code": delivery.delivery_code,
                    "resource_code": payload.get("resource_id"),
                    "state": delivery.state,
                    "channel": delivery.channel,
                    "access_grant": _mask(copy.deepcopy(grant)),
                }
                if delivery.state == "granted" and grant:
                    effective_grants.append(row)
                else:
                    pending_grants.append(row)
        return {
            "effectiveGrantCount": len(effective_grants),
            "pendingOrInactiveGrantCount": len(pending_grants),
            "resourceCodes": sorted(resource_codes),
            "effectiveGrants": effective_grants,
            "pendingOrInactiveGrants": pending_grants,
            "renewalBoundary": "真实 data_apply_renewal 无行；不伪造续期成功路径。",
        }
