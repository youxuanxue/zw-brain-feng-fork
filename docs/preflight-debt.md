# preflight-debt

> **现算账本（debt-as-function，D46 同构）**：每条 debt 的 open/stale-fixed/invalid 状态不再靠人读本文判断，
> 由 `.testing/debt/<slug>.debt.yaml` 的 assert 对活树**现算**派生，机器视图见 `.testing/debt/debt-status.md`
> （`scripts/gen_debt_status.py` 生成、段 64/65 守卫）。本文档**保留为散文归档 + 段 34 wave-snapshot 反向链接
> 锚点源 + 各 `# full-scan-ok:` / `# trigger:` 代码注释的回链目标**，不再作为「哪些 debt 还开着」的真相源。
> 已僵死被关的条目（如 BFF in-memory→Redis、customer_acceptance_up.sh strict）其 `.debt.yaml` 现算为
> stale-fixed 后已从 `.testing/debt/` 移除，散文条目留此处作审计链。

Outstanding items intentionally deferred from the current preflight gate set. Each entry must list
the symptom, the deferred decision, and the trigger that forces a re-evaluation.

## 2026-06-13 — render-debt 守卫 slug-grep 判据升级（上帝视角复核 #273 暴露的守卫设计缺陷）

> #273 渲染债分诊清账过程中，上帝视角二次复核（67-agent 对抗式审计 + 人工 trace-to-consumer）
> 暴露 render-debt 守卫的「已渲染」判据是纯 slug 字面量 grep，对 zw-brain「单一 system.snapshot
> 读路径 + 注册表/NL 派发」架构系统性假阴性。现算状态见 `.testing/debt/debt-status.md`。

- **render-debt 守卫 slug-grep 判据假阴性** — debt `render-guard-slug-grep-false-negative`（external，owner+trigger 跟踪）：
  - **Where**：`scripts/check_webui_capability_rendered.py` —— 判「已渲染」用 `zw-brain-web/src`
    下 capability slug **字面量 grep**。
  - **Implication**：前端经**单一 `system.snapshot` 胖快照**（`/api/snapshot`，~32 文件）读数 +
    `pages.generated.ts` 注册表派发 + a2a/NL 工具绑定触达的能力，前端无写死 slug → 守卫一律判
    「未渲染」=系统性假阴性。本期 79 降级里 **`system.snapshot`（全站唯一读路径）即被误判降级**，
    靠人工 trace 才接住；当前 5 条「假阴性/派发可达/读路径」豁免本质就是该缺陷的人工工作量。
    `pages.generated.ts` 从 manifest webui 标志**生成**，当 webui 证据是循环论证——这次 67-agent
    workflow 初报「35 误降」即被此循环信号污染，trace 后真值=1。
  - **Why deferred**：升级判据属**可机械化**（解析 `useSnapshot→/api/snapshot` 端点映射反查 +
    区分 pages.generated.ts 真实派发 vs 纯生成 + a2a/NL 绑定作渲染信号），但 ROI 待评估——当前
    手工豁免成本低、缺陷已文档化（`docs/webui-capability-render-triage.md` 纠偏注记）；本 PR 是
    分诊清账非工具重构，不扩边。
  - **立项指针**：升级 `check_webui_capability_rendered.py` 把「已渲染」从 slug 字面量升级为
    「webui 可达」——① `/api/snapshot` 读路径反查 ② pages.generated.ts 真实派发 vs 纯生成区分
    （消除循环信号）③ a2a/NL 工具绑定作渲染信号；并在守卫文档固化「pages.generated.ts=生成物、
    非独立证据」警示。
  - **Trigger to re-evaluate**：(a) 再出现一次 webui-critical 能力被 slug-grep 误降、靠人工接住；
    或 (b) 渲染/能力面工具化迭代立项窗口 → 升级判据，消除系统性假阴性，关债。
  - **[2026-06-13 已关债·本 PR 实现]**：`check_webui_capability_rendered.py` 判据从纯 slug
    字面量(LIT) 升级为 **webui 可达并集 LIT ∪ ROUTE ∪ PINNED**——ROUTE 专属 REST 路由（openapi
    `x-zwbrain-skill-id` 现取 slug→路由，路由串在 src 即可达，自动认 system.snapshot 经
    `/api/snapshot`）+ PINNED 契约测试钉死 webui（注册表派发/D2 基础能力的非循环人工锚，自动认
    governance.iam_overview / tenant.policy.evaluate）。3 个架构假阴性由守卫**自动识别**、已从
    手工豁免移除；台账只剩 NL/内置 Agent 工具可达（platform.docs.*）= 守卫**设计内**合理豁免。
    回潮锁 `tests/test_webui_capability_render_guard.py`（5 测，防退回纯 slug-grep）。
    `.debt.yaml` 现算 stale-fixed 已移除，本条留作审计链。

## 2026-06-08 — 0605 验收回合批次 2（T5 目录详情字段核账 / T7 行内编辑暂缓）

> 批次 2 = T6 代理服务注册角色口径纠正（D54 GATE-1，已实现）+ T7 已注册 API 服务操作列（已实现）
> + T5 目录详情字段核账（= 本节记债）。现算状态见 `.testing/debt/debt-status.md`。

- **T5 目录详情导入富集债** — debt `catalog-detail-import-enrichment`（assert=grep_absent 现算）：
  - **Where**：`zw_brain/adapters/legacy/mappers/catalog_metadata.py` `_map_data_catalog`(:218-240) summary 字典。
  - **核账结论**：投影链路 + 渲染**已就位**——`catalog_service.catalog_meta()`(:442-465) 已投影
    domain/applicationScenario/sourceSystem/resourceFormat/businessUpdateCycle/dataUpdateCycle，
    `typedDetailDisplay.ts` compilationRows/decisionRows 已渲染。实读 `.data/zw_brain.db`
    catalog_entry 1222 行（189 条来自 data_catalog 全字段映射）：resource_format(189)/update_cycle/
    catalog_type/shared_type/open_type/published_time 有值；但 **application_scenario=0 / source_system=0
    / domain≈0** —— `_map_data_catalog` 未映射 `use_desc`(应用场景)、`domain_id`/`domain_name`(所属领域)、
    `business_update_cycle`(业务更新周期单列)、`use_claim`、`data_region_range`。
  - **Implication**：189 条真实目录详情上述字段**诚实空态**（有键无值，D11：不伪造，显空）。非源缺供——
    旧平台 `old/12-datastructure/dsp_catalog.xml`(data_catalog) 确有这些列（use_desc 应用场景描述 /
    domain_id 数据所属领域 / business_update_cycle 业务更新周期 / use_claim 使用要求 / data_region_range
    数据区域范围），是**导入富集缺失，可补**。
  - **Why deferred**：本期口径=核账 + 记债（承 T5 卡片「不含则属上游导入富集债→记 docs/preflight-debt.md」）；
    富集回填属上游导入侧工作，且业务方未坚持本轮必补（D53/旧平台事实已锁定口径，无新业务决策）。
  - **Trigger to re-evaluate**：业务方坚持补这些详情字段，或 T3 在线编制(B1)落地后口径统一 →
    在 `_map_data_catalog` summary 补 application_scenario/domain/business·data_update_cycle/use_claim/
    data_region_range，重跑导入富集存量目录 → 详情有值，关债。

