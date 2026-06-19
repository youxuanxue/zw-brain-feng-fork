# D64 · 供数侧资源/目录详情路由错配修复（IA 重定位，D28 GATE）

> **类别**：IA / 可见性重定位 · **D28 GATE**（旅程边界 / 角色心智）· `decision_only`
> **签字**：薛娇（产品研发负责人）2026-06-18 — **已签**；初定档 A，**真浏览器走查证伪档 A 后改定档 B（独立供数详情路由）**（见 §四）。
> **签字账本**：`.testing/signoff/provider-detail-intent-routing.signoff.yaml`
> **来源**：乔布斯军团审查 #300 落地后，负责人发现「供数据点未发布资源跳到找数据消费详情」错乱，要求核验并出 GATE 方案。
> **D-编号**：D64（决策已签；原拟 D63，因 main #305 iam-pub-user-role-materialization 先入索引占 D63，本条让号至 D64）；索引行已随 **D65**（2026-06-19）落 `docs/decisions/decision-log.md`——D-索引整体移出 CLAUDE.md 热路径、段68/72 字符守卫退役，原「待腾额度」约束消解（见 §六）。

---

## 一、背景（根因，已逐行核实）

两条旅程在 IA 上各管一件事（D39 定型 2 旅程）：

- **找数据（J1 / P2）** = 消费方心智：「这条**已发布**的数据，我能不能**申请**」。详情 = `P2ResourceDetail`，围绕 `canApply` / 申请按钮 / 凭据。
- **供数据（J2 / P5）** = 供数方心智：「我这条数据**办到哪一步、下一步该做什么**」（编目 / 挂接 / 发布态 / 驳回理由 / 续编）。

但供数侧管理清单的「查看」**写死跳到消费方详情**，且供数侧**没有自己的详情路由**——于是供数方点自己未发布的资源，落到消费方「暂不可申请」页，**拿错了心智模型**：owner 不是来申请自己数据的，是来管理它的。

## 二、现状错配（三处证据 + 触发条件，全部 file:line 核实）

| # | 错链点 | 去向 | 性质 |
|---|---|---|---|
| 1 | `zw-brain-web/src/lib/providerProjection.ts:401` `providerResourceRows()` | `viewHref = #/discovery/resource/:id` → `P2ResourceDetail` | **资源·主诉** |
| 2 | `zw-brain-web/src/lib/providerProjection.ts:376` `providerCatalogRows()` | `viewHref = #/discovery/catalog/:code` → `P2CatalogDetail` | **目录·孪生** |
| 3 | `zw-brain-web/src/pages/P5CatalogReviewInbox.vue:202,207` 目录审核收件箱 | `#/discovery/catalog/:code` | **目录·审核侧孪生** |

- 路由表唯一资源详情 = `router/index.ts:59` `/discovery/resource/:id → P2ResourceDetail`；供数侧 `grep /provider/resource|/provider/catalog/:id = 0`（无自有详情路由）。
- 渲染于共享表壳 `ProviderManageList.vue:85` `<a v-if="r.viewHref" ... >查看</a>`。
- **触发"暂不可申请"的精确条件**（#300 我新加的诚实兜底，恰把此错配照出来）：`P2ResourceDetail.vue` `showNotPublishedNote` = 资源已加载 ∧ `canPerformAction('request.create')` ∧ `lifecycleStatus !== 'active'`。
  - `request.create` 权 = `ROLE_ORGAN_OPERATER` + `ROLE_ORGAN_MANAGER`（`policy.py:104` + 前端 `pageAccess.ts:170` 两侧一致）——这两岗也是供数 shell 成员，故**点自己非 active 资源必触发该句**。
  - 触发态 = **所有非已发布态**（draft / 待发布 / 审核中 / 暂停…），不止草稿。
  - 安全审计员可进供数 shell 但无 `request.create` 权 → 静默（无按钮也无解释句）。

**不在修复面（消费方正当用途，勿误伤）**：`ResourceCard.vue:54,89`（找数据卡片，J1 正主入口）、`objectionLabels.ts:25`（异议指向资源的合理消费深链）、`P2CatalogBrowse/P2CatalogDetail/P2Discovery` 内部导航。

## 三、定性（乔布斯）

> **这是"两个意图共用一个壳"的错配，不是小 bug。** 详情该由"进入它的**意图**"决定呈现，而不是由"同一条**数据**"决定。

负责人的诊断成立，证据扎实。

## 四、裁决（负责人 2026-06-18 — 初定档 A，走查证伪后改定档 B）

