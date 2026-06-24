# zw-brain 场景智能体设计 · v1（两类 · 乔布斯重审后收敛稿）

> 状态：**设计收敛稿（待协同定版）**。本稿在 v0 基础上，经一轮地面事实重核（30/31 skill_id 逐字命中真实注册表）
> + 6 棱镜乔布斯批判 + 对抗性证伪（63 条批判存活 17 条）后重写。取代 `scenario-agents-design-v0.md`。
> 落地形态：每个场景智能体 = `agents/<id>/AGENT.yaml` + `capabilities.json`（sidecar 只作 zw-brain 元数据），
> 可执行工具必须在 `AGENT.yaml tools[]` 显式声明为 `kind:api` 并指向本地 OpenAPI spec；AgentRuntime 只作为独立服务运行。
> 平台**运维员**在 B1.2 管理面构建/配置/启停。
>
> **两个被反复混淆的层级，先钉死：**
> - **设计收敛清单**：A 类 ~20 + B 类候选池 ~18（本稿全列，保留发散）。这是"设计上认账的场景空间"。
> - **本期建造（Wave 1）**：**1 条 A 链 + 至多 1 条 B 试点**。乔布斯铁律：聚焦＞覆盖，先做精一条能签收的端到端链，其余冻结待解冻。
>   "~20" 不是没了，它是候选池；变的是"本期真正动手做几个"。

---

## 0. 乔布斯一句话总评

> 发散是诚实的、地面是扎实的（30/31 skill_id 精确命中、§8.5 方向对），但**把两类当对称两半同期铺开是贪多**——
> 先用 A① 一条已 live 的链证明承载形态能签收，B 类此期只立规范 + 一个 `net_new=none` 的法人画像试点，
> 其余凡需平台新建后端的一律诚实降级，绝不让副驾偷偷越过 §8.5 替人裁决落库。

---

## 1. 两类场景智能体（本稿的核心框架）

| | **A 类 · 平台内副驾** | **B 类 · 外部独立用数方智能体** |
| --- | --- | --- |
| 定位 | 操作 zw-brain 本身，把 J1/J2/B1 旅程的"多菜单 + 靠人记"压成"一句话→起草/分诊/推荐→人按角色拍板" | 不操作平台，而是**作为被授权的用数方**，消费 zw-brain 已编目的跨部门共享数据/服务，去交付下游业务结果（惠企匹配、信用核验、双随机靶向、危险源研判…） |
| 承载 | `AGENT.yaml tools[]` 显式声明 `kind:api` 工具，经 OpenAPI 回调 zw-brain 已发布 `/api/skills/*`；`capabilities.json` 只保留权限/展示元数据并由守卫校验同名 | 同样写 `AGENT.yaml tools[]` 的 `kind:api`/`kind:a2a`（受 schema + manifest 守卫校验），或作为外部应用经 5 消费面之一（API/A2A）消费 |
| 信任级 | `trust_level: platform`（**仅内置可得**），运行在 trusted_gateway 内 | `trust_level` 默认 `untrusted`，由运维员审核升 `verified`（**外部永拿不到 platform**） |
| 授权 | 只读/起草能力默认开放消费面，无需逐事项授权 | 每份有条件共享资源逐项走 `application.resource.submit → approval.review_decide → credential.issue`，运行时 `credential.query` 取凭据，全程进审计总线 |
| 新后端 | 零（只调既有 live 能力） | **必须 `net_new=none`**；凡需平台新建数据服务/编排的，是后端立项不是智能体 |
| 本期成熟度 | **可签收的运行时交付** | **规范 + 一个垂直试点**（接入面触发式未实装，见 §2 事实⑥） |

> **不对称是本稿的诚实底色**：A 类是"平台自己的副驾、本期可签收"；B 类是"外部系统作为用数方消费共享数据、本期只立规范 + 一个试点"。
> 并列写法必须明示这条不对称，否则读者会把 B 类当成与 A 类同等成熟度的交付物。

---

## 2. 设计包络（地面事实已重核 · 含 v0 的 6 处必改）

来自对真实仓库的逐条核查（`zw_brain/capability_registry/registered/`、`schemas/agent.schema.json`、
`docs/approved/zw-brain-architecture.md` §8、`docs/agent-runtime-t1-readiness.md`、`zw_brain/domain/policy.py`）：

