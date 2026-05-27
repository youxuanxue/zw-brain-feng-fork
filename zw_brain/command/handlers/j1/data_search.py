"""J1 `data.search` handler — search_resources 从 BrainService 物理迁出（F1 turn 2）。"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


def handler(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    query = str(payload.get("query", ""))
    page = int(payload.get("page", 1))
    return search_resources(brain, query, page)


def search_resources(brain: BrainService, query: str, page: int = 1) -> dict[str, Any]:
    query = query.strip()
    store = brain._state_store.database_store
    if store is None:
        haystack = query.lower()
        resources = []
        for item in brain._snapshot["discovery"]["resources"]:
            text = " ".join(
                [
                    item["name"],
                    item["desc"],
                    item["provider"],
                    item["zone"],
                    " ".join(item.get("fields", [])),
                    " ".join(item.get("explain", [])),
                ]
            ).lower()
            if not haystack or haystack in text:
                resources.append(copy.deepcopy(item))
        for api_res in brain._snapshot.get("api_resources", []):
            if api_res.get("lifecycle_status") in {"draft", "revoked"}:
                continue
            summary = api_res.get("summary_json") or {}
            text = " ".join(
                [
                    api_res.get("title", ""),
                    api_res.get("resource_code", ""),
                    api_res.get("owner_org_id", ""),
                    str(summary.get("domain", "")),
                    str(summary.get("desc", "")),
                ]
            ).lower()
            if not haystack or haystack in text:
                resources.append(
                    {
                        "id": api_res["resource_code"],
                        "name": api_res.get("title", api_res["resource_code"]),
                        "provider": api_res.get("owner_org_id", ""),
                        "zone": "API 资源",
                        "status": api_res.get("lifecycle_status", "active"),
                        "desc": str(summary.get("desc") or summary.get("domain") or api_res.get("title", "")),
                        "kind": "api",
                        "resource_kind": api_res.get("resource_kind"),
                    }
                )
        # NL recall — append real-catalog candidates from the recall dictionary
        # when the query matches a dictionary title. Only fires when query is
        # non-empty (would otherwise add 25 thin cards to every page load).
        if haystack:
            seen_ids = {r["id"] for r in resources}
            recall = brain._snapshot.get("discovery", {}).get("recallDictionary", {})
            for entry in recall.get("sample_titles", []):
                title = entry.get("title", "")
                if not title or haystack not in title.lower():
                    continue
                cand_id = f"recall:{title}"
                if cand_id in seen_ids:
                    continue
                seen_ids.add(cand_id)
                resources.append(
                    {
                        "id": cand_id,
                        "name": title,
                        "provider": entry.get("owner_org_id", "") or "—",
                        "zone": "官方目录推荐",
                        "status": entry.get("lifecycle_status", "active"),
                        "desc": f"NL 召回字典命中（来自 dsp_catalog 真数据，{entry.get('lifecycle_status','active')}）。",
                        "kind": "recall_dictionary",
                        "score": 60,
                        "repository": {
                            "catalogCode": cand_id,
                            "lifecycleStatus": entry.get("lifecycle_status", "active"),
                            "ownerOrgId": entry.get("owner_org_id") or "",
                        },
                    }
                )
    else:
        if not query:
            resources = [copy.deepcopy(item) for item in brain._snapshot["discovery"]["resources"]]
        else:
            haystack = query.lower()
            records = store.catalog_repo.search_entries(query, tenant_id=_DEFAULT_TENANT_ID)
            resources = [
                brain._catalog_record_to_card_dict(record) | {"topicProjections": brain._catalog_topic_projection_cards(record.catalog_code, store)}
                for record in records
                if brain._catalog_is_discoverable(record, store)
            ]
            existing_ids = {r["id"] for r in resources}
            for item in brain._snapshot["discovery"]["resources"]:
                text = " ".join(
                    [
                        item["name"],
                        item["desc"],
                        item["provider"],
                        item["zone"],
                        " ".join(item.get("fields", [])),
                        " ".join(item.get("explain", [])),
                    ]
                ).lower()
                if haystack not in text:
                    continue
                if item["id"] in existing_ids:
                    continue
                existing_ids.add(item["id"])
                resources.append(copy.deepcopy(item))
            for api_res in brain._snapshot.get("api_resources", []):
                if api_res.get("lifecycle_status") in {"draft", "revoked"}:
                    continue
                summary = api_res.get("summary_json") or {}
                text = " ".join(
                    [
                        api_res.get("title", ""),
                        api_res.get("resource_code", ""),
                        api_res.get("owner_org_id", ""),
                        str(summary.get("domain", "")),
                        str(summary.get("desc", "")),
                    ]
                ).lower()
                if haystack not in text:
                    continue
                rid = api_res["resource_code"]
                if rid in existing_ids:
                    continue
                existing_ids.add(rid)
                resources.append(
                    {
                        "id": rid,
                        "name": api_res.get("title", rid),
                        "provider": api_res.get("owner_org_id", ""),
                        "zone": "API 资源",
                        "status": api_res.get("lifecycle_status", "active"),
                        "desc": str(summary.get("desc") or summary.get("domain") or api_res.get("title", "")),
                        "kind": "api",
                        "resource_kind": api_res.get("resource_kind"),
                    }
                )
            recall = brain._snapshot.get("discovery", {}).get("recallDictionary", {})
            for entry in recall.get("sample_titles", []):
                title = entry.get("title", "")
                if not title or haystack not in title.lower():
                    continue
                cand_id = f"recall:{title}"
                if cand_id in existing_ids:
                    continue
                existing_ids.add(cand_id)
                resources.append(
                    {
                        "id": cand_id,
                        "name": title,
                        "provider": entry.get("owner_org_id", "") or "—",
                        "zone": "官方目录推荐",
                        "status": entry.get("lifecycle_status", "active"),
                        "desc": f"NL 召回字典命中（来自 dsp_catalog 真数据，{entry.get('lifecycle_status','active')}）。",
                        "kind": "recall_dictionary",
                        "score": 60,
                        "repository": {
                            "catalogCode": cand_id,
                            "lifecycleStatus": entry.get("lifecycle_status", "active"),
                            "ownerOrgId": entry.get("owner_org_id") or "",
                        },
                    }
                )
    page = max(page, 1)
    page_size = 20
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "query": query,
        "page": page,
        "results": resources[start:end],
        "total": len(resources),
        "summary": brain._discovery_summary(query, resources),
    }
