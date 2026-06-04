---
title: 国家数据平台接入方案（数据直达 — 国家通道立项启用 / 反转基线 §10.4）
scope: national-platform-access
status: approved  # 架构门 + 流程/状态机门：反转 §10.4「本期不实施」立项启用，产品研发负责人 sign-off 2026-06-04（D28 GATE，账本 .testing/signoff/national-platform-access.signoff.yaml）
date: 2026-06-03
deciders: 海若产品部产品研发负责人（GATE 决策门）
authors:
  - Claude Opus 4.8 (1M context) — 乔布斯式产品专家 + 高级系统架构师（worktree 设计与实现）
related_docs:
  - docs/approved/zw-brain-architecture.md   # §3.2/§3.3/§3.4 数据直达·强状态·外部依赖；§5.6 #8-9；§10.4 Wave 3
  - docs/decisions/c1-demo-removal-credential-honesty 账本(D47)  # 凭据诚实化先例
  - docs/decisions/data-model-referential-integrity-design.md   # D48 参照完整性
  - docs/preflight-debt.md
related_specs:
  - .testing/waves/wave-3-protocol-tenant-national/features/national-direct.feature
  - .testing/waves/wave-3-protocol-tenant-national/features/national-ext-elements.feature
ground_truth:
  - old/2024-06-28全国一体化政务数据共享数据直达接口规范v0.55.docx   # 协议权威源
  - old/12-datastructure/dsp_connect.xml      # 数据直达库真实 schema
  - old/12-datastructure/dsp_catalog.xml      # 目录库真实 schema（基本/扩展要素）
  - old/20260519/目录管理-国家目录治理/        # 27 页真实业务流程
---

# 国家数据平台接入方案（数据直达）

> 研发阶段：**设计 + 实现（一个大 PR / 多 commit）**，停在 `[人工审批]` 门禁前。两条子旅程
> （national-direct / national-ext-elements）在基线 §10.4 / §5.6 #8-9 被刻意延后
> （"本期不实施，flag 默认 off"，P2）。本方案**立项启用**它们 —— 反转一条 approved 基线决策，
> 属 **D28 GATE（流程/状态机）**，须产品研发负责人 sign-off 才进 D-编号、才由 InTest 转 Done。
> flag 默认 **off**：未签字、未配置接入凭据的租户，"本期不实施"依然成立。

## 〇·乔布斯审视与收敛（聚焦 / 简洁 / 端到端 / 设计即工作方式 / 精品意识）

工程上"接国家平台"很容易长成一坨协议适配器。按五原则收敛成一个产品判断：

1. **聚焦** —— 国家通道是 **业务运营员（ROLE_BUSIAUDIT）的独立子旅程**，不是给所有人的功能。
   业务原话"用得最少"（§3.2：数据直达 36 页但低频）。普通申请人**永不被国家通道复杂度绑架**：
   主链路（本省内共享 J1）心智零污染，国家通道待办**单独列出**，一票否决式独立——国家平台
   长时间不可达，只有国家通道子旅程受影响，J1 主链路完全不受影响。
2. **简洁** —— 不把"SQLite 能不能建 FK""manifest 该 builtin 还是 external"抛给负责人。
   架构层自己收敛成**两道正交门**（见 §二），负责人只拍"是否立项启用 + 默认 off"。
3. **端到端** —— 国家平台**不是虚构对象**，是真实 HTTP API（接口规范 v0.55）。我们是**地方端
   （省级平台）**，调它的查询/上报/消息同步接口。所以不做 mock、不假装"已联通"——而是实现一个
   **协议合规、未配置即静默的连接器**，和真实地方端在接入客户前的状态完全一致。
4. **设计即工作方式** —— UI 用人话（R12）："国家通道暂不可用，请稍后""国家通道待配置接入信息"，
   绝不暴露 flag/binding/provisioning 工程术语。flag-off → 入口**不渲染**（不是可见+置灰）。
5. **精品意识** —— **诚实边界写死在代码里**：凭据未签发就显"未签发"（承 D47），回执没回来就显
   "待国家平台回执"，绝不捏造回流。要么真，要么诚实地"待"，没有第三种。

**负责人只需拍两件事**：
- **① 立项启用**：是否批准反转 §10.4、把 national-direct + national-ext-elements 从占位转为
  真实能力（flag 默认 off、per-tenant 启用、未配置即静默）。
- **② 诚实边界**：是否接受"本期无真实国家端点可联调 → 已配置时对外只记意图 + 待回执，不伪造回流"，
  以及"协议合规测试桩 ≠ 业务数据 mock（D11）"的口径。

