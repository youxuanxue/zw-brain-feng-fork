---
doc_id: design-zw-brain-architecture
status: approved
gate: approved
approved_by: xuejiao02 + 王红军（海若产品部业务方）
revision_date: 2026-05-20
authors:
  - 薛娇（产品研发负责人）
  - Claude Code (claude-opus-4-7) — 设计协作
related_docs:
  - docs/approved/zw-brain-data-model.md
  - docs/approved/zw-brain-roles.md
  - docs/approved/research-yibiaotong.md
  - docs/agent-runtime/product-integration-guide.md
  - docs/agent-runtime/agent-runtime-api-cn.md
  - old/代码信息抽取/代码信息抽取-27newbranch/All-Project_对外提供API清单.md
  - old/代码信息抽取/代码信息抽取-27newbranch/All-Project_外部SDK和接口文档(含项目交互关系).md
  - old/代码信息抽取/代码信息抽取-27newbranch/All-Project_数据库表结构文档.md
  - old/12-datastructure/
  - old/10示例数据/
  - old/html/
  - old/使用日志分析情况/
  - old/huiyijiangjie/20260417092236-转写_一体化大数据平台介绍-转写智能优化版-1.txt
  - old/20260519/平台系统角色菜单梳理v5.xlsx
related_prs: []
related_commits: []
phase_after_approval: Phase 0（先打通首条黄金链路 J1 找数→用数；再扩展 J2 挂数→维数；B1 后台支撑面与 Wave 2 三引擎并行）
---

# 政务数据大脑（zw-brain）AI 原生重构架构基线

> **权威性**：本文是 zw-brain AI 原生重构的**唯一权威架构基线**（spine）。
> **修订规则**：后续修订请在本文上原位演进；新增决策追加 D-编号（写入 `CLAUDE.md §决策记录`），新增架构主张追加 R-编号（写入本文 §十一）；业务流程类决策必须业务方 sign-off（R13）。
> **设计哲学**：以乔布斯产品哲学（聚焦、简洁、端到端体验、精品意识）与 OPC 哲学（杠杆最大化、流程极简、自动化优先）为收敛准绳。

## 〇、文档结构与阅读顺序

| 章节 | 回答的问题 | 读者 |
|------|-----------|------|
| 一、我们造什么 | 产品身份 + 用户场景 + 做/不做什么 + 成功标准 | 所有人（客户/业务方先读） |
| 二、设计哲学 | 为什么必须做减法 | 决策者 / 架构师 |
| 三、从证据得到什么结论 | 旧平台事实对新平台的含义；外部依赖边界 | 架构师 / 产品 |
| 四、AI-Native 重构原则 | AI 原生 5 条件 + 硬边界 | 架构师 / 工程 |
| 五、产品形态 | 旅程、页面与不进 IA 的清单 | 产品 / UX |
| 六、统一能力契约 | 五个消费面如何共用一套能力 | 工程 / 外部接入 |
| 七、架构与代码边界 | 运行时分层与代码分层 | 工程 |
| 八、外部能力集成模型 | 新能力的接入路径 | 工程 / 生态 |
| 九、数据模型 | 领域语义与 Phase 1 物理边界 | 工程 |
| 十、实施路线图 | 先做什么、后做什么、不做什么 | PM / 架构师 |
| 十一、关键设计主张 | R1-R15 设计主张 | 决策审计 |
| 附录 A | 旧能力簇 → 新能力面映射 | 产品 / 迁移 |
| 附录 B | 关键证据索引 | Reviewer |
| 附录 C | 软规则 → 机械检查映射 | 工程 / OPC 自检 |

---

## 一、我们造什么

### 1.1 产品身份

**zw-brain 是一个让政府部门之间共享数据的产品——"数据共享网关"。**

旧平台已经被各省客户磨练多年，骨架已经成型——**5 步骨干**：

```
编制 → 审核 → 发布 → 申请 → 交换
```

zw-brain 的工作是：
- 保留 5 步骨干（旧平台已验证的正确逻辑）
- 删除多年累积的冗余（18 项一级目录 → 8 页面，删 56%）
- 加上 AI 让定制不靠改代码（项目级流程/表单/推荐通过配置 + AI 辅助生成）

项目代号 `zw-brain`（"政务数据大脑"）继续沿用；产品身份是"数据共享网关"。

### 1.2 用户每天做什么

**J1 找数→用数**（每日高频，数据使用方）：

> 搜资源 → 申请 → 审批通过 → 凭据领取（API Key + curl 示例）→ 调用使用

**J2 挂数→维数**（部门提供方）：

> 在线编制目录 → 资源挂接 → 部门内审 → 平台发布 → 处理使用方异议

**B1 看全局→处异常**（后台支撑面，仅大数据局管理员/审计员）：

> 看共享是否合规 → 看异常是否被处理 → 看绕过流程的违规

普通用户每天只接触 J1+J2；B1 是合规底线，不是产品差异化重点。

### 1.3 不做什么

| 不做的事 | 原因 |
|---|---|
| 数据治理 / 清洗 / 质量 / 血缘 | 集团数据治理中心已经做 |
| 数据分类分级 / 敏感识别 / 脱敏 | 集团数据安全中心已经做 |
| 大屏 / 指挥中心 / 演示页面 | 没人天天看大屏，是演示功能 |
| 主题库 / 专题库 / 人口库 | 各部门线下建库 + 数据治理中心治理 |
| 运行监控 / 告警 / 巡检 | 集团统一运维监控平台 |
| 国家目录治理 / 国家直达 | 客户重心在本级共享 |
| 数据存证 / 区块链 | 可插拔 adapter；外链 down 不阻塞业务 |
| 标准服务 / 指标平台 / 应用案例 | 旧平台"几乎不用" |
| 脚本管理 / 通用服务 / 融合服务编排 | 同上 |
| 客户级后端 fork | 客户差异通过配置承接 |

完整不进 IA 清单见 §5.6。

### 1.4 差异化承诺

1. **项目级个性化不再改代码**——审批流/表单/推荐通过配置 + AI 辅助生成（§10.3 三引擎）
2. **人 + Agent 共用同一能力面**——后端只维护一套契约，5 消费面（WebUI/API/CLI/MCP/A2A）自动投影
3. **合规默认内建**——审计总线 / 模型调用集团推理平台 / 区块链 adapter
4. **单一 WebUI**——不是旧平台 7 个独立 SPA 拼接，避免角色困惑
5. **基于旧平台真相而非纸上设计**——18 项一级目录 → 8 页面的减法逐项可追溯到旧库 678 表 / 291 离线 HTML 页面 / 21 条业务反馈

### 1.5 成功标准

不是"代码上线"，而是：
- **客户上线后第 90 天的真实使用频度**：J1 找数→用数 是否每日有 10+ 次申请？
- **项目个性化交付速度**：新客户落地的流程定制/表单定制是否能在 1 周内完成（不改代码）？
- **角色困惑次数**：业务方培训后是否还需要回头问"我是哪个角色"？（目标：0）
- **演示 vs 真实使用占比**：大屏 / 国家通道这类演示功能的使用占总申请 < 10%

---

## 二、设计哲学

### 2.1 Jobs：产品围绕旅程，而不是围绕模块名

旧平台已经证明：菜单多、系统多、接口多，不会自然汇聚成好产品。旧平台代码面和数据库面极大，但真实调用高度集中在少数能力簇与少数高频链路上。

采用乔布斯式减法：

1. **先定义少数关键旅程，再决定页面、Agent、契约怎么配合**——不先列 30 个子系统再找"AI 化位置"
2. **对大多数 legacy 表面说不**。源码里存在、数据库里存在、菜单里存在，不等于该进入新产品
3. **复杂度留在后端与底座，不留在前台心智里**
4. **写操作必须看得见**——自然语言可以加速，但不能藏掉状态机、确认边界、责任边界
5. **AI 的价值在于减摩，不在于夺权**——不是"像聊天一样顺"，而是减少语义、跨步骤、证据阅读摩擦

### 2.2 OPC：一人可运转，才有资格成为默认方案

1. **新增功能默认不进主仓库**——长尾能力优先外部构建为能力包再注册
2. **只允许一个事实源**——Capability contract 是唯一事实源，WebUI / API / CLI / MCP / A2A 都从它投影，不接受五处手维护
3. **先打通一条真正可用的黄金链路，再补治理后台**
4. **自动化优先于流程化**——能靠 schema、preflight、契约生成解决的，不靠会议、约定、人工同步
5. **拒绝 per-tenant fork**——客户差异落在配置、多租户策略、外部能力包

### 2.3 合规与治理必须内建，但不能长成另一个"平台产品"

政务场景要求：
- 写操作可审计、可回放、可追责
- 外部监管接口与国家通道语义不能被智能化重写
- 模型调用必须统一经集团推理平台收口

正确落地方式：把合规与治理**嵌入主旅程**，而不是做成又一套需要用户理解和切换的产品层：
- 审计、策略、租户、权限、回执必须成为主流程默认能力
- 注册中心、能力市场、治理后台只服务管理员和平台运营者
- 普通用户的第一心智始终应是"我怎么找、怎么要、怎么拿、怎么追踪"

### 2.4 总哲学

```text
少数高频旅程
        +
单一能力契约
        +
外部长尾注册优先
        +
合规默认内建
        +
控制面保持纤薄
        =
政务数据大脑
```

---

## 三、从证据得到什么结论

> 本章只提炼那些会改变架构决策的结论。原始证据见附录 B。

### 3.1 旧平台真实拓扑：17 模块 / 678 张表 / 7 个独立 SPA

旧平台真实拓扑的数据级事实（基于 `old/12-datastructure/` 17 个 XML schema 的 `<table id=...>` 实测）：

