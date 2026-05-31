# preflight-debt

> **现算账本（debt-as-function，D46 同构）**：每条 debt 的 open/stale-fixed/invalid 状态不再靠人读本文判断，
> 由 `.testing/debt/<slug>.debt.yaml` 的 assert 对活树**现算**派生，机器视图见 `.testing/debt/debt-status.md`
> （`scripts/gen_debt_status.py` 生成、段 64/65 守卫）。本文档**保留为散文归档 + 段 34 wave-snapshot 反向链接
> 锚点源 + 各 `# full-scan-ok:` / `# trigger:` 代码注释的回链目标**，不再作为「哪些 debt 还开着」的真相源。
> 已僵死被关的条目（如 BFF in-memory→Redis、customer_acceptance_up.sh strict）其 `.debt.yaml` 现算为
> stale-fixed 后已从 `.testing/debt/` 移除，散文条目留此处作审计链。

Outstanding items intentionally deferred from the current preflight gate set. Each entry must list
the symptom, the deferred decision, and the trigger that forces a re-evaluation.

任何一条 entry 在 trigger 触发时必须升级为 P0 fix 或转化为机械化 preflight check；不允许长期沉淀。

## entry 必填字段约定（2026-05-26）

**自本约定起新增的** trigger 化延后 entry，应含 `Where` / `Implication` / `Why deferred`
/ `Trigger to re-evaluate` 四个核心字段；并且**如果 trigger 触发当日落地的代码会撞 main
已占用的标识符**，必须额外补一行 `Reserved names (taken)`，记录当前 main 已占用、将来
trigger 触发时会撞名的标识符（字段名 / enum 值 / slug 前缀 / 类名 …）+ rename 取舍提示。

既有 entry（2026-05-26 之前）字段命名不严格统一，仅在触动重写时一并补齐——避免一次性
回填造成纯文字 PR 噪声。

目的：防止 trigger 触发当日才发现撞名再返工选 rename 路径。"已占名"清单与 entry 同生命周期，
trigger 关闭即可删除字段。

## 2026-06-01 — webui e2e 本机 --with-e2e 不能干净复现（2 超时 + 1 真断言失败）

- **Where**: `scripts/capture_feature_status.py --with-e2e` 在本机全栈（:8800 + mock 推理）实跑 15 个 Playwright spec：
  - `customer_acceptance_checklist.spec.ts`（webui-pages-real-data 引用）→ **timeout >600s**（单 spec 跑 10+min 未完）
  - `twin_browser_pages.spec.ts`（webui-routing-cleanup 引用）→ **timeout >600s**
  - `permission_invisibility.spec.ts:79`（webui-action-role-binding 引用）→ **真断言失败**：
    「P5DemandMatchDetail 受理并起草申请：OPERATER 可见 / MANAGER 不渲染」
- **Implication**: 这 3 个 webui feature 在本机 `--with-e2e` 测量轴非绿 → 指纹机制如实算它们**非 Done**（fail-closed 正确工作，未被环境噪声骗过）。因此本 PR（D46.g）终态保持 **Done 29 / Ready 3**——`webui-action-role-binding` / `webui-routing-cleanup` / `webui-pages-real-data` 不冒绿。
- **两类根因要分开**:
  - **(a) e2e 套件本机太慢**（customer_acceptance_checklist / twin_browser_pages 串行 >10min/spec）→ e2e 健壮性/提速债，与 `webui-pages-real-data`（2026-05-31 条）同类。CI 上这些 spec 标 `browser_e2e` 被跳过，故 CI 绿不代表本机 e2e 能跑完。
  - **(b) permission_invisibility:79 真断言失败**：MANAGER 角色下 P5DemandMatchDetail 仍渲染（或 OPERATER 不可见）——触及「无权限=不可见」安全语义，**值得查是测试脆还是 P5 真回归**。决策：本 PR 范围只登记，作独立 follow-up（产品研发负责人 2026-06-01 选 A）。
- **Why deferred**: D46.g 的目标是测量轴信任锚（已达成、CI 绿、机制经 --with-e2e 实跑验证）；webui Done 抬升依赖 e2e 能干净跑通,属独立工作面,不塞进信任锚 PR。
- **Trigger to re-evaluate**: (a) e2e 提速/分片使 customer_acceptance_checklist+twin_browser_pages 能在超时内跑完;(b) 查清 permission_invisibility:79——若 P5 真回归则 P0 修(关乎权限可见性安全语义),若测试脆则修断言;三者齐后 `capture --with-e2e` 全绿 → 现算自动抬 3 webui 回 Done(→31)。
- **No mechanical guardrail (now)**: e2e 能否本机跑完属环境/性能,无可机械化项;本 debt + CLAUDE.md D46.g 登记防遗忘。

## 2026-05-31 — 测量轴信任锚 git_sha → 内容指纹（D46.g，跳出孤儿/陈旧两难）

- **根因**：feature-status 测量产物以 `<git_sha>.json` 命名、段60 以「git_sha 须 HEAD 祖先」判新鲜。
  本仓 squash-merge（`(#NNN)`）下，**任何分支上采的测量一合并即孤儿**（`ad35667` = D46 分支被
  squash 掉的 commit，`git log --all --contains` 查无）→ 段60 永久 WARN（狼来了）+ green() 对
  存在但陈旧的产物把旧 `result==pass` 当真 → **可误标 Done**（fail-closed 只保护"测量缺失"）。
  实证危害：曾把 `request_service.by_id` DB 回源误报"未做"（实则 f96b7fb 已落）。
- **修复**：信任锚改为**被测内容指纹** `feature_fingerprint = sha256(.feature + 引用测试文件内容)`
  （`scripts/feature_status_lib.py`）。capture 写入每 feature 的 fingerprint；`green()` 要求
  指纹匹配才算绿；段60 改为"绿但指纹陈旧 → FAIL"。**squash 免疫**（squash 不动文件内容）、
  **可安全 FAIL 不炸 main**（只在测试/规格真变没重采时触发，本地重采即解）。
- **执行点**：CI（`ci.yml:55` 每 PR + push-to-main 跑 preflight）做指纹**检查**（便宜、不需 seed）；
  指纹**重采**（重活、真数据 feature 需 seed）本地做。**ops 待办**：开 main 分支保护
  「require CI green」把"合后变红"升级为"硬阻断"（当前无 branch protection）。
- **与 D11 的边界**：本修复让状态视图**不再说谎**，但指纹只保证"测试/规格自上次真过未变"，
  **不保证"只改实现没破坏真数据 feature"**——那仍归 D11「真数据测试进 CI 跑」独立轨（见下方
  2026-05-25 条），D11/`feature`/`e2e` debt 不再是"状态诚实"的前置，仅是"抓真数据回归"。

## 2026-05-30 — feature 测量产物 CI 自动刷新未接（D46）

- **Where**: `.testing/status/measurement/<sha>.json` 由 `scripts/capture_feature_status.py` 实跑 pytest 产出；本期靠 PR 提交基线 + 合并前本地手跑刷新，CI（push-to-main）未自动跑 capture 并持久化产物。
- **Implication**: 新增/改测试后若未重跑 capture，测量产物对新 feature 陈旧；状态函数 green() 对缺产物 fail-closed（算 InTest/Draft 不会误标 Done），段 60 对陈旧仅 WARN，不阻断。
- **Why deferred**: CI 内 auto-commit 产物需写权限 + bot 提交链路，风险高于本期收益；与 capture_acceptance_evidence 同人在环模型，先手跑。
- **Trigger to re-evaluate**: 测量陈旧致状态视图误判被发现，或首客上线前需"状态视图实时反映 HEAD"——届时在 ci.yml test job 后接 capture + 产物持久化（与 2026-05-29 验收证据 CI 化条合并做）。

## 2026-05-31 — j1-api-call-monitoring 无 P4 调用监控 UI（本地走查，留 InTest）

- **Where**: capability_call 数据层已实现+测试绿（CapabilityCallRecord + record_capability_call 中间件），但 P4 `#/delivery-exchange` **无调用监控视图**（无 curl 调用历史 / 配额 / QPS 展示 tab）。feature 7 个 Scenario 多标延后 W0-07（浏览器）/ Wave1+（配额引擎）。
- **Implication**: feature 声明 WebUI 面但 P4 监控 UI 未铺；2026-05-31 本地走查产品研发负责人确认看不到监控视图 → 留 **InTest**，不签。数据层/API 可用。
- **Trigger**: 铺 P4 调用监控 UI（接 capability_call 查询 + 配额/QPS 展示）→ 走查 → 往 .testing/signoff/ 追加 covers → 翻 Done。属 webui-capability-render-debt 一类。

