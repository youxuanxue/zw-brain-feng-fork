---
doc_id: j1-catalog-drilldown-acceptance-package
status: approved
gate: signed
scope: j1-catalog-drilldown
evidence: .testing/acceptance/j1-catalog-drilldown/evidence.json
signed_off_by: 海若产品部业务方
signed_off_at: 2026-05-30
sign_off_required:
  - 海若产品部业务方
vehicle_pr: "#171"
driven_by:
  - CLAUDE.md D42.b（F9 验收记的"下个 PR 打通目录主表录入 + 目录详情页"）
  - tests/test_catalog_resource_list.py
  - tests/e2e/j1_catalog_drilldown.spec.ts
---

# j1-catalog-drilldown 效果验收材料包 — 目录→资源钻取链路

> **D37 效果验收**（"做完的东西真能跑"）。本 PR #171 兑现 D42.b（F9 验收时记的"下个 PR
> 打通目录主表录入 + 目录详情页"）。验收点挂 `.testing/acceptance/j1-catalog-drilldown/evidence.json`，
> 由 `capture_acceptance_evidence.py` 在**干净全量真实库**（customer_acceptance_up 重建，1222 目录/186 资源）现场跑出，段 55 守卫。

## 验收范围

**覆盖**：
- 后端能力 `catalog.resource.list`（目录→资源钻取：列目录下 resource_asset；挂0资源诚实空列表；目录不存在404）+ 仓库方法 `list_assets_by_catalog` + 段28三一致 + 5消费面投影。
- 前端 `P2CatalogDetail`（目录详情页 `#/discovery/catalog/:code`）+ `P2CatalogBrowse` 接 `catalog.browse` 真 API 真钻取（修软搜索假钻取）。
- 目录浏览页信息增强：资源数列 + 责任方机构名（summary.org_name）+ 摘要列。
- seed 真实数据底座（学生课程信息 + 其下真资源；F9 5 医保目录录入主表可检索，兑现 D42.b）+ sync 录 catalog_code 断点修复。

**不在本次范围**：
- 全局其他 snapshot 字段数据缺位（资源发现空 query / 申请 / 审批 / 专题包列表仍 seed 精选）——已记 `docs/decisions/global-data-gap-audit.md`，另起 PR。
- 真数据 baseline 脆测试批量修——另起 test-fix PR。

## 验收点 + 证据

| 验收点 | evidence（机读证据） | 结果 | 业务方判定 |
|---|---|---|---|
| 5 消费面投影一致（含 catalog.resource.list 新能力零漂移） | `5 消费面投影一致`（contract） | pass | ☑ 通过 |
| 后端真链路全绿：能力 + 仓库 + 集成测试（有资源/空/404/分页/角色） + 全套不回归 | `后端 / 契约测试套`（pytest exit 0，干净全量真实库） | pass | ☑ 通过 |
| 目录→资源钻取真端到端：目录浏览列真目录 + 点目录看资源列表 + F9 医保目录诚实空 | `WebUI 活跑验收（j1_catalog_drilldown（真实库实跑））`（e2e 3 passed） | pass | ☑ 通过 |

## 业务方眼见为实（本地全集真实库逐页走查，2026-05-30 全部通过）

- 目录浏览页 `#/discovery/catalog-browse`：列真目录，每行「资源数」列（有资源蓝色高亮 / 0 灰显）、责任方机构名（"江西省教育厅"等）、说明列。
- 点目录 → 目录详情页：学生课程信息→9 资源；2023年物业管理维修资金→诚实空。
- F9 医保目录（医疗救助信息）→ 主表可检索 + 诚实空列表（兑现 D42.b）。

## 数字纪律

测试/投影计数为事实计数，住 evidence.json（脚本采集），prose 不裸写易漂移数字。

## 落盘（验收通过后 — 2026-05-30 业务方本地验收全部通过）

- [x] **A**：plan.yaml `[SIGNOFF-CLOSED 2026-05-30] covers j1-catalog-drilldown`
- [x] **B**：PR #171 加 label `business-signoff: j1-catalog-drilldown`
- [x] **C**：CLAUDE.md 追加 `D43` 决策条
- [x] **D**：本文 frontmatter `status: approved`

> A/C 由段 54 校验；本文证据真实性 + 结构由段 55 校验。
> 业务方 2026-05-30 本地全集真实库逐页走查通过。合并到 main 待产品负责人指令。