**已确认（v0 说对了的）：**
- **能力底座真实**：磁盘 249 个能力 JSON，`status==live` 恰为 185（`docs/agent_integration.md:494` 自证），"185+"属实且偏保守。v0 点名的 30/31 个 `skill_id` 逐字命中真实注册表，**无编造**。
- **运维员生命周期证据极硬**：`policy.py` 把 `package.rollback`/`package.trust_level.update`/`tenant.capability.{enable,disable}`/`capability.exposure.configure` 唯一授予 `ROLE_SYSTEM`。"构建/配置/启停在运维员权限内"成立。

**6 处必改（v0 二手摘要的偏差，已据权威源修正）：**

1. **§8.5 禁区表逐字对齐**（权威源 architecture.md 行858-862）：①"写审计"→"**审计总线（含统一审计聚合）**"；②canonical 核心状态机**不是 3 个而是 7 个**——`CatalogModel / Catalog / Resource / Application / ApprovalTask / DeliveryTask / ObjectionCase`（§9.2）。v0 只列 (Application/Approval/Delivery) 会让 C3 判据基准错列，放过本该砍的写操作（如 `catalog.entry.create` 写 Catalog 发布态、`objection.case.*` 写 ObjectionCase 态）；③补回第 3 项"**关键写操作的确认与问责边界**"——这正是"最终落库由角色拍板"的权威出处。
2. **`approval.case` 是不存在的裸 slug**：真实注册的是 `approval.case.decide`（裁决/写/§8.5 禁区前缀）与 `approval.view`（查看/读）。③ application-tracker 是只读跟踪副驾，**必须用 `approval.view`，绝不能 expand 到 `approval.case.decide`**。→ 立规则：**只读副驾的 `skill_id` 必须是 `query`/`view`/`list` 类；任何 `.decide`/`.review`/`.submit` 出现在只读 agent，review 必报 finding。**
3. **`trust_level` 是两个同名异义字段**（t1-readiness §3.1 称"本预案最重要的 contract 边界"）：**package 级**（enum `baseline/reviewed/restricted/revoked`，由 `package.trust_level.update` 写）vs **AGENT.yaml Registry 级** `metadata.trust_level`（enum `platform/verified/untrusted`）。运维员"trust_level 升降"指 package 级；A 类内置 agent 声明的是 Registry 级 `platform`；B 类外部 agent Registry 上限是 `verified`。
4. **`exposes_chat`/`exposes_a2a` 是逐 agent 开关**，不是统一样板：`a_zw_platform_guide`(chat:true/a2a:false 顶级问答)、`a_zw_search_helper`(chat:false/a2a:false 页内嵌)。`chat`=是否进 `GET /agents` 顶级选择；`a2a` 默认 false，仅链式协作才 true。**别给每个 A 类副驾无意开 A2A。**
5. **可执行工具的承载来源已随 D68 改写**：`capability_tools`/`skill_id` 仍可留在 `capabilities.json` sidecar 做 zw-brain 侧展示、权限过滤和守卫输入，但不再负责把工具注入运行时。AgentRuntime 真正可执行的是 `AGENT.yaml tools[]` 里的 `kind:api` 声明，且每个工具必须有本地 OpenAPI spec 的同名 `operationId`；preflight/单测已把 sidecar↔AGENT.yaml↔OpenAPI 三者一致性钉住。
6. **B 类外部接入＝"规范就位、运行时触发式实施"**（§8.6 + t1-readiness §1）：D68 后 Registry 4 字段、`validate`/`doctor` 校验和 preflight 段30 已落地为 T1 工具链；但真正外部第三方 Agent 接入仍需按首次真实需求走隔离实例、凭据和验收闭环。当前 A2A 是 AgentRuntime 内核**本地 agent 间调用**，**不是给外部系统直连 zw-brain Capability 的公网 API**。→ B 类任何"外部独立 agent 即插即用"的措辞仍是假面，须改为"触发 T1 后按工具链接入"。

**贯穿原则（乔布斯五条）**：聚焦（一个 agent = 一角色一旅程一件事）｜简洁（运维员开一个开关，非每个 agent 一套后端）｜端到端（沿旅程串链，各自独立可交付）｜设计即工作方式（manifest 即规格，sidecar 绑单一能力契约）｜精品意识（先做精一条能签收，不出半成品假面）。

---

## 3. 收敛判据（自上而下砍取的 6 把尺子）