## 2026-05-31 — j1-approval-conditional 两步条件审批运行时未铺（Wave1 延后，留 InTest）

- **Where**: 条件审批（部门审→平台复核两步，`ApprovalStepRecord.decision_mode`）的**运行时分派未 wired**——`application.dept_approve` / `application.platform_approve` 不在 dispatch、approval handler 无两步逻辑、snapshot/P3 待审列表不暴露 decision_mode（区分不出条件审批项）。本期只落了 legacy 导入 mapper（`ExchangeMapper.data_apply_dept_approve`，G1.5 2026-05-23 Unfreeze-Note）+ 8 个数据层测试（test_wave0_j1_approval_conditional.py 测导入态/状态机合法集，非运行时流转）。
- **Implication**: feature 的本期可交付 = legacy 条件审批数据导入（已测绿），但**两步条件审批业务运行时按 D-4 属 Wave1 延后**，UI 里走不了（无项可辨、无 handler 可走）。2026-05-31 本地走查无法演示两步 → 留 **InTest**，不签。
- **Trigger**: Wave1 立项条件审批运行时（dept_approve→platform_approve handler + P3 两步 UI + decision_mode 暴露）→ 走查两步真跑 → 追加 covers → 翻 Done。

## 2026-05-31 — topic.package.query 列表跑详情级投影，87 包 ~1.4s（P7 性能）

- **Where**: `zw_brain/domain/services/topic_package_service.py` `list_projection` → `projection_summary` → `catalog_projection_items`：列表每个专题包都跑**详情级**投影；`catalog_projection_items`（line ~118）对**每个目录项**调 `store.resource_api_repo.list_assets(tenant_id)` **全表加载再 Python 过滤** + 逐项查 `catalog_repo.list_items` / `list_schema_mappings` / `list_schema_snapshots`。87 包 × 每包目录项 × 全表扫 → `topic.package.query{status:published}` 实测 ~1.4s（本地）。
- **Implication**: P7「共享专题包」首屏加载慢（~2s 才出卡片）；快速点入会先看到加载态（已修 UX：加载期显「加载中」不再误显「暂无专题包」，commit 同批）。列表页实际只用 `activeCatalogCount` + title/scenario/status/isSubscribed，不需要 field_count/资源计数等详情字段。
- **Fix direction**: 给 `list_projection` 走**轻量投影**——`activeCatalogCount` 仅按 `entry_status` 数 active 目录项（不算 field_count）；`visibleOrgCount/visibleOrgs/applicationBoundary` 来自 visibility（已便宜）；跳过 `catalog_projection_items` 的 list_assets 全表扫 + mapping/snapshot 逐项查（那是 detail_to_dict 的事）。或把 `list_assets` 按 catalog_code 下推到 SQL / 一次性加载复用。**需带契约测试 + 实测前后延迟验证**（响应形状变化要核 topic.package.query 的投影测试与 5 消费面）。
- **Why deferred**: 改 domain service + 可能动 list 响应形状，需聚焦改动 + 测量验证，不在本次走查会话仓促重构。UX 误显已先修（症状消除）。
- **Trigger**: 客户现场 P7 包数增长致首屏明显卡，或下个 J2/F9 迭代——届时按 fix direction 做轻量列表投影 + 前后延迟实测。

## 2026-05-31 — j1-credential-revoke WebUI 撤回入口未铺（本地走查 #8，选 B 留 InTest）

- **Where**: `application.grant.revoke` / `application.grant.suspend` 能力已注册（write-critical + humanConfirmationRequired）且后端测试绿（tests/test_wave1_j1_credential.py + tests/test_wave0_j1_credential_call.py 含 revoke 断言），但 **webui 无任何撤回 UI 触发**：P4 凭据页（P4*.vue）无撤回入口；P3RequestDetail「撤回申请」按钮显示"撤回申请能力尚未在本环境开通"。
- **Implication**: feature `j1-credential-revoke` 声明 `# Consumer-faces: WebUI | API`，但 WebUI 面未铺 UI。2026-05-31 本地走查产品研发负责人**选 B**：声明 WebUI 面就该有 UI，无 UI 不签字 → 留 **InTest**（不走 D46 sign-off）。API/能力面已可用。
- **Why deferred**: 不按"能力绿就签"放水；WebUI 撤回入口（BUSIAUDIT 撤回授权 + 申请人主动放弃）作为明确待铺项。
- **Trigger to re-evaluate**: 铺好 P4/P3 撤回 UI（接 application.grant.revoke/suspend + 确认弹窗 + 申请人侧红色通知）→ 本地走查通过 → 往 .testing/signoff/ 追加 covers j1-credential-revoke → 现算自动翻 Done。属 webui-capability-render-debt（docs/webui-capability-render-debt.md）一类。

## 2026-05-31 — webui-pages-real-data e2e 因 dump 重建 seed 数据不一致未绿（D46.f；2026-05-31 复核根因）

- **Where**: `tests/e2e/customer_acceptance_checklist.spec.ts`（webui-pages-real-data # Pytest 指向的**整套** J1/J2/P7 验收）3 条 ✘，复核根因（非单纯断言脆）：
  - **P2**（line 34）：seed 无「案例」分类 → catalog-browse 无 `在发现页检索「案例」` 快捷链接。**真数据基线脆**（应断言任一分类）。
  - **P4**（line 105）：`credential.query` 返回 **HTTP 422 `entity_not_found`** —— delivery_task.status=`granted` 但**无对应 credential 记录**（dump 重建 seed 数据不一致：granted 交付未配套凭据实体）。**真 seed 数据不一致**，非测试脆、非 UI bug；凭据样例无从渲染。
  - **P7**（line 236）：`topic.package.subscribe` API 真成功（ok+audit_id，87 订阅按钮渲染），仅点击后「已订阅专题」提示文案断言脆。**唯一真 test-brittle**。
- **Implication**: webui-pages-real-data 现算停 Ready（已签 e5 + e2e 未全绿），非 Done。e5 在其 seed 上记 15 passed → 功能没坏，是 dump 重建 seed 内容/一致性差异。
- **Why deferred（不冒绿）**: P4 是真 seed 不一致——弱化测试让它过 = 掩盖 granted-无-credential 的数据缺陷，违背 truth-first。留 Ready 最诚实。
- **Trigger / 正解**: ① 修 seed 完整性——customer_acceptance_up / 凭据签发链确保 `granted` 交付必有 credential 记录（M0 seed 一致性，根治 P4）；② P2 改任一分类断言、P7 改按钮态断言（保留行为，去硬编码值）；③ 三者齐后重跑 `capture_feature_status.py --with-e2e` → 全绿 → 现算自动 Ready→Done。属 M0 seed 一致性 + e2e 健壮性聚焦改动，非本轮仓促弱化签字测试。
- **2026-05-31 深挖根因（比上更深更广，部分已修）**：P4 422 的真根因不止"无凭据"，是**系统性「内存快照 vs DB」陈旧 + M0 数据不一致**三层：
  - **(已修 Fix B)** `delivery_service.by_request_id` 只读 `brain._snapshot["delivery_tasks"]` 内存基底，DB 导入的交付（M0 dump）不在其中 → NotFoundError → credential.query 422。改为内存未命中回 DB（`task_from_record`，与 system.snapshot 同源）。422 → 优雅 200 not_issued。
  - **(已修 f96b7fb，2026-05-31 校正)** `request_service.by_id` 原只读 `brain._snapshot["requests"]`，DB 导入的 application_record（如 86013a7a）运行时 lookup 漏查 → credential.issue entity_not_found。**HEAD 已加 DB 回源**（`zw_brain/domain/services/request_service.py:261-277`：内存未命中回 `store.application_repo.get_record → record_to_request`，与 system.snapshot 同源），并带 `tests/wave_p4/test_request_db_fallback.py` 守卫。**此前本条标"未修"系测量轴对孤儿 sha 陈旧所致的误判（D46.g 修复对象）**。「可能更多」视图的系统性排查仍开放。
  - **(M0 数据)** 67 交付 0 个有 credential；2 个 granted 里 86013a7a↔approved（有效，仅缺签发）、46f0↔**withdrawn**（granted 交付绑已撤回申请，M0 导入状态不一致）。
  - **处置进展**：Fix B（delivery DB 回源）+ requests 视图 DB 回源**均已落地**（f96b7fb）；剩余 = M0 凭据签发链 + granted/withdrawn 一致性 + P4 测试取"有凭据"交付 + 「可能更多」视图排查。webui-pages-real-data 当前因 e2e 未在本期测量内实跑而 Ready（指纹轴下：签字∧未绿=Ready），morning `capture --with-e2e` 后按真实 e2e 结果现算。

