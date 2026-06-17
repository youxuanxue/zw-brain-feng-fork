# 工作台收口受理/审核 + 拆「办申请」· 实现记录与决策日志（待 GATE 批准 + e2e 重采）

> 状态：**代码集成完成、隔离栈端到端 live 复验通过、非-e2e 全门绿；旅程 GATE 已由负责人批准（2026-06-16，签字账本 .testing/signoff/workbench-inline-and-request-flow-dissolution.signoff.yaml）；e2e 迁移+全栈权威重采为唯一剩余门，须在 canonical 全真库环境执行（详见 §五）。**
> 分支：`feature/workbench-action-consolidation`。方法：契约锁定 + 三 file-disjoint 子 agent 独立 worktree 并行实现 + 乔布斯集成复核。
> 上游分析：见 `workbench-action-inline-consolidation-analysis.md`（上帝视角分析）。

---

## 一、两个产品决策（已实现）

1. **工作台收口"是/否"决策**：审核岗（部门管理员 dept_approve / 业务运营员受理）的待办在工作台**行内展开办理**——展开见要点、点通过/驳回/受理就地派发能力，**不跳出 `#/workbench`**。编制类（向导）、填表类（补录）、列表类不收。
2. **拆「办申请」**：`/request-flow` 列表页与「办申请」导航项退役；流水线各段归家——发起→找数据（本就在）、受理/审核→工作台（行内）、我的申请+我的授权→领数据（消费方"我的数据"一站式）。详情/审批/补录/异议/供需子路由保留作深链锚点。

---

## 〇、隔离栈端到端实测（Jobs 集成复核，真实库副本 :8801）

复制主仓 842MB 真实 DB 到隔离副本 + mock 推理起栈（不碰 canonical :8800），真流程铸单走查，
**复核抓出并修复 3 个单测漏网的集成缺陷**（这是并行 agent 开发里集成复核的核心价值）：

1. **部门审核面要点行为空**（`_dept_approve_action` 原 `context=[]`）：审批人展开只见按钮、不知审什么 → 补 request 入参现算 4 行要点。
2. **`action` 字段冲突**：聚合背包待办沿用 `action`(str) 作 aiSummary 分句，与新行内决策 `action`(dict) 同键 → 前端 `isActionable` 误判字符串可办理而渲染崩。重命名遗留键为 `actionClause`。
3. **流转后陈旧行内待办滞留**：sync upsert-only 不剪枝，受理通过后 BUSIAUDIT 的 accept 待办滞留且仍可点 → 误发 platform_approve 报错（原整体替换掩盖、增量后暴露）。新增 `remove_todo`，状态不再成立即剔除。

实测全链路通过（真实单据）：铸有条件单→submitted→**BUSIAUDIT 受理行内**（platform_approve + 受理/驳回 + 资源/申请人/用途/共享方式 4 行）→ 点受理→dept_approved→**BUSIAUDIT accept 剔除** + **MANAGER 部门审核行内**（dept_approve + 4 行要点）。三处缺陷修复均已 live 复验 + 单测钉死。

## 二、乔布斯在过程中做出的最优决策