| 旧 schema 模块 | 表数 | 业务领域 | 真实分量级 |
|---|---|---|---|
| `dsp_catalog` | 161 | 政务目录 + 资源 + 物化（data_resource_table / file / api）+ 共享审批 | **最大主线** |
| `dsp_basesubject` | 81 | 基础主题库（与政务目录并行的独立编制系统） | **并行主线** |
| `dsp_bsp` | 76 | IAM + 应用中心 + API 网关 + 用户/角色/权限/菜单 | 平台底座 |
| `dsp_metaresource` | 59 | 元数据 + 数据血缘（graphdb_node / graphdb_relation 5 表） | 含外部治理范围 |
| `dsp_connect` | 57 | 跨地市数据通道（48 张 dc_* 前缀）+ 国家直达（9 张非 dc_*） | **省市间真实主线** |
| `dsp_pipelines` | 50 | ETL 任务编排（batch_job / etl_meta） | 外部数据治理范围 |
| `dsp_monitor` | 50 | 服务调用 / 失败分析 / 告警工单 / 巡检 / 拨测 / 知识库 | **运行监控独立体系** |
| `dsp_require` | 29 | 申请审批 5 步流程（编制→校核→汇总→响应→反馈） | J1 主旅程核心 |
| `dsp_service` | 27 | API 服务网关 / 流控 / 黑白名单 | 平台底座 |
| `dsp_perform` | 16 | 数据质量评分（kpi_index_*） | 外部数据治理范围 |
| `dsp_app_center` | 15 | 应用注册 / 我的应用 | 平台底座 |
| `dsp_example` | 11 | 示例数据集成 | 辅助 |
| `dsp_pdf` | 10 | PDF 处理 | 辅助 |
| `dsp_handling` | 10 | 异议 5 维度（authz / catalog / content / resource / use）+ 2 流程辅助表（evaluate / process）+ 1 主表 + 2 辅助（消息 / flyway） | 强状态领域 |
| `dsp_block` | 10 | 数享链 / 数据存证 | 外部依赖 |
| `dsp_message` | 9 | 消息中心 | 平台底座 |
| `data_resource` | 7 | 资源主表 + 物化记录 + 治理任务 | J1/J2 共用 |

**真实拓扑结论**：

1. **真正的主线不是 6 个抽象"能力簇"**，是 17 个真实表簇。其中 3 个曾在抽象层未识别：基础主题库（81 表）、跨地市数据通道（57 表）、运行监控（50 表）。
2. **7 个独立前端 SPA**（基于 `old/old_codes/` 实测前端项目目录）：`portal-vue` / `app-center-web` / `catalog-front` / `data-operation-board-front` / `datasecurity-front` / `metricsmgr-front` / `standardservice-front` —— 旧平台不是单一 WebUI，是多 SPA 拼接。

### 3.2 真实业务价值密度：291 离线 HTML 页面 + 18 项一级目录

`old/html/` 下共 **291 个离线 HTML 页面**（18 个一级目录），分布如下：

| 一级目录（业务模块） | 页面数 | 占比 | 新平台中归属 |
|---|---|---|---|
| 运行监控 | **37** | 12.7% | §3.4 外部依赖（dsp_monitor 50 表对接集团运维监控平台） |
| 数据直达 | **36** | 12.4% | J1 子旅程 + §3.4 省市间数据通道 |
| 供需对接 | **36** | 12.4% | J1 供需对接子流程 |
| 目录管理-国家目录治理 | 27 | 9.3% | §5.6 独立子旅程，延后 P2 |
| 数据异议处理 | 24 | 8.2% | J1 异议子流程 |
| 融合服务 | 24 | 8.2% | §5.6 不进 IA |
| 目录管理 | 23 | 7.9% | J2 ✓ |
| 资源申请授权 | 21 | 7.2% | J1 ✓ |
| 资源管理 | 21 | 7.2% | J2 ✓ |
| 运行管理 | 18 | 6.2% | B1.1 / B1.2 |
| 数据应用推广 | 17 | 5.8% | §5.6 不进 IA |
| 数据交换 | 11 | 3.8% | J1 交付 |
| 工作台 | 8 | 2.7% | P1 ✓ |
| 政务数据服务门户 | 7 | 2.4% | 单一 WebUI 主入口 |
| 消息中心 | 3 | 1.0% | §3.4 外部依赖 |
| 应用中心 | 2 | 0.7% | §5.6 不进 IA |
| 绩效考核 | 2 | 0.7% | §5.6 不进 IA |
| _tools | 0 | 0% | 不适用 |

**真实价值密度结论**：

1. **运行监控 / 数据直达 / 供需对接** 是真实使用频度前三（37+36+36 = 109 页 ≈ 37%）—— §3.4 外部依赖承接。
2. **国家目录治理 27 页**虽多，但业务方原话"用得最少"—— §5.6 标 P2 优先级正确。
3. **18 项一级目录 → 8 页面是 56% 减法**——收敛逻辑见 §5.2.1。

### 3.3 真实强状态领域：6 态 catalog + 5 步申请 + 5 维度异议

| 领域 | 真实状态机 | 来源 | 处置 |
|---|---|---|---|
| **目录** | `data_catalog.status` 6 态（0 草稿 / 1 待审 / 2 审批通过 / 3 驳回 / 4 发布 / 5 下线）+ 2 应用层计算态（"国家通道转报中"/"撤销中"，由业务逻辑派生） | `dsp_catalog.xml:406-408` | §9.2 `Catalog` 标 6 态 + 2 计算态 |
| **共享类型** | `shared_type` 3 态（1 无条件 / 2 有条件 / 3 不予共享） | `dsp_catalog.xml:384-385` `data_catalog` | §9.2 `Catalog` 标 3 共享态 |
| **资源物化** | 3 种物化形式：`data_resource_table`（表）/ `data_resource_file`（文件）/ `data_resource_api`（接口） | `dsp_catalog.xml`（`data_resource_*` 系列） | §9.2 `Resource` 标 3 物化形式 |
| **申请审批** | 5 业务节点（编制 → 校核 → 汇总 → 响应 → 反馈）；XML `data_business.status` 实现为 0-6 共 7 态序列 | `dsp_require.xml:23-25` + 立项会议 | §9.2 `Application` 标 5 节点 |
| **异议处理** | 5 维度独立状态机（authz / catalog / content / resource / use）+ 2 张流程辅助表（evaluate / process） | `dsp_handling.xml`：`data_objection_authz`（54）/ `_catalog`（74）/ `_content`（89）/ `_resource`（132）/ `_use`（155）+ `_evaluate`（103）/ `_process`（120）= 7 张 | §9.2 `ObjectionCase` 标 5 维度 + 评价/过程流程链 |
| **目录编制双轨** | 政务目录 vs 国家扩展要素目录（不同 status 机 + 不同审批路径，`data_ext_elem_catalog_compile_task` 独立流程） | `dsp_catalog.xml` | §9.2 `CatalogModel` 标双轨 |
| **租户/区划** | 多级区划（省/市/区）+ 跨地市协作 | `dsp_bsp.xml` `pub_org` + `dsp_connect` dc_* | §9.2 `TenantOrg` 标多级 |

**强状态领域结论**：前台收敛可以激进（B1 后台 / 不做大屏），后台领域不能简化（6+2 态 / 3 共享态 / 5 节点 / 5 维度全保留）。

### 3.4 外部依赖证明：哪些必须保留为外部底座

旧平台反复依赖的身份、权限、监控、区块链、国家通道、推理平台等能力，说明新平台不应在内部重造。

**A. 平台底座类外部依赖（不复造）：**

| 外部底座 | 边界 |
|---|---|
| IAM / 组织 / 身份 | 认证继续由 IAF IAM 外部化；本地业务治理由 zw-brain Governance 承担；具体边界以 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准 |
| 集团推理平台 | 统一模型调用边界（preflight 段 10 强制） |
| 区块链 / 数享链 | 异步 adapter 接入；存证（用户 / 机构 / 系统 / 目录 / 资源 / 申请授权 6 类）能力包外部化，主仓不复造 `dsp_block` 10 表 |
| 国家平台 | 国家目录治理 / 国家数据直达 / 国家扩展要素编制 保持外部依赖 |
| 集团数据治理中心 | 数据清洗/质量/血缘**不是本平台能力**；本平台仅通过融合服务系统**注册并代理**治理后接口 |
| 集团数据安全中心 | 数据分类分级/敏感识别/脱敏策略/密钥管理 由集团数据安全中心承担，本平台 B1 后台仅为 `ROLE_SECURITY_ADMIN` 提供策略入口 |

**B. 旧平台真实分布与外部依赖：**

| 外部依赖类别 | 旧平台真实归属 | 处置 | 理由 |
|---|---|---|---|
| **消息中心** | `dsp_message` 独立模块（9 表） | **不复造，shared/notification 极薄封装对接集团统一消息** | 基础设施层 |
| **集团运维监控平台** | `dsp_monitor` 50 张独立表 | **不复造，对接集团统一运维监控** | 旧平台 37 页运行监控密度极高；新平台 B1.1/B1.2 仅消费监控数据 |
| **集团数据治理中心** | `dsp_pipelines` 50 + `dsp_perform` 16 + `dsp_metaresource` graphdb 5 = 71+ 表 | **不复造** | 71+ 表是真实规模 |
| **集团数据安全中心** | `db_meta_database_permission` 等脱敏隐私表分散 | **不复造，仅 B1.2 后台提供策略入口** | 由集团数据安全中心承担 |
| **数据存证 / 数享链** | 主体 `dsp_block` 10 张 + 跨地市 `dsp_connect` 48 张 dc_* 系列含存证 | **能力包外部化（adapter）；不在主仓 domain；外链 down 不阻塞业务** | 存证不止 dsp_block |
| **省市间数据通道** | `dsp_connect` 57 张表（48 dc_* + 9 国家直达） | **保持外部依赖；国家直达 + 跨地市统一为"省市间数据通道"adapter** | 运营层面延后立项 |

**注**：旧 BSP 内嵌的 API 网关子模块（`dsp_service` 27 表）+ 应用中心子模块（`dsp_app_center` 15 表）的本地业务治理由 zw-brain Governance 承担，IAM 由 IAF IAM 外部化；具体边界以 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准。

**C. 一表通（基层补报对接）的边界：**

立项会议红军强调"数据不一定来自基层"；一表通从默认路径**降级为可选预填 adapter**；`ROLE_ORGAN_OPERATER` 旅程改为"接到补差任务才出现"。详见 [docs/approved/research-yibiaotong.md](research-yibiaotong.md)。

### 3.5 真相导出的架构结论