- **T7 行内「编辑草稿」暂缓** — debt `api-service-row-inline-edit`（assert=grep_absent 现算）：
  - **Where**：`zw-brain-web/src/pages/P5ApiServiceWizard.vue`（已注册 API 服务列表操作列）。
  - **本期落地**：操作列按 lifecycle_status×角色门渲染 提交审核/发布/下线（均一键、仅需 resource_code、
    接既有能力）——直接解掉验收主诉「71 条草稿无任何动作」。
  - **Why deferred（编辑）**：`_change_api_resource` 走 `upsert({**existing, **payload})` 合并语义，
    半截编辑会用表单默认值覆盖未预填字段(clobber)。乔布斯「不出半截功能」：宁缺编辑、不出会丢数据的编辑。
    且批次 3 的 T8（表单改按钮触发展开）正重构同表单，叠加 edit 模式冲突面大。
  - **Trigger to re-evaluate**：T8 落地后或业务方要求行内改草稿 → 富集 provider.services 投影携带可编辑
    字段 + P5ApiServiceWizard 加 edit 模式预填（按钮「保存修改」接 `resource.api.change`），关债。

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

## 2026-06-06 — 0605 反馈批次 4：外部依赖立项 + 记债（F6 库表交换 ETL / B2 字段元数据 10 列 / G4 过期维度）

> 三项均依赖外部底座/上游字段缺供，本期不做完整实现——交付物 = 债账本 + 立项 proposal，把"为什么
> 不做、做需要什么、何时重启"确定性固化。现算状态见 `.testing/debt/debt-status.md`（assert 现算）。

- **F6 库表交换 ETL（立项 + 记债，最实质）** — debt `f6-library-table-exchange-etl`（外部依赖，assert=grep_present 现算）+
  立项 `docs/decisions/library-table-exchange-etl-external-integration-proposal.md`：
  - **Where**：`zw_brain/command/handlers/j1/delivery.py`（`delivery.exchange.{plan,publish,start,stop}`
    四 handler）→ `zw_brain/domain/services/delivery_service.py:134` `record_attempt`（仅记 planned/
    published/running/stopped 状态到 delivery_attempt / delivery_exchange_metric / 审计，
    `executor_kind="builtin_exchange"`，**不跑真实 ETL**）。
  - **Implication**：F6「交换 ETL 打通」不能在 zw-brain 内闭环——真实抽取/转换/装载是 NiFi 驱动的外部
    交换底座（旧 `subscribe_job` / `exchange_executor` / `exchange_pipelines.nifi_group_id` /
    `dc_subscribe_table`，`dsp_pipelines` 50 表）；架构 §3.4-B 既定为集团数据治理中心，**不复造**。
    zw-brain 诚实形态 = 下发订阅意图 + 展示交换状态/对账回执薄壳。
  - **Why deferred**：真实 ETL 在边界外，且须先与数据治理侧确认三类接口契约（订阅下发 / 状态回流 /
    对账数据，立项文档 §四 C1/C2/C3）——zw-brain 单侧无法定义外部底座 API。
  - **Trigger to re-evaluate**：(a) 数据治理侧确认 C1/C2/C3 三契约；(b) 负责人 sign-off（D28 外部依赖 +
    交付状态机门）→ 实现 `exchange_channel_gate` + `resolve_exchange_channel_state` 三态（复用 D50 双门）+
    订阅意图编排 + 回流/对账接入，env 注入外部底座端点真实联调 + 真实回流 e2e → 关债。
  - **现算锚点**：assert=grep_present `services\.delivery\.record_attempt\(payload, "delivery\.exchange\.` ⇒
    薄壳仍在即 open；真实打通后 handler 改走外部交换门 → 失配 → stale-fixed → 关债。

- **B2 字段元数据 10 列（记债，分期）** — debt `b2-field-metadata-10col`（script 现算）：
  - **Where**：`zw_brain/domain/models.py` `ResourceSchemaMappingRecord`（`source_schema_ref` 列 +
    `mapping_rule_json` ≈ 源字段→目标字段映射）。对标旧 `dc_resource_table_column`（18 列，含字段级
    元数据 10 列：字段名 `name_en` / 目录信息项 `catalog_item_id` / 类型 `type` / 长度精度 `length` /
    主键 `is_pk` / 可空 `is_null` / 更新主键 `is_up_id` / 更新时间 `is_up_time` / 数据标准 / 数据字典）。
  - **Implication**：当前挂接只承载源→目标 2 列映射，不承载字段级 10 列元数据（类型/长度精度/主键/
    可空/更新主键/更新时间/数据标准/数据字典）。
  - **Why deferred**：批次 3 的 B2 先补「业务基本信息块」（业务化 label + access/summary）；字段级 10 列
    元数据若全补属 L 上限，**分期到下期**（先业务字段、后字段级元数据）。**不改批次 3 拥有的
    `P5HookupSubmitWizard.vue` / `resource_mount.py`。**
  - **Trigger to re-evaluate**：批次 3 业务基本信息块落地后，下期立项库表字段级元数据 10 列（模型加
    字段级 metadata 承载 + 表单/向导补录 + 对标 `dc_resource_table_column` 10 列）→ 现算列数 ≥10 → 关债。
  - **现算锚点**：assert=script `check_b2_field_metadata_columns.field_metadata_debt_open()` ⇒
    `ResourceSchemaMappingRecord` 承载的字段级元数据列数 < 10 即 open（覆盖 ≥10 列 → stale-fixed）。
  - **[2026-06-12 已关债]** 0611 核查（§四 6.5#5.2）裁决「提前立项」（客户三轮重提=P0 信号），负责人
    确认提前本期（`old/问题反馈/字段级元数据10列-本期立项草案.md`），PR #257 落地：
    方案 A 注册逐列写 `ResourceSchemaSnapshotRecord`（与 legacy 导入同源同形、register: 来源覆盖式
    upsert），10 列写读键单源 `FIELD_METADATA_SNAPSHOT_KEYS` + 键对齐 pytest；现算守卫锚点同步迁到
    实际承载常量块（债 yaml 自述「同义命中即关债」口径，非绕守卫）→ predicate 10/10 stale-fixed，
    债 yaml 按先例移除（守卫脚本保留，受 tests/test_resource_mount.py 引用作回潮守卫）。