---

## 一·背景与真实锚定

权威协议源 `…数据直达接口规范v0.55.docx`：

- **国家端**（国家平台建设）暴露三类接口：**查询**（地方拉取国家目录/资源）、**上报**（地方把本级
  目录/资源/申请上报国家）、**消息同步**（异步入国家生产库）。**地方端**（我们=省级平台）调用之。
- **报文**：HTTP 头 `gjzwfwpt_rid`（请求者标识）/`gjzwfwpt_sid`（每接口服务标识）/`gjzwfwpt_rtime`
  （时间戳）/`gjzwfwpt_sign`；body = 全小写 utf-8 JSON；`POST /sysapi/<path>`；响应 `{code,message,data}`，
  200 成功 / 300 失败，分域返回码（catalog-/res-/api-/db-NNN）。
- **签名** = `base64(HmacSHA256(sid+rid+rtime, appsecret))`。
- **接入（附录C）**：国家平台向各省下发 `rid / appkey / appsecret / 每接口 sid / 接口 NAME`。
  **这些是配置，未接入客户前天然缺失。**

真实库（`dsp_connect.xml`=数据直达库；`dsp_catalog.xml`=目录库）与两条子旅程 1:1 对应：

- **national-direct（J1 子旅程）**：`dc_resource_apply_info`（status 0未上报/1上报待审/2管理员驳回/
  3国家驳回/4已撤销/5通过/8驳回；`up_apply_id` 国家回执）；申请转报 + 回流。
- **national-ext-elements（J2 子旅程）**：`data_basic_elem_catalog`（基本要素，国家下发）+
  `data_ext_elem_catalog_compile_task`（扩展要素编制任务，认领态 1默认认领/2不认领待审/3驳回/4不认领），
  与 `data_catalog` 主线状态机**完全独立**。

真实流程（`old/20260519/目录管理-国家目录治理` 27 页）：基本要素导入→编制（基本+扩展要素）→
业务部门审核→主管部门审核→下发→认领/异议→历史处理。

---

## 二·核心架构决策：两道正交门，都诚实

既有 10 个 `adapter.national.*` capability manifest（status=deferred:wave-3，binding=builtin）+
1 个 `catalog.national_ext_elem.compile`（builtin）已是 scaffolding。启用需同时满足三条守卫：
`is_live()` 二值只认 `status=="live"`；边界守卫 §1.3 禁 `adapter.national.* live && builtin`；
接入凭据是 per-tenant 运行时事实、无法做成 manifest 静态字段。唯一解 = 两道正交门：

- **清单门（构建期、边界诚实）**：国家平台**出站收口到子旅程 handler**——
  `application.escalate_national`（j1、builtin、live，新建）与 `catalog.national_ext_elem.compile`
  （j2、builtin、live；slug 不含 `adapter.national.` 前缀、本地编制非对外）经
  `national_channel_gate.outbound()` → `NationalDirectClient` 真实出站。两者都是 §1.3 之外的合法
  builtin live 能力。**10 个 `adapter.national.*` 保持 `deferred:wave-3` scaffolding**（仍在
  `_PASSTHROUGH_CAPS`，`require_surface()` 拒非 live、不可外呼、无害）：出站既已收口到 handler+gate，
  这 10 个 standalone adapter cap 对两条子旅程是无用 plumbing；把它们翻 `live` 需 binding
  `external_capability`（§1.3 禁 `adapter.national.* live && builtin`），但 external_capability 是
  严格契约（`compatibility==[]`、非 surface、`callback_only`、`failure_callback`、external_execution），
  10 adapter 不满足 → 误配会破契约投影守卫。故 **standalone live external-bridge 注册留作 future
  external-bridge 工作**（记 `docs/preflight-debt.md`），本期不强求清单门翻 live。

  > [C8 修订 2026-06-03] 原方案曾把 10 adapter 翻 `live && external_capability`（C4），但
  > external_capability 契约不匹配 → CI 红。收口到 handler+gate 后回退为 deferred scaffolding，
  > 国家集成的 live 性由 escalate(j1)/compile(j2) handler 经 gate 承载，更简且诚实。
- **运行门（请求期、接入诚实）**：`resolve_national_channel_state()` 纯函数派生三态
  `OFF / ON_UNPROVISIONED / ON_PROVISIONED`（env：`ZW_BRAIN_NATIONAL_CHANNEL_ENABLED` +
  `ZW_BRAIN_NATIONAL_ENDPOINT/RID/APPKEY/APPSECRET/SID_MAP`，密钥经 env 注入、禁硬编码、不进
  repr/日志/snapshot/manifest）。handler 在 `require_surface()` 放行后判态：OFF/未配置 → 返回诚实
  `pending`（记录意图、零对外、人话提示），**不是 404**——能力存在，能否对外是运行时事实。

