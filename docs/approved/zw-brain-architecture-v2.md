---
doc_id: design-zw-brain-architecture-v2
status: approved
gate: GATE-1
approved_by: xuejiao02
authors:
  - 薛娇（产品研发负责人）
  - Cursor Agent (claude-opus-4.7) — 设计协作
supersedes: design-zw-brain-architecture
related_docs:
  - docs/approved/zw-brain-architecture.md      # v1 基线（被本文取代）
  - old/代码信息抽取/                              # 旧平台 38 服务 API/DB/SDK 抽取
  - old/离线页面/政务数据服务门户/                  # 旧门户离线快照
  - hub/                                         # AIHub Skill/Agent 导出样例
  - hub/各类skill与智能体/aihub-integration-api.md # AIHub OpenAPI v1 集成规范
self_review_rounds: 1
phase_after_approval: Phase 0（脚手架 + AIHub 客户端 + 第一条端到端链路）
---

# 政务大脑（zw-brain）AI 原生重构基线 v2

> 调研日期：2026-04-22
> 取代关系：本文取代 `zw-brain-architecture.md`（v1, 2026-04-18 GATE-1 approved）；v1 决策 D1–D22 中**未在本文显式废止的全部继承**（详见 §十四「v1 → v2 决策迁移」），新决策从 D23 起编号。
> 触发原因：补充三类关键事实——(a) 旧平台代码层完整盘点（38 个后端服务 + 全量 API + 全量 DB schema + 全量外部 SDK 依赖）；(b) 旧门户离线 IA 快照（9 大顶层 + 30+ 子系统真实结构）；(c) 外部技能生态已有可用规范（AIHub OpenAPI v1 + Skill/Agent/Tool 三类资源 + A2A 协议样例）。这三类事实让 v1 中数处「待业务侧同步」的占位项可落定为正式契约。

---

## 〇、文档结构与阅读顺序

| 章节 | 解决什么问题 | 谁该读 |
|------|-------------|--------|
| 一、定位与目标 | 「我们要造什么」 | 所有人 |
| 二、设计哲学 | 「凭什么这么设计」 | 决策者 |
| 三、旧平台真实盘点 | 「我们正在替换什么」 | 架构师 / 产品 |
| 四、AI-Native 重构原则 | 「v1 的总纲，针对新事实加固」 | 架构师 |
| 五、产品形态 | 「用户/Agent 看到什么」 | 产品 / UX |
| 六、四入口与统一契约 | 「能力对外的唯一面孔」 | 工程 / Agent 接入方 |
| 七、核心架构分层 | 「代码长什么样」 | 工程 |
| 八、Hub（AIHub）集成模型 | 「能力从哪里来 / 到哪里去」 | 工程 / 生态 |
| 九、数据模型 | 「Agent 怎么消费数据」 | 工程 |
| 十、UI 收敛策略 | 「砍 90% 留 10% 的具体清单」 | 产品 |
| 十一、模型推理硬约束 | 「LLM 调用的唯一路径」 | 工程 |
| 十二、审计 / 合规 / 区块链 | 「政务行业的不可妥协」 | 安全 / 合规 |
| 十三、实施路线图 | 「先后顺序 + 里程碑」 | PM |
| 十四、决策记录 | 「v1→v2 迁移 + 新决策 D23+」 | 决策审计 |
| 附录 A | 数字漂移防御（stat 块清单） | 工程 |
| 附录 B | 旧→新功能映射全表 | 产品 / 迁移 |
| 附录 C | 旧平台 38 服务清单 | 工程 |
| 附录 D | 软→硬约束机械化映射 | 工程 / OPC 自检 |

---

## 一、定位与目标

### 1.1 一句话定位

**政务大脑** = 让政务数据「能被一个人/一个 Agent 用一句话端到端拿到、并且全程合规可证迹」的 AI 原生平台。

它**不是**：
- ❌ 旧「一体化大数据平台（政务）」的换皮（只换 UI、底层照旧）
- ❌ 一个「大模型客服」（只在前端贴个对话框）
- ❌ 一个「内部研发的 LLM 编排引擎」（重复造集团推理平台的轮子）

它**是**：
- ✅ 一组按业务旅程组织的核心 Agent（资源发现 / 资源申请 / 数据交换 / 国家直达 / 合规审计 / 运营洞察 ...）
- ✅ 一组按 AIHub 标准发布的可复用 Skill 和 Tool（OpenAPI / MCP / Custom）
- ✅ 一个以**精简 WebUI（≤10 核心场景页）+ 嵌入式自然语言加速器**为主入口的端到端用户体验
- ✅ 同时以 **REST / MCP / A2A / CLI** 四个对等入口暴露给外部 Agent / 第三方系统
- ✅ 一切扩展通过**注册外部 Skill / Agent**完成（AIHub 是默认上游生态），**而非内部加菜单**

### 1.2 三类目标用户

| 用户 | 主要入口 | 期望体验 |
|------|---------|---------|
| **政务数据使用方**（部门数据员 / 业务办事员 / 领导） | WebUI + 自然语言加速器；可视化大屏（领导专用） | 「我要 X 数据，请给我」一条龙 |
| **政务数据提供方**（部门资源管理员 / 数据治理人员） | WebUI + 后台管理 + 部分 CLI | 注册 / 上架 / 维护资源；审核申请 |
| **外部 Agent / 第三方系统**（其他厅局的智能体 / 国家平台 / 集团其他产品） | REST / MCP / A2A | 不进 WebUI，直接调能力；契约稳定可发现 |

### 1.3 与旧平台的本质差异

| 维度 | 旧「一体化大数据平台（政务）」 | 新「政务大脑」 |
|------|-----------------------------|--------------|
| 增能方式 | 加微服务 + 加菜单（已堆到 38 服务 / 9 大门户板块 / 30+ 子系统） | 注册外部 Skill / Agent（hub 即用） |
| 用户路径 | 多系统接力（目录 → 资源 → 申请 → 交换 → 落地） | 单一会话/旅程线（一个 Agent 跨步骤穿透） |
| 对外契约 | 主要 REST + 后台管理 UI；MCP/A2A 缺失 | REST / MCP / A2A / CLI 四等价入口 |
| AI 能力 | 几乎不用 | AI 原生（编排 / 自然语言 / Agent 协同 / 自动审计摘要 ...） |
| 模型调用 | 无统一约束 | 强制走集团推理平台 SDK |
| 审计 | 各模块各自记 | 统一审计总线 + 可选区块链锚定 |
| 研发模式 | 多团队 + 多代码库 + 手维护 | OPC + AI Coding + dev-rules 强约束门禁 |

---

## 二、设计哲学（与 v1 一致，针对新证据强化）

### 2.1 乔布斯产品设计哲学 —— 决定「做什么 / 不做什么」

