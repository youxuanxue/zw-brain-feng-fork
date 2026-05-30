---
doc_id: j1-data-gap-acceptance-package
status: approved
gate: signed
scope: j1-data-gap
evidence: .testing/acceptance/j1-data-gap/evidence.json
signed_off_by: 海若产品部业务方
signed_off_at: 2026-05-30
sign_off_required:
  - 海若产品部业务方
vehicle_pr: "#173"
driven_by:
  - CLAUDE.md D45 / D45.a / D45.b / D45.c（全局数据缺位修复 + 可用过滤 + 卡片密度 + 共享类型）
  - docs/decisions/global-data-gap-audit.md（D43.c(1) 审计地图）
  - tests/test_discovery_snapshot_projection.py
  - tests/e2e/j1_data_gap.spec.ts
---

# j1-data-gap 效果验收材料包 — J1 列表全量真实库投影 + 发现页可用过滤 + 卡片密度

> **D37 效果验收**（"做完的东西真能跑"）。本 PR #173 闭合 **D43.c(1)**（全局数据缺位 →
> 另起 PR）。验收点挂 `.testing/acceptance/j1-data-gap/evidence.json`，由
> `capture_acceptance_evidence.py` 在**干净全量真实库**（customer_acceptance_up 重建，
> 1222 目录 / 186 资源）现场跑出，段 55 守卫。

## 验收范围

**覆盖**：
- 后端 `zw_brain/domain/discovery_snapshot_projection.py`（3 enrich + `project_resource_cards`）：
  `system.snapshot` 的 `requests` / `approvals` / `discovery.resources` 由 seed 静态精选（5/5/12）
  升为 DB 全量真实库投影（replace-when-DB-nonempty-else-keep-seed）。
- requests = 申请类（排除需求类 require/original_require → 属 J2 供需线）；轻量 serializer 护 D-9 perf。
- 发现页默认只展示「可用」资源（D45.b：active + 待发布；草稿/审核/暂停/下线/过期不进默认视图）。
- `data.search` 空 query 改查 DB 全量真实资源（复用 `project_resource_cards`）。
- 资源卡信息密度优化（D45.c）：响应式多列 + 物化形态徽标（库表/文件/接口…）+ 更新日 +
  **共享类型色级 chip**（无条件/有条件/不予）+ 清洗 desc 噪声。共享类型映射权威 = 源表
  `dc_resource_base_info` DDL「1：无条件 2：有条件 3：不予」+ 真实数据双重确认。

**不在本次范围**：
- `data.search` typed query 返回目录而非资源（预存语义不一致，记 debt，另议）。
- P3RequestDetail prefilledFields 富字段（轻量卡 by-design 留空，记 debt R-001，待 detail 取数）。
- update_cycle 更新周期（源表注释「见附录4」、仓内无权威码表 → 守 D11 不猜测，本批不展示，记 debt）。
- 死字段 `topic_packages` / `provider.catalogs` / `discovery.catalogTree`·`recallDictionary`（#171/F9 后零/近死消费者，不做）。

## 验收点 + 证据

| 验收点 | evidence（机读证据） | 结果 | 业务方判定 |
|---|---|---|---|
| 5 消费面投影零漂移（本 PR 未改 manifest） | `5 消费面投影一致`（contract） | pass | ☑ 通过 |
| 后端真链路全绿：discovery_snapshot_projection 单测（replace/排他/保留 seed 两端 + 共享类型映射 + data.search）+ 全套不回归 | `后端 / 契约测试套`（pytest exit 0，干净全量真实库） | pass | ☑ 通过 |
| WebUI 活跑：发现页只展可用 + 多列 + 类型徽标 + 共享色 chip；P3 在途申请/待我审批全量真实库 | `WebUI 活跑验收（j1_data_gap（真实库实跑））`（e2e 3 passed） | pass | ☑ 通过 |

## 业务方眼见为实（本地全集真实库逐页走查，2026-05-30 全部通过）

- **A1 在途申请**：seed 5 → **全量真实申请**（列表带状态色 pill + 查看；申请人 PII 脱敏 `平****`）。
- **A2 待我审批**（审批角色）：seed 5 → **全量真实待审**（按 id 交叉引用 pending 申请）。
- **A3 资源发现**：seed 12 → **75 可用资源**（186 全量过滤掉 113 非可用态）；**4 列**密排；
  类型徽标（库表/文件/文件夹/接口/链接）；**共享类型色 chip**（无条件 49 绿 + 有条件 26 琥珀）；
  状态只剩 `可复用/待发布`（草稿/已下线/已过期挡在默认视图外，详情/目录线仍可达）。
- **C1 申请详情**：真实申请可开，复用资源 / 申请人(脱敏) / 用途 / 状态 / 时间全可见。
- **纠错保障**：共享类型映射用源表 DDL 权威（纠正 `approval_flow_baseline` 反向常量陷阱，避免把有条件标成无条件的合规风险）。

## 落盘三角

- **A（evidence）**：`.twin/e1-j1-journey/plan.yaml` `[SIGNOFF-CLOSED 2026-05-30 ... covers j1-data-gap]`。
- **B（PR label）**：PR #173 label `business-signoff: j1-data-gap`。
- **C（决策）**：CLAUDE.md D45 / D45.a / D45.b / D45.c（含 scope `j1-data-gap`）。
