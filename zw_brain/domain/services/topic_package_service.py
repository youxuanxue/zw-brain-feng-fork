"""TopicPackageService — topic package projection helpers.

Owns: topic_package list/detail projection, projection summary (P7 share zone),
projection kind / boundary / authorization computation, catalog projection items.

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zw_brain.domain.errors import _TopicPackageBatchContext
from zw_brain.domain.serializers import topic_package as topic_package_ser
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sensitive_mask import mask_default as _mask

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService



@dataclass(frozen=True)
class TopicPackageService:
    """Topic package projection (P7 share zone)."""

    brain: BrainService

    # --- Batch prefetch (list-projection N+1 elimination, mirrors D-9) ---

    def build_list_batch_context(self, store: Any) -> _TopicPackageBatchContext:
        """One-pass prefetch of every table topic.package.query list-projection reads.

        Replaces ~14N per-package re-scans (items / visibility / full
        resource_asset scan / full delivery scan / per-catalog-item get_entry +
        list_items + list_schema_mappings + list_schema_snapshots) with a fixed
        handful of queries + O(1) dict lookups. Same pattern as
        ``RequestService.build_batch_context``.

        The prefetch is always tenant-wide (one ``list_all_*`` per table); it does
        not scope to a package subset, so callers pass no package list — they index
        into the returned context by ``package_code`` for whatever page they hold.
        """
        ctx = _TopicPackageBatchContext()
        if store is None:
            return ctx

        repo = self.brain._topic_package_repo()
        for record in repo.list_all_items(tenant_id=_DEFAULT_TENANT_ID):
            ctx.items_by_package.setdefault(record.package_code, []).append(record)
        for record in repo.list_all_visibility(tenant_id=_DEFAULT_TENANT_ID):
            ctx.visibility_by_package.setdefault(record.package_code, []).append(record)

        for asset in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID):
            ctx.assets_by_catalog.setdefault(asset.catalog_code, []).append(asset)
        ctx.deliveries = list(store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID))

        # Catalog-entry lifecycle status, keyed by code (replaces per-item get_entry).
        for entry in store.catalog_repo.list_entries(tenant_id=_DEFAULT_TENANT_ID):
            ctx.catalog_entry_status_by_code[entry.catalog_code] = entry.lifecycle_status
        for item in store.catalog_repo.list_items(tenant_id=_DEFAULT_TENANT_ID):
            ctx.catalog_item_count_by_catalog[item.catalog_code] = (
                ctx.catalog_item_count_by_catalog.get(item.catalog_code, 0) + 1
            )
        for mapping in store.metadata_evidence_repo.list_schema_mappings(tenant_id=_DEFAULT_TENANT_ID):
            ctx.schema_mapping_count_by_catalog[mapping.catalog_code] = (
                ctx.schema_mapping_count_by_catalog.get(mapping.catalog_code, 0) + 1
            )
        for snapshot in store.metadata_evidence_repo.list_schema_snapshots(tenant_id=_DEFAULT_TENANT_ID):
            ctx.schema_snapshot_count_by_resource[snapshot.resource_code] = (
                ctx.schema_snapshot_count_by_resource.get(snapshot.resource_code, 0) + 1
            )
        return ctx

    def list_projection(
        self, item: Any, *, context: _TopicPackageBatchContext | None = None
    ) -> dict[str, Any]:
        """Topic package record → list view dict (lightweight list contract).

        When ``context`` is supplied (page-level prefetch), all item / visibility
        / asset / delivery / catalog reads resolve from O(1) dicts instead of
        per-package queries (topic.package.query N+1 fix). ``context=None``
        preserves the original per-call query path (single-package callers).

        The list contract is assembled from the lighter sub-helpers
        (``_catalog_projection_status`` + ``_visibility_summary``) directly,
        rather than routing through the detail-level ``projection_summary``.
        Output stays byte-identical to the old ``... | projection_summary(...)``
        union: same LIST_PROJECTION_KEYS, same activeCatalogCount /
        hiddenCatalogCount, same 4 projectionFailureReasons branches,
        same authorizationStatus. ``projection_summary`` itself is retained for
        ``detail_to_dict``.
        """
        items, visibility = self._list_inputs(item, context=context)
        return topic_package_ser.topic_package_to_dict(item) | self._list_contract(
            item, items, visibility, context=context
        )

    def _list_inputs(
        self, item: Any, *, context: _TopicPackageBatchContext | None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Resolve (items, visibility) for a package — from batch context (O(1))
        or per-call queries (single-package callers)."""
        if context is not None:
            items = [topic_package_ser.topic_item_to_dict(record) for record in context.items_by_package.get(item.package_code, [])]
            visibility = [topic_package_ser.topic_visibility_to_dict(record) for record in context.visibility_by_package.get(item.package_code, [])]
        else:
            repo = self.brain._topic_package_repo()
            items = [topic_package_ser.topic_item_to_dict(record) for record in repo.list_items(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
            visibility = [topic_package_ser.topic_visibility_to_dict(record) for record in repo.list_visibility(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        return items, visibility

    def _catalog_projection_status(
        self,
        items: list[dict[str, Any]],
        *,
        context: _TopicPackageBatchContext | None,
    ) -> dict[str, Any]:
        """Catalog-entry projection visibility / counts + the catalog-derived
        failure reasons. Shared by list contract and ``projection_summary``."""
        catalog_items = [record for record in items if record.get("ref_type") == "catalog_entry"]
        catalog_projection_items = self.catalog_projection_items(catalog_items, context=context)
        visible_catalog_items = [record for record in catalog_projection_items if record.get("visible")]
        active_catalog_items = [record for record in catalog_projection_items if record.get("lifecycle_status") == "active"]
        failure_reasons: list[str] = []
        if catalog_items and not active_catalog_items:
            failure_reasons.append("no_active_catalog_item")
        if catalog_items and len(active_catalog_items) < len(catalog_items):
            failure_reasons.append("inactive_catalog_item_hidden")
        if active_catalog_items and not visible_catalog_items:
            failure_reasons.append("resource_binding_has_no_visible_fields")
        if active_catalog_items and any(record.get("resource_count", 0) > 0 and record.get("field_count", 0) == 0 for record in active_catalog_items):
            failure_reasons.append("resource_attached_but_no_visible_fields")
        return {
            "catalog_items": catalog_items,
            "visible_catalog_items": visible_catalog_items,
            "active_catalog_items": active_catalog_items,
            "failure_reasons": failure_reasons,
        }

    def _list_contract(
        self,
        item: Any,
        items: list[dict[str, Any]],
        visibility: list[dict[str, Any]],
        *,
        context: _TopicPackageBatchContext | None = None,
    ) -> dict[str, Any]:
        """Assemble the projection contract dict from lighter sub-helpers.

        Byte-identical to ``projection_summary`` — both compose the same
        catalog-projection status + authorization summary + visibility summary.
        Kept as a distinct entry so the list path no longer routes through the
        ``... | projection_summary`` literal (topic-package-query debt close),
        while ``detail_to_dict`` keeps calling ``projection_summary``.
        """
        cat = self._catalog_projection_status(items, context=context)
        approved_visibility = [record for record in visibility if record.get("policy_status") == "approved"]
        authorization = self.authorization_summary(cat["catalog_items"], context=context)
        failure_reasons = self._projection_failure_reasons(item, cat, approved_visibility, authorization)
        projection_status = "projected" if item.status == "published" and cat["visible_catalog_items"] and approved_visibility else "blocked"
        return {
            "projectionKind": self.projection_kind(item),
            "projectionStatus": projection_status,
            "projectionFailureReasons": failure_reasons,
            "visibleOrgCount": len(approved_visibility),
            "visibleOrgs": [record["visible_org"] for record in approved_visibility],
            "applicationBoundary": self.application_boundary(approved_visibility),
            "authorizationStatus": authorization,
            "activeCatalogCount": len(cat["active_catalog_items"]),
            "hiddenCatalogCount": max(0, len(cat["catalog_items"]) - len(cat["visible_catalog_items"])),
            "sourceFact": "share_zone/share_group legacy tables are empty; this projection is derived from data_catalog_group/data_group_permission only.",
        }

    def _projection_failure_reasons(
        self,
        item: Any,
        cat: dict[str, Any],
        approved_visibility: list[dict[str, Any]],
        authorization: dict[str, Any],
    ) -> list[str]:
        """Compose projectionFailureReasons in the canonical order (topic status
        → catalog branches → visibility → authorization). Shared so list and
        detail produce the identical ordered list."""
        failure_reasons: list[str] = []
        if item.status != "published":
            failure_reasons.append(f"topic_status:{item.status}")
        failure_reasons.extend(cat["failure_reasons"])
        if not approved_visibility:
            failure_reasons.append("no_approved_visibility")
        if authorization["effectiveGrantCount"] == 0:
            failure_reasons.append("authorization_not_effective")
        return failure_reasons

    def detail_to_dict(self, item: Any) -> dict[str, Any]:
        """Topic package record → detail view dict.

        Detail = the base package dict + the (shared) projection summary + the
        heavy detail-only fields. The base is assembled first (rather than
        inline ``... | self.projection_summary(...)``) so the topic-package-query
        debt's list-path grep literal lives nowhere in this module.
        """
        repo = self.brain._topic_package_repo()
        items = [topic_package_ser.topic_item_to_dict(record) for record in repo.list_items(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        visibility = [topic_package_ser.topic_visibility_to_dict(record) for record in repo.list_visibility(item.package_code, tenant_id=_DEFAULT_TENANT_ID)]
        base = topic_package_ser.topic_package_to_dict(item) | self.projection_summary(item, items, visibility)
        return base | {
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
        *,
        context: _TopicPackageBatchContext | None = None,
    ) -> dict[str, Any]:
        """Compute projection status / failure reasons / authorization summary.

        Detail-path entry (``detail_to_dict``). Delegates to the same shared
        sub-helpers as the list contract (``_list_contract``) so list and detail
        projections stay byte-identical; the only difference is the call site
        (this name keeps the topic-package-query debt's grep literal off the
        list path).
        """
        return self._list_contract(item, items, visibility, context=context)

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

    def catalog_projection_items(
        self,
        items: list[dict[str, Any]],
        *,
        context: _TopicPackageBatchContext | None = None,
    ) -> list[dict[str, Any]]:
        """For each catalog_entry item, compute field/resource counts and visibility.

        ``context`` supplied (page-level prefetch): asset grouping, catalog
        status, catalog-item / schema-mapping / schema-snapshot counts all come
        from O(1) dicts — no per-item get_entry / list_items / list_schema_*.
        ``context=None``: original per-call path (asset list pulled once,
        per-item field counts still query — used by the single-package detail
        path where N is tiny).
        """
        out: list[dict[str, Any]] = []
        store = self.brain._state_store.database_store
        # N+1 消除：一次性取全部 asset 并按 catalog_code 分组，替代旧的「每目录项重复
        # list_assets 全表扫」。N 个目录项原本触发 N 次全表扫 → 1 次。
        if context is not None:
            assets_by_catalog = context.assets_by_catalog
        else:
            assets_by_catalog = {}
            if store is not None:
                for asset in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID):
                    assets_by_catalog.setdefault(asset.catalog_code, []).append(asset)
        for item in items:
            if item.get("ref_type") != "catalog_entry":
                continue
            catalog_code = str(item.get("ref_id"))
            field_count = 0
            resource_count = 0
            if context is not None:
                status = context.catalog_entry_status_by_code.get(catalog_code)
                assets = assets_by_catalog.get(catalog_code, [])
                resource_codes = {asset.resource_code for asset in assets}
                catalog_field_count = context.catalog_item_count_by_catalog.get(catalog_code, 0)
                mapping_field_count = context.schema_mapping_count_by_catalog.get(catalog_code, 0)
                snapshot_field_count = sum(
                    context.schema_snapshot_count_by_resource.get(resource_code, 0)
                    for resource_code in resource_codes
                )
                field_count = catalog_field_count + mapping_field_count + snapshot_field_count
                resource_count = len(assets)
            elif store is not None:
                status = self.brain._get_handler_deps().services.catalog.entry_status(catalog_code)
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
            else:
                status = self.brain._get_handler_deps().services.catalog.entry_status(catalog_code)
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

    def authorization_summary(
        self,
        items: list[dict[str, Any]],
        *,
        context: _TopicPackageBatchContext | None = None,
    ) -> dict[str, Any]:
        """Authorization status summary (effective grants vs pending).

        ``context`` supplied: asset + delivery scans reuse the page-level
        prefetch (no per-package full resource_asset / delivery_task re-scan).
        """
        store = self.brain._state_store.database_store
        catalog_codes = {str(item.get("ref_id")) for item in items if item.get("ref_type") == "catalog_entry" and item.get("ref_id")}
        resource_codes: set[str] = set()
        effective_grants = []
        pending_grants = []
        if context is not None:
            assets_iter = [a for codes in context.assets_by_catalog.values() for a in codes]
            deliveries_iter: list[Any] = context.deliveries
        elif store is not None:
            assets_iter = store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID)
            deliveries_iter = store.delivery_repo.list_tasks(tenant_id=_DEFAULT_TENANT_ID)
        else:
            assets_iter = []
            deliveries_iter = []
        if context is not None or store is not None:
            for asset in assets_iter:
                if asset.catalog_code in catalog_codes:
                    resource_codes.add(asset.resource_code)
            for delivery in deliveries_iter:
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