## 2026-05-31 — e2e 测量产物靠本地手跑，CI 未自动接（D46.f，与上方 D46 测量 CI 条合并）

- **Where**: `capture_feature_status.py --with-e2e` 实跑 Playwright 需 :8800 全栈 + 干净 seed 库 + vite build；本期本地手跑产出测量产物，CI（`-m "not browser_e2e"`）不跑 e2e。
- **Implication**: e2e 结果靠人工在干净栈刷新；新 webui 改动后若未手跑 capture --with-e2e，e2e 轴对其陈旧（green() fail-closed 不误标 Done）。
- **Trigger to re-evaluate**: 与「feature 测量产物 CI 自动刷新」同批做——CI 加 e2e job（起栈 + capture --with-e2e + 持久化产物）。

## 2026-05-30 — P3RequestDetail 真实申请详情缺 prefilledFields（D45 轻量卡的 by-design 取舍）

- **Where**: `zw-brain-web/src/pages/P3RequestDetail.vue:34` 读 `req.value.prefilledFields`（来自
  `lookupRequest` → snapshot.requests，无 detail API fallback）；D45 `enrich_requests_snapshot` 的
  **轻量卡**只产 id/resourceId/resourceName/applicant/applicantDept/purpose/status/submittedAt/sharingType，
  **不含** `prefilledFields`（及 timeline/diffFields/reviewFocus 等富字段）。
- **Implication**: 真实申请的详情页「预填字段」区为空。**注意是净改善非回潮**——D45 前真实申请 id 不在 seed-5
  → `lookupRequest` 全空（resourceName/status 也空，详情页等于打不开）；D45 后 resourceName/purpose/status
  全可见，仅 prefilledFields 缺。富字段由重序列化器 `application_service.record_to_request` /
  `prefilled_fields()` 产出，轻量卡刻意不调它（97 条重序列化炸 D-9 perf 预算，见 CLAUDE.md D45）。
- **Why deferred**: 富详情正解 = P3RequestDetail 走一个 detail 取数（新 `request.detail` capability 或复用
  `request.list` 单条），而非靠 snapshot 预填——属前端 + 可能新 capability 的独立工作，超 D45 后端投影范畴。
  在轻量卡里廉价拼 prefilledFields 会与重序列化器口径分叉，不做。
- **Trigger to re-evaluate**: (a) 业务反馈真实申请详情页「预填字段」缺失影响验收；
  (b) P3RequestDetail 立项接 detail API（届时富字段从 API 取，snapshot 卡只做列表/兜底）。
- **No mechanical guardrail (now)**: 富字段完整性属前端渲染判断，无机械检查项；本 debt + CLAUDE.md D45 登记防遗忘。

## 2026-05-30 — 资源卡 update_cycle（更新周期）码→中文映射缺权威源（附录4 未在仓）

- **Where**: `resource_asset.qos_policy_json.update_cycle`（码 1-7，覆盖 73/75 可用资源）。源表
  `dc_resource_base_info` DDL 注释为「更新周期（见附录4更新周期）」——映射在外部附录4，**代码库无权威
  code→中文表**，仓内 `old/` dump 也无该 code 字典。
- **Implication**: D45.c 卡片本可加「更新周期（实时/每日/每月…）」做数据新鲜度信号（用户 sign-off「A」要的两字段之一），
  但码义不确定。常见 GB/T 政务标准是 1实时/2每日/3每周/4每月/5每季/6每半年/7每年，但**未经附录4 确认**；
  政务产品上标错更新频率是误导。守 D11「不猜测、不 Mock」→ **本批不展示 update_cycle**，只上已双重确认的共享类型。
- **Why deferred**: 缺附录4 权威映射；猜测有合规/误导风险。
- **Trigger to re-evaluate**: 业务给出附录4（或确认 GB/T 标准映射）→ 在 `_asset_to_resource_card` 加
  `_UPDATE_CYCLE_DISPLAY` 码表 + 卡片 meta 行补「更新 {date} · {cycle}」（前端已预留 meta 行）。
- **No mechanical guardrail (now)**: 数据语义需业务确认，无可机械化项；本 debt + CLAUDE.md D45.c 登记防遗忘。

## 2026-05-30 — data.search typed query 返回目录而非资源（P2Discovery 资源中心语义不一致）

- **Where**: `zw_brain/command/handlers/j1/data_search.py` —— 有 query 时走 `deps.repos.catalog.search_entries`
  搜 `catalog_entry`（**目录**），空 query（D45 已修）走 `project_resource_cards` 返 `resource_asset`（**资源**）。
- **Implication**: P2Discovery 是资源中心页（架构 §5.2.1，渲染「可复用资源」ResourceCard），但 typed
  搜索返回的是目录命中——**空搜索看资源、打字搜目录**的语义割裂。**预存 smell、非 D45 引入**（D45 只修空 query
  默认视图缺位 + 资源中心裁决）。
- **Why deferred**: 改 typed query 搜资源 = 搜索语义重构（resource_asset 全文检索 + 召回字典 + API 资源融合
  逻辑重排），远超「数据缺位修复」范畴；且需业务确认 P2Discovery 搜索目标到底是资源还是"目录+资源混合"。
- **Trigger to re-evaluate**: (a) 业务确认 P2Discovery 搜索应搜资源 → 立项搜索语义重构；
  (b) 客户反馈"搜出来的和默认看到的不是一类东西"。
- **No mechanical guardrail (now)**: 语义判断，无可机械化检查项；本 debt + CLAUDE.md D45.a 登记防遗忘。

## 2026-05-30 — F9 专题包引用目录未录入 catalog_entry 主表（不可检索 / 无详情页）

- **Where**: F9 三标杆专题包引用的 5 个目录（医疗救助 / 医保码 / 异地就医统筹区·定点机构·经办机构）
  只存在于：① NL 召回字典 `discovery.recallDictionary.sample_titles`（软提示，`data_search.py`
  造 `id="recall:<标题>"` 候选）；② 专题包 `topic_package_item.ref_id`（引用）。**`catalog_entry`
  主表 0 条可检索**（`catalog.entry.query` keyword 搜不到），且**无 `catalog.entry.detail` 能力**
  （目录本身无详情页）。
- **Implication**: 本地验收（2026-05-30）暴露：① P2 发现页召回候选卡片点「查看详情」→
  `catalog.resource_view?resource_id=recall:...` → `entity_not_found`/422；② P7 专题详情想给目录
  「加链接跳转查看」无处可跳。本 PR #170 已诚实收口：召回候选改占位态（去坏按钮）、P7 目录项改纯
  文本 + 注「目录详情与检索入口待 J1 目录主表录入后开放」——不假装有去处。
- **Why deferred**: 把这些目录录入 catalog_entry 主表（可检索）+ 加 `catalog.entry.detail` 能力 +
  目录详情页，是 **J1 找数→用数**的真功能，跨模块（seed/后端能力/前端页），不在 F9 专题包范围。
- **Trigger to re-evaluate**（下个 PR 即修）:
  - (a) 下个 PR 专项打通「F9 引用目录录入主表 + 目录详情页」—— 届时 P7 目录项恢复可达链接、
    召回候选卡片可点进真目录；
  - (b) J1 找数能力整体立项时一并纳入。
- **No mechanical guardrail (now)**: 召回候选↔主表的可达性无机械校验；本 debt + 诚实占位 UI 防误导。

## 2026-05-30 — 概念 B「部门级数据供给契约」（真业务订阅）待立项

- **Where**: F9 本地验收发现 P7「订阅专题」是旧平台**弱概念 A（专区收藏，真实使用=0）**的退化实现，
  本期已降级为诚实回显（isSubscribed，无下游业务）。真正有价值的是**概念 B**：部门向部门/上级/
  国家平台建立**持续数据供给契约**（旧表 `dc_subscribe` / `subscribe_job` / `exchange_pipelines_subscribe`，
  驱动同步任务 + 供给统计 + 国家平台回执 `up_sub_id`）。完整分析见
  `docs/decisions/subscription-business-analysis.md`。