- **C1 真实痛点支撑**：有 `old/问题反馈/`、`使用日志` 实证。
- **C2 复用既有能力（零新后端）**：映射到现有 185 个 live 能力；需大量新能力的降级。
- **C3 副驾安全区**：只做起草/分诊/校验/推荐/问答，不碰 §8.5 禁区（**按修正后的 7 状态机 + 审计总线 + 问责边界判**）与 canonical 写。
- **C4 黄金链路 / 数据厚度优先**：A 类压 J1/J2 高频；B 类压"非跨部门共享数据不可、且数据已编目样例丰富"的场景。
- **C5 角色清晰**：服务某个明确角色的明确任务。
- **C6 运行时就绪度（新增）**：本期能否真交付，取决于承载面是否已实装。A 类内置 Agent 必须经独立 AgentRuntime + `kind:api` OpenAPI 工具跑通；B 类外部接入面即使工具链就绪，也要等真实第三方需求触发隔离部署与凭据验收。**就绪度不准则"可签收"判定不可靠**——这是 B 类不进本期 Wave 的根因。

---

## 4. A 类设计清单（~20，重审后保留并修正，按解冻顺序分层）

> **本期只建造 A①**；②–㉑ 全部冻结到 A① 在 P2 资源发现页演示 + 被业务方签收之后逐个解冻。聚焦＞覆盖。

**A①（本期唯一可签收交付）· `data-discovery-copilot`（升级现存 `a-zw-search-helper`）**
J1 用数方找数首步 · 痛点：搜索反复/术语对不上 · 能力：`search.intent.parse`+`data.search`+`catalog.browse`+`catalog.entry.query`（全 live+a2a 只读）·
`exposes_chat:false`（页内嵌副驾）· 形态：意图解析 + 可行性评分 + TOP-N 推荐 + 术语对齐。**它跑通即证明 `AGENT.yaml kind:api + OpenAPI 回调 + capabilities.json 元数据` 这套承载端到端可交付——是后续所有 A 类乃至 B 类共用底座的地基。**

**Wave 2（A① 签收后第一条，端到端合并）· `用数方全程副驾`＝ v0 的 ②③④ 合并**
②申请起草 + ③申请跟踪（`approval.view` 非 `approval.case`）+ ④交付对账 是同一用数方在同一旅程的连续动作，合成一条 J1 端到端链比四个独立副驾更聚焦。

**Wave 2–3 候选（冻结）**：⑥目录编制向导 · ⑦元数据补齐 · ⑧资源挂接发布 · ⑩供需匹配 · ⑫异议分诊 · ⑭审核研判（**守 §8.5：只研判不裁决**）· ⑮工单分诊 · ⑯告警根因 · ⑰权限合规自查（只读不裁决）· ⑱运营报表 · ⑳NL 审批流/表单起草 · ⑲平台指南（已有，`exposes_chat:true`）。

**已降级/改写**：
- **⑬ data-quality-sentinel → 降级**：v0 把"业务字段级异常检测"伪装成 `audit.event.anomaly`（实为平台审计事件 Top-N 三规则、`side_effects:[]`、不返业务 payload）。改为"基于异议历史 + 对账异常的**只读问答**"，去掉"字段级主动哨兵"承诺；真要字段级质量预警归入 §6「需新增能力」另立项。
- **⑤ API 集成 / ⑨ 血缘自查 / ⑪ 需求成效 / ㉑ 审计回放**：保留为 Wave 4 候选。

---

## 5. B 类候选池（~18，发散全列，按 `net_new` 诚实分区）

> **本期只立规范 + 至多 1 个试点**。下表 `NONE` = 零新后端、可作试点；`NEW` = 需平台新建数据服务 = **后端立项不是智能体**，本期推迟。

### 5.1 净零后端（`net_new=none`，13 个，试点资格）

| 智能体 | 领域 | 承载 | 消费的真实共享数据（地面） |
| --- | --- | --- | --- |
| **★ b-legal-person-credit-profiler 法人信用画像核验** | 企业/法人 | external_api | 法人库群体画像 `bzk_frk_app_qthx`（失信/黑名单/经营异常/纳税信用等级/参保数/注册资本…）+ `corporation_statistic` 行业基准 + 已编目企业登记服务 |
| b-material-waiver-verifier 材料免提交核验编排 | 民生 | external_a2a | 政务服务事项 `data_item`+材料 `data_item_material`+共享资源 |
| b-onestop-guide-copilot 一件事一次办导办 | 民生 | builtin-api | `data_item`/事项 FLOW + 材料共享 |
| b-dual-random-targeting-engine 双随机靶向抽查名单 | 监管 | external_a2a | 法人画像 + 处罚/信用标签 |
| b-social-org-watchdog 社会组织监管异常预警 | 监管 | external_a2a | 社会组织登记 + 法人异常标签 |
| b-hazard-source-fusion-briefer 重大危险源研判 | 公共安全 | external_a2a | 重大危险源基本信息 + 跨部门画像 |
| b-safety-permit-compliance-checker 安全生产许可证体检 | 公共安全 | external_api | 安全生产许可/环境隐患排查类已编目资源 |
| b-regional-econ-pulse 区域经济运行月度研判 | 经济 | external_a2a | 历年 GDP + 纳税 + 法人统计 |
| b-industry-chain-insight 产业链/规上企业洞察 | 经济 | external_a2a | 法人统计画像 + 行业分布 |
| b-gdp-tax-linkage 区域 GDP–税收联动洞察 | 经济 | external_a2a | GDP + 纳税信用/规模 |
| b-parking-onemap-service-agent 停车一张图 | 城市治理 | external_a2a | 停车场信息 + 车辆状态 |
| b-parking-file-integrity-checker 停车文件完整性核验 | 城市治理 | external_a2a | 停车文件资源 + 对账字段 |
| b-traffic-eng-exchange-recon-agent 交通工程竣工对账 | 城市治理 | external_a2a | 市政交通工程竣工验收信息 + 交换对账 |