- **D-Jobs-1 自描述待办契约**：后端 todo 挂可选 `action`（capability/gate/basePayload/context/decisions），前端据此现渲染行内决策面。一个契约贯通后端投影与前端面板，复用既有 `DetailPanel/DetailActions/invokeActionStub/canPerformAction`，**不造抽屉框架**。
- **D-Jobs-2 先部门管理员、再业务运营员**：dept_approve 待办本就带 `request_id`（零后端 re-grain）；业务运营员受理待办原被 `enrich_workbench_backlog` **整体替换**丢弃 → 改为**增量保留**（`_enrich_busiaudit_backlog`），逐单受理待办（携 action）存活、剔除重复的「待受理申请」聚合。
- **D-Jobs-3 驳回语义按类型参数化**：`application.dept_approve`(通过/驳回)、`application.platform_approve`(有条件受理/驳回)、`approval.case.decide`(无条件受理通过/退回补正/驳回) 各自状态机，决策按 `shared_type` 选 capability，**绝不拍平成一个驳回键**。
- **D-Jobs-4 自门控纪律**：行内 CTA 不经路由守卫 → 新建 `GatedAction`，`canPerformAction(gate,role)` 不过即不渲染（"无权=不可见"由它在行内兜底）。
- **D-Jobs-5 详情页保留**：一个决策组件两个宿主（工作台行内 + `/request-flow/review/:id` 深链），不重复实现。
- **D-Jobs-6 拆办申请用增量、保子路由**：删导航项+列表页，但 `/request-flow/*` 子路由保留并由 `ROUTE_ROLE_OVERRIDES` 守正确角色门（审核人深链仍进得去），`/request-flow` 重定向 `/delivery-exchange`；非破坏式。
- **D-Jobs-7 集成复核抓修**：部门审核行内面原 `context=[]`（只见按钮不见审什么）→ 补现算要点行。
- **D-Jobs-8 范围纪律**：异议受理内联 + 深链落点精准化列为后续（同机制再应用一次），不塞进本轮污染验证面（承分析里「scope creep 是头号失败模式」）。

---

## 三、并行 worktree 子 agent 分工（file-disjoint）

| 子 agent | 切面 | 关键文件 | 自检 |
|---|---|---|---|
| A 后端 | 待办挂 action + BUSIAUDIT 增量 | `sync.py` `demo_state_sync.py` `workbench_backlog_projection.py` + 后端测试 | 20 passed，全 preflight 绿，无 --no-verify |
| B 前端 | 行内面板 + 自门控 | `GatedAction.vue` `WorkbenchTodoActionPanel.vue` `P1Workbench.vue` `workbench-fixture.ts` + vitest | typecheck OK，vitest 6 passed，全 preflight 绿 |
| C IA | 拆办申请归并领数据 | `productShellNav.ts` `router/index.ts` `pageAccess.ts` `P4Delivery.vue`（删 `P3RequestFlow.vue`）+ 测试 | typecheck OK，62+ pytest pass，全 preflight 绿 |

集成（乔布斯）：三片 cherry-pick 零冲突 → 死链核查（C 担忧的 `backlog-application` 裸链被 A 的 drop 兜住）→ 联合回归 **66 passed** → typecheck OK。

ROUTE_ROLE_OVERRIDES（C 加，集成已核角色正确）：
- `/request-flow/review` → [BUSIAUDIT, ORGAN_MANAGER]（审核人深链可达）
- `/request-flow/request` → [ORGAN_OPERATER, ORGAN_MANAGER]
- `/request-flow/objection`、`/request-flow/supply-demand` → [OPERATER, MANAGER, BUSIAUDIT]（保守非回归，可酌情收窄）

P4Delivery 新结构：`我的申请`(申请人可见) / `我的授权`(申请人可见) / `交付任务`(交付 shell 全角色)。

---

## 四、验证现状（诚实）

- ✅ 后端单测/集成：`test_workbench_inline_action` `test_workbench_backlog_projection` `test_page_access` `test_product_shell_nav_roles` `test_request_flow_dissolution` `test_role_codes_alignment` 合计 **66 passed**。
- ✅ 前端 typecheck（vue-tsc）OK；vitest 6 passed（GatedAction + P1Workbench）。
- ✅ 集成提交全套 preflight（common + 全项目段，含 feature 指纹/orphan-rows/signoff 账本）**PASS**。
- ⚠️ **e2e 未重采（唯一剩余门）**：行内化使 `workbench_todo_closure.spec.ts`（feature-backed）的「每条待办都是跳走的链接」断言对受理待办失效；拆办申请使 ~12 个 spec 命中列表根 `#/request-flow` 或断言「办申请」导航项（其中 `role_projection_views`/`twin_browser_pages`/`national_channel`/`workbench_todo_closure` 为 feature-backed）。需迁移这些 spec + 跑 `capture_feature_status.py --with-e2e`（:8800 全栈、干净 seed）刷新指纹后方可合并。本 worktree 环境下全栈 e2e 重采过重，未在本轮执行。

---

## 五、待办（剩余门 + 后续）