> "It means saying no to the hundred other good features that there are." — Steve Jobs

旧平台的事实清单（来自 §三）显示：**38 个后端服务、9 大顶层栏目、30+ 子系统底栏入口**。这是堆出来的复杂，不是设计出来的复杂。v2 的第一动作仍然是**对一千个功能说不**——但说"不"的对象现在有了具体名字（见 §十）。

核心原则（与 v1 一致）：

1. **聚焦**：≤10 个 WebUI 核心场景页，其余都不进主导航；无法证明「真有人在用」的旧功能默认下沉为可选 Skill 或砍掉。
2. **简洁但不取消可见性**：政务数据产品天然要求「字段精确、操作可见、状态可读」。**纯对话框入口是反模式**。WebUI 是默认入口，自然语言用于「跨步骤一句话穿透 + 自动填表」。
3. **端到端**：用户的核心旅程「我要别人的某条数据，并且要拿到」必须是同一会话 / 同一旅程线，**不是 5 个系统接力**。
4. **设计即工作方式**：每一项能力都必须能被任何一个入口（WebUI/REST/MCP/A2A/CLI）调用——一个 Skill，五个入口共享，绝不双轨实现。
5. **精品意识**：宁可少做。每一个保留的功能都必须达到「客户用一次就再也不愿回到老版本」的水准。

### 2.2 OPC（One-Person Company）哲学 —— 决定「谁来做 / 做多少」

> 一个人 + AI 数字分身 = 一个精干团队的产出。

1. **杠杆最大化**：旧平台 38 服务的研发与运维被压缩到 1 人 + N 个 Agent。
2. **流程极简**：旧的「目录注册 → 资源注册 → 服务注册 → 申请 → 审核 → 数据交换 → 落地」7 步流程，能 NL 一句话触发的就**不要做表单**。
3. **自动化优先**：所有「需要人类点击」的步骤必须先回答「为什么 Agent 不能替代」。
4. **深度 > 广度**：一次只重构核心场景，不试图一次性覆盖旧平台的全部 30+ 子系统。
5. **反脆弱**：所有规则、契约、技能注册全部代码化、版本化，不依赖任何一个工程师的记忆。

### 2.3 政务行业三条硬约束（不能让 Jobs/OPC 把它们删掉）

1. **合规可证迹（Compliance & Auditability）**：每一次数据流通都要可被国家政策审计。所有 Agent 行为**强制落审计库**（同步阻塞，写入失败必须熔断），并可通过**区块链 adapter** 异步锚定到外部链（数享链 / 政务链）。
2. **国家上下行通道兼容（National Channel Compatibility）**：「数据直达」与国家平台对接 API 由国家定义，本平台必须严格遵守；重构再激进，对国家平台的接口语义不能改。
3. **模型服务统一收口（Inference Platform Mandate）**：所有 AI 模型推理（LLM / Embedding / ASR / Rerank / OCR / 多模态 / 任意未来新增模型能力）**必须且只能**通过集团推理平台（`../pcowork/推理平台/`）的统一 SDK / API 调用。**禁止任何模块直连**任何第三方 LLM 服务商 API。理由：合规 / 采购 / 可审计 / 可替换。preflight 段 10 强制检查。

### 2.4 三个哲学的交汇

```
       Jobs（聚焦 / 简洁 / 端到端）
            │
            ▼ 决定形态
   ┌──────────────────────────────────────────────┐
   │  政务大脑 = 精简 WebUI（≤10 页核心场景）        │
   │           + 嵌入式 NL 加速器                  │
   │           + 独立可视化大屏（K12，对外门面）      │
   │           + N 个核心 Agent + M 个 AIHub Skill │
   │           + 全程合规可证迹（强制审计 + 链锚定）  │
   │           + 模型推理统一走推理平台 SDK         │
   └──────────────────────────────────────────────┘
            ▲ 受约束于
            │
       OPC（自动化 / 杠杆 / 深度）   政务三条硬约束（合规 / 国家通道 / 推理平台）
```

---

## 三、旧平台真实盘点（基于 `old/代码信息抽取/` 与 `old/离线页面/`）

> v1 基于「介绍材料 + 47 张界面截图」做盘点，v2 基于代码扫描结果与离线 HTML 快照——颗粒度从「印象」升级到「事实」。

### 3.1 后端服务规模

旧平台共 **38 个独立后端服务**（详见附录 C），按业务域聚类：

| 业务域 | 代表服务 | 数据库 |
|--------|---------|--------|
| 应用中心 | `app-center-server`, `app-center-web` | `aep_app_center` |
| 资源目录 | `dsp-catalog-*`, `dsp-metaresource-*` | `dsp_catalog`, `dsp_catalog_v4`, `dsp_metaresource` |
| 数据资产与安全 | `icp-idlf-asset-*`, `icp-idlf-security-*` | `icp_idlf_asset`, `icp_idlf_security` |
| 消息总线 | `dsp-message-*` | `dsp_message` |
| 任务调度 | `xxl-job-admin` | `xxl_job` |
| 数据交换 / 直达 | （多服务，散布在交换 / 直达 / 异议处理） | （多库） |
| 治理 / 督导 / 绩效 | （多服务） | （多库） |

**事实结论**：
- 服务数量已经远超 v1 估计的「20+」——是 38。
- 数据库至少 9 个独立 schema，存在明显的领域散落。
- 主要技术栈：Spring Boot + MyBatis Plus + MySQL + Kafka + MinIO + Keycloak/IAM。
- 部分凭据明文/弱加密入库（违反 OPC 安全基线，迁移期间必须彻底重做）。

### 3.2 旧门户真实信息架构

`old/离线页面/政务数据服务门户/` 离线快照显示门户顶层导航与底栏链接：

**顶层导航（9）**：首页 / 政务数据目录 / 政务数据资源 / 融合服务 / 应用中心 / 典型应用案例 / 通用服务 / 知识中心 / 数字化运营。

**底栏入口（30+ 子系统，按业务域聚类）**：

| 业务域 | 旧子系统 |
|--------|---------|
| 共享与交换 | 数据共享系统 / 资源申请授权 / 数享链 / 数据异议处理 / 数据应用推广 / 数据资源库 / 数据直达 / 数据交换 |
| 分析与可视化 | 数据分析系统 / 数据可视化 |
| 运维运营 | 运维运营 / 运行管理 / 运行监控 / 绩效考核 / 合规督导 |
| 数据治理 | 数据治理系统 / 管理中心 / 数据集成 / 数据标准 / 元数据管理 / 数据质量 / 数据开发 / 数据建模 / 数据标签 / 数据安全 |
| 资源管理 | 数据资源管理 / 目录管理 / 资源管理 |
| 计算存储 | 大数据计算与分析 / 大数据存储与分析服务 |
| 供需 / 消息 / 标准 | 供需对接系统 / 消息中心 / 标准服务 / 数据安全中心 |