- **G4 过期维度（核查 + 记债）** — debt `g4-acceptance-overdue-dimension`（script 现算）：
  - **Where（真库核查结论）**：`zw_brain/domain/models.py` `ApplicationRecord` 字段 =
    id/tenant_id/application_code/status/applicant_name/applicant_org/payload_json/submitted_at/
    created_at/updated_at —— **无受理截止期/超时/有效期字段**。唯一 `due_at` 在 `ApprovalStepRecord`
    （审批步骤级），且**全仓零写入**（无任何 writer，seed_snapshot.json 零 due_at）。旧
    `dc_resource_apply_info` 亦无受理截止期（只有授权后接口使用期限 `use_days` + `apply_time`/`audit_time`
    时间戳，非 pending 受理超时）。
  - **Implication**：G4「受理已过期」维度（`_backlog_todos` 无 expired）**无真实上游截止期数据可算**——
    硬造截止期会虚构 SLA，违 D11（业务数据禁 Mock）/ D22（不静默吞错）。
  - **Why deferred**：依赖 application/resource 受理截止期字段；当前真库无该字段，需上游补供或客户上线接
    真数据。**不改批次 2 拥有的 `workbench_backlog_projection.py`。**
  - **Trigger to re-evaluate**：上游（旧平台/客户）补「受理截止期/办理时限」字段（或 `approval_step.due_at`
    被真实流程写入）→ application/resource 携带截止期 → 据真实截止期算 expired 维度 + workbench 待办过期
    提醒 → 关债。
  - **现算锚点**：assert=script `check_g4_acceptance_deadline.acceptance_deadline_debt_open()` ⇒
    `ApplicationRecord` 无受理截止期字段（`due_at`/`deadline`/`expire`/`valid_until` 任一缺）即 open
    （补字段后 → stale-fixed）。

## 2026-06-04 — 高杠杆三连（DB 复合索引 / CI 接 e2e+测量 / policy deny 审计化）

> 上帝视角审视裁出三条「测量绿掩盖不到」的低成本高杠杆欠账，一个 PR 三 commit 收。

- **DB 复合索引（commit 1，纯收益已落）**：`legacy_object_mapping`(68916 行) 加
  `ix_legacy_object_mapping_batch(tenant_id,canonical_type,canonical_ref)` —— EXPLAIN 实证
  BEFORE 单列 `ix_*_tenant_id` 全扫单租户~68k 行 + temp b-tree → AFTER 三列 SEARCH seek；
  `service_invocation_metric_projection`(18946 行) 加 `ix_service_invocation_metric_list
  (tenant_id,metric_scope,resource_code,time_bucket)` —— 消除 list_metrics 的 USE TEMP
  B-TREE。**诚实剔除** `ix_*_resolve`：EXPLAIN 实证其 5 列等值路径已被 uq autoindex 前缀
  覆盖（加不加计划相同），建之只是冗余写放大。无 alembic，索引随 create_all 在 fresh DB 建。

- **policy deny 审计化（commit 2，发射半已落）**：见下方 `ops-deny-audit` 债条 Status——
  发射在 `_enforce_manifest_policy` 收口，非阻塞，护栏 `tests/test_policy_deny_audit.py`；
  熔断语义 + 业务方 sign-off 仍 open（D28 状态机门，本期不擅改）。

- **CI 接 e2e + 测量（commit 3）**：`.github/workflows/ci.yml` 新增 `e2e-measurement` job——
  真栈(mock 推理 + IAM bypass + committed `seed_snapshot.json`，**不需** 500MB dump)起 :8800，
  跑 `capture_feature_status.py --with-e2e` **限 seed-light 规格**，CI 当**验证者不当提交者**
  （不 commit-back，避免 push 循环）。诚实范围：dump-依赖的 e2e 规格（catalog drilldown /
  ops invocation / national 等）留本地，CI 只覆盖 seed-light 子集，**绝不假绿**——见 ci.yml
  job 注释 allowlist。关 `e2e`/`feature` 两 debt（ci.yml 现含 `with-e2e` + `capture_feature_status`）。

## 2026-06-03 — wave-residuals：补三条 shipped/partial wave 各藏的真产品残差（PR 代码已落，测量重采待 e2e 环境）

> 上帝视角对账发现每个 `shipped`/`partially-shipped` wave 各藏一条已具备地基、卡在最后一截的残差。
> 本 PR（commits A–D）补齐三条**代码 + 单测**；`.feature` un-defer + 测量重采 + 业务 sign-off 收尾见下。

- **Wave 1 — j2-resource-mount（J2-4 trigger 已触发）**：实现 `resource.mount.{table,file}.prepare`
  能力 + `command/handlers/j1/resource_mount.py`（诚实结构校验：mapping_ready 真算、库连通性
  not_probed 不伪造、库口令去敏不入库）+ `P5HookupSubmitWizard.vue`（仅 table/file，砍 api tab，
  债务文档预留名 + route `/provider/wizard/hookup-submit`）+ P2CatalogDetail 物化形式选择尾巴
  （闭合挂数→用数端到端）。**顺带修潜伏 bug**：resource.asset submit_review/review 经 brain shim
  传空 skill_id 致 audit KeyError（直连 ctx 修复）。单测 `tests/test_resource_mount.py`(10)。
  **下方 2026-05-27 J2-4 条 trigger=(a) 已兑现**，该条转本条收口。
- **Wave 2 — 审批引擎执行深度**：`domain/approval_flow_walker.py` 让 committed 自定义 live schema
  真正驱动 J1（always/on_decision 串行，expression 边 deliberately fail-closed——零业务需求，不做
  求值器）+ `ApprovalFlowSchemaRepo.find_live_for_scope` 项目级选择；request.py 优先自定义否则
  **原样回落 baseline（2 baseline 路径零改动，golden 回归钉死）**。单测
  `tests/integration/test_approval_flow_schema_drives_j1.py`(8)。
- **Wave 3 — a2a 线级测试（纯测试债）**：`tests/_iaf_a2a_http.py` + `tests/test_a2a_wire.py`(4) 补
  5 消费面之一零 over-socket 覆盖（discover→invoke / 多轮 audit 链 / trust 裁剪 / 投影一致性）+
  `entry/a2a/server.py` trust 旋钮（`ZW_BRAIN_A2A_CALLER_TRUST_LEVEL`，**部署级 env、非 per-caller
  身份**，诚实标注同 MCP）。**无需业务 sign-off**（协议测试 + 部署旋钮）。