1. **e2e 迁移 + 重采（合并前必做）**：
   - `workbench_todo_closure.spec.ts`：受理/审核待办按 `action` 拆断言——可内联者断言"展开见面板、办理后留在 #/workbench"，非内联者仍断言跳走。
   - 拆办申请 ~12 spec：`permission_matrix_walkthrough`(去导航矩阵「办申请」)、`twin_browser_pages`(页矩阵 #/request-flow→领数据)、`role_projection_views`/`national_channel`/`d57_permission_batch`/`webui_smoke`/`j1_data_gap`/`nl_accelerator_live`/`wave15_two_stage_walkthrough`/`r12_rendered_language`/`perf_loading`：列表根入口改 `/delivery-exchange` 或重定向语义。
   - 跑 `scripts/capture_feature_status.py --with-e2e` 刷新 feature 指纹，提交 `.testing/status/measurement/*`。
   - **为何必须在 canonical 全真库环境跑（已实测证伪 worktree 重采）**：`feature_status_lib.load_measurement()` 取 `captured_at` 最新的**单个** measurement 文件作全特性权威源（非按特性跨文件择新）。在 worktree（dev 库 842MB 副本、6/15 累积态、mock 推理）跑全栈 `--with-e2e` 会让我的产物成为权威，任何在本环境 skip/flake 而 canonical 绿的 spec 都会把对应 Done 特性打回非绿（污染单一事实源、即 ci-scoped 隔离要防的「假绿陷阱」）。
   - **2026-06-16 实测证据（隔离栈 :8801 + 真库副本，rebase 后）**：起栈跑 3 个**我未改动**的 spec 探保真度 → **2 个失败**：`b11_compliance.spec.ts:120`（ROLE_SYSTEM 退审计）+ `typed_resource_detail.spec.ts:163`（提供部门筛选 after>0 实得 0）。二者代码路径我都没碰（b11 零改动；P2Discovery 我只改「我的申请」深链 href，与"部门筛选返回 0"无关）——属真库副本相对 clean build 的**数据脏化**（`local-db-pollution-vs-test-brittleness`），非我代码回归。**故 worktree 跑权威重采会误伤这 2 个 canonical 绿特性、污染单一事实源；权威重采须在 clean 全真库（customer_acceptance_up M0 导入，需 dumps——本环境无）/CI 等价环境执行。**
   - **行内 spec 迁移做法（已 live 验证逻辑，canonical 重采时套用）**：`workbench_todo_closure.spec.ts` 把 BUSIAUDIT todos 按 `isInline(t)=!!t.action` 分区——`linked`(无 action) 断言渲染 `workbench-todo-link`+点击跳走（计数 == linked.length）；`inline`(有 action) 断言渲染 `workbench-todo-expand`+展开出 `workbench-todo-action-panel`+hash 仍 `#/workbench`（计数 == inline.length；inline.length==0 跳过该段）。已真流程铸单 live 复验此行为成立。
2. ~~**GATE 批准（拆办申请）**~~ **【已闭合】** 负责人 2026-06-16 会话内批准（「两件一起、本轮全做完」），签字账本 `.testing/signoff/workbench-inline-and-request-flow-dissolution.signoff.yaml`（decision_only）。
3. **【tracked 回归 · 待下一 PR 归位】国家通道 UI 孤儿**：clean 真库权威重采复核发现——被删的 `P3RequestFlow.vue` 不止装列表，还装着**国家直达转报 tab**（`p3-tab-national`/`p3-national-pane`/`p3-escalate-btn`，D50 `application.escalate_national` 的**唯一前端入口**）；拆解时漏归位 → 该能力现为**孤儿**（后端 capability/policy/角色门 `canViewNationalChannel` 全在，前端无入口）。`requestFlowRoles.ts:86`/`pageAccess.ts:223` 仍描述/守一个已不存在的 tab。**严重度：flag 门控（`nationalChannel.enabled` 默认 OFF）→ 默认部署零影响、潜伏；仅对签了 D50 的 flag-on 租户是真回归。** 负责人 2026-06-16 裁：记为 tracked 回归、本轮不修。**归位方案**：把国家直达转报队列+转报动作从被删 P3 抽成保留子路由 `/request-flow/national`（沿用拆解的「子路由保深链」范式）或工作台 flag-gated 行内，业务运营员 flag 门入口，并 un-skip `national_channel.spec.ts` 用例 1&3。`national-direct.feature` 维持 Ready（未据残缺 UI 打绿，诚实）。
4. **后续（同机制再应用）**：异议受理（`objection.case.accept`）按条内联；非内联聚合待办深链落点精准化；P3 NL 加速器面板归位（次要——NL 加速在 P2/B11/B12 仍在）。

## 〇'、clean 真库权威重采（2026-06-16，承负责人「从原始数据重建+重采」）

- **clean DB**：`customer_acceptance_up.sh` 从 `old/10示例数据/*.sql` + `old/12-datastructure/*.xml` 重建 129M M0 真灌库（含 approval_case 等 75 表），解之前「无 dumps→只能用脏 dev 库副本」的环境保真度阻断。
- **环境保真度实证**：脏库副本上失败的 `typed_resource_detail`（部门筛选）在 clean 库**转绿**；残留 `b11_compliance` 失败 = `waitAppReady` app-load 抖动（retries 吸收，非真失败）。
- **可提交性**：pytest golden（wave0/conditional）此前 vacuous-skip 仅因 clean 库建在 `.clean.db` 而 seed-guard 查默认 `.data/zw_brain.db`；把 clean 库置默认路径后 wave0 **11 passed/1 deliberate-skip**，权威 measurement 转为忠实（不再误伤 canonical-绿 pytest 特性）。
- **12 spec 全迁移**（5 我做 + 7 子 agent，行内/深链分区 + 拆办申请归领数据 + p3→p4 testid + 受理/审核移工作台行内）；**我编辑的特性全绿 Done**（j1-role-projection-views / webui-routing-cleanup / webui-pages-real-data / 工作台行内）。
- **clean 库暴露的历史债修复 2 处**（非本特性）：`objectionLabels.ts`（异议 kind snake_case R12 漏，三页共享）、`customer_acceptance_checklist.spec.ts`（P4Delivery 标题改名连带）。**留 2 处 pre-existing**（不阻合并、非 request-flow）：`webui_smoke` 字段候选（mock 推理空）、`d57` A6 挂接审核（#294 部门数据隔离 org-scope vs 硬编码 mint org）。

---

## 〇''、M5 供数侧彻底行内 + 全局同类遗漏审计（2026-06-16，承负责人「不彻底」反馈 + 「全局检查同类遗漏」）

负责人本地走查供数据页反馈「受理/审核就地办不彻底」——M1 只内联了「申请受理/审核」，供数侧聚合
待办（发布/审核/异议受理）仍是计数深链。本轮把供数侧 backlog **彻底 re-grain 为 decision-list 行内**：

- **后端**（`workbench_backlog_projection.py`）：`_backlog_todos`（BUSIAUDIT）+ `_manager_review_todos`
  （MANAGER）把 7 类聚合待办从「count+href」改为「枚举真实积压实体 + 逐条挂 decision-list 载荷」：
  目录发布 / 资源发布 / 目录平台审 / 目录部门审 / 反向草稿审 / 挂接资源审 / 异议受理。每条 item 带
  `capability/gate/basePayload/decisions`，行内逐条办（通过/驳回·带 reason）。
- **前端**（`WorkbenchTodoActionPanel.vue` + `P1Workbench.vue` + `workbench-fixture.ts`）：`action` 加
  `kind:"decision-list"` 分支，聚合待办展开成逐条列表，每条 GatedAction 自门控 + reason textarea。
- **集成缝**（两 agent 并行各自不见对方改动，集成时两处语义碰撞，均为正确组合行为）：
  ① M5 把 `backlog-objection` 给了行内 decision-list → M1 测试「无 action」断言切到未 re-grain 的
  `backlog-demand`；② M1 BUSIAUDIT 增量 enrich 无条件剔除 `backlog-application`（逐单受理覆盖）→ A
  测试改在 `_backlog_todos` 原始层断言。
- **守卫修真**：`test_action_role_gates_aligned_with_backend_policy` 正则 `\{([^}]+)\}` 在注释
  `={ROLE_BUSIAUDIT}` 处截断 body，**静默只对账 3/36 门**（M1/M5 依赖的核心门全漏查=假绿）。修后
  全查 36 门 **0 漂移**（无真实安全漂移被掩盖），仅 1 条纯视图门 `.view` 加后缀识别跳 set-equal。

**孤儿收口**（集成顺手，负责人批准范围内）：
- `delivery.trigger_recovery`：后端 capability/policy/契约/5 面俱全却**无 UI 入口**（孤儿门）→ 归位
  P4DeliveryTaskDetail 失败态「触发恢复」，状态门 + 无权不可见，补 spec 3 例。
- `objection.case.accept`：P5ObjectionInbox/Detail 两页逐字重复同一 invokeActionStub → 收口
  `lib/objectionActions.ts` 单一 builder（工作台行内走后端 `_objection_item` 派生、不经此）。
- `service.publish_or_suspend` 死门已删（src 内零 CTA 调用）。

**全局同类遗漏审计结论（两 todo 源全扫 + 全角色）= 无新增遗漏**：
- 内联齐全：M1 受理/部门审（per-request）+ M5 发布×2/平台审/部门审/反向草稿审/挂接审/异议受理。
- 深链是**刻意正确**（均非简单是/否）：补录任务（填表多字段）、汇总/准入（多步）、督办（多步）、
  服务审核（向导多步）、申请进度（只读跟踪）、申请聚合（per-request 受理已覆盖）。
- **API 发布无独立遗漏**：`resource.asset.publish` handler 多态路由 API 资产（与 table/file 同表，
  `_list_assets_pending_review(api_side=True)` 即证）→ `backlog-resource-publish` 已枚举含 API 资产，
  行内发布对 API 服务同样生效。
- 操作员工作台 = 申请进度/补录（applicant 视角，无是/否决策）；安全审计员只读；运维员 ops——皆无隐藏是/否 backlog。

### M5 全栈 e2e 验证 + 浏览器端到端走查（2026-06-16，承负责人「推 PR 前必浏览器走查」）

- **浏览器端到端走查（隔离栈 :8801 + clean M0 真库 + Playwright 实跑）**：BUSIAUDIT 工作台 3 待办全行内
  （待发布目录 5/资源 2/异议 1，「展开办理」展成逐条 + 发布/受理按钮）；MANAGER 2 待办全行内
  （目录审核 10 条「通过/驳回」，M8 部门隔离实证 10/11）；**真执行一条**：异议「受理」→ POST 200
  objection.case.accept → 绿 toast「已受理」→ 队列 1→0 → **停留工作台不跳走** → 办理建议实时重算。
  操作员工作台 0 行内是/否（进度跟踪，诚实空）。截图存档。
- **全栈 e2e 重采（39 pytest + 8 spec 实跑 against :8801）**：我改动触达的特性全绿——
  `twin_browser_pages` 13✓（工作台渲染）/`role_projection_views` 5✓（角色投影）/
  `permission_invisibility` 4✓（无权不可见门）；39 pytest 模块全 pass。
- **measurement 决策（不污染单一事实源）**：worktree 重采唯一非绿 = `p0_feedback_0611_chain` 链路1
  **超 300s 总超时**（编目→挂接→发布×2→申请 长链 + mock 推理延迟 + 134MB 库），卡在 `submit-draft-btn`
  步；**经 git diff 实证该流程文件（P3RequestDetail.vue / application.py / sync.py）自 6b3d33d7 基线零改动**、
  且错误是总预算超时非元素缺失、同环境 链路2 通过 → 判定为 **worktree 环境慢化 flake，非代码回归**
  （同 §〇' 记的 worktree env 保真度问题）。按本仓既定政策「worktree 重采会污染单一事实源、权威测量须
  canonical/CI」——**不提交该 worktree measurement**（提交即把 canonical-绿特性误标非绿），保留 canonical
  cd0e6dd8（43/51，指纹新鲜、gen --check + check_feature_measurement 双 OK）。我改动的非 feature-backed
  测试不动任何 feature 指纹，故 canonical measurement 对本 PR 仍有效（D46.g）。

### 供数据页删与工作台重复的办理队列（2026-06-17，承负责人「工作台行内办理了，那其他地方的就应该删掉」）

工作台行内化后，供数据页（P5Provider.vue）仍重复留着三张**逐条带按钮的办理队列卡**（待审核目录/待发布目录/待发布资源）——同一简单是/否两处维护（反简洁/货架尺子）。本轮收口为单一动作面：

- **删三张办理队列卡**（`P5Provider.vue`）：连同 loader/handler/computed/watch/孤立 style/dead import 一并减法（~150 行）。**供数据页定位收敛为管理面**：编目/挂接/注册向导 + 目录/资源管理概览（待发布/审核中等计数只读保留）+ 协作待办导航（进详情收件箱办多步/长列表流）+ 数据质量待补全；页头改「从这里编目、挂接、注册…（发布/审核去工作台办理）」。
- **不丢功能**：发布时的「重复率提醒」此前仅供数据队列 publishDraft 渲染、工作台行内发布静默丢——`WorkbenchTodoActionPanel` 派发后查 `duplicate_warnings` 非空则 warn toast 保值（浏览器实证「检测到 72 条可能重复」）。
- **5 个 e2e spec 迁移**：发布/审核步骤经被删队列 → 改走工作台行内（新 helper `publishViaWorkbench` 切 BUSIAUDIT→展开积压→点该条发布→验「已发布」）；`permission_matrix` 发布卡可见性断言迁工作台 publish-todo 可见性；`p0_feedback` 链路2 反向草稿按码经 API 触发终态（标题不可靠）。
- **p0_feedback 链路1 真因纠正（上一节误判修正）**：`submit-draft-btn` 卡死**非 worktree 慢化**，而是 request.create 写后快照与详情页读取竞速（#126 同会话预取）→ 详情读到「未找到该申请」、submit 不渲染、吃满超时预算（误显为"链路慢"）。修复 = 提交前 reload 取铸单后新快照（同链路2 reload 口径）；修后链路 35s（非 600s）。回退误加的 600s 超时。
- **session-init 计时脆性**：`waitAppReady` #role-switch 30s→60s（每用例新上下文冷启动会话装载，134MB 真库副本在慢环境偶尔 >30s）。
- **全栈 e2e 权威重采（死磕单发：fresh clean M0 + 重置 db 去陈旧 wal + warm 栈 + 单发不重启）= 43/51 全绿**（与 cd0e6dd8 基线齐平、无回归）；3 个被改 feature-backed spec（j1-approval-conditional / j2-resource-mount / webui-pages-real-data）+ twin（webui-routing-cleanup）全 pass、指纹刷新；national vacuous-skip = 既有 orphan。**踩坑（已记 memory）**：①重采前必 `rm db-wal` 否则陈旧 wal 致 `database disk image is malformed`→全 e2e 假失败；②**单发铁律**——第二遍 capture 跑在第一遍 mint 脏化的 db 上致 b2/customer_acceptance 假失败（40/51）；fresh db 单发即 43/51。

---

## 附：本轮改动文件指纹（集成分支）

后端：`zw_brain/command/sync.py`（action builder + upsert）、`zw_brain/command/demo_state_sync.py`（upsert_todo 加 action）、`zw_brain/domain/workbench_backlog_projection.py`（BUSIAUDIT 增量 `_enrich_busiaudit_backlog`）。
前端：`zw-brain-web/src/components/GatedAction.vue`、`WorkbenchTodoActionPanel.vue`、`pages/P1Workbench.vue`、`pages/P4Delivery.vue`、`config/productShellNav.ts`、`router/index.ts`、`lib/pageAccess.ts`、`fixtures/workbench-fixture.ts`、（删）`pages/P3RequestFlow.vue` + 多页深链/面包屑。
测试：`tests/test_workbench_inline_action.py`、`test_request_flow_dissolution.py` 等。
