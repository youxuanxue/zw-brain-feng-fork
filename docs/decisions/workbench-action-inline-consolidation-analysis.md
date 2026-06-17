# 工作台动作内联收口 · 上帝视角分析（提案，待 D28 GATE 评审）

> 状态：**提案 / 未签字 / 未进 D-编号**。本文是「办申请合并进工作台、遍布各页的受理/审核动作是否直接在工作台展开详情」的上帝视角分析与分阶段建议。涉及流程/状态机契约反转（投影 `无新页面、无新流转` 契约），落地前须走产品研发负责人 D28 sign-off。
>
> 方法：5 路读图 + 4 路对抗设计透镜 + 乔布斯综合，全部断言已对真实代码 file:line 复核。

---

## 一、结论（一句话）

**不要**把「办申请」作为页面并进工作台，**不要**把工作台做成「动作中心」。要做的是：把**审核岗的「是/否」决策**（受理 / 审核 / 驳回 / 退回补正）以**行内展开**的形式收进「我的工作台」，**先从已带实体 id 的部门管理员审批待办起步**——因为大家默认的「业务运营员零成本切入点」其实**不存在**。

---

## 二、把问题问对：病不在「分散」，在「点不到可办处」

工作台**已经是**全角色、按真实库现算的统一积压聚合面：`workbench_backlog_projection.py` 为 5 个角色码各自现算真实积压，每条待办带一个深链 `href`（`workbench_backlog_projection.py:391-443`）。最难的事（一屏、全积压、按角色、零捏造）**已经做完**。

所以「动作分散在各页」是表象。真正的痛，D57 裁决一自己已经诊断过——**「有待办、点不到可办理处」**。病灶是那趟**没有任何决策价值的往返空跑**：

```
审核岗清一条待办的真实路径：
  ① #/workbench 点待办
  ② 落到 #/request-flow/review/{id}：读 6 行字段 + 时间线，点「通过/驳回」
  ③ 导航回 #/workbench 看下一条
中间这一页（P3ReviewDetail，166 行）唯一的存在理由 = 承载两个按钮。
```

供数侧更糟——聚合计数待办的 href 指向**收件箱根**（非具体条目），于是是 `工作台 → 收件箱列表 → 行 → 详情 → 办` 的 **4 跳**，且第一跳根本点不到可办处。

治法不是「页面合并」（会造出杂物抽屉、还会铲掉申请人的家），而是**为审核岗的本职工作消灭这趟空跑**。

---

## 三、精品级的分治：三类东西，三种待遇

待办背后是**三类**性质完全不同的东西，混为一谈是设计灾难：

| 类别 | 实例 | 形态 | 处置 |
| --- | --- | --- | --- |
| **决策（是/否）** | 受理/审核/驳回/通过、异议受理 | 6 行字段 + 时间线 + 2 个按钮（`P3ReviewDetail.vue:144-165`，按钮即 `invokeActionStub` 能力调用 `:89-141`） | **内联进工作台行内展开。** 3 跳 → 0 跳 |
| **编制（多步）** | API服务化/反向编目/在线编目/质量规则向导、供需对接 search→draft | 多步向导、`EditableFormPanel`（271 行，含自动填充/AI 建议/锁定） | **保留为独立目的地。** 向导塞进抽屉=镀金灾难 |
| **创建 / 跟踪** | 发起申请、我的申请/我的授权 | `P3RequestFlow` = 申请人自己的 4 tab 列表主页 | **原地不动。** 发起=从「找数据」向前的动作；跟踪=申请人的家，别推土机进工作台 |

> 「办申请」(`P3RequestFlow`) 是申请人的家，不是审核详情页。合并它要么删掉申请人的主面、要么把工作台胀成 mega-page，且在 ≤10 约束上**一分钱不省**（≤10 数的是场景页，业务运营员现 6/10，详情页是不入预算的 meta 子页）。**收的是审核岗的「动作」，不是申请人的「列表」。**

---

## 四、关键事实纠正（对抗验证的产出）

最诱人的「零成本切入点」是个**假命题**，必须钉死：