| # | 结论 | 真相来源 |
|---|---|---|
| 1 | **内建只承接 J1 + J2 两条核心旅程，B1 后台仅作合规底线** | §3.2 页面密度 + §3.1 dsp_require 5 步流程主线 |
| 2 | **强状态领域全保留，前台收敛激进，后台领域不简化** | §3.3 6+2 态 catalog / 5 节点申请 / 5 维度异议 / 3 共享态 / 3 物化形式 / 双轨编制 / 多级区划 |
| 3 | **长尾能力默认外部化**（§3.4 6 类外部依赖 + §5.6 13 项不进 IA） | §3.1 dsp_monitor 50 表 / dsp_pipelines 50 表 / dsp_basesubject 81 表 — 真实运行但不该进主仓 |
| 4 | **控制面保持最小可用**（Capability Registry / Policy / Audit / Compatibility / Rollback） | 旧 dsp_bsp 76 张表 + dsp_service 27 张表是过度膨胀的反例 |
| 5 | **客户差异通过 R14 三引擎 + 多租户策略 + 外部能力包**承接，**不通过 fork 后端** | 立项会议红军原话"各项目门户、表单、流程都个性化；旧平台靠改代码 + 改数据库" |
| 6 | **旧平台前端的多 SPA 拼接是反模式**——zw-brain 必须单一 WebUI + 同一能力契约 | §3.1 旧 7 个独立 SPA → 单一 zw-brain-web/ |
| 7 | **旧平台 18 项一级目录 → 56% 减法是 Jobs 式正确** | §3.2 HTML 密度 + §5.2.1 收敛表 |

---

## 四、AI-Native 重构原则

### 4.0 AI 原生的五条成立条件

"AI 原生"只有五条同时成立时才成立：

1. **研发方式 AI 原生**：平台以 AI coding 为默认研发方式，规则、契约、检查都必须可被 Agent 理解、执行、校验。
2. **能力形态 AI 原生**：平台内部以统一 Capability 为最小单位，再投影到 WebUI / API / CLI / MCP / A2A。
3. **体验形态 AI 原生**：用户看到的首先是**结构化主旅程优先**的产品界面；AI 只作为嵌入式副驾介入少数关键摩擦点。
4. **扩展路径 AI 原生**：新增功能默认在外部 Agent 中构建，通过 AgentRuntime 声明式协议（`AGENT.yaml`）注册进入平台（详见 §八 / R15）。
5. **可配置化 AI 原生**：政务场景项目级个性化（**审批流、表单字段、推荐规则、门户布局**）是基本盘；**真正的 AI 原生差异化是把"改代码 / 改库"以前必须做的事，提升为"用自然语言生成 schema → 平台运行可配置物"**（§10.3 三引擎；R14）。

### 4.1 Capability 是唯一中性最小单位

平台内部真正稳定的最小单位是 **Capability**。

每个 Capability 至少回答：
- 它做什么
- 输入 / 输出是什么
- 谁能调
- 在哪个租户范围内调
- 是否需要人工确认
- 调用后落什么级别的审计
- 由什么执行绑定完成
- 能暴露给哪些消费面

页面、REST、CLI、MCP、A2A 都只是同一 Capability 的投影。

### 4.2 五个消费面共享契约，但不要求同速成熟

- **契约层必须统一**
- **投影层自动生成**
- **生产级硬化顺序服从真实需求**

WebUI / API / CLI 是首波必须做实的消费面；MCP / A2A 必须从同一契约投影出来，但可随 Agent 真实接入需求逐步硬化。绝不允许因为追求协议对称而推迟主旅程交付。

### 4.3 核心高频内建，长尾默认外部化

| 层级 | 定义 | 默认去向 |
|------|------|----------|
| Core | 跨项目高频、直接构成主旅程 | 平台内建 |
| Common | 有复用价值，但不必进入主导航 | 后台入口 / 可选能力 |
| Long-tail | 项目特有、低频、试验性、行业特化 | 外部 Agent 经 AgentRuntime AGENT.yaml 注册 |

### 4.4 自然语言只负责加速，不负责越权提交

自然语言强介入**四类**关键摩擦点：

- **语义入口**：把一句话转成检索条件、申请草案或字段候选值
- **上下文编排**：在发现 → 申请 → 审批 → 交付之间保留上下文，减少重复填写与重复理解
- **证据摘要**：把审计、异常、异议、交付状态转成可读的判断辅助
- **配置生成**：把项目个性化需求用自然语言生成可执行 schema（审批流节点 + 选人规则 / 表单字段 + 校验 / 推荐过滤规则），由管理员在结构化配置页确认并入库——**不是直接生效**

自然语言不能承担：
- 替代结构化页面本体
- 直接触发责任性写操作
- 绕过审批与确认
- 替代关键状态展示
- 让用户失去对自己当前处于哪一步的感知
- **直接修改生产配置**（配置生成必须走管理员"草稿 → 预览 → 确认入库"三步）

涉及申请、审批、交付、共享、下线、跨租户访问等写操作的 Capability，必须显式声明 `human_confirmation_required`，并在结构化页面内完成确认与回执留存。

**一句话原则**：AI 原生不是"全页面 AI 化"，而是"关键摩擦点 AI 化 + 项目个性化可配置化"；主工作流仍必须结构原生。

### 4.5 控制面必须存在，但要保持纤薄

Registry / Policy / Audit / Compatibility / Rollback 这些控制面能力遵循四条约束：

1. 只保留负载真正决策的字段与状态
2. 不为"未来也许会用到"提前造复杂审批流、版本矩阵、市场前台
3. 所有消费面的投影从同一 registry/contract 派生
4. 普通用户不需要理解控制面概念

### 4.6 canonical model 优先，但物理边界分波次落地

- 在概念层，`CatalogModel`、`Catalog`、`Resource`、`Application`、`ApprovalTask`、`DeliveryTask`、`ObjectionCase`、`AuditEvent`、`CapabilityPackage`、`TenantOrg` 都是 load-bearing 语义
- 在 Phase 1 物理落地层，不必把每个概念都拆成独立服务、独立子系统、独立前台面
- 先把最影响主旅程的聚合边界做对，再按真实压力把概念升格

### 4.7 代码层服从项目既有分层纪律

运行时可以谈 Surface / Experience / Control Plane / Domain / Runtime / External，但代码组织不能因此膨胀成一层一个王国。

本项目代码层仍服从：

```text
entry → command → domain → shared
```

Capability、Registry、Policy、Audit 等实现都必须回落到这套代码纪律里。

---

## 五、产品形态

### 5.1 两条核心旅程 + 一个后台支撑面

产品形态收敛为 **2 核心旅程 + 1 后台支撑面**：

| 类型 | 名称 | 用户意图（人话） | 主要角色 | 收敛旧入口 | 备注 |
|------|------|--------------|---------|---------|------|
| **J1 找数→用数**（核心旅程） | 我要这份数据来做这件业务 | `ROLE_ORGAN_OPERATER` 发起 + `ROLE_ORGAN_MANAGER` 部门审 + `ROLE_BUSIAUDIT` 平台受理/审批 | 资源发现 + 申请审批 + 交付 | 含供需对接子流程 + 异议处理子流程；明示有条件 vs 无条件共享审批分支 | 每日高频；AI 落点最密集 |
| **J2 挂数→维数**（核心旅程） | 我的数据可被发现可被申请可被授权 | `ROLE_ORGAN_OPERATER` 编制/挂接 + `ROLE_ORGAN_MANAGER` 部门审 + `ROLE_BUSIAUDIT` 平台复核/发布 | 编目/上架/发布/异议 | 含发布时重复率检测提醒（不硬拦） | 部门提供方日常；Wave 1 闭环 |
| **B1 看全局→处异常**（后台支撑面，非旅程） | 让全局可用、异常可追、合规可证 | `ROLE_BUSIAUDIT` + `ROLE_SECURITY_AUDIT` + `ROLE_SECURITY_ADMIN` + `ROLE_SYSTEM` | 合规运营 + 平台接入 | **后台支撑面**：少数管理员/审计员使用；不进普通用户主导航 |

**关键边界**：

- **"生态接入"是 B1 内的后台能力**（仅管理员使用），不是普通用户旅程
- **国家数据直达**作为 J1 下的独立子旅程（业务方原话"用得最少"，延后立项；详见 §10.4）
- **国家扩展要素目录编制**作为 J2 下的独立子旅程（客户重心在本级共享，延后）
- **编号空间区分**：`J1/J2` = 用户核心旅程；`B1` = 后台支撑面；`R1-R15` = 架构约束设计主张（§11）；`D-编号` = GATE 后决策（写入 CLAUDE.md）

### 5.2 WebUI 核心页面

产品界面收敛为 **8 个主页面**，硬上限 `≤<!-- stat:zwbrain.webui-pages-cap -->8<!-- /stat -->`。普通用户主心智应聚焦核心旅程页面（P1-P5/P7），后台支撑面（B1.1 / B1.2）仅管理员访问。

| 页面 | 服务的旅程 / 后台面 | 说明 |
|------|--------------------|------|
| P1 工作台 | 全局入口（所有用户） | **首屏=今日待办**（不是菜单树）；按 超时 > 临期 > 普通 排序；中央=进行中事项（近 7 天）；右侧=推荐 + 通知 |
| P2 资源发现 | J1 找数→用数 | 检索、筛选、目录展开、资源详情；UI 不堆工程术语 |
| P3 申请 / 审批 / 跟踪 | J1 找数→用数 | 发起、补件、审核、回执、进度；含有条件/无条件共享审批分支 |
| P4 交付 / 交换 / 直达 | J1 找数→用数 | 交付渠道、任务状态、结果回执；**必含凭据领取页**（授权码 / API Key + curl/Python/Java 调用样例 + 配额 + 监控入口） |
| P5 提供方管理 | J2 挂数→维数 | 编目、上架、发布、异议处理；发布时重复率检测提醒（不硬拦） |
| P7 共享专区 / 专题包 | J1 找数→用数 + J2 挂数→维数 | 主题化聚合与订阅入口 |
| B1.1 合规与运营 | B1 后台支撑面 | 审计回放、统计、异常、追责；仅管理员/审计员 |
| B1.2 平台接入与扩展中心 | B1 后台支撑面 | 仅管理员；能力包审核注册、外部接入配置、暴露矩阵与租户策略 |

### 5.2.1 旧平台 18 项一级目录 → 新平台 8 页面的真实收敛逻辑

> 让 8 页面的减法透明可追溯——基于 `old/20260519/平台系统角色菜单梳理v5.xlsx` + `old/html/` 291 离线 HTML 分簇 + `old/old_codes/portal-vue` 路由事实。

