"""CatalogService — catalog entry projection + helpers.

Owns: catalog entry status / discoverability / projection card / field dicts
/ access policy / sensitive policy / reuse gap hint / explain / next hints
/ enrich catalog detail.

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zw_brain.domain.serializers import metadata as metadata_ser
from zw_brain.domain.serializers import resource_api as resource_api_ser
from zw_brain.domain.serializers import topic_package as topic_package_ser
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sensitive_mask import mask_default as _mask

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService



@dataclass(frozen=True)
class CatalogService:
    """Catalog domain operations (read-projection helpers).

    All methods take ``store`` / ``record`` explicitly; the service holds a
    ``brain`` reference for snapshot / sibling-service access.
    """

    brain: BrainService

    # --- Catalog entry status / discoverability ---

    def entry_status(self, catalog_code: Any) -> str | None:
        """Lifecycle status of a catalog entry. Returns None when no DB store."""
        store = self.brain._state_store.database_store
        if store is None or not catalog_code:
            return None
        record = store.catalog_repo.get_entry(str(catalog_code), tenant_id=_DEFAULT_TENANT_ID)
        return record.lifecycle_status if record is not None else None

    def is_discoverable(self, record: Any, store: Any) -> bool:
        """Whether a catalog record is currently discoverable for J1."""
        if record.lifecycle_status != "active":
            return False
        projections = self.topic_projection_cards(record.catalog_code, store)
        return any(projection.get("projectionStatus") == "projected" for projection in projections) or not projections

    def topic_projection_cards(self, catalog_code: str, store: Any) -> list[dict[str, Any]]:
        """List of topic projection cards referencing this catalog code."""
        cards: list[dict[str, Any]] = []
        topic_repo = self.brain._topic_package_repo()
        for package in topic_repo.list_packages(tenant_id=_DEFAULT_TENANT_ID):
            items = [topic_package_ser.topic_item_to_dict(record) for record in topic_repo.list_items(package.package_code, tenant_id=_DEFAULT_TENANT_ID)]
            if not any(item.get("ref_type") == "catalog_entry" and item.get("ref_id") == catalog_code for item in items):
                continue
            visibility = [topic_package_ser.topic_visibility_to_dict(record) for record in topic_repo.list_visibility(package.package_code, tenant_id=_DEFAULT_TENANT_ID)]
            summary = self.brain._get_handler_deps().services.topic_package.projection_summary(package, items, visibility)
            cards.append({"package_code": package.package_code, "title": package.title, "projectionStatus": summary["projectionStatus"], "visibleOrgCount": summary["visibleOrgCount"], "projectionFailureReasons": summary["projectionFailureReasons"]})
        return cards

    # --- Card / detail projection ---

    def record_to_card_dict(self, record: Any) -> dict[str, Any]:
        """Catalog record → card dict for P2 discovery list."""
        from zw_brain.shared import clock  # noqa: PLC0415

        summary = _mask(copy.deepcopy(record.summary_json or {}))
        body = self.summary_body(summary)
        provider = body.get("org_name") or body.get("imported_by_org_name") or record.owner_org_id or summary.get("provider", "—")
        desc = body.get("description") or body.get("source_service_item_catalog_name") or summary.get("desc") or record.title
        access_policy = self.access_policy(body, record)
        # Legacy migration occasionally carries an updated_at that is in the future
        # (planning-date semantics in dsp_catalog). Clamp to today so the customer
        # never sees "更新于 2026-08-19" on a UI rendered 2026-05-22.
        raw_updated = summary.get("updatedAt") or summary.get("updated_at") or summary.get("update_time") or record.updated_at.date().isoformat()
        today_iso = clock.now_date()
        if str(raw_updated)[:10] > today_iso:
            raw_updated = today_iso
        return {
            "id": record.catalog_code,
            "name": record.title,
            "status": record.lifecycle_status,
            "provider": provider,
            "zone": summary.get("zone") or self.brain._region_label(record.region_code) or "官方目录推荐",
            "updatedAt": str(raw_updated),
            "coverage": summary.get("coverage", "真实旧平台目录"),
            "score": int(summary.get("score", 80 if record.catalog_code.startswith("basic-elem:") else 75)),
            "desc": str(desc),
            "fields": list(summary.get("fields", [])),
            "explain": list(summary.get("explain", ["已匹配真实旧平台目录", f"目录状态：{record.lifecycle_status}"])),
            "nextHints": list(summary.get("nextHints", ["先看字段证据", "只申请必要字段"])),
            "kind": summary.get("kind", "catalog_entry"),
            "regionCode": record.region_code,
            "accessPolicy": access_policy,
            "sensitivePolicy": self.sensitive_policy([]),
            "reuseGapHint": self.brain._reuse_gap_hint([], []),
            "repository": {
                "catalogCode": record.catalog_code,
                "lifecycleStatus": record.lifecycle_status,
                "ownerOrgId": record.owner_org_id,
                "regionCode": record.region_code,
            },
        }

    def enrich_detail(
        self,
        detail: dict[str, Any],
        record: Any,
        store: Any,
        *,
        focused_resource_code: str | None = None,
        context: Any | None = None,
    ) -> None:
        """Mutate ``detail`` dict in place with catalog enrichment fields."""
        catalog_code = record.catalog_code
        fields = self.field_dicts(catalog_code, store, context=context)
        if context is not None:
            mapping_records = list(context.schema_mappings_by_catalog.get(catalog_code, []))
        else:
            mapping_records = list(store.metadata_evidence_repo.list_schema_mappings(catalog_code=catalog_code, tenant_id=_DEFAULT_TENANT_ID))
        if focused_resource_code:
            # Focused-resource lookup is a tiny set; one filtered SQL is cheap.
            mapping_by_code = {item.mapping_code: item for item in mapping_records}
            for item in store.metadata_evidence_repo.list_schema_mappings(resource_code=focused_resource_code, tenant_id=_DEFAULT_TENANT_ID):
                mapping_by_code[item.mapping_code] = item
            mapping_records = list(mapping_by_code.values())
        mappings = self.brain._mapping_diagnostics(mapping_records, store=store, context=context)
        if focused_resource_code:
            mappings["items"] = [item for item in mappings["items"] if item["resource_code"] == focused_resource_code]
            mappings["summary"] = self.brain._mapping_summary(mappings["items"])
        if context is not None:
            asset_records = context.resource_assets_by_catalog.get(catalog_code, [])
        else:
            asset_records = [item for item in store.resource_api_repo.list_assets(tenant_id=_DEFAULT_TENANT_ID) if item.catalog_code == catalog_code]
        resources = [
            resource_api_ser.resource_asset_to_dict(item)
            for item in asset_records
            if not focused_resource_code or item.resource_code == focused_resource_code
        ]
        resource_codes = {item["resource_code"] for item in resources} | {item["resource_code"] for item in mappings["items"]}
        if context is not None:
            snapshot_records = [
                snapshot
                for code in resource_codes
                for snapshot in context.schema_snapshots_by_resource.get(code, [])
            ]
        else:
            snapshot_records = [item for item in store.metadata_evidence_repo.list_schema_snapshots(tenant_id=_DEFAULT_TENANT_ID) if item.resource_code in resource_codes]
        snapshots = [metadata_ser.schema_snapshot_to_dict(item) for item in snapshot_records]
        legacy_refs = self.brain._legacy_mapping_refs(store, "catalog_entry", catalog_code, context=context)
        legacy_refs.extend(self.brain._legacy_mapping_refs(store, "catalog_item", [field["item_code"] for field in fields], context=context))
        legacy_refs.extend(self.brain._legacy_mapping_refs(store, "resource_schema_mapping", [item["mapping_code"] for item in mappings["items"]], context=context))
        legacy_refs.extend(self.brain._legacy_mapping_refs(store, "resource_asset", list(resource_codes), context=context))
        detail["fields"] = [field["title"] for field in fields] or detail.get("fields", [])
        detail["catalogFields"] = fields
        detail["fieldBindings"] = mappings["items"]
        detail["fieldBindingSummary"] = mappings["summary"]
        detail["resourceAssets"] = resources
        detail["schemaSnapshots"] = snapshots
        detail["legacyMappings"] = legacy_refs
        detail["accessPolicy"] = self.access_policy(self.summary_body(_mask(copy.deepcopy(record.summary_json or {}))), record)
        detail["sensitivePolicy"] = self.sensitive_policy(fields)
        detail["reuseGapHint"] = self.brain._reuse_gap_hint(fields, mappings["items"])
        detail["repository"] = detail.get("repository", {}) | {
            "catalogCode": catalog_code,
            "canonicalType": "catalog_entry",
            "legacyMappingCount": len(legacy_refs),
            "resourceCount": len(resources),
            "schemaSnapshotCount": len(snapshots),
        }
        detail["explain"] = self.explain(detail, fields, mappings["summary"])
        detail["nextHints"] = self.next_hints(fields, mappings["summary"])

    def field_dicts(
        self, catalog_code: str, store: Any, *, context: Any | None = None
    ) -> list[dict[str, Any]]:
        """Catalog item rows mapped to handler-shape dicts."""
        source = context.catalog_items_by_catalog.get(catalog_code, []) if context is not None else store.catalog_repo.list_items(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        return [
            {
                "item_code": item.item_code,
                "catalog_code": item.catalog_code,
                "title": item.title,
                "item_kind": item.item_kind,
                "display_order": item.display_order,
                "summary_json": _mask(copy.deepcopy(item.summary_json or {})),
                "source_ref": item.source_ref,
            }
            for item in source
        ]

    # --- Policy summaries ---

    def summary_body(self, summary: dict[str, Any]) -> dict[str, Any]:
        """Strip the wrapping ``summary`` key if nested."""
        nested = summary.get("summary")
        return nested if isinstance(nested, dict) else summary

    def access_policy(self, summary: dict[str, Any], record: Any) -> dict[str, Any]:
        """Catalog access policy dict for share / open semantics."""
        return {
            "shareType": summary.get("shared_type"),
            "shareWay": summary.get("shared_way"),
            "shareCondition": summary.get("shared_condition") or "未登记附加共享条件，按受控申请审批。",
            "openType": summary.get("open_type"),
            "openCondition": summary.get("open_condition") or "未登记公开条件。",
            "regionCode": record.region_code,
            "provider": summary.get("org_name") or summary.get("imported_by_org_name") or record.owner_org_id,
        }

    def sensitive_policy(self, fields: list[dict[str, Any]]) -> dict[str, Any]:
        """Per-catalog sensitive level summary derived from field summary_json."""
        levels = sorted({str((field.get("summary_json") or {}).get("sensitive_level")) for field in fields if (field.get("summary_json") or {}).get("sensitive_level") not in {None, ""}})
        return {
            "fieldSensitiveLevels": levels,
            "display": "查询与导出侧按字段敏感级别脱敏；申请侧只勾选必要字段。",
            "maskedOnRead": True,
        }

    def explain(
        self, detail: dict[str, Any], fields: list[dict[str, Any]], mapping_summary: dict[str, Any]
    ) -> list[str]:
        """Human-readable explain lines for a catalog detail."""
        out = ["已命中真实旧平台目录", f"提供方：{detail.get('provider') or '—'}"]
        if fields:
            out.append(f"字段清单 {len(fields)} 项")
        if mapping_summary.get("total"):
            out.append(f"字段绑定证据 {mapping_summary['total']} 条，可回放到 legacy_object_mapping")
        return out

    def next_hints(
        self, fields: list[dict[str, Any]], mapping_summary: dict[str, Any]
    ) -> list[str]:
        """Suggested next actions for a catalog detail."""
        hints = ["先看字段口径和敏感级别", "只选择本次确需字段"]
        if not fields or mapping_summary.get("diagnosis") != "ok":
            hints.append("把未绑定字段写入缺口说明")
        return hints
