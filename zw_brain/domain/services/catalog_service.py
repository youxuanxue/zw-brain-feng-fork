"""CatalogService — catalog entry projection + helpers.

Owns: catalog entry status / discoverability / projection card / field dicts
/ access policy / sensitive policy / reuse gap hint / explain / next hints
/ enrich catalog detail.

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zw_brain.domain.resource_kind import canonical_resource_kind
from zw_brain.domain.serializers import metadata as metadata_ser
from zw_brain.domain.serializers import resource_api as resource_api_ser
from zw_brain.domain.serializers import topic_package as topic_package_ser
from zw_brain.domain.serializers import typed_resource_detail as typed_resource_detail_ser
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sensitive_mask import mask_default as _mask

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


# 旧平台编制规范码 → 中文（反馈 5：目录详情按编制规范展示，码值不直接示人）。
_SHARE_TYPE_LABELS: dict[str, str] = {
    "1": "无条件共享",
    "2": "有条件共享",
    "3": "不予共享",
}
_OPEN_TYPE_LABELS: dict[str, str] = {
    "1": "无条件开放",
    "2": "有条件开放",
    "3": "不予开放",
}
# 业务/数据更新周期码 → 中文（旧平台 update_cycle 枚举）。
_UPDATE_CYCLE_LABELS: dict[str, str] = {
    "1": "实时",
    "2": "每日",
    "3": "每周",
    "4": "每月",
    "5": "每季度",
    "6": "每半年",
    "7": "每年",
    "8": "不定期",
    "9": "不更新",
}
# 信息资源格式码 → 中文（旧平台 resource_format 枚举，常见档位）。
_RESOURCE_FORMAT_LABELS: dict[str, str] = {
    "0100": "结构化数据",
    "0200": "库表",
    "0300": "非结构化数据",
    "0310": "文件",
    "0320": "文件夹",
    "0400": "接口",
    "0500": "链接",
}
# 信息资源格式码 → 物化形态 kind（与 resource_asset.resource_kind / ResourceCard 徽标同口径）。
# 资源类型收敛为「库表 / 文件 / API」（D53）：结构化/库表→table；文件→file；接口→api。
# 文件夹(0320)/链接(0500) 不再单列物化类型，折叠为 file（与归一化闸门 folder/url→file 一致）。
_RESOURCE_FORMAT_TO_KIND: dict[str, str] = {
    "0100": "table",
    "0200": "table",
    "0310": "file",
    "0320": "file",
    "0400": "api",
    "0500": "file",
}



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
        return self._discoverable_from_cards(record, projections)

    def is_discoverable_with_cards(self, record: Any, projections: list[dict[str, Any]]) -> bool:
        """Card-aware discoverability — reuses already-computed projection cards.

        Same predicate as `is_discoverable` but takes the projection cards the
        caller already batch-computed (P1 fix), so it never re-queries the topic
        packages. Keeps the projection computation single-sourced.
        """
        return self._discoverable_from_cards(record, projections)

    @staticmethod
    def _discoverable_from_cards(record: Any, projections: list[dict[str, Any]]) -> bool:
        if record.lifecycle_status != "active":
            return False
        return any(projection.get("projectionStatus") == "projected" for projection in projections) or not projections

    def topic_projection_cards(self, catalog_code: str, store: Any) -> list[dict[str, Any]]:
        """List of topic projection cards referencing this catalog code.

        Uses the catalog→package reverse index (`list_packages_referencing`,
        indexed on `ref_type`/`ref_id`) so only packages that actually reference
        this catalog are loaded, instead of walking every package's items
        (P1/P3 N+1 engine). For the matched packages, item/visibility prefetch
        + projection_summary reuse the topic_package list batch context, so a
        catalog referenced by K packages costs ~3 + K queries, not 116×items.
        """
        topic_repo = self.brain._topic_package_repo()
        referencing_codes = set(
            topic_repo.list_packages_referencing("catalog_entry", catalog_code, tenant_id=_DEFAULT_TENANT_ID)
        )
        if not referencing_codes:
            return []
        packages = [
            package
            for package in topic_repo.list_packages(tenant_id=_DEFAULT_TENANT_ID)
            if package.package_code in referencing_codes
        ]
        if not packages:
            return []
        topic_service = self.brain._get_handler_deps().services.topic_package
        context = topic_service.build_list_batch_context(store)
        cards: list[dict[str, Any]] = []
        for package in packages:
            items = [
                topic_package_ser.topic_item_to_dict(record)
                for record in context.items_by_package.get(package.package_code, [])
            ]
            visibility = [
                topic_package_ser.topic_visibility_to_dict(record)
                for record in context.visibility_by_package.get(package.package_code, [])
            ]
            summary = topic_service.projection_summary(package, items, visibility, context=context)
            cards.append(
                {
                    "package_code": package.package_code,
                    "title": package.title,
                    "projectionStatus": summary["projectionStatus"],
                    "visibleOrgCount": summary["visibleOrgCount"],
                    "projectionFailureReasons": summary["projectionFailureReasons"],
                }
            )
        return cards

    def topic_projection_cards_by_catalog(
        self, catalog_codes: list[str], store: Any
    ) -> dict[str, list[dict[str, Any]]]:
        """Batch variant of `topic_projection_cards` for a set of catalog codes.

        Builds the catalog→package reverse map + topic_package list batch context
        ONCE for the whole page, then projects each referenced package once. This
        is the P1 fix: `data.search` over K hits previously called
        `topic_projection_cards` K× (each walking all 116 packages → K×116×items
        sessions). Here the whole search costs a fixed handful of queries +
        per-referenced-package projection, regardless of K.

        Returns ``{catalog_code: [cards]}``; absent codes map to ``[]``.
        """
        result: dict[str, list[dict[str, Any]]] = {code: [] for code in catalog_codes}
        if store is None or not catalog_codes:
            return result
        topic_repo = self.brain._topic_package_repo()
        topic_service = self.brain._get_handler_deps().services.topic_package
        # 1 indexed query gets every (package, catalog) reference for the page.
        wanted = set(catalog_codes)
        catalog_to_packages: dict[str, set[str]] = {code: set() for code in catalog_codes}
        all_items = topic_repo.list_all_items(tenant_id=_DEFAULT_TENANT_ID)
        referenced_package_codes: set[str] = set()
        for record in all_items:
            if record.ref_type == "catalog_entry" and record.ref_id in wanted:
                catalog_to_packages[record.ref_id].add(record.package_code)
                referenced_package_codes.add(record.package_code)
        if not referenced_package_codes:
            return result
        packages = [
            package
            for package in topic_repo.list_packages(tenant_id=_DEFAULT_TENANT_ID)
            if package.package_code in referenced_package_codes
        ]
        context = topic_service.build_list_batch_context(store)
        # Project each referenced package exactly once, then fan out to codes.
        card_by_package: dict[str, dict[str, Any]] = {}
        for package in packages:
            items = [
                topic_package_ser.topic_item_to_dict(rec)
                for rec in context.items_by_package.get(package.package_code, [])
            ]
            visibility = [
                topic_package_ser.topic_visibility_to_dict(rec)
                for rec in context.visibility_by_package.get(package.package_code, [])
            ]
            summary = topic_service.projection_summary(package, items, visibility, context=context)
            card_by_package[package.package_code] = {
                "package_code": package.package_code,
                "title": package.title,
                "projectionStatus": summary["projectionStatus"],
                "visibleOrgCount": summary["visibleOrgCount"],
                "projectionFailureReasons": summary["projectionFailureReasons"],
            }
        # sorted() so topicProjections card order is deterministic across processes
        # (package_codes is a set; set iteration of strings is hash-seed dependent).
        for code, package_codes in catalog_to_packages.items():
            result[code] = [card_by_package[pc] for pc in sorted(package_codes) if pc in card_by_package]
        return result

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
            "coverage": summary.get("coverage", ""),  # 无业务值不渲染（前端 v-if），不给工程出处话术
            "score": int(summary.get("score", 80 if record.catalog_code.startswith("basic-elem:") else 75)),
            "desc": str(desc),
            "fields": list(summary.get("fields", [])),
            "explain": list(summary.get("explain", ["来源：省一体化大数据平台共享目录"])),
            "nextHints": list(summary.get("nextHints", ["先看字段证据", "只申请必要字段"])),
            "kind": summary.get("kind", "catalog_entry"),
            # 反馈 7 — 资源类型筛选维度：从目录 resource_format 派生物化形态
            # （库表/文件/文件夹/接口/链接），让发现页按资源类型筛选。缺则 None（不参与筛选）。
            "materializationKind": _RESOURCE_FORMAT_TO_KIND.get(str(body.get("resource_format"))),
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
            # indexed getter (resource_api.py:42, # indexed-ok) pushes the
            # catalog_code equality into SQL instead of loading every tenant
            # asset and filtering in Python. Byte-identical: same tenant +
            # catalog_code equality, same order_by(resource_code).
            asset_records = store.resource_api_repo.list_assets_by_catalog(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
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
            # PERF: push resource_code filter into SQL (.in_()) instead of scanning
            # every tenant snapshot (~5560 rows) and filtering in Python. 空 set →
            # repo 直接返回 []（同语义）。
            snapshot_records = store.metadata_evidence_repo.list_schema_snapshots(resource_codes=list(resource_codes), tenant_id=_DEFAULT_TENANT_ID)
        snapshots = [metadata_ser.schema_snapshot_to_dict(item) for item in snapshot_records]
        # 反馈 6 — 资源分型详情：给 focused 资源拉其 channel binding（文件/库表/接口/链接
        # 的类型化事实），投影为 typedDetail 块。focused 路径是单资源（resource_view），
        # list_bindings(resource_code=) 一条索引查询，无 N+1。列表路径（context 批量）此处
        # 不展开 typedDetail（卡片不需要），保持读路径成本不变。
        if focused_resource_code:
            focused_asset = next(
                (item for item in resources if item["resource_code"] == focused_resource_code),
                None,
            )
            if focused_asset is not None:
                binding_records = store.resource_api_repo.list_bindings(
                    resource_code=focused_resource_code, tenant_id=_DEFAULT_TENANT_ID
                )
                binding_dicts = [resource_api_ser.binding_to_dict(b) for b in binding_records]
                detail["focusedResourceCode"] = focused_resource_code
                # 读路径折叠（D53）：存量 folder/url/link → file，绝不裸出 legacy kind 到详情徽标。
                detail["resourceKind"] = canonical_resource_kind(focused_asset.get("resource_kind"))
                detail["resourceBindings"] = binding_dicts
                detail["typedDetail"] = typed_resource_detail_ser.typed_resource_detail(
                    resource_kind=focused_asset.get("resource_kind"),
                    bindings=binding_dicts,
                )
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
        masked_summary = _mask(copy.deepcopy(record.summary_json or {}))
        detail["accessPolicy"] = self.access_policy(self.summary_body(masked_summary), record)
        detail["catalogMeta"] = self.catalog_meta(masked_summary, record)
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
        """Catalog access policy dict for share / open semantics.

        ``shareType`` / ``openType`` 保留旧平台原始码（既有 consumer 依赖，不破坏）；
        额外投影 ``shareTypeLabel`` / ``openTypeLabel`` 旧平台编制规范中文（无条件共享/
        有条件共享/不予共享 等），UI 渲染用 label、机器逻辑用码。
        """
        return {
            "shareType": summary.get("shared_type"),
            "shareTypeLabel": _SHARE_TYPE_LABELS.get(str(summary.get("shared_type")), summary.get("shared_type")),
            "shareWay": summary.get("shared_way"),
            "shareCondition": summary.get("shared_condition") or "未登记附加共享条件，按受控申请审批。",
            "openType": summary.get("open_type"),
            "openTypeLabel": _OPEN_TYPE_LABELS.get(str(summary.get("open_type")), summary.get("open_type")),
            "openCondition": summary.get("open_condition") or "未登记公开条件。",
            "regionCode": record.region_code,
            "provider": summary.get("org_name") or summary.get("imported_by_org_name") or record.owner_org_id,
        }

    def catalog_meta(self, summary: dict[str, Any], record: Any) -> dict[str, Any]:
        """目录编制规范字段全集（反馈 5 — 不能少于旧平台目录编制规范）.

        旧平台「目录编制/目录维护」字段：数据资源分类、目录名称、来源系统、目录代码、
        内部部门、提供方、所属领域、应用场景、信息资源格式、业务/数据更新周期、共享方式、
        共享类型、共享条件、开放类型、开放条件、摘要。把它们从 summary_json 一次投影成
        机读 dict（缺则 None，前端诚实空态）。决策字段（共享/更新/提供方/摘要）由 accessPolicy
        + card 承载并占首屏；本块承载「次屏/折叠编目字段」全量，一个不少但不抢首屏。
        """
        body = self.summary_body(summary)
        provider = body.get("org_name") or body.get("imported_by_org_name") or record.owner_org_id
        resource_format = body.get("resource_format")
        update_cycle = body.get("update_cycle")
        return {
            "catalogName": record.title,
            "catalogCode": record.catalog_code,
            "catalogType": body.get("catalog_type"),
            "provider": provider,
            "internalDept": body.get("internal_org_name"),
            "domain": body.get("domain") or body.get("theme_group_id"),
            "sourceSystem": body.get("source_system") or body.get("from_system_name"),
            "resourceFormat": resource_format,
            "resourceFormatLabel": _RESOURCE_FORMAT_LABELS.get(str(resource_format), resource_format),
            "updateCycle": update_cycle,
            "updateCycleLabel": _UPDATE_CYCLE_LABELS.get(str(update_cycle), update_cycle),
            "catalogVersion": body.get("cata_version"),
            "publishedTime": body.get("published_time"),
            "summary": body.get("description"),
            "regionCode": record.region_code,
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
        out = ["来源：省一体化大数据平台共享目录", f"提供方：{detail.get('provider') or '—'}"]
        if fields:
            out.append(f"字段清单 {len(fields)} 项")
        if mapping_summary.get("total"):
            out.append(f"字段绑定证据 {mapping_summary['total']} 条（可审计回放）")
        return out

    def next_hints(
        self, fields: list[dict[str, Any]], mapping_summary: dict[str, Any]
    ) -> list[str]:
        """Suggested next actions for a catalog detail."""
        hints = ["先看字段口径和敏感级别", "只选择本次确需字段"]
        if not fields or mapping_summary.get("diagnosis") != "ok":
            hints.append("把未绑定字段写入缺口说明")
        return hints

    def discovery_summary(self, query: str, resources: list[dict[str, Any]]) -> dict[str, Any]:
        """Build the discovery aiCopilot summary card from the matched resources.

        Action H commit 3: lifted from ``BrainService._discovery_summary``;
        callers route through ``deps.services.catalog.discovery_summary(...)``.
        """
        base = copy.deepcopy(self.brain._snapshot["discovery"]["aiCopilot"])
        if resources and query:
            base["summary"] = f"已按“{query}”找到 {len(resources)} 条可申请目录或基础要素。先看字段、共享条件和字段证据；仍缺的字段再进入最小申请。"
            base["missingQuestions"] = ["是否限定使用区域或时间窗？", "本次只需要哪些字段，哪些字段属于缺口？"]
            base["nextActions"] = ["打开资源详情", "核对字段口径", "整理最小申请字段"]
            base["evidence"] = [item.get("name", item.get("id", "")) for item in resources[:3]]
        return base

    def resolve_resource_for_application(self, resource_id: str) -> dict[str, Any]:
        """Resolve catalog/provider aliases (e.g. cat-parking) to canonical discovery.resources rows.

        Action H commit 4: lifted from ``BrainService._resolve_resource_for_application``;
        callers route through ``deps.services.catalog.resolve_resource_for_application(...)``.

        R-001 fix (PR #149 local-acceptance): inline the discovery-resources lookup
        instead of calling ``zw_brain.command.demo_state_sync.resource_by_id`` —
        that was a runtime ``domain → command`` reverse-layer import (the only
        residual one after Action H). The 4-line lookup belongs naturally on the
        catalog service since it's a domain query over ``snapshot["discovery"]``.
        """
        from zw_brain.domain.errors import BrainServiceError, NotFoundError  # noqa: PLC0415

        snapshot = self.brain._snapshot

        def _discovery_resource_by_id(rid: str) -> dict[str, Any]:
            """Look up a discovery resource by id; raise NotFoundError when absent.

            Inlined from ``demo_state_sync.resource_by_id`` to keep the catalog
            service free of the ``domain → command`` reverse-layer import.
            """
            for item in snapshot["discovery"]["resources"]:
                if item["id"] == rid:
                    return item
            raise NotFoundError(rid)

        provider_cat = next(
            (
                c
                for c in snapshot.get("provider", {}).get("catalogs", [])
                if c.get("id") == resource_id
            ),
            None,
        )
        provider_canonical_id = (
            (provider_cat or {}).get("canonical_resource_id")
            or (provider_cat or {}).get("application_resource_id")
        )
        if provider_canonical_id:
            try:
                return copy.deepcopy(_discovery_resource_by_id(str(provider_canonical_id)))
            except NotFoundError as exc:
                raise BrainServiceError(
                    f"catalog {resource_id!r} declares canonical_resource_id {provider_canonical_id!r} but no matching discovery.resources entry exists"
                ) from exc
        try:
            return copy.deepcopy(_discovery_resource_by_id(resource_id))
        except NotFoundError:
            pass

        store = self.brain._state_store.database_store
        catalog_record = (
            store.catalog_repo.get_entry(resource_id, tenant_id=_DEFAULT_TENANT_ID)
            if store is not None
            else None
        )

        summary: dict[str, Any] = {}
        if catalog_record is not None:
            sr = catalog_record.summary_json
            summary = sr if isinstance(sr, dict) else {}
            if not summary.get("canonical_resource_id") and not summary.get("application_resource_id"):
                return self.brain.get_resource(resource_id)

        if (
            store is not None
            and store.resource_api_repo.get_asset(resource_id, tenant_id=_DEFAULT_TENANT_ID) is not None
        ):
            return self.brain.get_resource(resource_id)

        canonical_id = (
            summary.get("canonical_resource_id")
            or summary.get("application_resource_id")
            or (provider_cat or {}).get("canonical_resource_id")
            or (provider_cat or {}).get("application_resource_id")
        )
        if canonical_id:
            try:
                return copy.deepcopy(_discovery_resource_by_id(str(canonical_id)))
            except NotFoundError as exc:
                raise BrainServiceError(
                    f"catalog {resource_id!r} declares canonical_resource_id {canonical_id!r} but no matching discovery.resources entry exists"
                ) from exc

        legacy_ref = summary.get("legacy_object_ref") or summary.get("legacyId")
        if provider_cat:
            legacy_ref = legacy_ref or provider_cat.get("legacy_object_ref")

        if legacy_ref:
            matches = [
                item
                for item in snapshot["discovery"]["resources"]
                if (item.get("trueData") or {}).get("catalog_code") == legacy_ref
                or item.get("legacyId") == legacy_ref
            ]
            if len(matches) == 1:
                return copy.deepcopy(matches[0])
            if len(matches) > 1:
                raise BrainServiceError(
                    f"ambiguous legacy mapping for catalog or alias {resource_id!r}: {len(matches)} discovery.resources "
                    f"match legacy_object_ref {legacy_ref!r}; set canonical_resource_id on the catalog entry to a single discovery.resources id"
                )

        if catalog_record is not None:
            cc = catalog_record.catalog_code
            matches = [
                item
                for item in snapshot["discovery"]["resources"]
                if (item.get("trueData") or {}).get("catalog_code") == cc
            ]
            if len(matches) == 1:
                return copy.deepcopy(matches[0])
            if len(matches) > 1:
                raise BrainServiceError(
                    f"ambiguous catalog_code mapping for {resource_id!r}: {len(matches)} resources share catalog_code {cc!r}; "
                    f"set canonical_resource_id on the catalog entry"
                )

        raise NotFoundError(resource_id)