| 旧平台菜单（实有项） | 旧 SPA 路由 | HTML 密度 | 处置 | 收敛动作 |
|---|---|---|---|---|
| 目录管理 | portal-vue `/catalog` | 23 | **P2 资源发现 + P5 提供方管理** | ✅ 保留+合并 |
| 资源管理 | portal-vue `/resource` | 21 | **P5 提供方管理 + P4 交付** | ✅ 保留+合并 |
| 供需对接 | dsp-require | 36 | **J1 供需对接子流程** | ✅ 保留并扩充 |
| 资源申请授权 | dsp-require | 21 | **P3 申请/审批/跟踪** | ✅ 保留 |
| 数据异议处理 | dsp-objection-handling | 24 | **J1 异议处理子流程**（在 P3/P5 嵌入） | ✅ 保留 |
| 共享专区 | portal-vue `/zones` | （并入门户） | **P7 共享专区** | ✅ 保留 |
| 目录管理-国家目录治理 | dsp-cascade-platform | 27 | **§5.6 延后子旅程（P2 优先级）** | ⏸️ 占位延后 |
| 数据直达 | dsp-cascade-down | 36 | **§3.4 省市间数据通道 adapter + 延后** | ⏸️ 占位延后 |
| 运行监控 | portal-vue `/digital-operation` | 37 | **§3.4 外部依赖：集团统一运维监控平台** | ❌ 不复造 |
| 数据安全中心 | datasecurity-front | （独立 SPA） | **§3.4 集团数据安全中心外部依赖** | ❌ 不复造 |
| 数据治理（清洗/质量/血缘） | data-operation-board-front | （独立 SPA） | **§3.4 集团数据治理中心外部依赖** | ❌ 不复造 |
| 标准服务 / 指标平台 | standardservice-front / metricsmgr-front | 2 + 0 | **§5.6 #1 #2 #16 不进 IA** | ❌ 不复造 |
| 应用中心 / 应用案例 / 通用服务 | app-center-web | 2 | **§5.6 #11 #12 不进 IA** | ❌ 不复造 |
| 融合服务编排 | independent | 24 | **§5.6 #12 不进 IA** | ❌ 不复造 |
| 基础主题库（basesubject） | dsp-basesubject | 81 表 | **§5.6 #13 不进 IA**（基于旧库 81 表事实） | ❌ 不复造 |
| 消息中心 / 工单管理 | message-center | 3 | **§3.4 外部依赖**（消息独立 + 工单走异议） | ❌ 不复造 |
| 平台运维配置 | dsp_bsp 后台 | （后台） | **B1.2 接入扩展中心**（仅管理员） | ✅ 后台 |
| 合规督查 / 审计 | independent | 18 | **B1.1 合规与运营**（仅管理员/审计员） | ✅ 后台 |
| 搜索结果页（search-result） | portal-vue `/search-result` | （并入资源发现） | **合并入 P2 资源发现的搜索结果区** | ✅ 合并 |
| 知识中心 | portal-vue `/knowledge-center` | （并入合规） | **合并入 B1.1 合规与运营的工单/知识 panel** | ✅ 合并 |

**收敛逻辑总结**（20 个旧入口的收敛动作分布）：

- ✅ **保留**（进 8 页面 P1-P5/P7 或 B1.1/B1.2，含合并）：10 项
- ❌ **不复造**（外部依赖或不进 IA）：8 项
- ⏸️ **占位延后**：2 项（国家通道）

**Jobs 式判断**：旧平台 18 项一级目录 + 7 个独立 SPA → zw-brain 8 页面 + 单一 WebUI，**真实减法 56%**。客户日常用的就是 J1+J2 这两条链。

### 5.3 嵌入式自然语言加速器

必要的核心页面内嵌自然语言输入，但其职责严格限定为减摩组件：

- 把一句话解析成检索条件、预填字段、跨步骤跳转建议
- 在结构化页面中完成确认
- 让人和 Agent 在同一上下文下协作
- **生成配置草稿**：管理员侧由自然语言生成审批流节点 / 表单字段 / 推荐过滤规则的 schema 草稿，结构化预览后入库；不直接修改生产配置

最适合内嵌 AI 的页面类型：
- 资源发现页（语义入口）
- 申请形成页（语义入口 + 上下文编排）
- 审批判断页（证据摘要）
- 合规调查页（证据摘要）
- 管理员配置后台（审批流可视化编辑器 / 表单 schema 编辑器 / 推荐规则编辑器）

最不适合让 AI 成为主交互的页面类型：
- 责任性确认页
- 高确定性配置生效页

**一句话原则**：自然语言负责缩短路径，不负责吃掉页面；AI 只减摩，不夺主；AI 可生成配置草稿，但生效必须经过结构化确认。

### 5.4 AI 体验设计原则清单

#### 5.4.1 总原则

1. **关键摩擦点 AI 原生，主工作流结构原生。**
2. **AI 是副驾，不是入口本体。**
3. **AI 减摩，不夺权。** 不能代替人提交、审批、授权、下线、跨租户放行。
4. **结构优先于对话。** 任何 AI 输出，最终都应落回结构化字段、状态、回执。

#### 5.4.2 必要性判据

只有满足以下三类之一，才值得上 AI：
- 用户不会说系统语言，只会说业务语言；
- 用户必须跨多个步骤反复搬运上下文；
- 用户面对大量证据、日志、审计信息，阅读成本高。

**硬判据**：去掉 AI 后，这个页面仍应能完成主任务。

#### 5.4.3 合理性判据

- AI 必须贴着当前动作出现
- AI 先给中间结果，不先给抽象评价
- AI 结论必须带证据或依据
- AI 的视觉权重必须低于主任务内容
- AI 的不确定性必须可见

#### 5.4.4 精准落点

每页 AI 助手都带一条**反约束**——划清"AI 减摩 vs AI 越权"的边界：

- **P2 资源发现**：搜索上下文助手（意图解析、缺口追问、推荐理由）；**不替代目录树、筛选器与资源详情**
- **P3 申请形成**：申请草拟助手（预填字段、补件建议、草拟摘要、审批风险预估）；**不自动提交，不自动确认责任字段**
- **P3 审批判断**：依据阅读助手（归纳依据、提示风险、反事实）；**不替审批人点通过 / 驳回 / 补正**
- **P4 交付与交换**：状态解释助手（解释阶段、异常原因、影响范围）；**不替代时间线、回执与任务状态本体**
- **B1.1 合规与运营**：调查摘要助手（证据分类、事件归纳）；**不覆盖原始审计证据，也不替代人工调查结论**
- **B1.2 平台接入后台**：审核缺项助手（标缺项、草拟退回意见）；**不自动批准、不自动发布**

#### 5.4.5 一票否决项

出现以下任一情况，应判定为 AI 体验失真：
- 首页以聊天框作为默认主入口
- AI 替代结构化页面或状态机
- AI 直接触发责任性写操作
- 审批/交付/合规结论没有证据支撑
- 用户看不懂当前步骤，只能靠 AI 才知道自己在哪
- AI 组件压过表格、字段、时间线、回执本体
- 每页机械性塞一个 AI 模块，只为"看起来 AI 原生"

#### 5.4.6 评审 AI 组件时的六个问题

任何新增 AI 组件在评审前都必须用这六个问题自检（任一回答失格 = 该组件不该上）：

1. 这个 AI 组件到底在减少哪一种摩擦？（语义 / 上下文搬运 / 证据阅读 / 配置生成）
2. 去掉它，主任务还能不能完成？（答否 = AI 抢了页面本体，违反 §5.4.1 #2）
3. 它有没有让责任边界变模糊？（写操作的人是谁，必须始终清晰）
4. 它的输出能不能落回结构化字段、状态、回执？（不能 = AI 输出是漂浮文本，违反 §5.4.1 #4）
5. 它的结论有没有证据来源？（无来源 = AI 在评价，不在辅助）
6. 它是在帮用户完成任务，还是在向用户解释系统？（后者 = 真正要修的是页面，不是加 AI）

### 5.5 不再复刻旧门户的信息架构

legacy 门户的信息架构只能作为遗留能力索引，不再作为新 WebUI 导航蓝本。新导航依据：高频旅程 / 角色职责 / 确认边界 / 合规边界 / Agent 可消费能力面。

**UI 工程术语黑名单（R12）**：以下词汇**禁止出现在前端 UI**：`package` / `projection` / `capability` / `write-with-audit` / `register-version` / `apply-tenant-policy` / `reconcile-receipt` / `submit-evidence` / `policy_decision` 等。改用业务语义：`capability_call` → "操作"；`projection` → "视图 / 统计"；`package` → "能力包"（仅在 B1.2 接入中心可用）；`policy_decision` → "审批结果"。

### 5.6 什么不进主导航

**不进 IA 13 项**（业务方 sign-off + 基于旧库真实分布）：

| # | 旧能力 | 处置 | 反馈来源 |
|---|---|---|---|
| 1 | 指标平台 | 完全不进 IA，外部系统 adapter（§3.4 已是外部依赖） | 业务反馈 #16 |
| 2 | 脚本管理 | 完全不进 IA（应用中心内部能力） | 业务反馈 #12 |
| 3 | 目录分级授权 | 本期**不做**（部门写 + 读全开放；业务方原话"可忽略"） | 业务反馈 #10 |
| 4 | 代理授权申请 | 已无，删除所有引用 | 业务反馈 #7 |
| 5 | API 白名单 / 限流配置 | 独立"运行参数维护"页面（运维角色），**非审批依据** | 业务反馈 #9 |
| 6 | 牵头 / 关联部门授权耦合 | 改为目录元数据字段 + `tag_lead_dept` 标签位（仅 2 项菜单），与授权链解耦 | 业务反馈 #11 |
| 7 | 数据采集质量检测 | 仅留 B1 后台旁路抽查（"长期无人申请的目录"诊断）；数据治理不进本产品 | 业务反馈 #14 |
| 8 | 国家数据直达独立流程 | 独立子旅程（本期不实施，IA 占位；优先级 P2） | 业务反馈 #13 |
| 9 | 国家扩展要素目录编制 | 独立子旅程（本期不实施；优先级 P2） | 业务反馈 #18 |
| 10 | 工单管理（旧 `dsp_handling` 10 表） | 不长工单子系统；异议走 J1 异议子流程 / 补差走 J2 | 旧平台真实归属对照 §3.4 |
| 11 | 数据资源库（主题库/专题库/人口库/法人库） | 不复造；由各部门**线下建库 + 数据治理中心治理**形成 | 立项会议红军 02:06:36 |
| 12 | 融合服务编排 / 通用服务 / 应用案例 | 不重构（旧平台"几乎不用"，重激活需走 product-dev.mdc 流程） | 立项会议红军多处确认 |
| 13 | 基础主题库（`dsp_basesubject` 81 张独立表） | 不复造；归外部数据治理中心或客户线下编制 | 旧平台真实存在的并行编制系统，与政务目录平行（基于 `dsp_basesubject.xml` 81 表事实） |