- **Implication**: 概念 B 的载体是 J1 找数→用数 + 交换线（一表通/上下级交换），**不属 P7 专区、
  不在 F9**。当前 P7 订阅按钮只是诚实标记关注。
- **Why deferred**: 概念 B 跨 J1+交换线、需独立设计 + 业务方 GATE；旧平台真实订阅数据 ≈ 0
  （`dc_subscribe` 仅 1 条演示），需先确认数据局是否有真实运营诉求；守 D11 不提前建复杂度。
- **Trigger to re-evaluate**（任一触发即升级）:
  - (a) 业务方/数据局明确「部门级数据供给契约」真实诉求 → 走 R13+GATE 立项产生新 D-编号；
  - (b) 交换线（一表通/上下级交换）立项时一并评估订阅入口归属。
- **No mechanical guardrail (now)**: 业务概念待澄清，无可机械化检查项；本 debt + 分析文档登记防遗忘。

## 2026-05-29 — build_true_data_seed.py 生成器 recall sample_titles 25-total-cap vs 手编 seed 29 条偏差

- **Where**: `scripts/build_true_data_seed.py` 的 `_build_a2_recall_dictionary` 封顶 25 条
  （`PRIORITY_RECALL_TITLES` 4 条优先 + 采样补到 25 **总**上限）；`zw_brain/domain/seed_snapshot.json`
  `discovery.recallDictionary.sample_titles` 现手编 29 条（#168 在既有 25 条之上追加 4 条医保/异地就医）。
- **Implication**: 干净 DB 重跑 generator 会得 25 条（4 优先 + 21 采样），与手编的 29 条不一致 ——
  committed seed 与 generator 输出不可逐字复现。#168 的核心目标（4 条医保目录确定性进召回）由
  `PRIORITY_RECALL_TITLES` 已达成，偏差仅是 4 条非医保 sample_titles 多出。
- **Why deferred**: #168 PR body 已明文「generator 逻辑改动留作干净 DB 重生成对齐」；本机 `.data/zw_brain.db`
  撑肥，generator 本就无法在本机复现 committed seed（与该 debt 同源）；强改封顶语义会二次猜测一个
  文档化的合理推迟。
- **Trigger to re-evaluate**（任一触发即升级）:
  - (a) 下次 catalog 真数据补种进 seed（新增目录）—— 届时重跑 generator，顺带把封顶语义改为
    「优先项 additive、采样封顶 25」使输出 == committed 29，或反向把手编裁到 25；
  - (b) `build_true_data_seed.py` 任何改动 —— 必须同时消解 25-cap vs 29 偏差。
- **No mechanical guardrail (now)**: 无脚本校验 committed seed == generator 输出（跨撑肥/干净库异构）；
  本 debt 登记保证 recall 偏差有据可查，trigger 化对齐而非靠自觉。

## 2026-05-29 — 验收证据 CI 化采集（消除人工采集 env 依赖）

- **Where**: `scripts/capture_acceptance_evidence.py` 当前由人在本机手跑；段 55
  `check_acceptance_package.py` 校验 evidence.json 的 `git_sha` 是否 HEAD 祖先。
- **Implication**: 人工采集时 env 拓扑导致"绿 pytest"与"正确 sha"二选一 ——
  bare worktree 无 venv → pytest fail；主仓 venv 在 sibling commit → sha 非祖先。
  D38 e5 验收据此落在 sibling sha,段 55 永久 WARN「异线」(非阻塞,但 approved 记录带注记)。
- **Why deferred**: D37 本期只建守卫 + dogfood；CI emit evidence job 是独立工程,
  且首个真验收(e5)已能在 WARN 下完成,不阻塞。
- **Trigger to re-evaluate**（任一触发即升级）:
  - (a) 下一个效果验收签字(eN)启动 —— 届时若仍人工采集会再现 WARN;
  - (b) CI evidence job 立项(在 PR commit 上跑 contract+pytest+e2e 并 emit evidence.json,
    git_sha 天然 = PR HEAD,WARN 自动消除);
  - (c) 段 55 provenance WARN 累积到多个 approved 包(噪声超过信号)。
- **No mechanical guardrail (now)**: 段 55 WARN 已机械标记 provenance 缺口,召回有保证;
  补齐(CI 采集)是 trigger 化工程,非靠自觉。

## 2026-05-28 — D33.d 元规则脚本（外部协议词汇漂移扫描）trigger 化延后

- **Where**: CLAUDE.md D33.d 子项承诺写 `scripts/check_external_protocol_term_drift.py`，
  扫 zw-brain 代码标识符与 `docs/agent-runtime/*` 协议字段的同名异义；本 D33 PR 未实装。
- **Implication**: 当前防 skill ↔ AgentRuntime skills 同名异义靠 preflight 段 50
  `check_no_skill_identifier_in_zw_brain.py`（D33.c 落地）单一方向守住——zw_brain/
  代码标识符不出现新 skill 命名。但反方向漂移（AgentRuntime 协议更新 / 新增 MCP /
  A2A / ANP 字段，意外与 zw_brain 现有标识符撞名）目前**无机械守卫**。
- **Why deferred**: D33.d 是元规则承诺（GATE 决策必同步审视外部协议词汇边界），脚本
  实现需要协议字段抽取器 + 标识符 namespace 比对器，工程量超出 D33 命名收敛 PR 范围；
  且当前仅 AgentRuntime AGENT.yaml 一个外部协议在用，未到「多协议同名风险高发」拐点。
- **Trigger to re-evaluate**（任一触发即升级 P0）：
  - (a) 接入第二个外部协议（如 MCP server / 国家平台 / 集团推理平台 SDK 新增声明式 schema）；
  - (b) D33 baseline 之后下一次 GATE 决策（按 D33.d 元规则承诺手工审视一遍外部协议词汇，
        回炉成脚本）；
  - (c) AgentRuntime 协议 spec_version 升级（anp-agent/v1.3+），新增字段命名意外撞 zw_brain
        现有标识符。
- **No mechanical guardrail (now)**: 本 PR 防回潮段 50 单方向已足够防住 zw_brain 内部
  skill 命名回潮；多协议反方向漂移在拐点前不值得提前盖楼。

## 2026-05-28 — 三引擎 commit_to_live A 方案 hack（版本号膨胀）

- **Where**: `zw_brain/domain/{approval_flow_schema,form_schema,recommendation_rule}.py`
  的 `commit_to_live(...)` 三处。原写 `record.version = (record.version or 1) + 1`，
  E3 F8 业务方浏览器走查时撞 `UNIQUE (tenant_id, code, version)` — 因为 commit 时
  `+1` 后的 version 已被历史鬼数据占用。当场 hack 改为
  `record.version = max(existing_max + 1, (record.version or 1) + 1)` 让 demo 跑通。
- **Implication**: 业务方判定保留"每次点入库自动 version+1"语义（A 方案）。代价是
  **version 号膨胀且无业务含义**——同一 schema_code 在 sd-default 内重复 demo 几次
  后 version 可能达 8 / 10 / 12+。版本号本应反映"配置真实演化次数"，目前与 demo
  操作次数耦合，对客户"为什么我的鞍山审批流是 v=11"无法解释。
- **Why deferred**: 业务方在 E3 F8 sign-off 时明确选择 A：先 hack 让 demo 跑通，
  **真实版本语义后续业务方决策**。备选 B/C：B = 一个 schema_code 同 tenant 只一份
  live + 编辑产生新版（v 累计有意义）；C = schema_code 全局唯一不可重复
  （v=1 不可重入，要改名）。三选一需要业务方/产品 30 分钟单独 review。
- **Trigger to re-evaluate**（任一触发即升级 P0）：
  - (a) 首个客户接入前——客户问"为什么版本号跳跃 / 是否每个版本可审计回放"
        必须给出明确语义；
  - (b) `select count(*) from approval_flow_schema where tenant_id='sd-default'
        and schema_code='anshan_4level_v1'` ≥ 20（demo 摸索多了膨胀失控）；
  - (c) Wave 2.x R14 三引擎 1 周客户落地实测——客户实际改配置 ≥ 3 次时需要
        "看历史版本" / "回退到 v2" 真实业务诉求，B 方案就要落地。
- **No mechanical guardrail (now)**: 不加 version 上限门禁——上限是版本演化的
  业务问题，不是工程红线；门禁会逼出"刷分式重置"反模式。等 A/B/C 决策后再加
  对应守卫（B 决策：preflight 段扫"同 code 多份 live"；C 决策：扫"重复 commit
  同 schema_code"）。

