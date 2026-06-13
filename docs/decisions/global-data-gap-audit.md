---
title: 全局数据缺位审计 — snapshot 字段 seed 精选 vs 真实库
scope: global-data-gap-audit
kind: 工程审计记录（非 GATE 决策；backlog 已由 D45 处置）
status: resolved  # 审计 backlog 已由 D45（2026-05-30）穿透代码事实处置，详见正文「状态」段
date: 2026-05-30
authors: 工程交付（产品研发负责人审阅）
related_docs:
  - CLAUDE.md D45 决策索引
---

# 全局数据缺位审计 — snapshot 字段 seed 精选 vs 真实库

> **状态（2026-05-30 D45 更新）**：本审计 backlog 已由 **D45** 处置——穿透代码事实把 5 项缺位
> **收敛为 3 项 alive 并修复**，其余 3 项判定为 #171/F9 后的**死消费者、不做**（详见下「D45 处置」节）。
> 原始审计结论保留在下文作上下文。
>
> **审计原状态**：审计结论 + 修复 backlog。2026-05-30 本地验收（全集真实库）逐个发现"页面显示 seed
> 精选 demo 而非真实库全量"后，做的系统性全局审计。**不在 PR #171（钻取链路）范围**——
> 钻取已独立完整合入；本文供**另起的「全局数据缺位修复」PR** 用。

## D45 处置（2026-05-30，关本 backlog）

穿透前端消费者代码事实，审计的 5 项缺位**收敛为 3 项 alive**（其余已是死消费者）：

| 字段 | 处置 | 说明 |
|---|---|---|
| `requests` | ✅ **已修**（`enrich_requests_snapshot`） | 真实库**申请类 97 条**（排除 166 需求类 require/original_require → 属 J2 供需线）。审计原写"263"是含需求的 naive 计数。 |
| `approvals` | ✅ **已修**（`enrich_approvals_snapshot`） | 真实库 267 approval_case，轻量 `{id, suggestion}`，P3 按 id 交叉引用 requests。 |
| `discovery.resources` | ✅ **已修**（`enrich_discovery_resources_snapshot`） | 真实库 **resource_asset 186**（资源中心，架构 §5.2.1；P2CatalogBrowse #171 已独占目录浏览）。**D45.b**：默认只展示「可用」= active+待发布 = **75**（草稿/审核/暂停/下线/过期不进默认视图）。**D45.c**：卡片信息密度优化（多列 + 类型徽标 + 更新日 + 清洗 desc 噪声）。 |
| `provider.catalogs` | ❌ **不做（近死）** | 仅 P5 `deriveFieldDecisions` fallback，已被 DB `field_decisions`（`enrich_provider_snapshot`）取代。 |
| `topic_packages` | ❌ **不做（死）** | P7 已走 live `topic.package.query`（F9），零 snapshot 消费者。 |
| `discovery.catalogTree` / `recallDictionary` | ❌ **不做（死）** | 零前端消费者。 |

实现：`zw_brain/domain/discovery_snapshot_projection.py`（3 enrich + `project_resource_cards`）；接线
`system_ops.py` snapshot handler + `data.search` 空 query。merge = **DB 有行替换 / 空库保留 seed**（CI 不变）。
轻量 serializer（禁用 `record_to_request` 重序列化器，护 D-9 perf）。详见 CLAUDE.md **D45**。

**follow-up（D45.a，未做）**：`data.search` **typed** query 返回 `catalog_entry`（目录）而非 resource——
与 P2Discovery 资源中心语义的预存不一致；属搜索语义重构，记 `docs/preflight-debt.md`。

---

> **数据策略前提**：本地验收/演示用全集真实库（customer_acceptance_up 导入，catalog_entry
> 1222 / resource_asset 186）；CI 用 seed 最小真实对。本文针对的是"产品默认页展示 seed 精选
> 而非真实库"的缺位。

## 根因（一句话）

`/api/snapshot` → `system.snapshot`（`system_ops.py:48-55`）= `brain.snapshot()`（**seed_snapshot.json
静态基底**）+ 三个 `enrich_*`（provider / zones / disputes，用 DB 真实数据增强）。**核心列表字段
（资源发现 / 申请 / 审批 / 专题包）没有 enrich**，停在 seed 精选 demo → 真实库有几百条、页面只显示 5-12 条。
这统一解释了逐个发现的所有"数据缺位"问题。

