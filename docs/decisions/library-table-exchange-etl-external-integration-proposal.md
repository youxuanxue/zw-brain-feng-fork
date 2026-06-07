---
title: 库表交换 ETL 打通（下发订阅意图 + 交换状态/对账回执薄壳，真实 ETL 外部底座）— 立项方案（待立项）
scope: library-table-exchange-etl-external-integration
status: proposed  # 外部依赖立项门：需产品研发负责人 sign-off（D28）+ 数据治理侧接口契约确认 才进 D-编号；本文是方案，不是已实现
date: 2026-06-06
deciders: 海若产品部产品研发负责人（GATE 决策门）+ 集团数据治理侧（接口契约确认）
authors:
  - Claude Opus 4.8 (1M context) — 乔布斯式产品专家 + 高级软件研发工程师
related_docs:
  - docs/approved/zw-brain-architecture.md                          # §3.4 外部依赖证明（dsp_pipelines 50 表=集团数据治理中心，不复造）
  - docs/decisions/national-platform-access-D50.md                 # D50：另一处「外部出站」实例（清单门 + 运行门 双门范式，本方案复用）
  - docs/decisions/runtime-capability-registration-bridge-proposal.md  # 通用外部执行桥（外部能力运行时接入的姊妹方案）
related_code:
  - zw_brain/command/handlers/j1/delivery.py                        # delivery.exchange.{plan,publish,start,stop} 入口（当前空桩）
  - zw_brain/domain/services/delivery_service.py                    # record_attempt（仅记意图/状态，不跑真实 ETL）
  - zw_brain/command/handlers/b1/exchange_statistics_query.py       # 交换统计查询（消费回流后的状态/对账）
related_debt:
  - .testing/debt/f6-library-table-exchange-etl.debt.yaml           # 本方案对应记债条目
related_legacy:
  - old/12-datastructure/dsp_pipelines.xml                          # subscribe_job / exchange_executor / exchange_pipelines / exchange_pipelines_subscribe（NiFi 驱动的真实 ETL 底座）
  - old/12-datastructure/dsp_connect.xml                            # dc_subscribe_table（库表订阅明细：增量/批次/字段映射）
---

# 库表交换 ETL 打通 — 立项方案

> 阶段：**纯方案（设计 + 立项请求）**，零业务代码改动。回答反馈 F6（6.5#9 P0）——库表资源的
> 「交换 ETL」**真能在 zw-brain 内闭环吗**。
> 结论：**真实 ETL 执行不在 zw-brain 内闭环**（架构 §3.4 既定边界，非排期问题）；zw-brain 侧的诚实
> 形态 = 「下发订阅意图 + 展示交换状态/对账回执」**薄壳**，真实抽取/转换/装载依赖**外部交换底座**，
> 须先与集团数据治理侧确认三类接口契约 + 过负责人 sign-off 才打通。

## 一 · 代码事实（当前 `delivery.exchange.*` 是什么）

1. **`delivery.exchange.{plan,publish,start,stop}` 是状态记录壳，不是 ETL 执行器。** 四个 handler
   （`zw_brain/command/handlers/j1/delivery.py`）全部委托 `deps.services.delivery.record_attempt(...)`，
   只把一次交换"尝试"以状态（`planned`/`published`/`running`/`stopped`）写进 `delivery_attempt` /
   `delivery_exchange_metric` / 审计 feed（`delivery_service.py:134` `record_attempt`，`executor_kind=
   "builtin_exchange"`）。**它不连接任何真实抽取引擎、不读源库、不写目标前置库。**