- **收尾（✅ 已做 — 本地全栈 e2e 走查 + 测量重采）**：负责人指示「本地部署把 e2e 走查做了」，遂软链
  主仓 `node_modules`(playwright 1.60)+ 拷主仓 125MB 真库为 seed + `start-local.sh` 起 :8800 全栈
  (dev bypass + mock 推理)，跑 87 e2e：**76 passed / 6 failed / 5 skipped**。6 红逐一查实**全非本 PR 回归**——
  5 个在 main 同库同 spec 复现（依赖 D47 已删演示单如 `REQ-2026-05-25-0002` / 累积库态），1 个(twin)单跑
  14/14 绿属 87 连跑 flake。继而 `capture_feature_status.py --with-e2e`（per-spec 单跑，twin 不 flake）：
  **28 pytest + 3 e2e 全绿，0 fail**。三 `.feature` 去 deferred + 绑 pytest ref（j2-resource-mount→
  test_resource_mount.py / a2a-hardening→test_a2a_wire.py / engine-approval-flow 加 schema-drives ref），
  `gen_feature_status` → **j2-resource-mount + a2a-hardening 翻 InTest，engine-approval-flow 保持 Done**
  （Backlog 6→4）。a2a trust 场景标「部署级旋钮非 per-caller」、场景4/5 trigger-deferred（不抬全 SPEC，D46.f）。
  - **Done gate（D28）剩余**：j2-mount + 审批执行深度 = 流程/状态机决策，仍须业务方 sign-off（scope
    `wave-residuals-j2-mount` / `wave-residuals-approval-depth`）才从 InTest 翻 Done；a2a 测试债不进业务 signoff scope。

- **A2A scenario 4/5 trigger-deferred（新登）**：
  - 场景5 跨租户隔离 → **Trigger**：第二个租户/省接入（同 multi-tenant-policy）。
  - 场景4 anp-schema 必经 AgentRuntime 门控 → **Trigger**：首个外部 Agent 接入（AgentRuntime pilot，D30 T1）。

## 2026-06-02 — 结构性技术债清扫（struct-debt-sweep）：brain.py 死委托清除 + 死层残骸删除 + 三条已修债现算关闭归档 + #4 写侧投影评估后延后

> 承接 #191（读路径单一事实源）/ #192（删演示单 + 凭据诚实化）/ #185（prefilled 停止捏造）之后的纯结构清扫，
> 不引入业务变更、不碰 #185 文件。范围：`zw_brain/command/brain.py` + `zw_brain/skills/data_search/` +
> `.testing/debt/` 账本 hygiene + 本文归档。

- **brain.py 死委托 shim 清除**：`zw_brain/command/brain.py` god-object 从 1422 LOC / 154 def 降到
  1181 LOC / 100 def。删除 **54 个零调用纯委托 shim**（每个仅 `return self._get_handler_deps().services.X.Y(...)`
  或转 domain serializer，真实实现已在 `domain/services/*` + `command/handlers/*`）。判定方法：AST 枚举每个 def，
  跨 `zw_brain/` + `tests/` + `registered/*.json` + dispatch 表 + 字符串字面量（动态 dispatch）grep caller，
  仅删「brain.py 内零内部调用 ∧ 全仓零外部引用 ∧ 非字符串 dispatch 命中」者。首轮删 52；`/xj-review` 复核坐实
  `_diff_fields_for_gap` / `_prefilled_fields_for_resource` 两个 brain shim 本身亦零调用（live 读路径是
  domain-service 的 `application_service.diff_fields_for_gap/.prefilled_fields`，非 brain shim），补删 → 共 54。
  顺带删 `_external_adapter_repo` 唯一持有的 `ExternalAdapterRepository` import（ruff F401 清零）。
  验证：A/B（git stash）确认全部测试失败均为 main 既有的 test-isolation/DB-pollution 失败，本次删除**零新增失败**；
  `import zw_brain.command.brain` OK；`ruff` clean。承接 `.testing/debt/brainservice.debt.yaml` 的 god-class 下沉方向（仍 open）。
- **死层残骸删除（data_search）**：删 `zw_brain/skills/data_search/`（签名错的 legacy 兼容 shim，
  `run()` 内 `_handler(service,"data.search",{...})` 与 canonical `command/handlers/j1/data_search.py` 签名不符）。
  grep 确认零 importer（唯一引用是其自身 `__init__.py`；configs `pyproject packages=["zw_brain"]` 无显式枚举）；
  删后 `zw_brain.skills`（含 live 的 `blockchain_adapter`）+ `background_tasks` import 均 OK。
  `.testing/debt/dead-layer-remnants.debt.yaml` anchor 现算 absent → 整条 debt 关闭（见下「三条债现算关闭」）。
- **空包 agents/ + orchestrator/ 刻意保留**：产品研发负责人决定保留两空包（D3 编排保留命名空间 + docstring），不删。
- **standard.asset.sync.json 保留（监督者裁决：KEEP）**：`registered/standard.asset.sync.json`
  确认**无 dispatch 接线**（不在 `DISPATCH_TABLE` 亦不在 `_PASSTHROUGH_CAPS`）、P0-04 投影过滤已使其不出现于
  openapi/a2a/agent_card/runtime_bindings/mcp。审计把它列为「死注册/死层残骸」属**误判**——它不是死层残骸，而是
  `p0-contract-classification.md` P0-03（line 444）明确裁定的 **`deferred:wave-4` 设计完整性保留契约**
  （「保留 deferred:wave-4 + debt，retire trigger=Wave 4 legacy 退役期统一清理」；P0-04 投影过滤后与物理删除
  **业务效果等价**：UI 不可达 / 5 surface 不投影）。物理删除会反转该现行产品决策、且需改写**本任务所有权之外**
  的生成件 `docs/agent_integration.md`（footer 计数 233→232）。**监督者裁决 KEEP**：归属 P0-03 既有 debt 轨道
  （retire trigger=Wave 4），不在本结构清扫范围；本次仅删确凿死件 data_search。
- **三条债现算关闭并归档（无 code fix，仅验证 + anchor 修正 + 关债 rm）**：
  - `shared-command-reverse-dep`：#5 确认 `capability_provider.py` 的 `from zw_brain.command.brain import BrainService`
    在 `if TYPE_CHECKING:` 下（annotation-only）、`service.py` 改 IoC（`register_brain_provider`）不再 eager import；
    `check_domain_no_command_import.py` 已 `SCAN_DIRS=(domain, shared)` 且 PASS（exit 0）。原 anchor
    `pattern:"from zw_brain\.command"` 误命中 service.py 注释（永久假阳 open），收紧为行首 import 语句锚
    `^from zw_brain\.command` → grep absent → **stale-fixed**。
  - `prefilled-fake-enterprise-data`：#6 确认 PR #185（commit 98853b7）已在 main，`prefilled_fields()` 现返回
    诚实空值（value=""/「请填写」/「待填写」），捏造串「山东云启科技有限公司」仅残于 docstring + 诚实守卫测试；
    全字符串 anchor grep absent → **stale-fixed**；`test_application_prefilled_honesty.py` 4/4 pass。**未碰 #185 文件**。
  - `dead-layer-remnants`：#3 中确凿死件 `skills/data_search/__init__.py` 已删 → anchor 现算 absent。
    该 debt 原覆盖三件（data_search shim + agents/orchestrator 空包 + standard.asset.sync）：data_search 已删、
    agents/orchestrator 刻意保留（D3 reserved）、standard.asset.sync 归 P0-03 deferred:wave-4 轨道——三件均已
    fixed-or-reclassified，故整条 debt 关闭。