> **最终定档 = B（独立供数详情路由 `/provider/resource/:id`、`/provider/catalog/:code`，复用消费详情组件，按 `route.path` 前缀判供数视角）。** 供数清单/审核收件箱「查看」改指这两条供数路由；详情壳在 `/provider/*` 下抑制消费框架（不显申请按钮/「暂不可申请」）、出「回供数管理」回链；走供数 shell 角色门（操作员/管理员/业务运营员可达）。
>
> **为何由 A 改 B（真浏览器走查实证，2026-06-18）**：初定的档 A（复用消费详情 `/discovery/resource/:id?from=provider`）经真实点击走查证伪——① **`route.query.from` 在带参 hash 路由(`/discovery/resource/:id?from=provider`)不可靠**：真实点击后 `fromProvider` 恒 false、manage-note 从不渲染、档 A 实为 no-op（对照：P5InlineCatalogWizard 的**无参** `?code=` 工作正常；`route.path/params` 稳，`route.query` 在此组合下不稳）；② **业务运营员点供数「查看」→ 被 router 弹回工作台**（BUSIAUDIT 无 P2 消费详情访问权，而档 A 指向 /discovery 消费路由）。**档 B 同时根治两者**：独立 `/provider/*` 路由用 `route.path`（可靠）判模式、走供数角色门（BUSIAUDIT 不再被弹）。档 B 不撞 ≤10（子路由不计主入口枚举）、复用组件零新页维护。走查 3/3 全过（BUSIAUDIT 点查看进 /provider/resource + 管理视角、操作员供数待发布资源无「暂不可申请」、消费 active 申请照常）。下方三档原始评估保留备查。

**关键事实纠正**：决策**不应**以"≤10 红线"否决"新建供数详情页"——`architecture.md:452` 明文「子页(detail/inbox/wizard)不计入主入口枚举」，当前左导航仅 9 项、router 已有 17 个 P5 子路由，新增**子路由**不撞 ≤10。真正取舍是**复用 vs IA 纯净 / 维护成本**，不是页数。

| 档 | 方案 | 优 | 劣 |
|---|---|---|---|
| **A 轻量（推荐先做）** | 供数「查看」**按生命周期分流到正确管理语境**：草稿/被驳回→续编·编制向导（带驳回理由）；审核中→审核进度（只读）；已发布 active→可复用消费详情但标注「消费方视角预览」且对 owner 隐藏「暂不可申请」。**不新建详情页**，管理详情靠清单行+行内展开（时间线/驳回理由/行内动作，已具备）。 | 小、可逆、立刻消错配；零新增维护面 | 供数方无统一详情视图（靠清单承载） |
| **B 中量** | 新建供数侧详情子路由 `/provider/resource/:id`（+目录 `:code`），供数方视角呈现编目/挂接/发布态+本方可操作项，不含消费「申请」语义；三处错链改指它。 | IA 最纯净、最贴负责人「各自管理」直觉；不撞 ≤10 | 新页/组件维护面；与消费详情部分内容重叠 |
| **C 重量** | 单一详情组件做 **mode-aware**（供数管理态 / 消费申请态），按进入上下文+ownership 切换。 | 单页、零重复内容 | 一页背两套语义，条件复杂度高 |

**乔布斯建议**：**先 A（减法、立刻止血、零新增维护），把"供数方 owner 看自己数据落到消费申请页"这个错配当周消除**；待供数方确有"统一管理详情"需求再立项 B。C 仅在 A+B 都不够时考虑。三档都需把**目录孪生（#2/#3）一并纳入**修复面。

## 五、签字定性

- `decision_only: true`、`covers: []`——纯 IA / 可见性路由重定位，不抬任何 `.feature` 状态，对运行产品是"详情指向修正"。
- 角色门不变（供数 `/provider/*` 路由沿用供数 shell 门、消费 `/discovery/*` 不变），后端 handler/policy/状态机/能力**零改动**——只动前端路由表（+2 供数详情路由）、详情壳按 `route.path` 判模式、清单/收件箱链指向、面包屑。
- 非撞已签决策：承 D39（2 旅程分界）、D53④（供数 IA 重排）；与 D59（B11 折叠）同属纯 IA 重定位类。

## 六、落地约束（必读）

1. ~~**段72 聚合棘轮 headroom = 0**……加索引行会使聚合 > 上限 → preflight FAIL；两条出路 (A) 净零下架 / (B) 先落 B1 归档提案。~~ **【已消解 · D65 2026-06-19】** D-编号索引整体从 CLAUDE.md 移出到 `docs/decisions/decision-log.md`，段68/72 两道字符守卫随之退役；本条（D64）索引行直接写入 decision-log.md，不再撞任何棘轮。B1 归档提案（`d-index-active-archive-restructure`，未签 draft）被 D65「全量移出」取代、已删除。
2. D-编号在**负责人 sign-off 时已坐实**（薛娇 2026-06-18，本条 D64——原拟 D63，让号给 main #305 的 iam D63）；索引行落 `docs/decisions/decision-log.md`（D65 移出后无字符上限，仍遵格式契约）。

## 七、验证（档 B 已实现并实测，2026-06-18）

- **真浏览器走查 3/3 全过**：① 业务运营员供数清单点「查看」→ 进 `/provider/resource/:id`（**不再弹回工作台**）+ 出供数管理视角回链、无申请按钮、无「暂不可申请」；② 操作员 `/provider/resource/<待发布>` = 管理视角、无「暂不可申请」；③ 操作员消费 `/discovery/resource/<active>` → 申请按钮照常、无管理回链（零回归）。
- 单测：providerProjection.spec（viewHref 指 `/provider/*`、非 `/discovery`）、P2ResourceDetail.spec（route.path=/provider 时抑制申请框架）、roleProjection.spec —— 15 passed；webui `vue-tsc --noEmit` + build 通过。
- 待终态：全段 `scripts/preflight.sh` PASS（CI 跑）；如需 D37 效果验收单独附 evidence。