**事实结论**：
- 「9 大顶层」+「30+ 底栏入口」= 用户面对的是一个**菜单海洋**，不是一个产品。
- 大量子系统命名相近（如「数据共享系统 / 数据交换 / 数据直达 / 资源申请授权」），用户难以辨别该用哪个。
- 这是 v2 必须收敛到「≤10 核心 WebUI 场景页 + N 个 Agent」的根本理由（见 §十）。

### 3.3 旧 API 表面规模

`All-Project_对外提供API汇总.md` 显示仅 `app-center-server` 一个服务就暴露了几十个 REST 端点（应用管理 / 审核 / 详情 / 评论 / 标签 / 字段 / 行业 / 组织 / 用户 / 文件 / 资源申请 / 收藏 / 数购车 / 项目管理）。38 个服务全部叠加，对外暴露的 REST 端点数量级在 **数百到上千**，且**无 MCP / 无 A2A / 无标准化 OpenAPI 契约文档**。这是 v2 强调「四入口共享同一套 Skill 契约 + 自动生成」的原因。

### 3.4 外部依赖

`All-Project_外部SDK和接口文档.md` 显示旧平台核心外部依赖：

- **认证**：Keycloak / IAM Adapter Java
- **存储**：MinIO Java SDK
- **消息**：Kafka
- **网关**：内部 Gateway
- **接口管理**：BSP
- **未发现**：任何 LLM / Embedding / Agent 框架的依赖——印证「AI 能力几乎不用」的现状。

v2 的迁移策略：
- Keycloak / MinIO / Kafka / Gateway 在 Phase 1 继续复用（不在大脑内复造），通过 adapter 接入。
- BSP 视新平台对外契约能力是否覆盖再决定保留或下架。
- LLM / Embedding 等 AI 能力**统一走集团推理平台 SDK**（D6 不变）。

---

## 四、AI-Native 重构原则（v1 总纲，针对新证据加固）

### 4.1 五条总原则（v1 D1–D6 浓缩）

1. **产品形态固定**：精简 WebUI（≤10 页）+ 嵌入式 NL 加速器 + N 个核心 Agent + M 个可注册 Skill。**不复刻旧菜单导航形态，也不做"裸对话框"入口**。（继承 D1）
2. **四入口共享同一契约**：WebUI / REST / MCP / A2A 由单一脚本生成，禁止 4 处手维护。（继承 D2）
3. **能力扩展唯一路径 = Skill 注册**：禁止在 Agent / 编排层内嵌业务逻辑。（继承 D3）
4. **审计强制同步落库 + 区块链异步锚定**：审计写入失败必须熔断；外链 down 不阻塞业务但需告警重试。（继承 D4 / D5）
5. **模型服务统一走集团推理平台 SDK**：preflight 段 10 强制检查，违反者拒绝合并。（继承 D6 / D14）

### 4.2 v2 针对新证据的加固

**E1 — Hub 上游已落定为 AIHub**（v1 D13 占位项的实化）

v1 写「外部 Agent / Skill 接入是合法且必备的扩展路径，具体协议⏳ 待业务侧同步」。v2 据 `hub/各类skill与智能体/aihub-integration-api.md` 落定：

- **AIHub OpenAPI v1** 是政务大脑的默认 / 权威外部技能上游
- Skill / Agent / Tool 三类资源的契约 = AIHub 已发布的契约（详见 §八）
- 推送（Push）与导入（Import）双向通道复用 AIHub 的接口；**不在大脑内自研另一套 hub 协议**
- 多上游可后续支持，但 AIHub 永远是默认 + 一等公民

**E2 — 38 服务不是一次性吃掉的对象**

v1 已定 D10 砍 5 项低价值功能。v2 据 38 服务真实清单进一步细化：

- **Phase 1 重构盘子**：限定为「资源目录 + 资源申请授权 + 数据交换 + 数据直达」四块（占旧平台对外业务价值的 ~80%），其余 30+ 子系统**默认通过 adapter 只读消费旧库**或**等触发条件**才进入重构队列。
- **新决策 D23**（见 §十四）：Phase 1 重构白名单 = 4 块；其余「不主动迁移」，但**所有外部能力调用必须走新平台的 Skill 注册路径**——避免新平台沦为旧平台的代理层。

**E3 — 旧门户的"菜单海洋"是反例，不是参考**

旧门户 9 大顶层 + 30+ 底栏入口的结构是**功能堆叠的产物**，不是用户旅程的产物。v2 的 WebUI 设计**禁止以旧门户 IA 为蓝本**——而是以「用户的 5 类核心旅程」为蓝本（见 §五）。

**E4 — 数据库分裂是迁移负担，不是设计目标**

旧 9 个独立数据库是历史团队边界的产物。v2 不强求合并（Phase 1 通过 adapter 单向消费旧库），但**新建实体必须在新 schema 中**（v1 D7「Agent-Native 优先 + Adapter 层」原则不变）。

---

## 五、产品形态（用户/Agent 看到什么）

### 5.1 五类用户旅程（替代旧门户的 9 大栏目）

按真实业务诉求归并：

| # | 旅程 | 旧平台对应（散落在多子系统） | 新形态 |
|---|------|---------------------------|--------|
| J1 | **找数据**：我想知道有没有 X 数据，谁管，能不能给我 | 政务数据目录 + 资源 + 融合服务 | 1 个 WebUI 场景页 + `catalog.search` / `resource.lookup` Skill |
| J2 | **要数据**：申请 + 审批 + 拿到（接口/库表/文件） | 资源申请授权 + 数据交换 + 数据直达 | 1 个 WebUI 旅程页 + `resource.apply` / `exchange.fulfill` / `national.deliver` Skill |
| J3 | **管数据**（提供方）：上架 + 编目 + 资源审核 + 异议处理 | 目录管理 + 资源管理 + 数据异议处理 | 1 个后台 WebUI + 一组 Skill |
| J4 | **看大盘**（领导/督导）：运行情况 + 绩效 + 合规审计回放 | 数字化运营 + 运行监控 + 绩效考核 + 合规督导 | 1 个独立可视化大屏（K12）只读消费 `dashboard.*` Skill |
| J5 | **接生态**（外部 Agent / 第三方）：发现能力 + 调用 + 拿审计回执 | （旧平台几乎不支持） | REST / MCP / A2A 入口 + AIHub 注册的能力清单 |

### 5.2 ≤<!-- stat:zwbrain.webui-pages-cap -->10<!-- /stat --> 个 WebUI 核心场景页（硬上限）