- **#4 `approval-case-projection-stale` 评估后刻意不动（保持 open，external）**：read 侧已被 #191 单一事实源消解
  （approvals 现算自 `ApprovalRepository.list_cases`，71 条 legacy hex 审批不再陈旧、现网无可见 bug）；write 侧
  `sync_aggregate_tables` 投影循环重构 blast-radius 大、已立项归 C-1 跟进 PR（见下方 2026-06-02 C-1 条 Trigger）。
  在本结构清扫 PR 内重构 write 侧会与该跟进 PR 撞车、违「避免一次性大 PR」，故**不纳入**；账本保持 open。
- 账本现算结果：`scripts/check_debt_status.py` → **open=31 stale-fixed=0 invalid=0**；`debt-status.md` 已 regen。
  三条已 fixed 的 debt 由监督者按 debt-as-function 终态动作 `git rm <slug>.debt.yaml` **关闭**（散文条目留此处作审计链）。

## 2026-06-02 — C-1「去 snapshot↔DB 双轨」拆 PR：本 PR 收读路径单一事实源，删演示单/凭据诚实化另起

> 上帝视角审视裁出 3 关键缺陷（C-1 双轨割裂 / C-2 锚定重复 / C-3 反向依赖）。本 PR 落地
> **C-2 + C-3 + 数据模型地基（ApprovalCaseRecord.legacy_id/flow_schema）+ 读路径单一事实源**；
> 执行中坐实「删演示单」比计划更纠缠，与产品研发负责人确认**拆 PR**，余下登记于此。

- **本 PR 已落（读路径单一事实源）**：`discovery_snapshot_projection` / `dispute_snapshot_projection`
  三件 enrich 改**无条件以 DB 投影为准**（空库→诚实空，不再「DB 非空才替换/否则保留 seed」的半双轨）；
  `request_service.approval_by_id` / `delivery_service.by_id` 补 DB 回源（真实导入记录不再因不在内存
  快照而读不到）。**read 侧的 `approval-case-projection-stale` 已被单一事实源消解**（approvals 现算自
  `ApprovalRepository.list_cases`，legacy hex 审批不再陈旧）；该账本的 write 侧投影循环重构仍 external 开着。
- **Deferred to follow-up PR（删演示单 + 凭据诚实化 + 写路径收口）**：
  - **删演示单**：`seed_snapshot.json` 的 `REQ-/DLV-/DSP-/PKG-` 业务记录 + workbench todos + 演示
    audit/alerts。**注意**：`demo_state_sync.py` 非纯演示件——`upsert_todo/set_todo_status/resource_by_id/
    zone_by_id` 是工作台/合规承重助手，只有其中**硬编码 REQ-* 的 cascade**（`sync_demo_state_views`）可退役；
    不可整文件删。段 36 `check_no_demo_id_literals` 待删演示单后收紧（届时全仓零 demo id 字面）。
  - **凭据诚实化（✅ 跟进 PR 块A 已落）**：legacy 导入 granted 分支移除 `derive_demo_credential`
    捏造，改写 `credential=None` + `credential_status="not_issued"`（真实授权表
    `data_apply_authrization` **无 per-grant 凭据**，真凭据在 `dsp_service.api_service_app.SECRET`
    网关域、与 apply_id 无绑定供数）；`credential.query`/P4 已就绪诚实显「未签发」；段 66 重定向为
    「granted 分支显式处理凭据态(credential+credential_status) + 禁回潮捏造」。守卫测试
    `tests/test_credential_honesty_legacy_granted.py`。**仍待业务确认**：J1 凭据取网关 SECRET 口径 +
    `apply_id↔service↔app` 绑定供数（上游缺供）= 真凭据接入另一轨。
  - **历史单动作（混合裁决）**：P3/P4 动作入口按「DB 能否解析出完整运行时实体」门控（`legacy_id` 已就绪
    可判），历史导入单标「仅存档」、隐藏撤回/暂停/凭据动作（无权/不适用=不可见）。承接
    `j1-legacy-record-actionability`（2026-06-01）裁决落地。
  - **真数据基线**：删演示单后绿门禁需切「fresh DB import 缩小版真 dump 子集」+ 迁移依赖演示单的测试
    （`test_discovery_snapshot_projection` 等已先行改「空库→诚实空」）+ `capture --with-e2e` 重采。
- **Why split**：读路径单一事实源是干净可合闭环；删演示单触及真库重建 + 大面积测试迁移 + e2e 重采，
  blast-radius 大，单独成 PR 易 review/回滚（符合「避免一次性大 PR」）。
- **Trigger**：跟进 PR 立项 —— 按上述四点落地，关 `approval-case-projection-stale` write 侧 +
  `prefilled-fake-enterprise-data` + `j1-legacy-record-actionability` + `p3requestdetail`。

## 2026-06-02 — P0/P1 收尾 PR 判定不通宵改的 P2（记债不静默）

> 本批 P0(MCP/CLI prod 护栏) + P1(governance 下推 / grant 守卫 / 冷启动锁) 修复见
> `docs/acceptance/p0p1-remediation-walkthrough.md`。下列项经判定**通宵改不安全或属 #185**，
> 不纳入本 PR，机械账本见 `.testing/debt/*.debt.yaml`（现算 open/stale-fixed）：

- **prefilled 假企业数据**（`application_service.py` ~:312）：归 **PR #185（OPEN，验收中）**，标题即
  「prefilled 停止捏造企业数据」、diff 含该文件 + test_application_prefilled_honesty.py。本 PR 铁律
  不碰 #185 文件，仅记债交叉指向。账本 `prefilled-fake-enterprise-data`（grep "山东云启科技有限公司"，
  #185 合并移除即转 stale-fixed）。
- **approval_case 投影对 71 条 legacy hex 记录陈旧**：legacy 导入的 approval_case 从不进
  `sync_aggregate_tables` 的 snapshot 投影循环 → 投影态可陈旧；用户侧 status 读 application_record
  故被掩盖（现网无可见 bug）。结构性重构 blast-radius 大，通宵不安全。账本
  `approval-case-projection-stale`（external，无单一稳定 grep 锚）。
