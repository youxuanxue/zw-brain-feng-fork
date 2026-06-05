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

## 六 · 第二轮重做（2026-06-05，负责人实地走查后）

> 触发：负责人以用户身份本地实地走查（dev-bypass :8800 干净 seed），上帝视角逐页点验,
> 戳出第一轮残留的分裂体验与诚实缺口。本轮按「一张壳、一套词、零黑话、首屏只讲今天能用的、主操作排第一」收口。

### 四刀（上帝视角裁决,全部落地）
- **刀1 砍内置墙**：总览不再放 224 条 slug 浏览墙（首屏全是 adapter 管道、半数规划中,运营员看不懂也动不了）。
  内置卡收成一句话,清单退入默认收起的「查看技术清单（含规划中,面向研发）」`<details>`；人话浏览主体只剩外部接入 14 条。
- **刀2 去轴标签**：删「治理｜配置」两轴 label（内部分类泄漏,与 slug/三引擎同病）。单排 tab 按动手频率排序:
  `外部接入（主操作）· 能力总览 · 流程与表单配置`,默认 tab = 外部接入。共享外壳 `IntegrationAdminTabs.vue`
  渲染在 hub / 流程与表单配置页 / 外部系统详情页,永不消失、高亮当前。
- **刀3 hero 只讲已上线**：内置卡 bold 数字 = 「已上线 194 项」（live builtin 现算）;不挂"建设中"计数徽章
  （无日期的"在建"是换脸 overclaim）;未上线的只在折叠研发清单里留痕。外部卡补「已启用 N 个」诚实信号。
- **刀4 两个开放问题负责人已裁**：
  - **Q1 身份治理独立到左导航**（撤回第一轮 D-d "融入第三 tab"）——独立 nav 项 + `activeShellKey` 独立高亮,
    路由 `/integration-admin/iam-governance` 保留（契约测试不破）,页面不挂接入中心 tab 栏。
  - **Q2 内置可浏览性 = 折叠方案**（同意刀1 形态）。

### 一物一名（同屏多名清零）
- 左导航「接入管理」→「接入扩展中心」（与页标题统一）;
- 「三引擎配置」退役 →「流程与表单配置」（页标题/路由 meta/tab 同词,工程黑话清除,"Wave 2" 字样删除）;
- 「能力包详情」→「外部系统详情」（列表叫外部系统,详情同词）。

### 诚实与精致 correctness（随脊柱顺带修）
- 5 个外部包 seed 补中文短名（网关运行时/环境诊断/工单·CMDB·知识库/接口契约导入/外部任务编排）;
  前端 `normalizePackageRow` 砍掉 `desc` 兜底当名字——列表第一列从"整段描述墙"变为短名 + 描述次级灰字;
  详情页描述读对源（`desc`）,列表/详情同一事实。**注意:已部署胀库不会吃到新 seed 字段,干净重建 DB 才生效（与 zones/topic_packages 同约束）。**
- 业务域分布 journey=external 显示名「外部接入」→「对外协同」,消除同屏「外部接入 14 vs 29」同词两数撞车;
- 身份治理页正文去生 slug（`governance.policy_candidate.*` 不再出现在用户 prose）;
- 流程与表单配置页样例预设去省名（鞍山/四川/荆州 → 标准/完整/简化中性名,不与 sd-default 山东穿帮）;NL 智能检索收敛为 hub 仅一处;
- 死代码 `useEngineSlots.ts` 删除（hub slot-card 中转三跳取消,tab 直达配置页）。

### 反向防御（本轮与第一轮不同:动了 backing 测试,已按 D46.g 重采）
更新断言: `b12_intake`（旧 tab 名已与上线代码脱节,本轮修正）/ `p5_b12_unlock` / `twin_browser_pages`
/ `customer_acceptance_checklist`（三引擎→流程与表单配置 + 身份治理独立导航用例）。
被 4 个 `.feature` 引用 → 指纹陈旧,已跑 `capture_feature_status.py --with-e2e`（py312 override + :8800 干净 seed 栈）全量重采。
真 UI 走查证据:四个子面同一 tab 栏且高亮正确、外部表短名、hero 已上线 194、全页无 三引擎/Wave2/生 slug/跨省样例。

## 七 · 容器解体（2026-06-05 第三轮，负责人裁决）

> 触发：负责人三问——流程与表单配置该不该独立导航？能力总览该不该独立导航？能力分类该不该从
> 来源切面换成 关联系统/作用/价值 切面？上帝视角看是同一个问题：**为什么要有这个柜子。** 裁决：解体。

### 裁决与落地
- **「接入扩展中心」容器退役**：后台四模块各自独立左导航——`查审计 / 外部系统 / 流程表单 / 身份治理`。
  全角色页面数恰好 10,D1/D8 ≤10 红线压线成立。`IntegrationAdminTabs.vue` 共享外壳组件随容器退役（最好的壳是没有壳）。
- **短标签纪律**：外部系统/流程表单/身份治理 = 4 字（流程表单为「流程与表单配置」字面收缩,页头保留全名）;
  **查审计保持 3 字**——全站导航母语是三字动宾（找数据/办申请/领数据/供数据/查审计）,且其页面「合规与运营」（D41）本轮不动,硬凑 4 字须连页头改名,属另一决定不搭车。
- **能力总览解体而非独立**（比 Q2 原问更进一步）：阅读页不配导航位。来源叙事压成一句「能力账目」行进外部系统页头
  （内置 N 项已上线 / 外部 N 项来自 N 系统·已启用 N·待执行桥）;14 条外部能力以「外部能力契约」次级段留在外部系统页——
  **manifest 无 系统归属字段,不编造能力↔系统映射**（有归属数据后再挂进各系统详情页）;
  内置技术清单（折叠 details）整体退出产品 UI（研发走 registry/API,Q2 折叠方案被解体方案超越）。
- **Q3 价值切面分类**：方向认可（来源切面是治理语言,作用/价值切面才是用户语言）,但**缓行**——
  「价值」今天不是 manifest 字段,238 条须人工著录 + 持续维护,没人养的分类法会腐烂成谎言;
  「平台能力地图」待 明确 owner + 真实使用场景 再立项;「关联系统」轴随归属字段补齐自然解决。
- 路由零 churn（四条 `/integration-admin*` 路径全保留）;`activeShellKey` 补 engines 独立高亮;
  feature 叙述同步（b1-2-package-registration「接入扩展中心」→「外部系统模块」）;backing 测试更新 + 全量重采。