| # | 页面 | 服务的旅程 |
|---|------|-----------|
| P1 | 一站式找数据 | J1 |
| P2 | 数据申请 / 审批 / 跟踪 | J2 |
| P3 | 数据交付与落库 | J2 |
| P4 | 国家直达接口管理 | J2 |
| P5 | 资源上架与编目（提供方） | J3 |
| P6 | 资源审核 / 异议处理（提供方） | J3 |
| P7 | 我的工作台（个人 / 组织） | 全旅程入口 |
| P8 | 智能体与技能市场（消费 AIHub 能力） | J5 |
| P9 | 审计与合规回放 | J4 |
| P10 | 系统配置（平台集成 / 推理平台 / 区块链 adapter / IAM 等） | 仅管理员 |

> 这 10 页之外的所有功能要么是 Skill（被 Agent 编排调用），要么是后台运维工具，要么不做。**新增 WebUI 页面必须先答「为什么 Skill + 自然语言不够」**。

### 5.3 嵌入式 NL 加速器

每个 WebUI 页面顶部内置一个 NL 输入框（不是外挂"客服小窗"）。NL 的职责限定为：

- 跨步骤一句话穿透：「帮我把张局上周申请的'幼儿信息'数据交换到我们厅库里」→ 自动跳过 P1/P2/P3 中间步骤
- 自动填表：根据 NL 描述预填表单字段，用户审阅后提交（一次按下，多次确认）
- 上下文延续：在同一会话内可继续追加「换成接口形式」「再加一份月度统计」

**NL 不做**：替代 WebUI 表单中字段精度敏感的填写步骤；**永远不在没有可见审阅界面的情况下提交关键操作**。

### 5.4 K12 可视化大屏（独立部署）

继承 v1 D15：可视化大屏 = `zw-brain-dashboard/` 独立部署单元，只读消费 `dashboard.*` Skill，禁止内嵌写操作；故障与主大脑隔离。preflight 段 11 强制检查（v1 已落地）。

---

## 六、四入口与统一契约（能力对外的唯一面孔）

### 6.1 四入口对等

| 入口 | 服务对象 | 协议 |
|------|---------|------|
| WebUI | 普通用户 | HTTP + SSE |
| REST | 第三方系统、CLI 客户端 | REST + OpenAPI |
| MCP | Claude / Cursor / 其他支持 MCP 的 Agent IDE | MCP（stdio / SSE / HTTP） |
| A2A | 其他 Agent 平台（包括 AIHub 上其他 Agent） | A2A 协议（HTTP+JSON，参见 hub 样例 `a2a/agent_card.json`） |
| CLI | 运维 / 调试 / Headless 巡检 | 命令行 |

### 6.2 单一契约源

- 唯一事实来源：`zw_brain/skills/<skill>/skill.json` (Skill 定义) + `zw_brain/agents/<agent>/agent.json` (Agent 定义)
- 由 `scripts/export_agent_contract.py` 自动生成：
  - `docs/agent_integration.md`（人读契约表）
  - `openapi.json`（REST 入口）
  - `mcp.manifest.json`（MCP 入口）
  - `agent_card.json`（A2A 入口，遵循 AIHub A2A 样例规范）
- preflight 段 4 强制检查 `python scripts/export_agent_contract.py --check` 必须无 diff。

### 6.3 鉴权与租户

- 主鉴权：复用 IAM / Keycloak（旧平台已有，不重造）
- 二级凭证：每个 Agent / 第三方接入方有独立 API Key + 速率限额
- 租户：政务大脑天然是**多部门多区县**的多租户系统（见旧门户「省直 / 地市 / 区县」分级）；所有 Skill 必须 tenant-aware，禁止跨租户读写

---

## 七、核心架构分层

### 7.1 分层视图

```
┌──────────────────────────────────────────────────────────────────────┐
│                         L0 - Surface 层                               │
│  WebUI(≤10页) │ REST API │ MCP Server │ A2A Server │ CLI │ Dashboard  │
│                  └──────── 统一契约（单一脚本生成） ──────┘             │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓ 入站统一编排
┌──────────────────────────────────────────────────────────────────────┐
│                     L1 - Orchestrator 层                              │
│  意图识别 │ 多 Agent 协同 │ 上下文管理 │ 审计总线 │ 推理平台 SDK 路由     │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓ 调度
┌──────────────────────────────────────────────────────────────────────┐
│                     L2 - Core Agent 层                                │
│  CatalogAgent │ ResourceAgent │ ApprovalAgent │ ExchangeAgent │ ...   │
│  （每个 Agent 是 A2A 兼容的可执行体；可被本平台 / AIHub / 外部调用）       │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓ 组合
┌──────────────────────────────────────────────────────────────────────┐
│                     L3 - Skills 层（可注册 / 可热插拔）                  │
│  内置 Skill │ AIHub 导入 Skill │ 第三方注册 Skill                        │
│  Skill = SKILL.md(frontmatter) + scripts/ + assets/ + references/    │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓ 调用
┌──────────────────────────────────────────────────────────────────────┐
│                     L4 - Tools 层（被 Skill 调用的原子能力）              │
│  OpenAPI Tool │ MCP Tool │ Custom Python Tool                        │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓ 数据访问
┌──────────────────────────────────────────────────────────────────────┐
│                     L5 - Data / External 层                           │
│  zw-brain 自有库（PostgreSQL，新建 schema）                              │
│  ↕ Adapter（单向同步）                                                   │
│  旧平台 9 个 MySQL schema（aep / icp / dsp / xxl_job ...）              │
│  ↕ External SDKs：集团推理平台 / IAM / MinIO / Kafka / 区块链 / 国家平台    │
└──────────────────────────────────────────────────────────────────────┘
```

### 7.2 分层依赖（强约束）

- **方向**：Surface → Orchestrator → Agent → Skill → Tool → Data/External
- **禁止**：反向引用、跨层跳跃（如 Surface 直接调 Tool）
- **机械检查**：`scripts/check_layered_deps.py`（preflight 段 12，依赖 v1 D21 已落地的脚手架）

### 7.3 仓库目录骨架

```
zw-brain/
├── docs/approved/                  # 设计基线（本文件）
├── prototype/                      # GATE-1 配套原型（v1 D21 强制）
├── zw_brain/
│   ├── surface/                    # L0：webui / rest / mcp / a2a / cli
│   ├── orchestrator/               # L1：编排 + 审计总线 + 推理 SDK 路由
│   ├── agents/                     # L2：核心 Agent 实现
│   ├── skills/                     # L3：内置 + 注册 Skill
│   │   ├── builtin/
│   │   └── registered/             # 由 AIHub import 落盘的 Skill
│   ├── tools/                      # L4
│   ├── adapters/                   # 旧平台适配（单向消费）
│   └── shared/
│       ├── inference/              # 集团推理平台 SDK 封装（D14）
│       ├── audit/                  # 审计总线 + 区块链 adapter（D4/D5）
│       ├── auth/                   # IAM 客户端
│       └── storage/                # MinIO + PostgreSQL
├── zw-brain-dashboard/             # K12 独立部署（v1 D15）
├── scripts/                        # export_agent_contract.py / check_*.py / preflight.sh wrapper
├── dev-rules/                      # git submodule
└── docs/preflight-debt.md          # 未自动化检查的债务清单
```