- **shared→command 反向层依赖**（`shared/agent_runtime/service.py:8` + `capability_provider.py:8`
  eager import command）：违反 entry→command→domain→shared；preflight 段 49 只扫 `domain/` 不扫
  `shared/` 故未捕获。**未顺带加 shared 扫描守卫**——直接扩会立刻红（这两处即违例），需先给
  agent_runtime 加白名单（=把 prose 例外写进 config，未消债只静音），故记债跟踪、触发时一并解耦 + 扩守卫。
  账本 `shared-command-reverse-dep`（grep "from zw_brain.command"）。
- **brain.py god-object debt 计数陈旧**：原写 3462 LOC / ~192 方法，**已更正为 1425 LOC / 152 方法**
  （见下方 2026-05-26 条目 Where/Implication）。
- **死层残骸**：`skills/data_search/__init__.py` 死且签名错的 shim（run() 调 _handler 签名不一致）+
  空 `agents/` + 空 `orchestrator/` 占位包。不通宵删保持 PR 聚焦（删前须 grep configs，见 MEMORY
  「Delete-file grep must include configs」）。账本 `dead-layer-remnants`（grep "BrainService"）。

## 2026-06-01 — H2 区块链锚定 worker 部署形态：单副本 in-process（选 A，多副本前再评估）

> 产品研发负责人 2026-06-01 **选 A**（维持现状，本期无代码动作）。本条登记 PR #183 §5 的待决策。
>
> **✅ 2026-06-02 部分解决（C-2，本 PR）**：原「无行锁 → 多副本重复 anchor」的**急性风险已闭合**——
> drain 前对每行做**原子认领**（`DatabaseStore.claim_anchor_outbox`：`UPDATE anchor_outbox SET
> claimed_at=now WHERE content_hash=? AND delivered=0 AND (claimed_at IS NULL OR claimed_at<=stale)`，
> 仅 `rowcount==1` 才调 adapter）。SQLite 串行写下原子、Postgres 经 WHERE guard 等效，多副本不再双发；
> 失败的 anchor 留租约过期可重认领（`_ANCHOR_CLAIM_LEASE_SECONDS=300`，新增 `claimed_at` 列 + 列级模型
> 改动属 drop&recreate）。守卫测试见 `tests/test_h2_anchor_worker.py::test_claim_is_atomic_and_prevents_double_anchor`
> / `::test_stale_lease_is_reclaimable`。**剩余**=若「真链 + 多副本」仍想要更强的 leader 选举/独立
> worker 进程（PR #183 §5 的 B+C），按下方 trigger 评估；但重复链上交易这一核心危害已由认领消除。

- **Where**: `zw_brain/background_tasks/__init__.py`（`AnchorWorker` + `start_anchor_worker` / `stop_anchor_worker`）；
  `zw_brain/entry/rest/server.py::main()` 拉起 + finally 停；env `ZW_BRAIN_ANCHOR_WORKER` 门控、pytest 默认关。
  来源 = PR #183（H2 锚定回路根治）§5 待决策。
- **Implication**: in-process daemon 线程与 REST 进程同生命周期，drain 持久 `anchor_outbox` 表 → `audit_receipt`。
  **当前单副本（sd-default 单租户单省）+ mock `blockchain_adapter` 下安全、无重复**。多副本部署时每个副本各跑一个
  worker，共享同一张 `anchor_outbox` 表且**无行锁 / SELECT FOR UPDATE / leader 选举** → 同一 pending 行可能被两副本
  各 drain 一次 = 重复 anchor（mock adapter 幂等无害；真实链 = 重复链上交易 / 回执）。
- **Why deferred**: 当前部署单副本、adapter 为 mock，下方两触发条件均不成立；默认**可逆**（删 `start_anchor_worker()`
  调用或 `ZW_BRAIN_ANCHOR_WORKER=0` 即退回原状），晚定无沉没成本。独立 worker 进程 / 行级锁去重会增运维与工程面，
  未到拐点不提前盖楼（确定性自动化运营和运维：只为真实需求建复杂度）。
- **Trigger to re-evaluate**（**两条件同时成立**即升级 P0）:
  - (a) `blockchain_adapter` 从 mock 换成真实链；**且**
  - (b) REST 服务部署为多副本 / 非 sticky LB。
  - 任一单独不触发；二者齐 → 落地 `anchor_outbox` 行级锁（`SELECT ... FOR UPDATE SKIP LOCKED`）或拆**独立 worker
    进程 + leader 选举**（PR #183 §5 作者建议的 B+C 组合）。与「BFF session Redis backend」「dev-iam-bypass 生产守卫」
    「真数据进 CI」同属「多副本 / 首客上线前」批次，可一并评估。
- **No mechanical guardrail (now)**: 「真链 + 多副本」是运行时部署拓扑，无法在 commit 时机械检测；
  本 debt + PR #183 §5 登记防遗忘，trigger 触发当日按上述正解落地。

## 2026-06-01 — webui e2e 本机 --with-e2e 不能干净复现（2 超时 + 1 真断言失败）

- **✅ RESOLVED 2026-06-01（fix/webui-done-ci-status-loop）**：根因坐实为 e2e harness 盲等
  （`helpers.setRole/gotoHash` 用 `waitForTimeout` + 同 hash 重导航 no-op）+ 2 处 stale/race
  断言，**非「无权限可见」安全回归**（P5DemandMatchDetail v-if 正确门控）。修 helpers 去盲等
  （同 hash bounce 经哨兵 hash 强制 remount）+ P2 改钻取断言 / P7 改持久态断言，2 大 spec
  从 >600s → checklist 45.9s、twin 24.1s；permission 连跑 3× 全稳。干净真库重採 --with-e2e
  全绿 → 3 webui feature 现算 Ready→Done。原始症状记录留作审计链：
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

## 2026-05-31 — topic.package.query 列表跑详情级投影，87 包 ~1.4s（P7 性能）— **已 CLOSED 2026-06-03（readpath-perf-scan PR / M4）**

> **Closed**: M4 把 `list_projection` 改为从轻量子 helper（`_catalog_projection_status` + `_list_contract`）直接组装列表契约 dict，不再走 `... | self.projection_summary(...)` 字面量；`projection_summary` 保留给 `detail_to_dict`（重写为先建 base 再 union，字面量整体消失）。输出逐字节不变（LIST_PROJECTION_KEYS / activeCatalogCount / hiddenCatalogCount / 4 个 projectionFailureReasons 分支全保）。`.testing/debt/topic-package-query.debt.yaml` 已 `git rm`、debt-status open 计数 -1。本散文条目留作段-34 wave 反向链接锚（不删）。注：早前 045dad1 已把 `catalog_projection_items` 的 per-item `list_assets` 全表扫提到循环外（N→1），M4 是其后续的「list 不再跑详情级 projection_summary」结构收口。

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