## 2026-05-27 — J2-4 资源挂接 OPERATER 提交侧 wizard 立项延后

- **Where**: `.testing/waves/wave-1-j1-j2-closed-loop/features/j2-resource-mount.feature`
  Status: Backlog；`zw-brain-web/src/pages/` 0 个 `P5HookupSubmit*` / `P5ResourceMount*` 页面；
  `zw_brain/skills/` 0 个 `resource.mount.*` / `hookup.create.*` skill。`P5HookupReviewInbox.vue`
  是 BUSIAUDIT 审核侧入口，对应的「OPERATER 提交挂接」上游页未建。
- **Implication**: J2-4 是 Wave-1 必备走线（基线 §3.3 三物化形式 table / file / api +
  §10.2 J2 资源挂接 + 旧 xlsx 行 [57..61] 资源注册）。当前 OPERATER 在 P5Provider 上有
  在线编制 / API 服务化 / 质量规则 wizard，但**为已发布目录补挂 table/file 物化资源**没有入口，
  申请人 J1 只能拿到 api 物化的 catalog，table/file 形态完全走不通。
- **Why deferred**: 涉及新 wizard page + composable + `resource.mount` skill（≥3 个 skill：
  table/file/api 各一）+ data_resource 表（D23 二次升级删 alembic，需 drop&recreate）+
  字段映射 / 字段类型一致性校验子表单。≥500 LOC 新代码，walkthrough 中临时实现会绕过原型审批流。
- **Trigger to re-evaluate**: (a) 业务方提出"在线提交挂接"演示需求 → 走 product-dev.mdc
  R13 + GATE 流程立项；(b) Wave-2 三引擎落地时如果发现 OPERATER 仍只能挂 api → 把 wizard
  纳入三引擎 (R14) 作为表单引擎的首批落地场景（与发布审批同期）。
- **Reserved names (taken)**: 当前 main 已存在 `P5HookupReviewInbox.vue`（审核侧 inbox，
  BUSIAUDIT），新建提交侧 wizard 应命名为 `P5HookupSubmitWizard.vue` 或 `P5ResourceMountWizard.vue`
  以避免与现有 inbox 撞类名 / route 前缀；route 建议 `/provider/wizard/hookup-submit`
  （和现有 `/provider/inbox/hookup-review` 形成 submit↔review 对位）。
- **UI placeholder (2026-05-27)**: P5Provider PageFocusHeader 已加灰链「资源挂接（Wave-1 ⏳）」
  作为验收 walkthrough 时的可见占位，点击 toast "Wave-1 待立项"；不接路由。
- **No mechanical preflight check (now)**: Wave 真实 gap，非漂移。trigger 触发当日按
  product-dev.mdc 阶段 2 起原型 → GATE-2 审批后实施。

## 2026-05-27 — B1.1-A 长期无人申请目录诊断立项延后

- **Where**: `.testing/waves/wave-2-engines-b1-zones/features/b1-1-anomaly-detection.feature`
  Status: Backlog（Pytest: pending）；`zw_brain/skills/` 0 个 `catalog.dormant.*` /
  `dormant.diagnose.*` skill；`zw-brain-web/src/pages/B11ComplianceOps.vue` anomaly tab
  仅显示「审计异常（read-sensitive 反复触发等）」，**不包含** feature 要求的「按发布时长 ×
  申请数 二维诊断 → 建议下线 / 推广 / 观察」。
- **Implication**: B1.1-A 是基线 §5.6 业务反馈 #14 兑现路径（"B1 后台旁路抽查长期无人申请的目录"），
  也是 zw-brain 区分于"数据治理中心"的核心定位（仅基于自有的"申请数 + 发布时长"二维事实，
  **不**包含数据质量评分 / 血缘分析 / 敏感识别 — 那些归集团数据治理 + 安全中心）。当前缺失
  使得 BUSIAUDIT 旁路抽查能力没有具体抓手。
- **Why deferred**: 涉及新 skill (`catalog.dormant.diagnose`) 真实扫 audit_event +
  catalog status + 推送通知到 owner_org 部门管理员（D-编号 D-29 决策范围）+ 前端
  panel + CSV 导出。≥400 LOC + tests。
- **Trigger to re-evaluate**: (a) 业务方 sign-off Wave-2 ready 时优先考虑；
  (b) 三引擎 (R14) 落地后用 AI 配置引擎的"draft" capability 自动生成诊断报表配置，
  人工 promote 到 preview/live → 该路径作为三引擎首批应用场景；(c) 首个客户演练若
  问起"长期无申请目录怎么办"立即升级 P0。
- **Reserved names (taken)**: `B11ComplianceOps.vue` 当前 `activePanel` 4 值
  `'statistics' | 'anomaly' | 'accountability' | 'replay'`，新建第 5 tab 应命名
  `'dormant-catalog'` 而非 `'inactive'` / `'stale'`，与 feature 文件「长期无人申请」语义一致。
- **UI placeholder (2026-05-27)**: B11ComplianceOps anomaly tab 顶部加灰条
  「长期无人申请目录诊断（Wave-2 ⏳ 已立项）」+ 简短说明，作为验收 walkthrough 可见占位。
- **No mechanical preflight check (now)**: Wave 真实 gap，非漂移。trigger 触发后实施
  按 §10.3 三引擎落地 + R14 路径。

## 2026-05-26 — BrainService 残留读路径方法群下沉（brain.py god-class）

- **Where**: `zw_brain/command/brain.py`（3462 LOC）拆分后 185 cap dispatcher 全迁出至 `dispatch.py`
  + `handlers/{j1,j2,b1,infra}/`，但 `BrainService` 类本身仍持有 **~192 方法**，其中绝大多数是
  `_*_record_to_dict` / `_*_projection` / `_topic_*` / `_governance_*` / `_delivery_*` 读路径
  映射 + 投影 helper（语义上属 projection / repository 层，非编排层）。
- **Implication**: §10.2 已 re-scope —— AC1 真实意图「dispatch 不臃肿」由 `dispatch.py` 360 LOC +
  brain.py 内 0 case dispatcher 达成，brain.py 不再卡 LOC 上限。但 192 方法 god-class 仍是真实债：
  多 worker 若同时改读路径投影方法仍会在此文件 merge 撞车；类体过大降低可读性。
- **Why deferred**: 当前无活跃功能需要这些方法搬家；把 ~3000 LOC 读路径方法盲搬到 projection/domain
  层是高 blast-radius 的投机式重构（违反「不为假设造复杂度」）。re-scope 已入档 §10.2，状态板不再
  谎报 ≤500。
- **Trigger to re-evaluate**: (a) 出现一次 brain.py 读路径方法的多 worker merge 撞车 → 把撞车簇
  方法下沉到对应 projection repo；(b) Wave 2/3 读路径重构窗口期主动分批下沉（按 j1/j2/b1/governance
  域切）。任一触发当日按域切片下沉，不整文件一次性搬。
- **No mechanical preflight check (now)**: brain.py LOC 上限已显式退役（§10.2），不设 LOC 门禁避免
  把"不卡上限"的结论又机械化回来；debt 条目兜底跟踪。
- **Update (2026-05-26)**: 仍**不加** LOC / 方法数上限（与上一条一致）。本次只硬化两个**精准回归面**，
  非笼统增长门禁：① 段 35 `check_brain_no_request_state_singleton.py` —— per-request `role` 必走
  `zw_brain/shared/ui_request_context.py` 的 ContextVar，`_ui_state` 单例 backing dict 不得 seed
  `role`（锁死并发污染修复，`_UIStateProxy`）；② 段 36 `check_no_demo_id_literals.py` —— `REQ-/DLV-/PKG-`
  demo id 限 `zw_brain/command/demo_state_sync.py`，不得回潮进 `brain.py`/handlers。两者针对本轮已修的
  具体回归点，不构成对 §10.2「不卡 LOC 上限」结论的翻推。

## 2026-05-26 — 读路径热表 tenant-only 全扫白名单（PR #113 同模式残留）