---

## 八、Hub（AIHub）集成模型

> 本章是 v2 相对 v1 的**最大实化**。v1 写「外部 Skill 协议⏳ 待业务侧同步」；v2 据 `hub/各类skill与智能体/aihub-integration-api.md` 落定 AIHub OpenAPI v1 为权威契约。

### 8.1 Hub 三类资源

| 类型 | 形态 | 文件结构 | 用途 |
|------|------|---------|------|
| **Skill** | SKILL.md (YAML frontmatter) + scripts/ + assets/ + references/ | 见 `hub/skills/0a08501b-.../SKILL.md` 样例 | 可被任何 Agent 复用的最小能力单元 |
| **Agent**（Smart-Agent） | manifest.json + a2a/agent_card.json + skills/bindings.json + runtime/ + tools/ + prompt/ | 见 `hub/Excel问数智能体_v1_runnable_a2a/` 样例 | 完整的可独立运行 Agent，含 A2A 协议端点 |
| **Tool** | OpenAPI Spec / MCP Server 定义 / Python 入口 | （AIHub 已规范化） | Skill / Agent 调用的原子能力 |

### 8.2 Skill 契约（采纳 AIHub 规范）

`SKILL.md` frontmatter 必填字段（与 `hub/skills/*` 样例一致）：

```yaml
---
name: <Skill 名>
description: <用途说明 + 触发场景关键词>
metadata:
  author: <作者>
  version: "<语义化版本>"
  tags: "<逗号分隔标签>"
  category: <类别>
  platform-tools: <被调用的底层 tool / service 名>
---
```

`bindings.json`（多步 / 工具组合 Skill）字段：

```json
{
  "skill_name": "...",
  "skill_id": "<uuid>",
  "skill_type": "single_tool" | "multi_step",
  "version": 1,
  "input_schema":  { JSON Schema },
  "output_schema": { JSON Schema },
  "entry_point":   "scripts/execute.py:execute"
}
```

### 8.3 Agent 契约（采纳 AIHub A2A 规范）

`a2a/agent_card.json` 必含字段（与 `hub/Excel问数智能体_v1_runnable_a2a/a2a/agent_card.json` 一致）：

- `name` / `description` / `version`
- `supportedInterfaces`：协议绑定（HTTP+JSON / 其他）
- `capabilities`：streaming / pushNotifications / extendedAgentCard
- `skills[]`：内嵌 Skill 引用（id / name / description / inputModes / outputModes）
- `defaultInputModes` / `defaultOutputModes`

### 8.4 双向通道

```
zw-brain  ←──── push ────→  AIHub  ←──── push ────→  其他下游（海若大脑 / Cowork）
zw-brain  ←─── import ────  AIHub
```

zw-brain 暴露的内部 API（参考 AIHub 集成文档第 3 节）：

| 路径 | 用途 |
|------|------|
| `POST /api/skills/{skill_id}/push-aihub` | 把本地 Skill 推到 AIHub |
| `GET  /api/skills/aihub/list` | 列出 AIHub 上可导入的 Skill |
| `POST /api/skills/aihub/import` | 批量导入 |
| `POST /api/agents/{agent_id}/push-aihub` | 把本地 Agent 推到 AIHub |
| `GET  /api/agents/{agent_id}/aihub/versions` | 查询 Agent 在 AIHub 的版本 |
| `POST /api/tools/openapi/aihub/import` | 导入 OpenAPI Tool |
| `POST /api/tools/mcp/aihub/import` | 导入 MCP Tool |

zw-brain 调用的 AIHub OpenAPI v1（透传或客户端封装）：

- `POST /api/openapi/v1/skills` / `.../{slug}/versions`
- `POST /api/openapi/v1/smart-agents` / `.../{slug}/versions`
- `GET  /api/openapi/v1/public/skills`
- `GET  /api/openapi/v1/skills/{slug}/versions`

### 8.5 配置与多租户

按 AIHub 集成文档：

- 推荐通过「平台集成」配置项（slug=`aihub`）注入 `endpoint_url` + `api_key`，租户隔离
- 环境变量回退（`AIHUB_API_BASE_URL` / `AIHUB_API_KEY`）仅用于本地开发
- 所有 AIHub 推送 / 导入操作必须落审计日志（`action=skill.push_aihub` / `action=skill.import_aihub` 等）

### 8.6 政务大脑作为 Hub Provider 的特别约束

zw-brain 推到 AIHub 的 Skill / Agent **必须**：

1. 不携带任何政务敏感数据（仅能力代码 + 公开 schema）
2. `metadata.tags` 必含 `gov-brain` / `compliance-required`
3. Provider Agent 文档明确「本能力调用必须遵守国家政策与本地审计回执」
4. 推送前 preflight 检查（`scripts/check_aihub_push_safety.py`，待 Phase 0 落地——记入 `docs/preflight-debt.md`）

---

## 九、数据模型（Agent-Native 优先 + Adapter 层）

继承 v1 D7 总原则，针对新事实细化：

### 9.1 设计准则

1. **URN 主键**：所有跨系统可寻址实体用 URN（如 `urn:gov-brain:resource:山东省统一社会信用代码数据库信息:v3`），不用纯整型 ID
2. **显式状态机**：每个实体的状态字段必须配套显式 enum 与迁移图（写在 schema 注释里）
3. **可序列化 intent / decision**：用户意图与 Agent 决策必须以结构化 JSON 入库，便于审计回放
4. **审计字段一等公民**：`actor`, `actor_kind`(human/agent), `at`, `tenant`, `correlation_id` 必填
5. **PII 标签**：含个人信息字段必须打 `pii: true`，并由 Skill 层强制脱敏读取
6. **schema-as-doc**：模型即文档，不再单独维护 ER 图

### 9.2 核心实体（Phase 1 重构盘子）

| 实体 | 旧平台对应 | 关键字段 |
|------|-----------|---------|
| `Resource` | `dsp_metaresource.t_resource_*` | urn / kind(api/table/file/folder/link) / owner / status / pii_tags |
| `Catalog` | `dsp_catalog.t_catalog_*` | urn / parent / domain / region / source_dept |
| `Application` (申请) | `aep_app_center.resource_application_info` | urn / requester / target_resource / state(draft/pending/approved/rejected/delivered) / decision_log |
| `Delivery` (交付) | （多服务散落） | urn / application / channel(api/db/file) / receipt / blockchain_anchor |
| `AuditEvent` | （旧平台各自记） | id / actor / actor_kind / action / target / at / payload / tenant / blockchain_tx |

