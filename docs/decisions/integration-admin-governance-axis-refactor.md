---
title: 接入扩展中心重构 — 能力来源叙事 + 外部接入治理 + 身份治理融入（诚实化）
scope: integration-admin-governance-axis
status: proposed  # IA + 角色可见性确认（D28 GATE）：本 PR 提议，最终由产品研发负责人在合并时 ratify → 届时登记 D52 + 落 .testing/signoff 账本
date: 2026-06-04
deciders: 海若产品部产品研发负责人（GATE 决策门 / 上帝视角乔布斯）
authors:
  - Claude Opus 4.8 (1M context) — 乔布斯式产品专家 + 高级软件研发工程师（worktree 设计与实现）
related_docs:
  - docs/decisions/runtime-capability-registration-bridge-proposal.md  # B：真·自助接入 + 热更新的架构前提（本 PR 只做诚实信号，不做假按钮）
  - docs/approved/zw-brain-architecture.md          # §5.1 信息架构 2 旅程 + B1 后台；§9.5 adapter 写禁区
  - docs/approved/zw-brain-data-model.md            # B1.2：capability_package / capability_exposure / tenant_capability_policy
  - docs/customer-readiness/trial-feedback-0604-resolutions.md # 「接入管理文字太技术」改名先例（本 PR 前序低风险整改）
related_code:
  - zw-brain-web/src/pages/B12IntegrationAdmin.vue  # 接入扩展中心（能力总览 / 外部接入 / 身份治理）
  - zw-brain-web/src/pages/B12PackageDetail.vue     # 外部系统详情（开放范围段）
  - zw_brain/command/handlers/b1/intake.py          # exposure matrix 行增 name/description 投影（去 slug）
  - zw_brain/command/dispatch.py                    # 静态分发（诚实「已接入≠已能跑」的根因，见 B 方案）
evidence:
  - docs/decisions/evidence/integration-admin-governance-axis/01-overview.png
  - docs/decisions/evidence/integration-admin-governance-axis/02-browse-external.png
  - docs/decisions/evidence/integration-admin-governance-axis/03-external-systems.png
---

# 接入扩展中心重构 — 能力来源叙事 + 外部接入治理 + 身份治理融入

> 研发阶段：**设计 + 实现（独立 worktree / PR #214）**，停在 `[人工审批]` 合并门前。
> 触发：试用现场对「接入管理」页的连环诘问——三个平级 tab 像杂物间；「能力接入 5」与「开放范围 238」啥关系；
> 开放范围全是技术术语看不懂；身份治理要不要融入。第一版（两轴 + 保留总览）是**化妆，没解决根因**，被负责人当场戳穿，本版重做。

## 〇 · 乔布斯审视与根因（聚焦 / 简洁 / 端到端 / 设计即工作方式 / 精品意识）

根因是**把"整个平台能力注册表"误当成"接入治理对象"摆出来**：旧「开放范围总览」倒出全部 238 条原始 manifest（slug），
其中 224 条是平台**内置**功能（产品本身），只有 14 条才是外部带进来的。于是用户看到 5 和 238 对不上、满屏 slug，必然困惑。

收敛成一个产品判断：**同一能力底座，两种来源，两套准入强度。** 数字自洽 `238 = 内置 224 + 外部 14`；`5 = 外部接入的系统数`。
页面叙事从"倒注册表"改为"讲来源"，全程人话，并对**做不到的事诚实**（外部能力今天还不能跑；内置不能表单热加）。

## 一 · 决策（上帝视角乔布斯裁决）

- **D-a 按来源组织,「能力总览」当主屏**：现算 `内置(execution_binding=builtin) / 外部(external_capability)` 两卡 + 占比 + 按业务域分布。
  一屏说清 5↔238,消除困惑。
- **D-b 杀掉 238 行 raw slug 矩阵**：换**人话化浏览**——中文 title + 中文说明 + 中文消费面（页面/接口/命令行/MCP/智能体互联）+ 中文状态;
  slug 降级为右侧灰色「技术编号」。后端 `_matrix_row_from_manifest` 增 `name`/`description` 投影（238 manifest 全自带 title/description,只读不重算）。