`status=live` 让能力在 5 消费面可见且 `require_surface()` 放行，**与 flag 无关**——这是正确的：
能力**存在**是构建事实，能否**对外**是配置事实，后者表达为结果态、不表达为 404。

---

## 三·数据模型（复用为主，承 D47/D48）

复用 `adapters/legacy/mappers/connect.py` 已映射的 `dc_*/data_*`；`AdapterRunRecord`
（`uq_adapter_run_idempotency`）+ `ExternalObjectMappingRecord`（`up_*_id → external_object_id`）
已覆盖回执 + 幂等，**回执/映射无需新表**。新增 `NationalResourceCredentialRecord`
（对应 `dc_resource_api_auth_info`：state_url/state_appkey/state_sid）——**默认 `not_issued`，绝不
捏造**（承 D47 凭据诚实化；真凭据由国家平台签发后才落）。新增父子边登记进 `check_orphan_rows.py`
段67 边集合（覆盖=登记边集合、非 schema 全反射，承 D48）；`not_issued`/未接入租户的悬挂为
**诚实降级**、非硬 FK 失败。

国家扩展要素编制任务聚合与 `data_catalog` 主线**完全分离**（硬约束）：负向测试守"把扩展要素 task
写入 data_catalog → 拒绝"。national-direct 的"国家通道转报中"/"撤销中"是**应用层计算态**（读侧投影），
不写进 J1 主状态枚举。J2 业务部门→主管部门 2 级审核**复用 live approval-flow 引擎**
（engine-approval-flow 已 Done），注册独立 `flow_schema_code=national_ext_elem`。

---

## 四·诚实边界（REAL vs HONESTLY-PENDING）

**REAL（本期、不依赖网络即可单测）**：协议合规 client（envelope / 签名 / 返回码→域枚举）、未配置即
静默、回执存储 + `up_*_id` 幂等、组织映射、两套独立状态机、UI tab + 角色/flag 不可见性。

**HONESTLY-PENDING（记 `docs/preflight-debt.md` + 签字"业务方待确认"）**：
- 本期**无真实国家端点可联调** → 已配置时对外只记意图 + "待国家平台回执"，**不伪造回流**；真实回执
  对账无法在本期验证。
- 每资源凭据基数/生命周期（`dc_resource_api_auth_info` 自有 1已授权/0取消 态）、sid↔接口 NAME 映射 ——
  均为客户上线时配置，本期无法验证。

**测试桩 vs no-mock（D11）口径**：D11 禁的是**业务数据** mock（真实库回归、不造目录/资源/申请）。
国家平台是**外部基础设施**（§3.4 明确"保持外部依赖"），不是业务数据。协议合规桩
（`tests/national/stub_server/`，经 client 传输 seam 注入）只验"我方 client 是否会说协议"
（头/签名/小写 body/返回码解析），**不喂任何业务行**——与 c1 凭据诚实同姿态。明确标注 fixtures。

---

## 五·待人工审批事项（产品研发负责人 sign-off 清单）

1. **立项启用**反转 §10.4：national-direct + national-ext-elements 从占位转真实能力，flag 默认 off、
   per-tenant 启用。（GATE / 状态机门）
2. **出站收口决策**（C8 修订）：国家平台出站收口到 `escalate(j1)`/`compile(j2)` handler 经
   `national_channel_gate` + `NationalDirectClient`；10 个 `adapter.national.*` 保持 `deferred:wave-3`
   scaffolding，**不改边界守卫禁区清单**（保段22 诚实）。standalone live external-bridge 注册留作
   future（避免 external_capability 契约误配）。
3. **凭据诚实**（承 D47）：`NationalResourceCredentialRecord` 默认 `not_issued`，立为一等表保凭据
   生命周期（vs 折入 extra_json）—— 建议一等表。
4. **桩 vs no-mock 口径**（承 D11）：协议合规桩 = 外部基础设施测试夹具，非业务数据 mock。
5. **诚实边界**：已配置时对外只记意图 + 待回执、不伪造回流，作为本期交付的诚实上限。

> 签字落 `.testing/signoff/national-platform-access.signoff.yaml`（covers: national-direct,
> national-ext-elements）。签字前两条 `.feature` 状态函数返回 **InTest**（非 Done）。