- **Where**: 段 32 `scripts/check_read_path_full_scan.py` 在当前 main HEAD 扫到 12 处与
  PR #113 同模式的 `select(HotModel).where(tenant_id==X)` 不带 limit / 不带额外
  业务过滤维度的全量扫表点：
  - `zw_brain/domain/repositories/catalog.py::list_model_fields_all` —
    legacy verification 一次性 count/set-membership
  - `zw_brain/domain/repositories/delivery.py::list_tasks` —
    J1 投递任务全量列表
  - `zw_brain/domain/repositories/application.py::list_records` —
    J1 申请全量列表（governance/dispute/approval handler 复用）
  - `zw_brain/domain/repositories/approval.py::list_cases` —
    审批 case 全量列表（与 application 同步触发）
  - `zw_brain/domain/repositories/supply_demand.py::list_demands` —
    payload_json.kind 维度过滤需 SQL JSON 算子才能下推
  - `zw_brain/command/handlers/j2/metadata.py` `existing_reverse` 推断 —
    summary_json.source 同 JSON 维度场景
  - `zw_brain/domain/repositories/catalog.py::_entry_list_statement` return —
    PR #113 修复路径 query builder；调用方须传 filter/limit
  - `zw_brain/domain/repositories/catalog.py::list_items` —
    catalog_code 可选；None 时 tenant-only 全量 item
  - `zw_brain/domain/repositories/delivery.py::list_attempts` —
    delivery_code/attempt_code 可选；双 None 时 tenant-only
  - `zw_brain/domain/repositories/objection.py::list_cases` —
    status 可选；None 时 tenant-only 全量 objection
  - `zw_brain/domain/repositories/resource_api.py::list_assets` —
    lifecycle_status 可选；None 时 tenant-only 全量 resource
  - `zw_brain/domain/repositories/resource_api.py::list_bindings` —
    resource_code 可选；None 时 tenant-only 全量 binding
- **Implication**: 与 PR #113 catalog.entry.query 同形态的「读路径全量扫表 + 内存
  过滤」反模式残留点；当前单租户 sd-default 下行数 ≤ 数千，未触发 P5「待发布目录」
  级的卡顿，但**多租户接入或 J1/J2 量级进入万级时同类卡顿必定复现**。
- **Why deferred**: PR #113 修的是 P5 阻塞客户演示的最高优先级单点；本次本意是用段 32
  把这条「同模式 list-only-tenant」机械化，把残留 6 处一次性修完会显著超出
  「基线漂移收口」PR 范围。改修需要：(a) 给每个 repo 接口加业务维度参数；
  (b) 同步改 ≥10 个 caller；(c) JSON 列下推需要 SQLite vs PostgreSQL 分支。
  Jobs 风格的可逆决策：先用 `# full-scan-ok: <理由>` 把 6 处标记为显式接受的债务，
  机械守住「新增点不得回潮」，旧点等触发再批改。
- **Trigger to re-evaluate** (任一触发即升级为 P0 fix)：
  - **T1**：J1 申请量 / catalog 量进入万级（≥ 10k 行）→ 出现 P5 同类客户卡顿。
  - **T2**：第二个真实租户接入 → tenant-only filter 不再有界。
  - **T3**：再出现一次「客户演示卡顿被现场 hotfix」事件 → 不再容忍残留点。
  届时按 PR #113 同手法把每个 `list_*` 改造为业务维度下推 + paged 接口；
  JSON 列场景额外评估「把维度提到独立索引列」（D7 adapter 输入归口）。
- **Mechanical guardrail (now)**: 段 32 `scripts/check_read_path_full_scan.py`
  对**新增**的 `select(HotModel).where(tenant_id==X)` 不带 limit / 不带额外维度
  过滤的写法一律拦下，必须显式加 `# full-scan-ok: <≥7 字符理由>` 才放行；
  即未来回潮必先经过明确"接受债务"的动作，杜绝隐式漂移。

## 2026-05-25 — 真数据回归不在 CI 自动门禁（D11 张力）

- **Where**: 14 个真数据测试模块（`tests/test_wave{0,1}_*` J1/J2 黄金链路）靠 `tests/_seed_guard.require_real_seed`
  守卫；seed `.data/zw_brain.db` 是 gitignore 的本地 513MB→123MB 灌库产物。CI runner 无此 seed，
  这批测试全部 `pytest.skip`。
- **Implication**: 基线 D11「所有 Skill 必须以旧平台真实业务数据回归验证，禁止 Mock 业务数据」当前**只在本地手动跑**，
  不在 push/PR 的自动门禁内。CI 绿 ≠ 真数据链路绿——真数据回归靠本地或客户验收承接。
- **Why deferred**: 用户 2026-05-25 明确本期只硬化守卫，CI 覆盖转 debt+trigger。dumps（`old/10示例数据/*.sql`，
  最大 dsp_message 286MB）未 git-track，CI 引入真数据需先解决数据来源（轻量 seed 子集 git-track 化 or
  对象存储拉取）+ 构建时长，范围明显更大。
- **Trigger to re-evaluate**（任一触发即升级）：(a) 首个真实客户上线前——真数据回归必须进 CI 门禁；
  (b) dumps 完成脱敏 + 可 git-track 的轻量 seed 子集就位；(c) 再次出现"本地真数据抓到、CI 没抓到"的
  production 现场。届时新增 CI job：从 dumps/子集构建 seed → 跑 `tests/test_wave*` 真数据套件。
- **Mechanical guardrail (now)**: `tests/_seed_guard.schema_drift_reason()` 在 seed schema 落后于
  当前模型时**干净 skip + 打印重建命令**（替代此前 copy-paste `_seed_ready()` 只查行数、stale seed 抛
  61 个 `no such column` cryptic ERROR 的回潮路径）。

## 2026-05-25 — 推理客户端等真实网关验证（E6 AC2，卡集团 SDK 凭据）

- **Where**: `zw_brain/shared/inference/client.py`（239 LOC）**platform 模式 chat/embed 真实 HTTP 路径已实装**
  （`client.py:146-209`，POST `/v1/chat/completions` + `/v1/embeddings`），默认 strict platform，env 显式切 mock；
  非 mock-only。**代码层生产化已完成**，缺的是真实网关凭据下的连通验证。
- **Implication**: 基线 D6/D14 硬约束「所有模型推理调用走集团推理平台统一 SDK，禁止直连第三方 LLM」在产品形态
  + 代码路径均已就位；但真实推理质量/延迟/配额/鉴权未经真网关链路验证。E6 AC2 停止条件「真实模式 + mock 模式
  双跑通」中 platform 真链路一段未验——属外部依赖阻塞（缺凭据/endpoint），非工程内可推进项。
- **Why deferred**: 集团推理平台网关凭据 / endpoint 尚未同步到位（D14 已记此前提）；mock 模式保留给本机/演示。
- **Trigger to re-evaluate**: 集团推理平台网关凭据 / endpoint 到位日 → 跑 platform 真连通 e2e
  （`tests/integration/test_inference_client.py` 已有 platform case 骨架）+ preflight 段 10（禁直连第三方）回归确认。

## 2026-05-25 — 客户机房部署 + 监控对接未落地（E6 AC7）

- **Where**: 无 `scripts/deploy_*.sh`；`Dockerfile` / `Dockerfile_v1.0.0` 存在，CI（`ci.yml` / `security.yml`）
  覆盖 lint/test/build wheel，但**客户机房 dry-run 部署脚本 + 对接集团运维监控的证据缺位**。
- **Implication**: E6 AC7「CI/CD + 客户机房部署 + 监控对接集团运维监控」只完成 CI 段；现场部署 + 监控对接未做。
- **Why deferred**: 用户 2026-05-25 明确本期只登记 debt + trigger，不写部署脚本。客户机房环境 / 集团监控接入口径
  未明确前提前写 deploy 脚本属"为未验证需求盖楼"。
- **Trigger to re-evaluate**: 首个客户机房部署立项 → 落地 `scripts/deploy_*.sh` + 监控对接 + dry-run sign-off；
  与「dev-iam-bypass 生产守卫」「真数据进 CI」同属"首个客户上线前"批次触发，可一并处理。

## 2026-05-24 — AgentRuntime runtime 触发式延后（D30 retrofit）

- **Where**: 协议规范 `docs/agent-runtime/product-integration-guide.md` + `agent-runtime-api-cn.md` 完整；
  Registry schema 4 新字段（`runtime_spec_version` / `agent_yaml_ref` / `trust_level` / `workspace_required`）
  + `scripts/agentruntime_validate.py` + `scripts/agentruntime_doctor.py` + 内置 Agent `AGENT.yaml` 样本
  **均未创建**。