- 直觉：「业务运营员（BUSIAUDIT）的受理待办已带 `request_id`，今天就能内联，零后端改动。」
- **真相（已复核）**：`sync.py` 确实投了带 `#/request-flow/review/{request_id}` 的 BUSIAUDIT 受理待办，**但** `enrich_workbench_backlog` 对 BUSIAUDIT 是**整体替换**——`out["todos"] = _backlog_todos(tid)`（`workbench_backlog_projection.py:421-422`），而 `_backlog_todos` 每条都是**聚合计数 + 收件箱根 href**（如 `待受理申请 N 条 → #/request-flow`，无 id，`:132`）。带 id 的那条**在替换里被丢弃**。
- 对照：部门管理员（MANAGER）走的是 `_enrich_manager_backlog`，`todos = prepended + existing`（`:283`）——**叠加**而非替换，`sync` 投的带 `request_id` 的审批待办**得以幸存**。

> **真正的廉价滩头是部门管理员的 review/summary 待办，不是业务运营员。** 而 e2e `workbench_todo_closure.spec.ts` 恰恰只测 BUSIAUDIT、且断言每条都「navigate away」（`:56,:84-86`）——它把当前的「navigate away」契约钉死在了正是大家想改的那个角色上。

---

## 五、成本与门禁（不糊弄）

**便宜的部分（已是代码现成件，组合即可，非新框架）：**
- 行内展开 + 写后刷新原语**已经出货**：`P5HookupReviewInbox.vue:99-135`（`查看详情` 展开行 + 行内 `通过挂接/驳回` + 驳回理由面板 + `invokeActionStub`，带 `data-testid`）。
- 权限门**已经出货**：`canPerformAction` over `ACTION_ROLE_GATES`（`pageAccess.ts:125,211`，后端 policy 镜像）。「无权=不可见」就是一个 `v-if`。
- 决策组件**已经现成**：`P3ReviewDetail` 已算好 `showAcceptActions/showDeptReviewActions/showUnconditionalAcceptActions`，上下文走 `lookupRequest` 读已加载的快照，**零新拉取**。一个决策组件，两个宿主（详情页留作深链/书签锚点）。

**贵的部分（真实代价，必须预算）：**
1. **D28 GATE**：反转投影显式契约 `无新页面、无新流转`（`workbench_backlog_projection.py:24-25`）是有产品方向含义的变更，决策记录里**零先例**。须新签一条 D28，scope 严格限定「审核岗 per-entity 决策内联，不做 J1/J2 跨旅程搬迁」。当实现细节偷偷上=违反 GATE 元规则。
2. **e2e 重采**：`workbench_todo_closure.spec.ts:84-86` 硬断言待办「navigate away from #/workbench」。内联即破契约 → 必须**拆断言**（聚合/申请人/供需待办仍 navigate away；内联的审核待办断言面板就地打开、动作派发、待办原地消失且 hash 仍是 `#/workbench`）。改 feature-backed e2e 触发全量 `--with-e2e` 干净 seed 重采（D46.g 指纹）——**不是纯前端改动**。
3. **自门控纪律**：`router.beforeEach` 对内联面板**不触发**（`router/index.ts:130-139`）。每个内联 CTA **必须自调 `canPerformAction`**，否则向「能看到待办但无权办」的角色泄漏写动作。用共享 `<GatedAction>` wrapper（无通过门则拒渲染）+ 负向角色 e2e 兜底。
4. **驳回语义不可拍平**：`approval.case.decide` 的 `return_for_fix` vs `reject` vs 目录终态枪毙 vs 挂接 `return_for_fix`（非终态整改）是不同状态机。一个硬编码单一 decision 值的通用「驳回」会悄悄腐蚀其一并在文案上撒谎。**decision 按待办类型参数化。**

---

## 六、分阶段（先出价值，按门禁切片）

- **Phase 0（无 GATE、不破 e2e、可立即出）——深链落点精准化。**
  把聚合计数待办的 href 从收件箱根（`#/provider`、`#/request-flow`、`#/provider/inbox/catalog-review`）改为**预筛/锚定落点**，让「待发布目录 3 条」直接落在带着那几行的过滤列表上。这是 D57①「修可达性」、是既有代码方向，去掉 BUSIAUDIT 大部分摩擦且零代价。也是内联若被否的正确回退。