- **✅ RESOLVED 2026-06-01（fix/webui-done-ci-status-loop，machine debt .debt.yaml 已删）**：三 trigger
  齐活 → ① M0 seed 一致性：legacy 迁移 granted 分支补签 demo 凭据（granted ⟹ credential，
  根治 P4 422，并由段66 `check_credential_grant_invariant` 机械化）；② P2 改真目录钻取断言、
  P7 改持久「已订阅」态断言（去硬编码值，保留行为）；③ 干净真库重採 `--with-e2e` 全绿 →
  现算自动 Ready→Done。原始 3 ✘ 根因留作审计链：
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
  在线编制 / API 服务化等入口，但**为已发布目录补挂 table/file 物化资源**没有入口，
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

- **Where**: `zw_brain/command/brain.py`（**1425 LOC**，截至 2026-06-02 复核）拆分后 185 cap
  dispatcher 全迁出至 `dispatch.py` + `handlers/{j1,j2,b1,infra}/`，但 `BrainService` 类本身仍持有
  **152 方法**，其中绝大多数是 `_*_record_to_dict` / `_*_projection` / `_topic_*` / `_governance_*` /
  `_delivery_*` 读路径映射 + 投影 helper（语义上属 projection / repository 层，非编排层）。
- **Implication**: §10.2 已 re-scope —— AC1 真实意图「dispatch 不臃肿」由 `dispatch.py` 360 LOC +
  brain.py 内 0 case dispatcher 达成，brain.py 不再卡 LOC 上限。但 152 方法 god-class 仍是真实债：
  多 worker 若同时改读路径投影方法仍会在此文件 merge 撞车；类体过大降低可读性。
- **Why deferred**: 当前无活跃功能需要这些方法搬家；把读路径方法盲搬到 projection/domain
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

## 2026-05-25 — 推理客户端真实网关验证（已由 D68 关闭）

- **Status**: D68 后 zw-brain 进程内推理客户端已退役，模型调用不再属于 zw-brain REST 运行时。
- **Current boundary**: 模型网关凭据与默认模型只在独立 AgentRuntime 服务侧配置；zw-brain 仅经 HTTP 驱动 AR 并消费任务结果。
- **Trigger to re-evaluate**: 需要验证真实模型质量 / 延迟 / 配额时，在独立 AgentRuntime 服务侧跑真实网关链路验收；preflight 段 10/78 继续守住 zw-brain 禁直连模型与禁持有推理 env。

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
  `form_schema.*` 4 + `recommendation.*` 2；总 manifest <!-- stat:zwbrain.manifest-total -->246<!-- /stat -->）。`config_change_class` preview/draft
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
  4. **运行时 fail-closed**（2026-06-01 C1-hardening 落地）：
     `shared/runtime_config.get_dev_iam_bypass_enabled()` 在
     `ZW_BRAIN_DEPLOY_MODE in {prod,production}` 且 bypass env 在场时抛
     `DevBypassInProductionError`（不再 fail-open 静默放行）。REST `main()` /
     A2A `serve_http()` 在启动期捕获该异常并拒绝启动（SystemExit / exit 2），
     即「两 env 漏进生产」从「全角色鉴权全开」收敛为「进程拒绝启动」。
     复用既有 `ZW_BRAIN_DEPLOY_MODE` 信号（与 `validate_session_store_for_deploy`
     同源），**未新造 prod 标记**。守卫 `tests/test_c1n1_shared_resolver_and_guards.py`。
  这四条层叠兜底；不再加 prose 软提醒。
- **Status update (2026-06-01)**: 「prod guard deferred to first customer deployment」中
  **「启动期 fail-closed」这一最危险面已落地**（上述第 4 条）；**剩余 debt** = 删除 bypass
  代码层路径本体（`start-local.sh`/`customer_demo_5min.sh`/e2e 仍依赖），仍延后至首位真实
  客户上线。即本护栏把「泄漏即鉴权全开」降级为「泄漏即拒绝启动」，债部分收口、未全清。
  待决策：`ZW_BRAIN_DEPLOY_MODE in {prod,production}` 作为 prod 信号是否为团队约定的
  权威 prod 标记（当前与 session-store deploy guard 共用，本 PR 复用而非新造）— 请产品研发
  负责人 / 运维确认。

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

## 2026-06-03 — national-platform-access HONESTLY-PENDING（D50 / C7；国家平台外部依赖）

> 国家通道两条子旅程（national-direct 转报 / national-ext-elements 编制）工程已落地（C1-C6，
> flag 默认 off、per-tenant 启用）。国家平台是**外部依赖**，本期无真实端点/凭据可联调——以下
> 为诚实上限，绝不伪造回流（承 D50 §四 + D11 桩≠业务 mock）。两条 feature 现态 = **InTest**
> （有测试∧未签），等产品研发负责人本地真 UI 走查后签字转 Done。

- **Where**: `zw_brain/shared/national/`（client/gate）、`zw_brain/command/handlers/{infra/national_channel_gate,j1/escalate,j2/national_ext_elem}.py`、
  `zw_brain/capability_registry/registered/{adapter.national.*,catalog.national_ext_elem.compile,application.escalate_national}.json`。
- **Implication / 诚实上限**:
  1. **无真实国家端点可联调** → 已配置（provisioned）时对外只记意图 + 「待国家平台回执」；
     真实回流（A_7001 转报中 → 6 已授权 / 3 驳回）与回执对账**本期无法验证**，绝不伪造。
  2. **凭据基数/生命周期 + sid↔接口 NAME 映射** = 客户上线时由国家平台下发配置
     （接口规范 v0.55 附录C：rid/appkey/appsecret/每接口 sid/接口 NAME），本期 `not_issued`、不捏造。
  3. **flag-off→入口不渲染** 面由单测覆盖（`tests/test_national_channel_webui_snapshot.py` 三态 +
     `tests/test_page_access.py` 路由角色门）；真实 UI e2e（`tests/e2e/national_channel.spec.ts`）
     跑的是 **flag-on 角色门面**（BUSIAUDIT 可见 / OPERATER toHaveCount(0) / 未配置发布置灰），不假装跑了 flag-off。
- **签字账本本轮未落**: `.testing/signoff/` schema 禁空签（signed_by 必填非空），故本轮**不落** national-platform-access
  签字账本——待产品研发负责人**本地真 WebUI 走查**后按 D35/D37 模板签字（覆盖两条 feature）。
  工程证据已落 `.testing/acceptance/national-platform-access/evidence.json`（真实 UI e2e 3 passed + 后端单测真绿）。
- **测量未全量重采（D46.f e2e 环境债）**: worktree 薄 seed 下全量 `capture_feature_status.py --with-e2e`
  会让大量 real-data 单测/e2e 假失败（非本任务回归），故未 bulk 重采 shared 测量产物；national e2e
  已在本机 flag-on 全栈**真跑真绿**（证据见 evidence.json）。两条 feature 经 refs 现算为 InTest，不依赖该测量。