---

## 六、统一能力契约

### 6.1 一个 Capability，五个消费面

| 消费面 | 目标用户 | 首波优先级 |
|--------|---------|-----------|
| WebUI | 人类用户 | 高 |
| API | 第三方系统 | 高 |
| CLI | 运维 / Headless / 后台 Agent | 高 |
| MCP | IDE / Claude / Cursor 类 Agent（外部 Agent 经 AgentRuntime 声明式协议 `AGENT.yaml` 暴露） | 中 |
| A2A | 外部 Agent 平台（经 AgentRuntime 声明式协议暴露与调用） | 中 |

"中优先级"不是说 MCP / A2A 不重要，而是说**首波不为了协议对称牺牲交付顺序**。

### 6.2 Capability 最小契约

字段数量不是最重要的，重要的是这份定义必须足以让任一消费面回答四个问题：**能不能调 / 怎么调 / 何时要人确认 / 调完会留下什么回执与审计**。

```json
{
  "slug": "resource.apply",
  "version": "1.0.0",
  "input_schema": {},
  "output_schema": {},
  "tenant_scope": "tenant|cross-tenant-approved",
  "auth_policy": "user|service|agent",
  "human_confirmation_required": true,
  "audit_class": "write-critical",
  "execution_binding": "builtin|registered-package|adapter-call",
  "config_change_class": "live|preview|draft",
  "compatibility": ["webui", "api", "cli", "mcp", "a2a"]
}
```

> 字段说明：
> - `config_change_class`（D30 retrofit / R14 联动）：默认 `live` 立即生效；`preview` / `draft` 仅 Wave 2 三引擎走「草稿→预览→管理员入库」流时使用。由 `validate_manifest` 强制校验。
> - `compatibility`：实际 manifest 字段名（早期 spec 误用 `exposure`，2026-05-24 D30 retrofit 同步更正）。

**与 AgentRuntime `AGENT.yaml` 的关系**：`Capability` 是 zw-brain 内部最小单位（描述「平台能做什么」）；`AGENT.yaml`（`anp-agent/v1.2`）是外部 Agent 声明式协议（描述「外部 Agent 需要什么能力 + 如何被运行」）。外部 Agent 通过 `AGENT.yaml` 中的 `tools` / `mcp_servers` / `skills` / `permissions` 段消费 zw-brain Capability；Registry 维护映射并裁剪有效工具集。两者不可互换（详见 §八 / R15）。

### 6.3 投影原则

- WebUI：把 Capability 组装成页面与旅程
- API：把 Capability 暴露为 REST / OpenAPI
- CLI：把 Capability 暴露为命令与参数
- MCP：把 Capability 投影为工具 / 资源
- A2A：把 Capability 暴露为可发现的 agent skill / action

### 6.4 权限、租户、策略、审计必须内嵌在 contract 中

统一契约不仅描述"做什么"，还必须描述：谁能调 / 在哪个租户范围内调 / 是否需要审批 / 调用后落什么审计 / 是否可被外部消费面暴露。

### 6.5 契约生成原则

文档、OpenAPI、CLI spec、MCP manifest、A2A card 都应由同一 registry / contract 派生，而不是人工分别维护。

**自动生成本身就是产品边界的一部分**：手维护多个投影是 OPC 模式禁止的反模式；任何一处投影若需要"手改"，先回头修 registry / contract，再让生成器输出。

### 6.6 Registry 边界与能力预算（P0-05 落地）

能力 registry 不是"无限注册的容器"，而是与 WebUI §5.2 8 页面 cap 同等地位的**产品边界**。每条 manifest 必须在 `product_scope` 自报旅程归属与状态：

| 字段 | 取值 | 含义 |
|------|------|------|
| `product_scope.journey` | `j1` / `j2` / `b1` / `infra` / `external` / `national` | 该能力服务于哪条 §5.1 旅程或后台支撑面；非核心旅程必须显式声明 |
| `product_scope.status` | `live` / `deferred:wave-{1..4}` / `external` | `live` 才进 5 消费面投影；`deferred` 与 `external` 由 `export_agent_contract.py` 机械过滤掉，UI 不可达 |

**Per-journey live capability 预算（drift = registry 边界变更）：**

- J1 找数→用数：`<!-- stat:zwbrain.capability-budget-j1 -->65<!-- /stat -->` live capabilities
- J2 挂数→维数：`<!-- stat:zwbrain.capability-budget-j2 -->43<!-- /stat -->` live capabilities
- B1 后台支撑面：`<!-- stat:zwbrain.capability-budget-b1 -->60<!-- /stat -->` live capabilities
- Infra 底座（鉴权 / 审计 / actor / adapter health）：`<!-- stat:zwbrain.capability-budget-infra -->17<!-- /stat -->` live capabilities

这 4 个数字写进 `scripts/.stats.json`，preflight 段 8 自动校验。任意一项 drift（无论是增是减）都意味着 §5.1 旅程范围或底座边界被改动，**必须走 GATE 决策**，不允许悄悄漂移。

**已发现禁区前缀的回潮防护（preflight 段 22）：**

`scripts/check_capability_boundary.py` 按 skill_id prefix 把 manifest 分类到**当前已观察到曾出现 builtin 越界**的 7 类禁区前缀（血缘 / 质量 / 运维监控 / 工单 / 国家通道 / 国家直达 / 标准服务）。判定规则：

| skill_id prefix / 形态 | 归属禁区前缀 |
|---|---|
| `metadata.lineage.*`（仅此前缀，不含 skill_id 其它位置的 `lineage` 段） | §1.3 血缘 |
| `quality.*` / `ops.catalog.quality.*` | §1.3 质量 |
| `ops.gateway.*` / `ops.shift_handover.*` / `ops.exchange.diagnose` | §1.3 运维监控 |
| `ops.ticket.*` | §1.3 工单（外部消息中心） |
| `adapter.national.*` | §1.3 国家通道 |
| `direct_access.*` | §1.3 国家直达 |
| `standard.*` | §1.3 标准服务 |

判红条件：任一 manifest 同时满足 `product_scope.status == "live"` **且** `execution_binding == "builtin"`。

**作用边界（避免误解）：**

- 段 22 只防"主 zw-brain 自建 builtin"回潮，**不阻止通过 `execution_binding == external_capability` 桥接外部系统消费同域能力**——例如 `external.lineage.graph.build` / `external.quality.scan.execute` / `external.notification.workorder.dispatch` 均为合法形态，正是 §1.3 "集团中心已做" 的消费桥接。血缘禁区**刻意不用「skill_id 含 `lineage` 段」宽匹配**：`external.lineage.*` 等桥接能力靠 `status` + `execution_binding` 区分，段 22 只锁 `metadata.lineage.*` 曾出现的 builtin 回潮。
- 段 22 是**事后防回潮**，把 P0 已清理的 27 个越界 manifest 锁死；**不是 §1.3 完整 10 类的事前防违建**。伪装成核心旅程（j1/j2/b1/infra）的新建 builtin 无法靠 prefix 拦下，那属架构约束「能力扩展唯一路径 = Skill 注册」+「高频核心走 builtin、长尾默认外部化」+ reviewer 判断范畴。
- §1.3 出现新的 builtin 越界前缀时（例如未来若有 `dashboard.*` / `desensitize.*` 等），需同步更新 `check_capability_boundary.py::FORBIDDEN_ZONES`。

当前基线扫描结果：200 manifests / 27 落入禁区前缀 / 0 live+builtin 越界（13 `external` + 14 `deferred` + 1 `external_capability`）。任何把禁区 manifest 状态改回 `live + builtin` 的 commit 必然被段 22 拦下；回归保障由 `tests/test_capability_boundary.py` 自动化覆盖（6 个场景）。

**与 §7.3 webui-pages-cap 的关系**：8 页面 cap 是 UI 层"什么进主导航"的硬边界；本节的旅程预算 + 段 22 禁区前缀回潮防护是 capability 层"什么能成为 builtin live 能力"的硬边界。两者一上一下，共同构成产品形态的机械化执行面，杜绝旧平台"全菜单全能力"的形态复刻。

---

## 七、架构与代码边界

### 7.1 运行时视图

```text
L0 Surface
  WebUI | API | CLI | MCP | A2A

L1 Experience
  Structured Page Flow | Human Confirmation | Context Retention | NL Accelerator

L2 Control Plane
  Capability Registry | Policy Engine | Audit Bus | Exposure Router

L3 Domain Workflows
  Catalog | Resource | Application | Approval | Delivery | Objection | Compliance

L4 Runtime & Adapters
  Built-in Skills | Registered Packages | Adapter Skills | Tool Bindings | AgentRuntime（anp-agent/v1.2）

L5 Data / External
  Canonical DB | Audit Store | Registry Store | Legacy Adapters | IAM | 推理平台 | 区块链 | 国家平台 | 对象存储 | 消息
```

### 7.2 代码视图必须回落到项目既有分层

| 代码层 | 职责 |
|-------|------|
| `entry` | WebUI / API / CLI / MCP / A2A 的入口与适配 |
| `command` | Capability 调度、用例编排、确认边界、投影组装 |
| `domain` | 领域模型、状态机、策略约束 |
| `shared` | 审计、鉴权、推理、存储、注册、外部 SDK 封装 |

明确反对两种做法：
- 为每个消费面复制一套纵向实现链
- 为每个概念新建一个"中心"与一个顶级目录

### 7.3 依赖约束

允许：
- `entry → command`
- `command → domain / shared`
- `domain → shared`

禁止：
- 页面直接绕过 command / policy / audit 写数据
- 注册能力包直接读写 canonical DB
- domain 反向依赖 legacy schema 命名与旧门户结构
- WebUI / API / CLI / MCP / A2A 各自实现各自的业务逻辑

### 7.4 控制面的最小可用要求

- 注册 / 启停
- 暴露范围控制
- 版本与来源可追溯
- 权限 / 租户 / 审计边界声明
- 回滚目标声明