### 9.3 Adapter 层

- `zw_brain/adapters/<old_db>_adapter.py`：单向消费旧库，转译为新模型
- 禁止反向写入旧库（旧库进入只读维护模式）
- 每个 adapter 必须有 `fixtures/<entity>/*.json` 供测试（v1 D18 已立机械检查）

---

## 十、UI 收敛策略

### 10.1 必保留功能（K1–K12）

继承 v1，按新事实校准：

| ID | 功能 | 旧入口 | 新形态 |
|----|------|-------|--------|
| K1 | 一站式找数据 | 政务数据目录 + 资源 + 融合服务 | P1 |
| K2 | 数据申请 / 审批 / 跟踪 | 资源申请授权 | P2 |
| K3 | 数据交付与落库 | 数据交换 | P3 |
| K4 | 国家直达接口管理 | 数据直达 | P4 |
| K5 | 资源上架与编目（提供方） | 目录管理 + 资源管理 | P5 |
| K6 | 资源审核 / 异议处理（提供方） | 数据异议处理 | P6 |
| K7 | 我的工作台 | 工作台 | P7 |
| K8 | 智能体与技能市场（AIHub） | （旧平台无） | P8 |
| K9 | 审计与合规回放 | 合规督导 | P9 |
| K10 | 系统配置 | 管理中心 + 标准服务 + 数据安全中心 | P10 |
| K11 | 共享专区（融合服务） | 融合服务（埋深 + 无订阅 → 升级为一等公民） | 融入 P1，作为「跨域专题包」 |
| K12 | 可视化大屏（领导专用） | 数字化运营 + 运行监控 | 独立部署 `zw-brain-dashboard/` |

### 10.2 不主动重构（触发条件再评估）

继承 v1 D10：

| ID | 旧子系统 | 不主动重构原因 |
|----|---------|--------------|
| N1 | 数据资源库 | 与目录 + 资源功能重叠 |
| N2 | 绩效考核 | 客户使用率极低 |
| N3 | 应用案例独立子系统 | 静态展示型，融入 P9 即可 |
| N4 | 通用服务 + 链接资源 | 入口性质，不是产品 |
| N5 | 指标平台 | 业务边界不清 |

重激活前必走 product-dev.mdc 流程。

### 10.3 Phase 1 不主动迁移的旧子系统

按 §四 E2 决策：除上述 K / N 之外的 30+ 子系统在 Phase 1 **默认不主动迁移**——通过 adapter 单向只读消费旧库。何时迁移由「该子系统是否成为关键 Skill 的依赖」决定。

---

## 十一、模型推理硬约束

继承 v1 D6 / D14，无变化：

- **强制走集团推理平台 SDK / API**（`../pcowork/推理平台/`）
- **禁止任何模块直连**：OpenAI / Anthropic / 百川 / 智谱 / 通义 / DeepSeek / Moonshot / 月之暗面 / 任何境外 LLM 提供商
- **唯一封装位置**：`zw_brain/shared/inference/client.py`（Phase 0 mock，平台 SDK 文档到位后只换内部实现）
- **机械检查**：preflight 段 10（grep 禁词列表 + import 白名单）
- **覆盖范围**：LLM / Embedding / Rerank / ASR / TTS / OCR / 多模态 / 任意未来新增模型能力

---

## 十二、审计 / 合规 / 区块链

继承 v1 D4 / D5：

### 12.1 审计总线

- 位置：`zw_brain/shared/audit/bus.py`
- 写入策略：**同步阻塞**，写入失败必须熔断（向上抛错，业务流程中断）
- 必填字段：`actor`, `actor_kind`(human/agent/system), `action`, `target_urn`, `at`, `tenant`, `correlation_id`, `payload_hash`
- 落地：PostgreSQL `audit_event` 表 + Kafka topic `gov-brain.audit`（双写）
- 查询入口：P9「审计与合规回放」WebUI 页

### 12.2 区块链锚定（异步）

- 适配模式：`zw_brain/shared/audit/blockchain/` 下放 adapter（数享链 / 政务链 / 国家链）
- 触发：审计事件落库后，异步发送 hash 上链
- 失败策略：链 down 不阻塞业务；告警 + 重试队列；连续失败超阈值告警人工介入
- 协议：Phase 1 仅实现 adapter 接口骨架，外部链协议明确后再详设具体实现

### 12.3 合规规则

- 每个 Skill 必须声明 `compliance-required: true|false`（写在 SKILL.md frontmatter）
- 涉及跨部门数据流通的 Skill 必须 `compliance-required: true`，调用前必须经 `ApprovalAgent` 审批 / 审计回执
- 禁止任何 Skill 输出未脱敏 PII（由 L4 Tools 层强制）

---

## 十三、实施路线图

### Phase 0 — 机械守卫脚手架 + AIHub 客户端（4–6 周）

> 目标：让"任何不合规的代码 / 设计"在落盘前就被脚本拦下；同时打通 AIHub 客户端骨架，验证「导入一个 Skill → Agent 调用 → 审计落库」的最小闭环。

里程碑：

- [x] 设计基线 v1 落盘（GATE-1，2026-04-18 已完成）
- [ ] 设计基线 v2 落盘（本文）
- [ ] 13 项机械守卫接入清单（继承 v1 附录 A）
- [ ] `zw_brain/shared/inference/client.py` mock 实现 + preflight 段 10
- [ ] `zw_brain/shared/audit/bus.py` 同步落库实现 + 区块链 adapter 接口骨架
- [ ] AIHub 客户端 `zw_brain/skills/aihub_client.py`（push / pull / list / import / version）
- [ ] 第一条端到端链路：导入 1 个 AIHub Skill → 1 个 Core Agent 调用 → 审计落库
- [ ] `zw-brain-dashboard/` 骨架 + 1 个 `dashboard.*` 只读 Skill
- [ ] 项目特有 `scripts/check_*.py` 全套通过 + `scripts/preflight.sh` 全绿（含模板段与项目段，详见附录 D）

### Phase 1 — 四块核心业务重构（10–14 周）

按 §四 E2 决策的白名单：

- 资源目录（K1）端到端 Agent + Skill 落地
- 数据申请 / 审批（K2）
- 数据交换（K3）
- 国家直达（K4，与国家平台严格对齐）
- WebUI P1–P5 + P7 + P9（≤7 页先上线）
- adapter 接入旧 9 个 MySQL schema（只读）

### Phase 2 — 提供方 + 生态扩展（8–10 周）