- **10 adapter standalone live 注册=future external-bridge 工作**（C8 修订 2026-06-03）: 国家出站已
  收口到 `escalate(j1)`/`compile(j2)` handler 经 `national_channel_gate` + `NationalDirectClient`，
  10 个 `adapter.national.*` 保持 `deferred:wave-3` scaffolding（仍在 `_PASSTHROUGH_CAPS`，
  `require_surface()` 拒非 live、不可外呼、无害）。把它们注册为 standalone live 需 binding
  `external_capability`（§1.3 禁 `adapter.national.* live && builtin`），但 external_capability 是严格
  契约（`compatibility==[]`/非 surface/`callback_only`/`failure_callback`/external_execution），10 adapter
  不满足 → 误配破 `test_contract_projection` 契约投影守卫（C4 曾误配致 CI 红，C8 回退）。standalone
  external-bridge 注册留作 future（届时让 10 adapter 满足 external_capability 契约或新增 bridge binding 类型）。
- **Why deferred**: 国家平台端点/凭据是客户上线期外部输入，非本期可控；伪造回流违背 D50 诚实脊柱。
- **Trigger to re-evaluate**: (a) 客户上线下发真实接入凭据 → 配 env 后 provisioned 真实联调，验回流对账 +
  补真实回流 e2e；(b) 产品研发负责人真 UI 走查通过 → 落 `.testing/signoff/national-platform-access.signoff.yaml`
  + docs/acceptance 效果验收包，两条 feature 转 Done。

## 2026-06-04 — C9 国家通道「待转报队列」取数口径（national-direct；HONESTLY-PARTIAL）

> 负责人本地真 UI 走查发现 P3「国家通道」pane 原列的是用户自己在途申请（own-items）→
> 业务运营员自己 items 通常空、转报入口点不到单。C9 修取数口径：待转报队列 = 请求
> 国家级数据(channel_class=='national')且本级审核通过(dept_approved)的申请，不是 own-items。

- **Where**: `zw_brain/domain/workbench_backlog_projection.py`(`backlog-national-escalate` 工作台行内待办)、
  `zw_brain/domain/discovery_snapshot_projection.py`(`_record_to_request_card` 透 `channelClass`)、
  `zw_brain/domain/services/application_service.py`(`record_to_request` 同透，详情页一致)、
  `scripts/seed_national_escalate_fixture.py`(e2e 造数)。
- **最终口径**: `application_record` ∩ `payload_json.channel_class==='national'` ∩ `status==='dept_approved'`。
  该口径投到业务运营员工作台「国家通道待转报」行内待办；点击调用 `application.escalate_national`，
  未配置国家通道时只显示诚实 pending 回执，不污染主状态机。
- **诚实上限 / 残留缺口**:
  1. **national 信号来源**: `channel_class` 存于 `application_record.payload_json["channel_class"]`
     （supply_demand §scenario 5 占位口径）。真实旧平台导入的 apply 记录**当前无该字段**
     （legacy 无「请求国家级数据」标记位）→ 真库里 national 待转报单基数 = 0，待上游补「国家级
     数据请求」语义标记或客户上线据真实流程产生。本期 e2e 经 seed 注入确定性样例验证链路可点通。
  2. **dept_approved↔channel=national 组合无法经 in-memory request API 造出**（`_create_request`
     写内存快照非 DB；`dept_approve` 要 DB 记录在 submitted→dept_approved）→ e2e 直接 upsert DB
     apply 记录（`scripts/seed_national_escalate_fixture.py`），honest 造数、非业务 mock。
  3. 转报动作沿用 C6 `application.escalate_national`：未配置(provisioned=false)下诚实 pending
     「国家通道转报中」计算态 overlay，不污染主 status、不伪造回流（承 D50）。
- **No mechanical check**: 「上游补 national 标记」属外部数据语义，非本期可机械门禁；e2e 经 seed
  覆盖前端取数口径正确性即可，真实基数缺口由 trigger 触发。
- **Trigger to re-evaluate**: 上游（旧平台/客户）补「请求国家级数据」标记位，或国家平台上线后据真实
  转报流程产生 channel_class=national 申请 → 去 seed、真库直接出待转报单。

## 2026-06-13 — WebUI 渲染债务分诊：borderline 真需求转债

> 来源 = chore/webui-capability-render-triage（全文 `docs/webui-capability-render-triage.md`）。
> 81 个「契约声称大堂供应、实际没渲染」能力逐个分诊后，2 个 NL 可达留台账、79 个诚实降级
> （manifest `compatibility` 去 `webui`，能力+seed 保留、仍 live 在 REST/CLI/MCP/A2A）。
> 「接大堂」本批 = 0：IA 已 freeze ≤10 页（D1/D8），无用户刚需面板缺位。以下 borderline
> 能力**已降级（去 webui）**，但其用户侧需求若业务确认刚需，可另立项接面板复活——**复活前
> 不预先占 IA 页位**，须走 product-dev 原型→审批，并把 manifest `compatibility` 补回 `webui`、
> 接真实面板后从渲染台账除名。

- **订阅/交付生命周期用户侧中断面**（`delivery.replace_or_cancel` / `subscription.terminate`
  / `delivery.subscription.manage`）：撤回引发的替代-取消、订阅显式终止、持续订阅管理。
  当前由后端编排触发（D56 写路径单源），无独立用户面板。
  - **立项指针**：若 P4 交付域要给申请人/订阅方「自助中断/续订」用户面，立项接入 P4Delivery
    子面板（非新顶级页）；当前 deliberately 不接，交付中断以后端编排 + 通知为准。
- **目录条目撤回用户侧治理面**（`catalog.entry.withdraw`）：目录撤回治理动作当前由编目管理
  流程承接，未独立成面板。
  - **立项指针**：若 J2 编目管理要给部门管理员「条目撤回」显式操作面，立项接入 P5CatalogManageList
    行内操作（受 policy 角色门控）；当前 deliberately 不接。
- **服务评价面**（`service.rating.submit`）：交付完成后的可选服务评价环节，当前未接面板。
  - **立项指针**：若产品要闭环「交付满意度」，立项接入 P4 交付完成后评价入口；当前 deliberately 不接。
- **No mechanical check**：本条是「方向延后 + 立项指针」，非可 grep 的代码债——不建 `.debt.yaml`
  assert（避免 §77 过度机械化误报）。渲染缺位本身由段 52 守卫覆盖（去 webui 后已退出 live+webui 集合）。
- **Trigger to re-evaluate**：业务方确认上述任一为用户刚需 → 走 product-dev 立项，补 manifest
  `webui` + 接面板，渲染台账据实更新。