在首条黄金链路落地前，不要求做：面向普通用户的"能力市场"前台 / 复杂多级评审工作流 / 全协议全矩阵兼容后台 / 大而全的生态运营页面。

---

## 八、外部能力集成模型

### 8.1 AgentRuntime 声明式协议是外部能力接入的唯一桥接面

外部 Agent 不论由 ANP 平台、Cursor 还是其他工具构造，进入 zw-brain 必须以 AgentRuntime 声明式协议（`anp-agent/v1.2` 的 `AGENT.yaml`）形态声明并通过 AgentRuntime 执行内核运行。

- 上游构造来源是异构的：ANP 平台、Cursor、手写、第三方 Agent IDE
- 桥接面是唯一的：`AGENT.yaml` + AgentRuntime；不通过 AgentRuntime 的私有协议一律拒绝接入

**外部能力生态是平台的扩展机制，不是普通用户的主要产品心智。**

规范源（唯一）：`docs/agent-runtime/product-integration-guide.md` + `docs/agent-runtime/agent-runtime-api-cn.md`。

### 8.2 zw-brain 对外部 Agent 的产品决策

> **单一事实来源**：`AGENT.yaml` schema、字段语义、`trust_level` 三级定义、Embedded SDK / Standalone HTTP 集成方式、鉴权 / context / workspace 模式等**协议规范**由 `docs/agent-runtime/*` 承载。本节只声明 zw-brain 侧的产品决策。

| 决策项 | zw-brain 选择 | 原因 / 兜底 |
|---|---|---|
| 声明形态 | `anp-agent/v1.2` `AGENT.yaml`（唯一） | 不接受其它 schema |
| `trust_level` 默认 | 外部 Agent = `untrusted`；`verified` 由 B1.2 管理员审核升级；`platform` 仅限 zw-brain 内置 Agent | 政务场景默认收紧；Registry 可覆盖收紧、不可放宽 |
| 模型 provider | 必须指向 zw-brain 集团推理平台 gateway | preflight 段 10 强制 |
| 运行形态 | Phase 1 默认 Embedded SDK；Standalone HTTP 留 Wave 3+ 评估 | 与 R4「控制面纤薄」一致 |
| 鉴权模式 | `static_api_key` 或 `trusted_gateway`；禁用 `none` | 生产 readiness gate 阻断 |
| 多租户模式 | `tenant_id="sd-default"` 单租户；不启用 `tenant_mode=multi` | 与默认租户模型对齐 |
| Context / Memory | `regulated_minimal` 或 `session_memory`；默认禁用 memory write | 合规优先 |
| `admin:runtime` scope 映射 | 仅授予 `ROLE_SYSTEM` | 与 7 角色码体系对齐（R10） |

### 8.3 Registry 最小字段

| 字段 | 含义 |
|------|------|
| `slug` / `version` | 稳定标识 |
| `package_kind` | skill / agent / tool / bundle |
| `source_type` | builtin / imported / external-register |
| `review_status` | draft / pending / approved / disabled / archived |
| `tenant_scope` | 可见范围 |
| `auth_policy` | 调用边界 |
| `audit_class` | 审计等级 |
| `human_confirmation_required` | 是否要求人工确认 |
| `compatibility` | 支持哪些消费面 |
| `runtime_binding` | 实际执行绑定 |
| `rollback_target` | 回滚版本 |
| `runtime_spec_version` | 必须为 `anp-agent/v1.2`，其它 schema 拒绝注册 |
| `agent_yaml_ref` | AGENT.yaml 在能力存储中的引用 |
| `trust_level` | `platform` / `verified` / `untrusted`（从 AGENT.yaml 反射 + Registry 可覆盖收紧，不可放宽） |
| `workspace_required` | 是否需要文件型 workspace |

### 8.4 注册流水线

外部 Agent 进入生产链路的最短路径（**不接受任何非 AGENT.yaml 入口**；具体命令与 readiness gate 见 `docs/agent-runtime/*`）：

1. 外部 Agent 在源工具构建 → 产出 `AGENT.yaml`
2. zw-brain 侧 validate + doctor 检查
3. 声明租户、权限、审计、确认边界（zw-brain Capability 映射）
4. 审核：默认 `untrusted` → `verified`，由 B1.2 管理员决策
5. 注册进 Registry
6. 投影到允许的消费面（默认 A2A / MCP；WebUI / API / CLI 由 Capability 投影机制承接）
7. 调用回到统一审计与观测面：Runtime 事件落入 zw-brain `audit_event` 聚合

### 8.5 允许外部化与禁止外部化的边界

允许外部化：
- 行业特定 Skill
- 项目特有流程
- 长尾能力
- 试验性 Agent
- 快速迭代能力
- 三引擎的「配置草稿生成器」（自然语言 → schema 草稿，管理员确认后入库；不直接修改生产配置）

不能外部化：
- 租户 / 权限 / 策略 / 审计总线
- canonical domain 的核心状态机
- 关键写操作的确认与问责边界
- 模型推理统一接入边界（必须走集团推理平台，preflight 段 10）

**机械边界**：禁止外部化的项不可通过 AgentRuntime `permissions` / `tool_policy` / `capabilities` 反向声明绕过——即使外部 Agent 在 `AGENT.yaml` 中声明了相应工具，Runtime 仍按 Registry 的 `trust_level` 与 zw-brain Capability policy 裁剪有效工具集，并由 B1.2 审核段拦截。

### 8.6 落地形态：规范先行，触发式实现（D30 retrofit）

§8.1–8.5 是协议规范与产品决策；**运行时与 Registry schema 的具体落地按"真实需求触发"原则推进**。zw-brain 现阶段无外部 Agent 接入排队，按 OPC 「只为真实需求建复杂度」拒绝提前盖楼。

**当前已落地（Wave 0/Wave 1 实有）：**
- 协议规范文档 `docs/agent-runtime/product-integration-guide.md` + `agent-runtime-api-cn.md`
- Registry 单源派生 5 消费面（`product_scope.{journey,status}` 字段就位，`status != live` 不进任何投影）
- `config_change_class: live|preview|draft` 字段就位（默认 `live`），为 Wave 2 三引擎「草稿→预览→入库」流预留契约

**触发条件 → 立即升级为产品需求并机械化：**
- **T1**：出现首个真实外部 Agent 接入需求（无论来自 ANP / Cursor / 第三方 IDE）→ 立即新增 Registry schema 字段 `runtime_spec_version` / `agent_yaml_ref` / `trust_level` / `workspace_required`；实现 `scripts/agentruntime_validate.py` + `scripts/agentruntime_doctor.py`；preflight 加段强制约束
- **T2**：客户要求 zw-brain 内置 Agent 以 `AGENT.yaml` 形态对外暴露 → 选 1 个低风险 builtin Agent 转 `AGENT.yaml` 形态作为 reference
- **T3**：B1.2 接入扩展中心 UI 立项（Wave 2 范围）→ §8.4 7 步流水线 UI 化

**绝不预先盖楼**：在 T1/T2/T3 任一触发前，主仓库不引入未被消费的 schema 字段、不写空跑的 validate/doctor 脚本、不在测试夹具里维护 AGENT.yaml 样本。

**事故防线**：本节"触发式落地"不解除 §8.5「禁止外部化清单」与 §6.6 / §段 22「禁区前缀回潮防护」的机械边界——任何接入路径都受现有 capability policy + trust_level 默认 untrusted 兜底。

---

## 九、数据模型

### 9.1 设计准则

1. **模型围绕旅程与审计组织，不围绕 legacy 表名组织**
2. **关键实体必须有显式状态机**
3. **每次 Capability 调用都应能回放到实体变化与审计事件**
4. **旧 schema 只作为 adapter 输入面**
5. **概念层完整，物理层分波次**

### 9.2 概念层的 load-bearing 领域概念

基于 `old/12-datastructure/` 真实表事实补充状态机 + 概念到真实表簇的完整溯源：

| 概念 | 说明 + 真实状态机 | 真实表簇溯源（旧库具体表） |
|------|------|------|
| `CatalogModel` | 目录模板、属性、维度、步骤定义；旧库支持"政务目录 + 国家扩展要素目录"双轨编制 | `dsp_catalog.xml`: `data_catalog_model`, `data_catalog_model_field`, `data_basic_elem_catalog`, `data_ext_elem_catalog_compile_task` |
| `Catalog` | 目录节点与主题分类；`status` 真实 6 态（0 草稿/1 待审/2 通过/3 驳回/4 发布/5 下线）+ 2 应用层计算态；`shared_type` 真实 3 态（1 无条件 / 2 有条件 / 3 不予共享） | `dsp_catalog.xml`: `data_catalog` (51 字段), `data_catalog_item`, `data_cascade_catalog_topic` |
| `Resource` | 可被发现与申请的数据资源；旧库 3 种物化形式：`data_resource_table`（表）/ `data_resource_file`（文件）/ `data_resource_api`（接口） | `dsp_catalog.xml`: `data_resource`, `data_resource_table`, `data_resource_file`, `data_resource_api`, `data_resource_table_column` + `data_resource.xml` 模块 |
| `Application` | 申请单；旧 `dsp_require` 5 业务节点（编制 → 校核 → 汇总 → 响应 → 反馈），XML `data_business.status` 实现为 0-6 共 7 态序列 | `dsp_require.xml`: `data_require`, `data_original_require`, `data_require_approve`, `data_business`, `business_requirements` |
| `ApprovalTask` | 审批任务与决策轨迹；与 `ObjectionCase` 边界：前者是申请审批 5 节点，后者是异议 5 维度独立状态机 | `dsp_require.xml` 含 `data_business_approve` + `dsp_catalog.xml` 含 `data_catalog` status 联动 |
| `DeliveryTask` | 交付、交换、直达任务 | `dsp_connect.xml`: `dc_catalog`, `dc_example_resource`, `dc_example_matters`（48 张 dc_* 跨地市表的核心；另含 9 张非 dc_* 国家直达表） |
| `ObjectionCase` | 异议与纠错链；旧 `dsp_handling` 5 维度独立状态机（authz / catalog / content / resource / use）+ 2 张流程辅助表（evaluate 评价 / process 处理过程） | `dsp_handling.xml`: `data_objection_authz`（54）, `data_objection_catalog`（74）, `data_objection_content`（89）, `data_objection_resource`（132）, `data_objection_use`（155）, `data_objection_evaluate`（103）, `data_objection_process`（120）= 7 张 |
| `AuditEvent` | 全量审计事件 | 旧库分散在各 dump 的 *_log / *_record / capability_call 等；新平台 zw-brain audit_event 统一 |
| `CapabilityPackage` | 注册能力包元信息；**zw-brain AI 原生重构引入的承重抽象**，无旧库继承 | **无旧库表对应**——为 AI 原生扩展模式新发明 |
| `TenantOrg` | 组织、租户、部门、区域上下文；旧库支持多级区划（省/市/区）+ 跨地市协作 | `dsp_bsp.xml`: `pub_org`, `pub_org_role`, `pub_org_region`, `sys_user_role`, `sys_permission`（IAM 由 IAF 外部化，本地保留 actor_org_role_binding 投影） |