- **Phase 1（一条紧 scope 的 D28 + 一次 e2e 重采）——内联部门管理员决策。**
  在 `P1Workbench` 上把 MANAGER 的 review/summary 待办（`request_id` 已在 href，零后端 re-grain）做成行内展开决策，复用 `P5HookupReviewInbox` 展开行 + `invokeActionStub`(write→`invalidateSnapshot`→`invalidateWorkbench`→reload，待办就地消失) + `canPerformAction` v-if。叠加 BUSIAUDIT/MANAGER 的**异议受理**内联（`objection.case.accept` 是浅上下文单步 status-flip，唯一廉价的 BUSIAUDIT 内联）。先证明 pattern，清一条紧 scope 的 D28，重采一次 e2e。

- **Phase 2（仅当 Phase 1 证明价值、独立决策）——re-grain 业务运营员聚合背包。**
  把 `_backlog_todos` 从「按类型计数」改为「按实体一行」，每行挂 `entity_id + capability_id + 角色门`，让业务运营员也能内联办受理/平台审核。这是透镜们为 BUSIAUDIT 低估的「贵的 80%」，**用实测需求 gate 它，别用假设**。供需对接与异议处理无论如何留详情面。

---

## 七、围栏（明确不做的事——守住精品边界）

1. **永不**把供数（J2）收件箱的 IA 拉进用数（J1）工作台——这跨越已签的旅程线（0605 决策四明确选「供数页内重排」而非「折叠到别处」以保 J1/J2 分立）。把审核岗的 J2 待办按角色显示在他个人工作台上 = 按角色显示，OK；把供数收件箱的 **IA 搬进 J1** = 禁止的跨旅程合并。目录/挂接收件箱本就行内办 approve/reject——**供数内联归属在那里**。
2. **永不**内联「补录/重提」编辑（`P3RequestDetail` 挂 271 行 `EditableFormPanel`）——编辑不是决策，带自动填充的表单是真活儿、值得专注面；且 D57② 正面禁止给操作员工作台塞「协作待办」。
3. **永不**内联供需对接（`P5DemandMatchDetail` 的 search→match→draft 不可化约——`catalog.entry.query` 必须先匹配到真实本地资源才能 `request.create`，单按钮要么对匹配撒谎要么跳过守卫）。
4. **永不**给安全审计员/平台运维员工作台加任何写面（D55/P22 收敛纯只读「无任何写操作权限」；动作中心正是签字决策所禁的泄漏入口）。`todos=[]` 只读到底。

---

## 八、验证锚点（落地后据此判真假）

- 内联待办：点击 → 行内面板就地打开（`data-testid` 新增）→ 动作派发 → 待办原地消失 → **hash 仍 `#/workbench`**（与拆分后的 e2e 断言一致）。
- 负向角色 e2e：内联 CTA 对无权角色**不渲染**（堵 `beforeEach` 不兜底内联面板的洞）。
- 写路径单源（D56）：内联派发走真实能力 `invokeActionStub → /api/skills/<id> → CardSession/PersistMiddleware`，无捷径。
- Phase 2 防双轨漂移：工作台 per-entity 枚举须与收件箱自身投影（`deriveHookupReviews` 等）口径一致，否则工作台与收件箱对「什么还没办」各执一词。

---

## 附：本分析复核过的关键 file:line

- `zw-brain-web/src/pages/P1Workbench.vue:14-17,97-109`（工作台只渲染深链、零内联动作）
- `zw_brain/domain/workbench_backlog_projection.py:283`（MANAGER 叠加）, `:411`, `:418-422`（BUSIAUDIT 整体替换）, `:121-159`（聚合计数 + 收件箱根 href）, `:24-25`（`无新页面、无新流转` 契约）
- `zw_brain/command/sync.py:153-201`（带 request_id 的 per-application 待办来源）
- `zw-brain-web/src/pages/P3ReviewDetail.vue:63-74,89-141,144-165`（166 行薄决策面）
- `zw-brain-web/src/pages/P5HookupReviewInbox.vue:99-135`（行内展开 + 写后刷新原语已出货）
- `zw-brain-web/src/lib/pageAccess.ts:125,211`（`ACTION_ROLE_GATES` / `canPerformAction`）
- `zw-brain-web/src/router/index.ts:130-139`（`beforeEach` 不兜底内联面板）
- `tests/e2e/workbench_todo_closure.spec.ts:56,84-86`（硬断言 BUSIAUDIT 待办 navigate away）