- 提供方旅程 J3 完整：上架 / 编目 / 审核 / 异议（K5–K6）
- AIHub 双向通道完整：push 本地 Skill / Agent 到 AIHub
- 智能体与技能市场 P8 上线
- 区块链 adapter 接入实链（数享链或客户指定）

### Phase 3 — 大屏 + 运营 + 多租户加固（6–8 周）

- K12 大屏完整内容
- 多租户细化（部门 / 区县 / 角色）
- 性能与压测
- 旧平台并行运行 → 切流

### Phase 4 — 旧平台下线（视客户节奏，6+ 月）

按子系统逐步退役；不强求一次性切。

---

## 十四、决策记录

### 14.1 v1 → v2 决策迁移

| 来自 v1 | 状态 | 备注 |
|---------|------|------|
| D1 产品形态 | ✅ 继承 | §四原则 1 |
| D2 四入口共享契约 | ✅ 继承 | §六 |
| D3 Skill 注册唯一扩展路径 | ✅ 继承（强化） | §四原则 3 + §八 |
| D4 审计同步落库 | ✅ 继承 | §十二 |
| D5 区块链 adapter 异步 | ✅ 继承 | §十二.2 |
| D6 模型推理统一收口 | ✅ 继承 | §十一 |
| D7 Agent-Native 优先 + Adapter | ✅ 继承 | §九 |
| D8 ≤10 WebUI 核心场景页 | ✅ 继承 | §五.2 |
| D9 共享专区升级为 K11 | ✅ 继承 | §十.1 |
| D10 5 项不主动重构（N1–N5） | ✅ 继承 | §十.2 |
| D11 旧平台真实数据回归验证 | ✅ 继承 | §十三 Phase 1 |
| D12 与外部系统保持「外部依赖」关系 | ✅ 继承 | §三.4 |
| D13 外部 Agent 接入 = 合法路径 | ✅ **实化为 D24（AIHub）** | 见下 |
| D14 推理平台 SDK mock 先行 | ✅ 继承 | §十三 Phase 0 |
| D15 K12 大屏独立部署 | ✅ 继承 | §五.4 |
| D16 URN 小白解释 | ✅ 继承 | §九.1 |
| D17 散文档数值漂移用 stat 块 | ✅ 继承 | 附录 A |
| D18 fixture 覆盖检查 | ✅ 继承 | §九.3 |
| D19 技术选型延后到 PoC | ✅ 继承 | §十三 Phase 0 |
| D20 stat 命名规范 | ✅ 继承 | 附录 A |
| D21 GATE-1 必须配套原型 | ✅ 继承 | preflight 段 13 |
| D22 外部引用悬空检查 + 自包含附录 | ✅ 继承 + 强化 | 附录 D（自包含 zw-brain 软→硬映射） |

### 14.2 v2 新决策

#### D23 — Phase 1 重构盘子限定为 4 块

**触发**：旧平台 38 服务清单显示规模远超 v1 估计；按 OPC「深度 > 广度」原则，Phase 1 必须限定盘子。

**决策**：Phase 1 **白名单 = 资源目录 + 资源申请授权 + 数据交换 + 数据直达**（J1 + J2 全旅程）。其余 30+ 子系统在 Phase 1 默认通过 adapter 只读消费旧库；何时进入重构队列由「是否成为关键 Skill 依赖」触发。

**影响**：
- §五 P1–P4 优先实现，P5–P10 延后
- adapter 层早期工作量增加；估算 1.5x v1 预估
- 客户沟通：Phase 1 上线时旧平台仍需保留运行

#### D24 — AIHub 落定为 zw-brain 默认且权威的外部技能上游

**触发**：`hub/各类skill与智能体/aihub-integration-api.md` 提供完整的 OpenAPI v1 集成规范 + `hub/skills/` 与 `hub/*_v1_runnable_a2a/` 提供 Skill / Agent 真实样例；v1 D13 占位项可落定。

**决策**：
1. zw-brain 的外部技能生态**默认对接 AIHub**；多上游可后续支持，AIHub 永远是默认 + 一等公民
2. Skill 契约 = AIHub `SKILL.md` frontmatter + `bindings.json`（§八.2）
3. Agent 契约 = AIHub `manifest.json` + `a2a/agent_card.json` + `skills/bindings.json`（§八.3）
4. 推送 / 导入 / 版本管理 API 形态对齐 AIHub 集成文档第 3 节
5. zw-brain 既是 AIHub 消费者也是提供者；提供者侧需通过 `check_aihub_push_safety.py` 防止敏感数据外泄

**影响**：
- §八 全章节据此实化
- Phase 0 必须落地 `aihub_client.py` 与端到端链路
- AIHub URL / API Key 通过「平台集成」配置而非 env 硬编码

#### D25 — 旧门户 IA 是反例不是参考

**触发**：旧门户 9 大顶层 + 30+ 底栏入口的「菜单海洋」结构是功能堆叠产物。

**决策**：v2 的 WebUI 设计**禁止以旧门户 IA 为蓝本**——而是以「§五.1 五类用户旅程」为蓝本。任何 reviewer 看到新 PR 提议引入「以旧菜单结构组织的页面」必须 reject。

**影响**：
- §五 P1–P10 是按旅程组织的，不是按子系统
- §十 K11 共享专区作为「跨域专题包」融入 P1，不再单独建子系统

#### D26 — 数据库分裂在 Phase 1 不强求合并

**触发**：旧平台 9 个独立 MySQL schema 是历史团队边界产物；强求合并会拖慢 Phase 1。

**决策**：
1. Phase 1 通过 adapter 单向只读消费旧 9 库
2. 新建实体必须在新 schema（PostgreSQL，`zw_brain` 库）中
3. 跨旧库 join 通过 Agent 编排在内存中完成，禁止写跨库 SQL
4. Phase 4 旧平台下线时一次性清算

---

## 附录 A — 数字漂移防御层（stat 块清单）

继承 v1 D17 / D20，并按 dev-rules `digital-clone-research.md §三` 的「禁止虚荣计数」原则裁剪：只有真正的设计契约（cap / SLO / 预算）才进 `dev-rules/.stats.json` 注册表。当前已注册的 stat：

| stat key | 当前值 | 角色 | compute（注册到 `dev-rules/.stats.json`） |
|----------|-------|------|------------------------------------------|
| `zwbrain.webui-pages-cap` | <!-- stat:zwbrain.webui-pages-cap -->10<!-- /stat --> | 设计上限 | awk §5.2 P-rows |

> K1–K12 / N1–N5 / 旧平台 38 服务等数字本身是描述性计数（非 cap/SLO），按反虚荣原则**不写为 stat 块**——表格行数自证，删掉数字段落仍完整传达意图。

---