**真相溯源结论**：

1. **10 概念覆盖度 ≈ 70%**：`CapabilityPackage` 是 zw-brain 新发明，其余 9 个全部能溯源到 dsp_* 真实表簇。
2. **零覆盖区域**（10 概念未触及但旧库真实存在）：基础主题库（basesubject 81 表）/ 运行监控（dsp_monitor 50 表）/ ETL 编排（dsp_pipelines 50 表）/ 数据血缘（graphdb_* 5 表）/ 数据质量（dsp_perform 16 表）—— 这些已在 §3.4 / §5.6 标为外部依赖或不进 IA。
3. **多概念合并到 Phase 1 聚合**（§9.3）：10 概念按 6 个物理聚合落地。

### 9.3 Phase 1 物理落地边界

Phase 1 先收敛到最影响主旅程的聚合边界：

| Phase 1 聚合边界 | 吸收的概念 |
|----------------|-----------|
| `CatalogResourceAggregate` | `CatalogModel` / `Catalog` / `Resource` |
| `ApplicationApprovalAggregate` | `Application` / `ApprovalTask` |
| `DeliveryAggregate` | `DeliveryTask` |
| `ObjectionAggregate` | `ObjectionCase` |
| `AuditAggregate` | `AuditEvent` |
| `CapabilityRegistryAggregate` | `CapabilityPackage` / `TenantOrg` 相关暴露与治理信息 |

**这样做的目的**：保留领域语义（10 概念仍在），控制 Phase 1 物理复杂度（6 聚合而非 10 子系统），避免因为"概念上重要"就立刻长成"系统上独立"。哪个聚合在真实压力下确实需要拆，再升格——而不是先拆完再找压力。

### 9.4 物理存储分层

- **Canonical DB**：核心聚合与状态机
- **Audit Store**：审计事件、执行轨迹、回执
- **Registry Store**：能力包注册、发布、停用状态
- **Search / Cache**：检索与页面加速
- **Legacy Adapter Reads**：只读读取 legacy MySQL / 文件 / 外部接口

### 9.5 Adapter 规则

adapter 只负责：
- 读取 legacy 数据（如需调研对比，**纯只读**）
- 为迁移评估提供输入证据

adapter 绝不负责：
- 成为新的业务写入口
- 承担新的业务状态机
- 把 legacy schema 原样扩散到 domain 层
- 作为常驻数据同步通道（zw-brain 是全新项目，adapter 只在 PoC / 调研期出现）

### 9.6 数据库 schema 管理：drop_all / create_all

zw-brain 是**全新项目**，没有历史客户、没有存量数据需要迁移。schema 管理遵循"全新项目"原则：

- **SQLAlchemy `Base.metadata` 作为唯一 schema 真相**：`zw_brain/domain/models.py` 是 schema 单一事实来源
- **本机 / CI / 部署用 `Base.metadata.drop_all()` + `create_all()`**：每次启动重建 schema；不维护迁移链
- **alembic 不进入产品基线**：对全新项目维护迁移链是历史兼容思维的副产品
- **alembic 启用条件**：第一个真实客户上线 + 第一次生产 schema 变更时，把当时的 schema 作为新 baseline 启动 alembic

---

## 十、实施路线图

### 10.1 Wave 0：机械守卫 + 首条黄金链路

目标：先证明"统一能力契约 + 合规边界 + 一条真实旅程"能成立，而不是先堆平台全景。

必须完成：
- Capability Registry 最小 schema（含 §8.3 AgentRuntime 新增字段）
- WebUI / API / CLI 的契约投影打通
- MCP / A2A 从同一契约可生成，但不要求首波全部产品化
- 审计总线最小闭环
- 推理平台统一入口 mock / 封装
- **首条黄金链路 = J1 找数→用数**：检索 → 申请草稿 → 提交审批（含**有条件 / 无条件共享分支**两种内置流程）→ 通过后凭据领取 → 调用样例 → 调用监控；这一条必须能让客户跑通真实数据

一句话：**先做成一个真能用的最小产品，不先做一个看起来完整的平台。**

### 10.2 Wave 1：J1 闭环深化 + J2 挂数→维数最小闭环

- J1 异议处理子流程（异议 5 维度独立状态机）
- J1 供需对接子流程（meta 合并，非数据合并；6 步流程）
- J2 在线编制 → 资源挂接 → 部门审 → 平台发布的核心 4 步
- 审计回执与基本运营可见性
- ~~首个外部 Agent 接入端到端验证~~（D30 触发式延后）
- ~~AgentRuntime Embedded SDK 最小集成~~（D30 触发式延后 → Wave 2+ 起，触发条件 = 出现首个真实外部 Agent 接入需求；详见 §8.6 与 [docs/preflight-debt.md](../preflight-debt.md)）

约束：
- 不追求长尾覆盖率
- 不为每个入口分别开发业务逻辑

### 10.3 Wave 2：AI 原生差异化三引擎 + B1 合规底线 + 共享专区

**三大差异化引擎**——R14（项目级可配置 = AI 原生差异化）的兑现：

| 引擎 | 来源 | 解决什么 | AI 原生落点（§4.4 第 4 类） |
|---|---|---|---|
| **审批流可视化引擎**（业务反馈 #4） | 项目级流程定制是基本盘（鞍山"编制→二级部门审→一级部门审→发布"） | 替代硬编码状态机；节点 + 选人规则 + 条件分支可配置；**先内置"有条件 / 无条件共享"两种基线流程**，再开放项目级编辑 | 自然语言生成流程草稿、节点建议、选人规则；管理员结构化确认入库 |
| **表单 schema 化引擎**（业务反馈 #17） | 各项目（四川 / 荆州）表单都改；旧平台靠改数据库 | 字段、校验、布局 schema 化；不再回主仓发版 | 自然语言生成字段定义、校验规则；管理员结构化确认入库 |
| **智能推荐前置引擎**（业务反馈 #6） | 一开始不确定要哪些目录时应有推荐 | 需求登记前置：相似目录推荐 → 推荐失败再转人工需求登记 | 真正的 AI 价值落点；基于 J1 历史申请 + J2 资源元数据 |

**Wave 2 其他内容**：
- B1.1 合规与运营最小可用（异常发现 + 抽查 + 督查三段）
- B1.2 接入扩展中心（外部 Agent 经 AgentRuntime AGENT.yaml 注册、启停、回滚；含 trust_level 升降级、§8.4 流水线 UI 化）
- 共享专区 / 专题包（P7）
- 一表通可选预填 adapter（**降级路径**，不默认；详见 §3.4 C）

**三引擎与 AgentRuntime 的关系**：审批流 / 表单 schema / 推荐三引擎本身仍是 zw-brain 内建 Capability（不外部化）；外部 Agent 可作为「配置草稿生成器」接入（自然语言 → schema 草稿 → 管理员确认入库），但**不直接修改生产配置**（与 §8.5 边界一致）。

**Wave 2 客户落地 sign-off 材料**（E3 F8 自动产出）：路径 `.data/wave2-acceptance/SIGN_OFF.md`，由 `tests/integration/test_wave2_three_engines_acceptance.py` 跑过即重生成；包含鞍山 4 级审批 / 四川 7 字段表单 / 荆州 5 条推荐规则三例的 e2e 入库证据、duration 时长记录、真实历史 hit-rate、§ 3 业务方签字栏（待业务方填）。业务方签字后此 Wave 2 「客户落地 ≤ 1 周」承诺由 pending 升 completed。

### 10.4 Wave 3：协议扩展硬化 + 多租户深化 + 国家通道独立子旅程

- MCP / A2A 生产级硬化
- 多租户 / 多部门 / 多区域策略深化
- 成本、性能、调用配额、观测告警
- **国家数据直达**独立子旅程实现（优先级 P2）
- **国家扩展要素目录编制**独立子旅程（优先级 P2）
- AgentRuntime Standalone HTTP 形态评估

### 10.5 Wave 4：legacy 退役

退役判断标准不再是"迁完多少菜单"，而是：
- 核心旅程（J1 / J2）是否已被稳定替代
- 后台支撑面（B1）合规底线是否已被覆盖
- 长尾需求是否已被外部能力包覆盖
- legacy 是否仍承担唯一写入口

### 10.6 明确不做的事

在首条黄金链路与 J1 / J2 闭环前，明确不做：
- 不先做面向普通用户的能力市场前台
- 不先做全协议等成熟度投入
- 不先做大而全的治理运营后台
- 不先为长尾 legacy 能力寻找"新平台安置位"
- 不接受客户级后端 fork 作为交付手段
- 不复造数据治理 / 数据安全 / 消息中心 / API 服务网关 / 应用中心脚本管理 / 数据存证 / 工单管理
- 不维护数据库迁移链（schema 用 SQLAlchemy `drop_all` + `create_all`）

---

## 十一、关键设计主张

> 本节用 **R-编号** 标注本基线的核心设计主张，作为后续实现与扩展的硬约束。
> 新增决策追加请使用 D-编号（写入 `CLAUDE.md §决策记录`）；新增架构主张追加 R-编号。

### R1 — 产品叙事围绕"高频主旅程"，而非"平台能力全景"

普通用户只需要理解 J1 / J2 两条核心旅程；B1 后台支撑面只对管理员/审计员可见。

### R2 — 生态接入定位为后台支撑面，不进入前台旅程

能力注册放在 B1.2 管理员面，不进入普通用户主导航心智中心。

### R3 — 五个消费面共享一套契约，但硬化顺序服从真实需求

WebUI / API / CLI 先做实；MCP / A2A 同 contract 生成，但不要求首波等成熟度。

### R4 — 控制面必须存在，但以最小可用为先