- **Implication**: 架构基线 §8 / R15 描述了外部 Agent 通过 AgentRuntime 接入的产品决策；但运行时未实现。
  原 §10.2 "Wave 1 必达 ≥1 内置 Agent 用 AGENT.yaml 通过 validate+doctor"（产品负责人 sign-off 2026-05-22）
  已 D30 撤回为触发式（架构 §8.6）。
- **Why deferred**: 当前 zw-brain 无外部 Agent 接入排队，按确定性自动化运营和运维「只为真实需求建复杂度」拒绝提前盖楼；
  Registry 单源派生 5 消费面 + `product_scope.{journey,status}` 过滤已机械保证 status≠live 不进任何投影，
  外部 Agent 通过现有 capability 调用走 5 surface 任一面即可，不需要额外 runtime 层。
- **Trigger to re-evaluate** (任一触发即升级为 P0)：
  - **T1**：出现首个真实外部 Agent 接入需求（ANP / Cursor / 第三方 IDE）→ 立即新增 Registry schema 4 字段
    + validate/doctor 工具链 + preflight 段强制约束。
  - **T2**：客户要求 zw-brain 内置 Agent 以 `AGENT.yaml` 形态对外暴露 → 选 1 个低风险 builtin Agent 转写。
  - **T3**：B1.2 接入扩展中心 UI 立项（Wave 2 范围）→ §8.4 7 步流水线 UI 化。
- **No mechanical preflight check (now)**: 段 22 capability 禁区前缀 + `validate_manifest` 现有约束已兜底
  「未授权能力不得变 live+builtin」；额外的 AgentRuntime 字段守卫在 T1/T2 触发前是 noise。
- **不预先盖楼**：在 T1/T2/T3 任一触发前，主仓库不引入未被消费的 schema 字段、不写空跑的 validate/doctor 脚本、
  不在测试夹具里维护 AGENT.yaml 样本。
- **Reserved names (taken)**: `trust_level` (业务字段，能力包内置元数据，enum baseline/reviewed/restricted/revoked)
  — 触发 T1 时 AgentRuntime Registry trust_level (platform/verified/untrusted) 撞名，必须 rename 其中一方
  （建议把 AgentRuntime 字段改名为 `package_trust_level` 或 `runtime_trust_level`，业务字段已写进 2 manifest
  + policy 校验难翻盘）。

## 2026-05-24 — 附录 C 4 项 trigger 化 pending（D30 retrofit）

设计基线 §附录 C「软→硬映射」表中以下 4 条由"待接入"改为"trigger 化 pending"。每条配明确 trigger，
任一触发即升级为 P0 fix 或机械化 check：

- **外部能力包必须带治理元数据** — Trigger：出现首个外部能力包注册请求（与 §8.6 T1 联动）。
  届时新增 `scripts/check_external_package_metadata.py`（治理元数据 schema：rollback_target /
  audit_class / tenant_scope / auth_policy 必填）。
- **Capability 确认边界不得被 UI / Agent 绕过** — Trigger：出现 UI / Agent 绕过 `human_confirmation_required`
  的案例 OR §8.6 T1 触发。届时新增 `scripts/check_confirmation_boundary.py`（contract `human_confirmation_required=true`
  必须在 brain.invoke_skill 链路有运行时校验点）。
- **反 per-tenant fork** — Trigger：出现第二个真实租户 OR 客户提出 fork 后端意图。当前单租户 `sd-default`，
  无 fork 风险；多租户实装时新增 `scripts/check_no_tenant_fork.py`（仓库 grep 拒绝 `tenant_id == "specific-customer"`
  类硬编码分支）。
- **控制面不得出现多处手维护投影** — Trigger：`export_agent_contract.py --check` drift 后发现手维护痕迹。
  当前 5 消费面均派生自单 registry；新增 `scripts/check_no_hand_maintained_projection.py`
  扫 5 投影目录是否含"AUTO-GENERATED; DO NOT EDIT BY HAND"banner 之外的人工 patch 痕迹。

## 2026-05-24 — Wave 2 R14 三引擎已落地，待 T1 客户演练验证（D-31d，2026-05-25 更新）

- **Status (2026-05-25 更新)**: 不再是 "0% 实现 / deferred"。三引擎已在 **PR #92** 落地：检索
  `zw_brain/capability_registry/registered/` 现有 10 个三引擎 capability（`approval_flow.*` 4 +
  `form_schema.*` 4 + `recommendation.*` 2；总 manifest <!-- stat:zwbrain.manifest-total -->233<!-- /stat -->）。`config_change_class` preview/draft
  流已激活（当前 preview 2 / draft 4）。
- **What remains**: 代码侧已交付；**未完成的是 T1 真实客户演练验证**——用三引擎在 ≤1 周内不改代码
  完成"鞍山 4 级审批 + 四川 7 字段表单 + 荆州 5 条推荐规则"项目级定制，由业务方 sign-off。
  sign-off 权威源 = `.testing/signoff/e3-engines.signoff.yaml` 账本（D46.b）；reviewer
  本地跑 `pytest tests/integration/test_wave2_three_engines_acceptance.py -v` 生成
  `.data/wave2-acceptance/` 下 SIGN_OFF.md + consolidated.json artifact（gitignored）。
  等真人门禁（属 R13 业务流程类决策）。
- **Trigger to re-evaluate**: 首位真实客户演练。届时跑通三引擎项目级定制并由海若产品部业务方
  sign-off → 本 entry 关闭并写入 D-编号；若演练暴露引擎缺口（节点/字段/推荐规则不够表达）→ 升级为 P1 fix。
- **No mechanical preflight check (now)**: `config_change_class` 取值已由 `validate_manifest` 强制校验
  （∈ {live, preview, draft}）；三引擎 preview/draft 实例增减不需要新增 preflight 段。

## 2026-05-26 — BFF session Redis backend（P0-E 关闭）

- **Where**: `zw_brain/shared/auth_session.py` — `RedisAuthSessionStore` + `create_auth_session_store()`;
  `zw_brain/entry/rest/server.py` startup calls `validate_session_store_for_deploy()`.
- **Implication**: 多 REST worker / 非 sticky LB 部署时，设置 `ZW_BRAIN_SESSION_REDIS_URL` 即可共享
  HttpOnly BFF 会话；未设置时仍走单进程 `InMemoryAuthSessionStore`（`start-local.sh` 默认路径不变）。
- **Prod guard**: `ZW_BRAIN_DEPLOY_MODE=prod|production` 且未配置 `ZW_BRAIN_SESSION_REDIS_URL` →
  `zw-brain-rest` 启动即 `SystemExit`。
- **Mechanical check (now)**: `tests/test_auth_session_redis.py`（fakeredis 双实例共享会话 + prod guard）。
- **Ops**: 生产镜像需 `uv pip install 'zw-brain[redis]'` 或等价安装 `redis>=5.0`；可选
  `ZW_BRAIN_SESSION_REDIS_KEY_PREFIX`（默认 `zw-brain:session:`）。

## 2026-05-18 — BFF session store is single-process in-memory — **已 superseded 2026-05-26**

> 历史条目保留审计链。实现已升级为 Redis 可选 + 内存 fallback；见上条 P0-E 关闭记录。

- **Where (was)**: in-memory only.
- **Trigger (was)**: multi-replica → **已落地 Redis backend**。

## dev-iam-bypass — `ZW_BRAIN_DEV_IAM_BYPASS=1` 仅限本机/演示

- **Where**: `scripts/start-local.sh`、`scripts/customer_demo_5min.sh` 默认 export
  `ZW_BRAIN_DEV_IAM_BYPASS=1` + `ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only`，使本机不依赖
  IAF/OIDC 即可登录走 WebUI；逻辑在 `zw_brain/shared/auth_session.py` + `zw_brain/entry/rest.py`
  的 bypass 分支。
- **Implication**: 该 bypass 在生产环境会绕过真实 IAM；客户机房若误开等于无身份认证。
- **Status (2026-05-23 G1.4 升级)**: Mechanical preflight (now) — 段 23
  `scripts/check_iam_prod_guard.py` 扫描部署清单（`Dockerfile*` /
  `docker-compose*.yaml` / `scripts/deploy*.sh`），若同文件同时出现
  `ZW_BRAIN_DEPLOY_MODE=prod` 与 `ZW_BRAIN_DEV_IAM_BYPASS*` 任一关键字
  → exit 1。debt entry trigger（「首个真实客户部署上线前」）由 G3「找一个真客户
  在屏幕前 30 分钟跑通」等价触发，故此 G1 期落地。