## 全局数据缺位地图（核实真实数字 2026-05-30）

| 字段 | 数据源现状 | seed 精选 | 真实库 | 缺位 | 消费页面 | 严重度 |
|---|---|---|---|---|---|---|
| `discovery.resources`（资源发现空 query） | seed 静态，未 enrich | 12 | 186 (resource_asset) | 174 | P2 资源发现 | 🔴 |
| `provider.catalogs`（目录） | seed 静态 | 8 | 154 (catalog_entry active) | 146 | P2/P5 | 🔴 |
| `requests`（申请流） | seed 静态 | 5 | 266 (application_record) | 261 | P1 工作台 / P3 申请流 | 🔴 |
| `approvals`（审批流） | seed 静态 | 5 | 270 (approval_case) | 265 | P1/P3 | 🔴 |
| `topic_packages`（专题包） | seed 静态（F9 建的 enrich 是 zones 不是这个） | 3 | 113 (topic_package) | 110 | P7 专题 | 🟠 |
| `delivery_tasks`（交付） | **已 enrich**（list_delivery_tasks 替换） | 5 | 67 | — | P4 交付 | ✅ 已真实 |
| `disputes`（异议） | **已 enrich**（enrich_disputes_snapshot merge） | — | — | — | B1.1 | ✅ 已真实 |
| `provider.{field_decisions,hookup_reviews,demand_matches,objection_cases}` | **已 enrich**（enrich_provider_snapshot） | — | — | — | P5 | ✅ 已真实 |
| `workbench`（各角色仪表板） | seed-only | — | — | — | P1 | ~ 设计即精选，无需改 |

## 能力层缺位（query 类空参返回 seed）

- `data.search`（`data_search.py:100-102`）：空 query 走 `deps.view.discovery.get_resources()`（seed 12 条），
  不查全库；有 query 才 `search_entries`（搜真实库**目录** catalog_entry，非资源）。
  → 资源发现页空 query = seed 12 条。**注**：搜出的是目录（kind=catalog_entry），与「资源发现」
  页名存在语义混淆（该页本质是目录发现 + 钻取看资源，与 PR #171 钻取链路配套）。

## 修复模式（现成可复用）

`enrich_provider_snapshot`（`provider_snapshot_projection.py:147-163`）的 **seed←DB merge 范式**：
```
out = copy.deepcopy(snapshot)
inbox = project_*_from_db(tenant_id)   # 查真实库
out[key] = inbox[key]                   # DB 数据覆盖/合并 seed 字段
```
三种变体：(1) seed+DB merge（provider，推荐）；(2) 完全替换（delivery_tasks）；(3) 追加 dedup-merge（disputes）。

## 修复 backlog（另起 PR，按严重度）

- **P1（阻挡"真实数据充分展现"验收）**：
  - `enrich_discovery_resources`（让资源发现页空 query 展现全库资源/目录）+ `data.search` 空 query 改查 DB
  - `enrich` provider.catalogs（目录列表全量）
- **P2**：`enrich_requests` / `enrich_approvals`（J1 申请/审批流列表全量）
- **P3**：`enrich_topic_packages`（P7 专题包全量）；api_resources / audit_events / capability_packages 逐个评估
- **配套**：资源发现页语义澄清（目录发现 vs 资源），与 PR #171 钻取链路对齐

## 关键文件
- `zw_brain/command/handlers/b1/system_ops.py:48-55`（enrich 入口，新 enrich_* 在此挂）
- `zw_brain/domain/provider_snapshot_projection.py:147-163`（enrich 范例）
- `zw_brain/domain/dispute_snapshot_projection.py`（merge 范例）
- `zw_brain/command/handlers/j1/data_search.py:100-102`（空 query 缺位点）
- `zw_brain/command/views.py:131-133`（discovery facade）

## 验证（修复 PR 收尾）
- 本地全集真实库起服务，逐页确认：资源发现/目录/申请/审批/专题包默认展现真实库全量（非 seed 精选）。
- CI seed 最小对仍绿（enrich 在 DB 有数据时覆盖、无数据时回退 seed，不破坏 CI 测试）。