Registry / Policy / Audit 先服务主旅程和扩展秩序，不先长成平台产品。

### R5 — 领域概念完整保留，Phase 1 物理边界按聚合收敛

承认目录、审批、交付、异议等是强状态领域，但不在首波一次性拆成全套独立系统边界。

### R6 — 代码实现服从 `entry → command → domain → shared`

防止"运行时分层图"演化成另一套膨胀的代码组织。

### R7 — 外部长尾注册优先，主仓库只承接高频核心与底座

OPC 模式下，主仓只保留高频核心与底座，长尾能力默认转向外部能力包路径。

### R8 — 反 per-tenant fork 作为硬边界

客户差异只能通过配置、多租户策略、外部能力包实现，不能回到客户分叉后端模式。项目级流程 + 表单 + 推荐规则由 R14 三大引擎承接。

### R9 — AI 原生定义为"关键摩擦点 AI 原生 + 项目级可配置化"，主工作流结构原生

页面设计与原型评审以"结构化主旅程是否完整、AI 是否只在关键摩擦点减摩"为标准，而不是以"每页是否有 AI 组件"为标准。与 R14 联动：AI 不只是页面减摩，更承担"把以前必须改代码改库的事变成可配置物"。

### R10 — 用户角色定义严格对齐旧平台 ROLE_* 码，不引入并行命名空间

7 角色码（`ROLE_SYSTEM` / `ROLE_BUSIAUDIT` / `ROLE_ORGAN_MANAGER` / `ROLE_ORGAN_OPERATER` / `ROLE_SECURITY_ADMIN` / `ROLE_SECURITY_AUDIT` + `tag_lead_dept` 标签）冻结；新增需走 GATE + 业务方 sign-off；由 `policy.assert_no_legacy_role_codes()` + preflight 段双层兜底。

### R11 — 角色与数据流向解耦：方向由运行时计算，不通过角色拆分表达

部门管理员 / 操作员**同一角色既可为提供方也可为需求方**，方向由 `applicant_org_code` / `owner_org_code` 对照运行时计算。**禁止再通过新增角色码表达"提供方 vs 需求方"方向**——任何此类提案归 R10 + R13 拦截。

### R12 — 工程术语不进 UI

`package` / `projection` / `capability` / `write-with-audit` / `register-version` / `apply-tenant-policy` / `reconcile-receipt` / `submit-evidence` / `policy_decision` 等仅在代码与契约出现，前端必须用业务语义命名（详见 §5.5）。

### R13 — GATE-x 元规则：角色 / 业务流程 / 状态机决策必须业务方 sign-off

任何"角色定义 / 业务流程 / 状态机"类决策必须有业务方 sign-off 才能进 D-编号；立项会议输出（白皮书 + 转写录音 + 角色梳理）是 GATE 决策的强制输入。

### R14 — 项目级可配置化是 AI 原生在政务场景的真正差异化

Wave 2 必达三引擎（审批流可视化引擎 + 表单 schema 化引擎 + 智能推荐前置）；任何反对"项目级流程 / 表单 / 推荐通过改代码改库实现"的硬边界由本条约束。AI 在三引擎中的角色严格限定为"生成配置草稿，结构化预览，管理员确认入库"，不直接修改生产配置。**本条与 R8（反 per-tenant fork）联动**：客户差异由配置 + 多租户策略 + 外部能力包承接，**不由主仓代码分叉**。

### R15 — 外部 Agent 接入 = AgentRuntime 声明式协议唯一桥接面

外部 Agent 不论由 ANP 平台、Cursor 还是其他工具构造，进入 zw-brain 必须以 AgentRuntime 声明式协议（`AGENT.yaml`）形态声明并通过 AgentRuntime 执行内核运行。zw-brain 侧产品决策见 §8.2；协议规范单一事实来源 = `docs/agent-runtime/*`。**本条与 R7（长尾外部化）/ R14（项目级可配置）联动**：外部 Agent 仅承担长尾能力与配置草稿生成，**禁止承接 §8.5 禁止外部化清单**（租户 / 权限 / 策略 / 审计总线 / canonical 核心状态机 / 关键写操作确认边界 / 模型推理统一入口）。

**落地形态（D30 retrofit）**：本条是协议规范约束；运行时 Registry schema（`runtime_spec_version` / `agent_yaml_ref` / `trust_level` / `workspace_required`）+ validate/doctor 工具链 + 内置 Agent `AGENT.yaml` 转写按 §8.6 三类触发条件推进，不预先盖楼。

---

## 附录 A — 旧能力簇 → 新能力面映射

| 旧能力簇 | 新能力面 | 默认去向 |
|---------|---------|----------|
| 目录 / 分类 / 模板 / 信息项 | `CatalogResourceAggregate` + P2 / P5 | Core |
| 资源申请 / 审批 / 撤回 / 续期 | `ApplicationApprovalAggregate` + P3 | Core |
| 交换 / 交付 / 直达 | `DeliveryAggregate` + P4 | Core |
| 异议处理 / 纠错 | `ObjectionAggregate` + P5 | Core |
| 组织树 / 用户 / 角色 / 权限 | `TenantOrg` + Auth Policy + zw-brain Governance | Platform substrate；具体边界以 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准 |
| 服务报表 / 调用统计 / 资源统计 | B1.1 合规与运营 | Core / Common |
| 共享专区 / 专题能力 | P7 + 注册能力聚合 | Common |
| 外部 Skill / Agent 导出样例 | `CapabilityRegistryAggregate` | Platform substrate |
| 门户静态入口 / 低频后台岛 | 不重构或外部化 | Long-tail / Drop |

---

## 附录 B — 关键证据索引

### B.1 旧平台接口与依赖证据

- `old/代码信息抽取/代码信息抽取-27newbranch/All-Project_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/All-Project_外部SDK和接口文档(含项目交互关系).md`
- `old/代码信息抽取/代码信息抽取-27newbranch/All-Project_数据库表结构文档.md`

### B.2 旧平台数据结构证据

- `old/12-datastructure/dsp_catalog.xml`（161 表，最大主线）
- `old/12-datastructure/dsp_bsp.xml`（76 表，平台底座）
- `old/12-datastructure/dsp_metaresource.xml`（59 表）
- 其余 `old/12-datastructure/*.xml`（共 17 个 XML，678 表汇总）

### B.3 真实使用证据

- `old/使用日志分析情况/烟台接口统计结果(含调用少于100次).xlsx`
- `old/使用日志分析情况/宁夏接口统计结果(含调用少于100次).xlsx`
- `old/使用日志分析情况/内蒙接口统计结果(含调用少于100次).xlsx`
- `old/使用日志分析情况/三项目接口调用异同分析(含调用100条以下)[副本].xlsx`

### B.4 真实页面密度证据

- `old/html/`（18 个一级目录，291 个离线 HTML 页面）：实测页面密度详见 §3.2

### B.5 角色与菜单梳理证据

- `old/20260519/平台系统角色菜单梳理v5.xlsx`（7 角色码 + 菜单覆盖数详见 `docs/approved/zw-brain-roles.md`）
- `old/20260519/会议信息/疑问&建议.txt`（21 条业务反馈处置详见 §5.6）

### B.6 外部 Agent 接入规范源（AgentRuntime）

- `docs/agent-runtime/product-integration-guide.md`（产品集成与声明式 Agent 开发指南）
- `docs/agent-runtime/agent-runtime-api-cn.md`（API 接入文档）

---

## 附录 C — 软规则 → 机械检查映射

| 规则 | 当前机械状态 | 备注 |
|------|-------------|------|
| 统一能力契约由单一来源派生 | 已有基础 | 继续依赖 `export_agent_contract.py --check` |
| 模型调用只能走集团推理平台 | 已 wired | 继续依赖 preflight 段 10 |
| 角色码不得出现 r1-r8 字面值（R10） | 已 wired | `policy.assert_no_legacy_role_codes()` 启动检查 + preflight 段做仓库级 grep |
| 工程术语不得出现在前端 UI（R12） | 已 wired（D30）| preflight 段 24 `scripts/check_ui_term_blacklist.py` —— 扫 `zw-brain-web/` 9 词黑名单，剥离 ${...} / HTML 属性 / skill_id slug 后查残留 UI 文本 |
| 角色 / 业务流程 / 状态机决策必须业务方 sign-off（R13） | 软约束 | preflight 暂不强制（涉及人工审批，硬化收益低） |
| 项目级可配置物必须经管理员"草稿→预览→确认入库"三步（R14 / Wave 2） | 字段就位（D30）；三引擎 Wave 2 落地 | manifest schema 已增加 `config_change_class: live\|preview\|draft`（默认 `live`），由 `validate_manifest` 强制；Wave 2 三引擎落地时由配置 capability 显式改 `preview` / `draft` |
| 外部引用悬空不得合并 | 已 wired | 继续依赖 preflight 段 14 |
| adapter 禁止成为新写入口（§9.5）| 已 wired（D30）| preflight 段 25 `scripts/check_adapter_write_ban.py` —— `zw_brain/adapters/legacy/` 之外任何 adapter 出现 `session.add/commit/merge/delete` 或裸 SQL `INSERT/UPDATE/DELETE` token 拦下 |
| 外部能力包必须带治理元数据 | trigger 化 pending | 触发条件 = 出现首个外部能力包注册请求；届时新增 package schema 检查；详见 [preflight-debt.md](../preflight-debt.md) |
| Capability 的确认边界不得被 UI / Agent 绕过 | trigger 化 pending | 触发条件 = 出现绕过案例 OR §8.6 T1 外部 Agent 接入；届时新增 contract-to-runtime 一致性检查 |
| 反 per-tenant fork | trigger 化 pending | 触发条件 = 出现第二个真实租户 OR 客户提出 fork 后端意图；当前单租户 `sd-default`，无 fork 风险 |
| 控制面不得出现多处手维护投影 | trigger 化 pending | 触发条件 = `export_agent_contract.py --check` drift 后发现手维护痕迹；目前 5 消费面均派生自单 registry |

---

## 文档维护说明

- 本文是 zw-brain AI 原生重构的**唯一权威架构基线**；脚手架、契约、聚合边界、实施路线均以本文为收敛方向
- 后续修订请在本文上原位演进；新增决策追加 D-编号（写入 `CLAUDE.md §决策记录`），新增架构主张追加 R-编号
- 重大架构变化需新建一份 status 提案并走 GATE 流程，不得直接覆盖本基线