2. **真实 ETL 底座在旧平台是 NiFi 驱动、独立 50 表。** `old/12-datastructure/dsp_pipelines.xml`
   的 `subscribe_job`（库表交换任务，29 列：`job_type` 一次性/周期性、`exchange_type` 转发/点对点、
   `apply_id`↔`resource_id`）/ `exchange_executor`（执行器→`executor_pipeline_id` 交换通道）/
   `exchange_pipelines`（通道，带 `nifi_group_id` = NiFi 数据交换通道 GROUP ID）/ `exchange_pipelines_
   subscribe`（订阅任务通道下发表）/ `dc_subscribe_table`（库表订阅明细：`subscribe_mode` 全量/时间戳/
   批次增量、`timestamp_column_name`、`column_mapping` 字段映射、`clean_target` 清空目标表）—— 这是一套
   **NiFi 流程编排 + 前置库同步**的真实 ETL，与质量评分（`dsp_perform` 16 表）合计 71+ 表。
3. **架构早已把它划在 zw-brain 边界外。** `docs/approved/zw-brain-architecture.md` §3.4-B 明确：
   `dsp_pipelines` 50 + `dsp_perform` 16 + `dsp_metaresource` 5 = 71+ 表 = **集团数据治理中心，不复造**；
   §3.1 表「`dsp_pipelines` | 50 | ETL 任务编排 | 外部数据治理范围」。数据清洗/质量/血缘**不是本平台能力**
   （§3.4-A「集团数据治理中心」行）。

→ 所以「在 zw-brain 内自己跑库表 ETL」会复造 71+ 表的外部底座、违背 §3.4。F6 的诚实交付 = 把
  zw-brain 定位为**订阅意图的下发方 + 交换状态/对账回执的展示方**，真实 ETL 留在外部交换底座。

## 二 · 关键边界：意图下发 vs ETL 执行，归属根本不同

- **意图下发 + 状态展示 = zw-brain 内部职责。** 「这个申请要订阅哪个资源、全量还是增量、目标前置库
  是谁、字段怎么映射」是业务语义，zw-brain 已有 `delivery_task` / `delivery_subscription` /
  `delivery_attempt` / `delivery_exchange_metric` 实体承接。**本方案在这一侧把薄壳做实**（订阅意图结构
  化下发 + 回流状态/对账回执诚实展示），不伪造执行结果。
- **真实 ETL（抽取/转换/装载/NiFi 通道编排）= 外部交换底座职责。** 执行逻辑、源库连接、增量水位、
  前置库装载全在外部；zw-brain 不该、也不能用一个 handler 复刻 NiFi。**本方案只解决"如何把意图交给
  外部底座、如何把外部底座的状态/对账回执接回来诚实展示"，不解决 ETL 执行本身。**

## 三 · 目标架构（薄壳 + 双门，复用 D50 范式）

zw-brain 侧只做两件事，**两件都不执行 ETL**：

### 3.1 下发订阅意图（出站，结构化交给外部底座）
- `delivery.exchange.plan` 从"记状态"升级为"**编排一条订阅意图报文**"：把 `subscribe_job` 等价语义
  （资源/申请绑定、`job_type` 一次性/周期性、`exchange_type`、目标前置库 `database_id`、`column_mapping`
  字段映射）组装成与外部交换底座约定的**订阅下发契约**，经统一外部出站门（同 D50 `national_channel_gate`
  范式的 `exchange_channel_gate`）交给外部底座，**不在本地执行**。
- 凭据/端点**不捏造**：未配置外部交换底座时诚实 `pending`（承 D50「未配置即诚实 pending 非 404」、
  D47「凭据 not_issued 不捏造」），不伪造"交换成功"。

### 3.2 展示交换状态 / 对账回执（入站，接回外部底座的事实）
- 外部底座回流交换状态（运行中/完成/失败 + 提供数量/接收数量/数量差异，对标 `account_statistics` /
  `statisc_exchange_*`）→ zw-brain 经 `delivery.receipt.ingest`（已存在）落 `delivery_receipt` +
  `delivery_exchange_metric`，B1 `exchange.statistics.query` / `ops_exchange` 面板诚实展示。
- 对账回执（`delivery.reconcile-receipt`，已存在）核对本地链路事实与外部回执一致性，**不一致即诚实报差**，
  不静默吞错（守 D22）。