- **D-c 外部接入治理 + 诚实信号**：「外部接入」tab = 5 个外来系统的审批/启停/回滚/信任级 lifecycle;
  **明示「审批接入治理已就位,但外部能力的实际运行时调用待执行桥(AgentRuntime)打通——已接入 ≠ 已能跑」**(不 overclaim)。
- **D-d 身份治理融入为第三个治理 tab**（负责人已定）：治理轴 = 能力总览 / 外部接入 / 身份治理;配置轴 = 流程与表单配置。
  身份治理保留既有子页路由（契约测试不破）,以 tab 样式入口导航进入。
- **D-e 内置可扩展 = 研发代码路径,不放假自助按钮**：内置卡如实说"由研发按能力注册路径新增,非运行时自助"。
  **真·自助接入 + 热更新今天做不到**（静态 DISPATCH_TABLE + 段28 三处一致 + external_capability 空壳）,需先建执行底座——见 B 方案
  `runtime-capability-registration-bridge-proposal.md`,属独立架构 + 安全门立项。
- **D-f 角色可见性已满足**：本页已经 productShellNav 角色门(`ROLE_BUSIAUDIT`/`ROLE_SYSTEM`)+路由守卫限定;
  仅修正陈旧注释,**不改角色集**（BUSIAUDIT 是本页主操作角色）。

## 二 · 本期实现（已落地 + 真 UI 验证）

前端 + 一处只读后端投影,加法式、可逆,无路由/角色改动:

1. `intake.py`：matrix 行增 `name`(title)+`description`(只读投影,238 manifest 自带)。
2. `B12IntegrationAdmin.vue`：能力总览主屏(来源两卡 + 业务域分布 + 人话浏览) + 外部接入 tab(人话 + 诚实信号) + 身份治理 tab + 配置轴;全程中文 label 映射(R12)。
3. `B12PackageDetail.vue`：外部系统详情保留「开放范围」段(消费面 + 租户启用,人话)。
4. `b12-fixture.ts`：ExposureMatrixRow 增可选 name/description。

**真 UI 走查**（隔离栈 :8801 + 干净 seed + mock 推理 + 真实库 238 能力 / 5 外部系统,role=业务运营员）：

- 能力总览：平台共 238 项 = 内置 224 + 外部 14·5 系统;按业务域分布人话;诚实「已接入≠已能跑」框 ✓
- 人话浏览：首条能力名「同步用户角色投影」(非 slug)、外部首条「外部级联同步执行契约」;slug 降级技术编号 ✓
- 身份治理 = 治理轴第三 tab ✓
- `vue-tsc --noEmit` 干净;`scripts/preflight.sh` PASS;证据截图见 `evidence/`(01 总览 / 02 外部浏览 / 03 外部系统)

## 三 · 反向防御（不破坏什么）
路由零改动（`iam-governance` 契约测试断言保留）;`twin_browser_pages` 仅断言 heading「接入扩展中心」「三引擎配置」,均保留;
未改任何 `.feature`/backing 测试 → 无指纹陈旧 FAIL;后端仅**加字段**(test_b12_intake 按 skill_id 取值,不断言固定键集)。

## 四 · ruled-but-staged
- 真·自助外部接入 + 热更新：**B 方案独立立项**(执行桥 + 动态分发 + 守卫分轨 + 信任默认级 + 审批门 + 安全评审)。
- 人话浏览的搜索/分页:本期封顶 40 条 + 计数,搜索后续。
- 配置轴升独立主导航 / 角色集精化收紧:更重 IA·角色变更,留后续。

## 五 · Sign-off（待合并时 ratify）
属 **D28 GATE（IA + 角色可见性确认）**。实现已完成并真 UI 验证,**决策待产品研发负责人在合并门 ratify**——
届时登记 **D52** + 落 `.testing/signoff/integration-admin-governance-axis.signoff.yaml`(decision_only)。合并永远人工。ratify 前 `status: proposed`。