- **Why preflight (and not deletion of bypass code yet)**: bypass 在
  `start-local.sh` + `customer_demo_5min.sh` + Playwright e2e 路径仍是
  默认入口；删除代码层 bypass 路径在首位客户上线后处理。当下机械守的是
  「漏到生产清单」这条最危险路径。
- **Mechanical guardrail (now)**:
  1. `start-local.sh` 的 prod-mode 拦截（运行时）
  2. `customer_demo_5min.sh` 的 127.0.0.1 绑定（网络层）
  3. **段 23 preflight scan**（commit-time，G1.4 新增）
  这三条层叠兜底；不再加 prose 软提醒。

## 2026-05-23 — 集成测试用 `brain.invoke_skill()` 直调，绕过 trust-stamp 路径

- **Where**: `tests/test_wave1_j2_pipeline.py`、其他通过 `_call(brain, skill, payload)` →
  `brain.invoke_skill(...)` 直调集成测试。生产 mutate skill 入口是
  `REST cookie session → build_trusted_skill_payload → _TRUSTED_SESSION_MARKER stamp → invoke_skill`，
  这些集成测试**完全跳过 stamp 步骤**。
- **Implication**: 任何因 `_TRUSTED_SESSION_MARKER`（object() 哨兵）跨序列化边界泄漏导致的
  TypeError，**pytest 集成层无法覆盖**——必须 e2e（Playwright cookie session）才能复现。
  PR #79 的 B1 + B3 两个 production 500 都属此类（existing 20 项 regression 全过、客户演练打一发就 500）。
- **Why deferred**: 全面在集成层补 trusted-payload fixture 是一次较大的测试 pyramid 改造（每个
  mutate skill 测试都要加 fixture），单 PR 内做会过度扩张范围。PR #79 已在 `tests/test_trusted_session_context.py`
  新增 `test_mutate_skill_with_trusted_payload_persists_anchor_outbox` 作为此 bug 类的护栏——
  下次出现类似 sentinel 跨边界问题，本测试会失败。但**其他 mutate skill 仍存在层级缺口**。
- **Trigger to re-evaluate**: (a) 再出现一次"e2e 抓到、pytest 没抓到"的 production 现场——立即把
  trusted-payload helper 提取到 `tests/_trusted_payload.py` 并所有 mutate skill 集成测试改走该 helper；
  (b) Wave 2 测试 pyramid 整改窗口期，主动 retrofit。
- **No mechanical preflight check (now)**: 检测"集成测试是否经过 trust-stamp"需要 AST 分析或测试
  覆盖率打标，复杂度高于价值。Debt 条目兜底，加 R-001 类点护栏。

## 2026-05-28 — BrainService snapshot model 抽离 (Action E follow-up; Action H partial close)

- **Where (Action H 后剩余)**: `zw_brain/command/pipeline.py`（`PolicyMiddleware` /
  `IdentityMiddleware` 仍持 `brain` 引用；`PersistMiddleware` / `AnchorMiddleware` 已不需要
  通过 `brain._sync_state_views` 间接调，直接传 snapshot 给 module-level sync helper）；
  `zw_brain/domain/services/provider_service.py::find_api_resource` 等读 `self.brain._snapshot`。
- **Action H 落地 (2026-05-28)**: ✅ `sync.sync_state_views(snapshot, status_text)` /
  `sync.sync_request_todos(snapshot, status_text)` 签名改为 snapshot dict + 纯 callback，
  不再取 BrainService 引用；✅ `demo_state_sync.sync_demo_state_views(snapshot, status_text)`
  完全脱离 BrainService — 7 个 module-level helper (`set_todo_status` / `upsert_todo` /
  `maybe_request` / `maybe_delivery` / `maybe_package` / `resource_by_id` / `zone_by_id` /
  `package_status_text`) 全部接受 snapshot dict；✅ `BrainService._set_todo_status` /
  `_upsert_todo` / `_resource_by_id` / `_zone_by_id` / `_package_status_text` 收为 1 行
  delegate shim（segment 48 允许）；✅ PersistMiddleware 直接调 `state_sync.sync_state_views(self._brain._snapshot, ...)`
  + `state_sync.persist(self._brain._state_store, ...)`，不再经过 BrainService 的 sync 方法。
- **Implication (剩余)**: BrainService 内 `_snapshot` 字典 + `_ui_state` proxy 仍是 sync /
  projection / view 的 SoT 持有者，但只有 4 middleware 中 2 个 (`PolicyMiddleware` /
  `IdentityMiddleware`) 还需要 `brain` 引用来调 `_enforce_manifest_policy` /
  `_actor_for_role`。Action H 完成了「demo cascade 脱离 brain」与「sync helper 脱离 brain」
  两条线，剩余的 brain 引用是 policy/identity 跨切，与 snapshot model 无关。
- **Why deferred (剩余 policy/identity 部分)**: 拉出来需要 (a) 把 `_actor_for_role` 拆为
  `policy.actor_for_role` + auth_context 后缀两段；(b) 把 `_enforce_manifest_policy` 翻译层
  下沉到 `policy.enforce_manifest_policy` 内部（DomainAccessDeniedError → AccessDeniedError）。
  这两点是 policy 层去耦合，不属 snapshot 模型范畴。
- **Trigger to re-evaluate**: (a) 下一次需要在 middleware 注入新跨切（rate limit / OTLP /
  circuit breaker）发现 brain ref 阻碍单测构造时；(b) Wave 2.x R14 三引擎落地需要 state-store-
  keyed projection 模型时；(c) provider_service 因多 worker merge 撞车需要把 snapshot
  访问从 service 拉到 brain.py 之外时。
- **No mechanical preflight check (now)**: preflight 段 48 (`brain-no-cross-cutting`) 已守
  cross-cutting / state-sync helper 的 shim shape，反向不允许把 body 写回 BrainService；
  Action H 改 demo_state_sync 后该段仍 PASS（5 state-sync shim 均 ≤3 stmt）。本条目跟踪的
  剩余 policy/identity 解耦改造，结构性的，当前没有"误回潮"风险点可机械化拦截。

## 2026-05-27 — customer_acceptance_up.sh strict 模式与真实 dump 设计脱节 — **已 closed 2026-05-27**

> 历史条目保留审计链。修复落地：`ImportStats.add_issue` 加 `severity`（默认 `"error"`，
> `governance.py` 两处 missing_manifest 标 `"warn"`）；`_common.finish_run` 区分 errors vs warns
> 写 failure_count 与 error_summary，`error_summary` 现在 100% 非 None 当有任何 issue；
> `customer_acceptance_up.sh` 默认 non-strict + `--strict` flag + warn 行打印；preflight 段 41
> `check_no_silent_error_swallow_in_adapter.py` 守 mapper add_issue+continue 必经 finish_run。
> 详见 PR（独立于 #128 / Action A）。

## 2026-05-29 — request.list 性能基准断言负载敏感（间歇 flaky）

- **Where**: `tests/test_wave0_j1_request_list_perf.py::test_request_list_under_one_second_real_data`
  断言 `worst_ms <= 1000`（D-9 perf 回归预算，对真实 `.data/zw_brain.db` 跑 request.list 3 次取最差）。
- **Implication**: 机器高负载（如 CI runner 抢占 / 本地并行跑多套件）时单次采样会冲到 ~1500ms
  触发 FAIL，全量套件间歇红；正常单跑稳定在 ~680-710ms，远低于预算。属负载敏感、非功能回归。
  PR #163 xj-review 全量连跑时复现（样本 708/684/**1510**ms），与本 PR（推理 env 收敛 D37）无因果。
- **Why deferred**: 修法是 perf 测试设计取舍（抬预算留余量 / 改 p50 而非 worst / 加 warmup 丢弃首样 /
  降级为非门禁基准只记录不断言），属性能测试专项决策，不该塞进推理 env 收敛 PR；且 CI 单跑通常过，
  红了按"瞬态/负载"`gh run rerun` 即可。
- **Trigger to re-evaluate**: (a) CI 上该用例**非负载场景**稳定超 1000ms（=真实 perf 回归，立即 P0 查
  request.list 读路径）；(b) 该 flaky 在 CI 反复 rerun 仍频繁红影响交付节奏 → 立项做 perf 测试设计
  （warmup + p50 + 带余量预算或迁出门禁）。
- **No mechanical preflight check (now)**: 负载敏感阈值本身无法机械区分"瞬态尖刺"与"真回归"；
  需人工或 CI 趋势观察，不强行脚本化（避免 `|| true` 类伪绿）。