### 3.3 双正交门（复用 D50 清单门 + 运行门）
- **清单门**：库表交换出站收口到 `delivery.exchange.*` 经 `exchange_channel_gate` + 外部交换客户端，
  不散落进 §9.5 adapter 写禁区（守段 25），不新增写库 token 到非 adapter 层。
- **运行门**：`resolve_exchange_channel_state` 三态（env 注入外部底座端点/凭据；flag 默认 off；未配置即
  诚实 pending）。默认 off → 未签未配租户「本期不实施」仍成立。

## 四 · 须与数据治理侧确认的接口契约（立项前置）

| # | 契约 | 方向 | 内容（对标旧表语义） | 阻塞点 |
|---|---|---|---|---|
| C1 | **订阅下发契约** | zw-brain → 外部底座 | 资源/申请绑定（`apply_id`/`resource_id`）、`job_type`（一次性/周期）、`exchange_type`（转发/点对点）、目标前置库标识（`database_id`）、增量口径（`subscribe_mode` 全量/时间戳/批次 + `timestamp_column_name`）、字段映射（`column_mapping`）、是否清空目标表（`clean_target`） | 外部底座是否暴露"接收订阅意图"的入站 API？报文 schema？幂等键？ |
| C2 | **状态回流契约** | 外部底座 → zw-brain | 交换运行态（草稿/待启动/已启动/已停止，对标 `subscribe_job.job_status`）、提供数量/接收数量/数量差异（对标 `account_statistics`）、失败原因 | 回流是推（webhook/MQ）还是拉（轮询 API）？回流频率？鉴权？ |
| C3 | **对账数据契约** | 外部底座 → zw-brain | 交换批次对账明细（统计日汇总 `statisc_exchange_daily` / 汇总 `statisc_exchange_summary` 等价）、对账回执号、对账时点 | 对账粒度（批次/日/任务）？对账口径以哪侧为准？差异如何裁决？ |

**三条契约任一未确认 → F6 真实打通不能开工**（zw-brain 单侧无法定义外部底座的 API 形态）。本期仅把
薄壳做诚实、记债、走立项。

## 五 · 与现状/其它决策的关系（不是从零造）

- **D50 国家通道**是同构的"外部出站 + 双门"先例：F6 复用其 `*_channel_gate` + `resolve_*_channel_state`
  三态 + 默认 off + 诚实 pending 范式，**不新发明**机制。
- **通用外部执行桥方案**（`runtime-capability-registration-bridge-proposal.md`）是更上位的外部能力运行时
  接入框架；F6 的订阅下发可作为其一个具体 binding，但 F6 可独立先行（双门已足够）。
- **§3.4 外部依赖**是本方案的边界依据：真实 ETL = 集团数据治理中心，zw-brain 不复造。

## 六 · 分期建议

1. **本期（已落 = 本 PR）**：记债（`f6-library-table-exchange-etl`）+ 立项文档；薄壳保持诚实（不伪造
   交换成功），不复造 ETL。
2. **下期（契约确认后）**：C1/C2/C3 三契约与数据治理侧确认 → 实现 `exchange_channel_gate` +
   `resolve_exchange_channel_state` + 订阅意图编排 + 回流/对账接入；真实联调走 env 注入外部底座端点。
3. **打通后**：补真实回流 e2e、对账差异诚实展示，过负责人真 UI 走查 + sign-off → 翻 Done。

## 七 · 立项门（D28 + 外部契约门）

本方案触及**外部依赖 + 交付状态机**，须：
1. 产品研发负责人 sign-off（D28 GATE），且
2. 集团数据治理侧确认 §四 C1/C2/C3 三类接口契约，

两者齐备才进 D-编号、才开工真实打通。**本文是 proposal，非签字包**：status=proposed，未落
`.testing/signoff/`，不得当已立项/已验收。