## 附录 B — 旧→新功能映射全表

| 旧子系统 | 旧门户位置 | 新形态 | 备注 |
|---------|-----------|--------|------|
| 政务数据目录 | 顶层 | P1 + `catalog.search` Skill | K1 |
| 政务数据资源 | 顶层 | P1 + `resource.lookup` Skill | K1 |
| 融合服务 | 顶层 | P1「跨域专题包」 | K11 |
| 应用中心 | 顶层 | P8（智能体 / 技能市场） | K8 |
| 典型应用案例 | 顶层 | 融入 P9 | N3 |
| 通用服务 | 顶层 | 不重构 | N4 |
| 知识中心 | 顶层 | 不重构（静态站点足够） | — |
| 数字化运营 | 顶层 | K12 大屏 | 独立部署 |
| 数据共享系统 / 资源申请授权 | 底栏 | P2 + `resource.apply` / `approval.*` | K2 |
| 数据交换 | 底栏 | P3 + `exchange.fulfill` | K3 |
| 数据直达 | 底栏 | P4 + `national.deliver` | K4，国家通道兼容硬约束 |
| 数享链 | 底栏 | 区块链 adapter 接入 | §十二.2 |
| 数据异议处理 | 底栏 | P6 + `dispute.*` | K6 |
| 数据应用推广 | 底栏 | 不主动迁移 | adapter 只读 |
| 数据资源库 | 底栏 | 不重构（与 K1 重叠） | N1 |
| 数据分析系统 / 数据可视化 | 底栏 | K12 大屏 + Skill 调用 | — |
| 运维运营 / 运行管理 / 运行监控 | 底栏 | P9 + `dashboard.*` Skill | — |
| 绩效考核 | 底栏 | 不重构 | N2 |
| 合规督导 | 底栏 | P9 审计与合规回放 | K9 |
| 数据治理系统 / 集成 / 标准 / 元数据 / 质量 / 开发 / 建模 / 标签 / 安全 | 底栏 | Phase 1 不主动迁移；adapter 只读 | 触发再评估 |
| 数据资源管理 / 目录管理 / 资源管理 | 底栏 | P5 + `catalog.publish` / `resource.*` | K5 |
| 大数据计算与分析 / 存储与分析服务 | 底栏 | 通过 Skill 包装现有计算服务 | 不在大脑内复造 |
| 供需对接系统 | 底栏 | Skill 化（`supply.match`） | Phase 2 |
| 消息中心 | 底栏 | 复用 Kafka + `notify.*` Skill | — |
| 标准服务 | 底栏 | P10 配置之一 | — |
| 数据安全中心 | 底栏 | P10 配置之一 + L4 Tools 强制脱敏 | — |
| 工作台 | 顶层右上 | P7 我的工作台 | K7 |
| 指标平台 | （未在快照中显式可见） | 不重构 | N5 |

---

## 附录 C — 旧平台 38 服务清单（待 Phase 0 抽取报告注册）

完整清单参见 `old/代码信息抽取/代码信息抽取-38默认分支/All-Project_对外提供API汇总.md` 与 `All-Project_数据库表结构文档.md`。本文档不内嵌完整清单（避免漂移），由 Phase 0 落地的 `scripts/extract_legacy_inventory.py` 在 PR 中维护并由 `zwbrain.backend-services-legacy` stat 自动校核。

---

## 附录 D — 软→硬约束机械化映射（zw-brain 自包含权威）

### D.1 通用层（与 dev-rules 通用 preflight 对齐）

| ID | 软规则 | 机械检查 |
|----|-------|---------|
| G1 | 设计文档必须有 frontmatter | `dev-rules/scripts/check_approved_docs.py`（preflight § 7 R1） |
| G2 | `pending` + 已 ship 烟雾 | preflight § 7 R3 |
| G3 | `shipped` 必须有 `related_prs` 或 `related_commits` | preflight § 7 R4 |
| G4 | `approved_by: pending` 不许 land 到 main/master | preflight § 7 R5 |
| G5 | 分支命名规范 | preflight § 1 |
| G6 | dev-rules submodule SHA 远端可达 | preflight § 2 |
| G7 | `.cursor/rules/` 与 submodule 不漂移 | preflight § 3（`dev-rules/sync.sh --check`） |
| G8 | 散文档数值漂移 | preflight § 8（`dev-rules/sync-stats.sh --check`） |
| G9 | 跨文档外部引用悬空 | preflight § 14（`scripts/check_external_refs.py`） |
| G10 | 模块导入无副作用 | （项目 lint，详见各项目自行落地） |
| G11 | 输入安全基线（路径校验等） | （项目 lint） |
| G12 | 状态文件原子写 | （项目 lint） |
| G13 | 层间依赖（entry → command → domain → shared） | （项目 lint） |
| G14 | 契约文档自动生成且与代码一致 | `scripts/export_agent_contract.py --check`（preflight § 4） |
| G15 | `docs/preflight-debt.md` 列出未自动化检查 | preflight § 5 |
| G16 | LaunchAgent 跨机器同步 | `verify-rules.sh` |

### D.2 zw-brain 项目特有层

| ID | 软规则 | 机械检查 |
|----|-------|---------|
| Z1 | 模型推理走集团推理平台 SDK | preflight § 10（grep 禁词 + import 白名单） |
| Z2 | 大屏与主大脑解耦 | preflight § 11（`zw-brain-dashboard/` 不能 import `zw_brain.surface.webui`） |
| Z3 | adapter ↔ fixtures 覆盖 | preflight § 12（`scripts/check_fixture_coverage.py`） |
| Z4 | GATE-1 必须配套原型 | preflight § 13（`scripts/check_gate1_prototype.py`） |
| Z5 | 跨节引用幽灵编号检测 | `dev-rules/check-doc-xrefs.sh` |
| Z6 | AIHub 推送安全检查（无敏感数据） | `scripts/check_aihub_push_safety.py`（Phase 0 待落地，记入 preflight-debt） |
| Z7 | 审计同步写入失败必须熔断 | （单元测试断言 + 集成测试） |
| Z8 | Skill / Agent 契约对齐 AIHub 规范 | `scripts/check_skill_agent_schema.py`（Phase 0 待落地） |

> 凡新发现的"靠自觉"规则必须升级为 Z 系列条目并附机械检查；不能落到自动化的暂存 `docs/preflight-debt.md` 并设截止日期。

---

## 文档维护说明

- 本文档是 zw-brain 当前唯一权威架构基线；与本文冲突的旧文档（含 v1）以本文为准
- 修改本文必须走 product-dev.mdc 高风险路径（GATE-1 审批）
- preflight 通过后才能合并到 main
- 任何代码层改动若与本文冲突，**修代码不修文档**——除非通过 GATE-1 重新审批