### 5.2 需平台新建后端（`net_new≠none`，5 个，本期推迟为"需新增能力"立项）

| 智能体 | 缺什么后端（→ §6 立项） |
| --- | --- |
| huiqi-policy-matcher 惠企政策免申即享 | 需"政策资格规则结构化判据库/政策规则目录"数据服务；否则只能候选召回 + 人工复核 |
| enterprise-launch-onestop-orchestrator 企业开办一件事编排 | 需"一件事子事项→材料/字段/归集源映射"的事项编排数据服务 |
| cohort-eligibility-profiler 群体精准服务画像 | 需"按资格条件群体筛查→脱敏名单"查询编排能力 |
| enterprise-credit-risk-profile-api 企业信用风险评分 API | 若要统一口径"综合风险分"需新建派生评分服务（推荐评分逻辑留外部侧，则回落为 5.1 的原子标签消费） |
| urban-risk-alert-watcher 城市运行字段级预警 | 需"交付资源质量/字段级异常检测"能力（现 `audit.event.anomaly` 只面向平台审计事件） |

---

## 6. 本期收敛结论（建造清单）

- **A①** `data-discovery-copilot`：做到**能在 P2 资源发现页演示 + 被业务方签收**。本期唯一可签收的运行时交付。
- **B 试点** `b-legal-person-credit-profiler`（`net_new=none`）：只走通一条"外部用数方注册 app → `application.resource.submit` → `approval.review_decide` → `credential.issue` → `credential.query` 取凭据 → 经消费面调 `data.search`/`delivery.view` 消费已编目法人画像"的**授权链路可行性证明**。
  - **前置闸**：先确认这是否**隐性触发 T1**。若是 → 本期 Wave 1 **仅含 A①**，B 试点退为"规范 + T1 重估"立项（不动运行时）。
- **判据修订（非交付但必须先做）**：§2 的 6 处地面事实错误先改对——判据不准则下面每个 agent 的安全形态判定都不可靠。
- **配比**：本期"真正做"= 1 条 A 链 + 至多 1 条 B 链；A ~17 + B ~10+ 候选退为"签收后解冻"的候选池。
- **若只能做一个**：**A①**。它已 live、风险最低、J1 首步最高频、升级现存 agent（独立 AR + `kind:api` 工具链已端到端跑通），签收即一次性证明承载形态可交付——胜过同时铺 20 个半成品假面。

---

## 7. 待你拍板（协同定版钩子）

1. **接受"本期建造 1–2 个"的聚焦吗？** 还是你要本期就铺更多（若铺 B 类，须接受 T1 实装成本先进来）？
2. **B 试点选 `b-legal-person-credit-profiler` 吗？** 还是换 5.1 里另一个 `net_new=none` 的（如双随机靶向、区域经济研判）？
3. **B 试点是否接受"先验 T1 触发、可能退为纯立项"** 的前置闸？
4. **A 类设计清单（~20）是否照 §4 的分层冻结**，还是要调整解冻顺序 / 增删？
5. **5.2 的 5 个"需新建后端"候选**，要不要现在就把其中哪个的数据服务立项（让它从 B 候选池升为真能落地）？

> 附：所有 `skill_id` 已对 `docs/agent_integration.md` 校验；落地写 `capabilities.json` 与 `AGENT.yaml tools[]` 时再逐一复核。当前守卫要求 `capability_tools`、`kind:api` 工具名与 OpenAPI `operationId` 三者一致，错了会被 validate / preflight 拦下。
