"""J1 `data.search` handler — search_resources 从 BrainService 物理迁出（F1 turn 2）。"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.discovery_snapshot_projection import (
    DISCOVERABLE_STATUSES,
    project_resource_cards,
)
from zw_brain.domain.resource_kind import canonical_resource_kind
from zw_brain.domain.resource_lifecycle import lifecycle_label
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID


def _recall_candidates(deps: Any, haystack: str, seen_ids: set[str]) -> list[dict[str, Any]]:
    """NL 召回字典命中 → 卡片（单一真相：0604 试用「两个入口效果不一样」修复）。

    召回项先回查目录库：**查得到 → 给真卡**（真 id、详情可达、真实状态中文标签——与
    目录浏览入口同一真相，哪怕该状态不在 D53① 默认发现集合（active-only），显式搜索
    命中即如实呈现——申请入口由前端按机器值门控，未发布不可申请）；
    查不到才给「录入中」诚实 stub（白话文案，无工程 token；前端按 recall_dictionary
    渲染为无链接软候选）。
    """
    out: list[dict[str, Any]] = []
    recall = deps.view.discovery.get_recall_dictionary()
    for entry in recall.get("sample_titles", []):
        title = entry.get("title", "")
        if not title or haystack not in title.lower():
            continue
        record = next(
            (
                r
                for r in deps.repos.catalog.search_entries(title, tenant_id=_DEFAULT_TENANT_ID)
                if r.title == title
            ),
            None,
        )
        if record is not None:
            # record_to_card_dict 已产中文 status + lifecycleStatus 原值（单一事实源），不再二次翻译。
            card = deps.services.catalog.record_to_card_dict(record)
            if card["id"] not in seen_ids:
                seen_ids.add(card["id"])
                out.append(card)
            continue
        cand_id = f"recall:{title}"
        if cand_id in seen_ids:
            continue
        seen_ids.add(cand_id)
        out.append(
            {
                "id": cand_id,
                "name": title,
                "provider": entry.get("owner_org_id", "") or "—",
                "zone": "官方目录推荐",
                "status": "录入中",
                "desc": "该目录已收录于官方目录字典，正在录入。",
                "kind": "recall_dictionary",
                "score": 60,
                "repository": {
                    "catalogCode": cand_id,
                    "lifecycleStatus": entry.get("lifecycle_status", "active"),
                    "ownerOrgId": entry.get("owner_org_id") or "",
                },
            }
        )
    return out


def handler(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    query = str(payload.get("query", ""))
    # LLM 工具编排常把可选字段显式填 null（page: null）；get("page", 1) 只在键缺失时回落，
    # 键存在为 None 时不回落 → int(None) 崩。用 `or 1` 对齐全仓既有惯例
    # （request.py / recommendation_suggest.py / direct_access.py / audit.py 同款），None 安全。
    page = int(payload.get("page") or 1)
    return search_resources(brain, query, page)


def _active_catalog_cards(
    deps: Any,
    records: list[Any],
    store: Any,
) -> list[dict[str, Any]]:
    """Project active catalog records for P2 data.search.

    `catalog.browse` defaults to active, real catalog entries. `data.search`
    must use the same availability gate: lifecycle active is enough for a
    directory card to be searchable/applicable. Topic projection cards are kept
    as explanation metadata only; they must not hide active catalog entries from
    search.
    """
    cards_by_catalog = deps.services.catalog.topic_projection_cards_by_catalog(
        [record.catalog_code for record in records], store
    )
    return [
        deps.services.catalog.record_to_card_dict(record)
        | {"topicProjections": cards_by_catalog.get(record.catalog_code, [])}
        for record in records
    ]


def search_resources(brain: BrainService, query: str, page: int = 1) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action B/C — recover deps for view/repo access
    query = query.strip()
    store = deps.state_store.database_store
    if store is None:
        haystack = query.lower()
        resources = []
        for item in deps.view.discovery.get_resources():  # Action C — read facade (deepcopies once)
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
        for api_res in deps.view.resources.list_api_resources():
            # 发现/找数据只展示已发布 active（D53①，与快照发现路径同口径——单一事实源
            # DISCOVERABLE_STATUSES）。待发布/审核中/暂停/过期/草稿/下线一律不进搜索结果，
            # 杜绝搜出未发布资源点进去却不可申请的断头路。
            if api_res.get("lifecycle_status") not in DISCOVERABLE_STATUSES:
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
                        # status=中文展示态（前端零词表）；lifecycleStatus=原值供前端申请门控比对。
                        "status": lifecycle_label(api_res.get("lifecycle_status", "active")),
                        "lifecycleStatus": api_res.get("lifecycle_status", "active"),
                        "desc": str(summary.get("desc") or summary.get("domain") or api_res.get("title", "")),
                        "kind": "api",
                        # 读路径折叠（D53）：service/未知 → api，绝不裸出 legacy kind 到「资源类型」筛选。
                        "resource_kind": canonical_resource_kind(api_res.get("resource_kind")) or "api",
                    }
                )
        # NL recall — append real-catalog candidates from the recall dictionary
        # when the query matches a dictionary title. Only fires when query is
        # non-empty (would otherwise add 25 thin cards to every page load).
        if haystack:
            seen_ids = {r["id"] for r in resources}
            resources.extend(_recall_candidates(deps, haystack, seen_ids))
    else:
        if not query:
            # D45 — 空搜索默认视图：DB 有真实资源则展现全量真实库（与 system.snapshot
            # discovery.resources enrich 同源），空库回退 seed 精选。
            real = project_resource_cards(tenant_id=_DEFAULT_TENANT_ID)
            resources = real if real else deps.view.discovery.get_resources()  # Action C — already deepcopied
        else:
            haystack = query.lower()
            records = deps.repos.catalog.search_entries(
                query,
                tenant_id=_DEFAULT_TENANT_ID,
                lifecycle_status="active",
                exclude_catalog_code_prefix="api-group:",
            )
            # P1 N+1 消除：旧实现对每条命中 record 各跑一次 topic_projection_cards
            # （每次遍历全部专题包），且 :111 与 is_discoverable 内各算一遍（重复计算）。
            # 改为：一次性批量算出所有命中 catalog 的投影卡片（catalog→package 反查索引 +
            # 单次 list batch context），再 O(1) 复用，既去重复算也去三重嵌套 N+1。
            # 但可申请搜索入口的可见性口径与 catalog.browse/catalog.entry.query
            # 对齐为 active 目录；专题 projectionStatus 仅作说明，不再过滤搜索结果。
            resources = _active_catalog_cards(deps, records, store)
            existing_ids = {r["id"] for r in resources}
            for item in deps.view.discovery.get_resources():  # Action C — read facade
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
            for api_res in deps.view.resources.list_api_resources():
                # 发现/找数据只展示已发布 active（D53①，与快照发现路径同口径——单一事实源
                # DISCOVERABLE_STATUSES）。待发布/审核中/暂停/过期/草稿/下线一律不进搜索结果，
                # 杜绝搜出未发布资源点进去却不可申请的断头路。
                if api_res.get("lifecycle_status") not in DISCOVERABLE_STATUSES:
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
                        # status=中文展示态（前端零词表）；lifecycleStatus=原值供前端申请门控比对。
                        "status": lifecycle_label(api_res.get("lifecycle_status", "active")),
                        "lifecycleStatus": api_res.get("lifecycle_status", "active"),
                        "desc": str(summary.get("desc") or summary.get("domain") or api_res.get("title", "")),
                        "kind": "api",
                        # 读路径折叠（D53）：service/未知 → api，绝不裸出 legacy kind 到「资源类型」筛选。
                        "resource_kind": canonical_resource_kind(api_res.get("resource_kind")) or "api",
                    }
                )
            resources.extend(_recall_candidates(deps, haystack, existing_ids))
    page = max(page, 1)
    page_size = 20
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "query": query,
        "page": page,
        "results": resources[start:end],
        "total": len(resources),
        "summary": deps.services.catalog.discovery_summary(query, resources),
    }
