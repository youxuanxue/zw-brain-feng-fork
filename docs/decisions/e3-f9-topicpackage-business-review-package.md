---
doc_id: F9-business-review-package
status: approved
gate: signed
scope: e3.F9
sign_off_required:
  - 海若产品部业务方
signed_off_by: 海若产品部业务方
signed_off_at: 2026-05-29
vehicle_pr: "#162"
driven_by:
  - docs/reconstructs/dsp-sharezone-topic-package-reconstruction-plan-v1.md
  - CLAUDE.md D34
---

# F9 业务方 review 材料包 — P7 共享专区 / TopicPackage 启动准入

> **目的**：F9 启动前的 R13 元规则硬门 — 业务方对 4 项业务决策点逐条 sign-off
> 后，F9（Wave 2 P7 共享专区 / TopicPackage 落地：schema + capability + 5 消费面
> 投影 + fixture + e2e）才能进入 D-编号并启动。
>
> **不是**：技术方案 review（schema/code 设计另走 PR review）；非签字范围内的
> 工程实现细节不在本次议程。
>
> **真值源**：
> - `docs/reconstructs/dsp-sharezone-topic-package-reconstruction-plan-v1.md` v1（active per D32.a）
> - `docs/approved/zw-brain-architecture.md` §5.6 #13（basesubject 不复造） / §3.4 C（一表通降级）
> - `docs/approved/zw-brain-roles.md`（7 角色码）
>
> **前置已满足（reviewer 责任 — 开会前 verify）**：
> 1. F8 Wave 2 三引擎业务方 sign-off 已落盘（2026-05-28 海若产品部产品负责人 / PR #151；
>    签字账本 `.testing/signoff/e3-engines.signoff.yaml`）
> 2. **已与业务方一对一澄清**：D 类 ✅ 复活的是承重语义（专题素材、标准资产 adapter
>    输入），不是「基础主题库整体复活 / 旧建库平台复造」。本前提如未完成澄清，本 review
>    框架不成立 → 退回 R13 等下次（避免会上才发现根本分歧）
>
> **元规则**（CLAUDE.md D28 / D32.b）：角色定义 / 业务流程 / 状态机变更需业务方
> sign-off 才能进 D-编号。本文 4 项均落在该范围内。

## 议程（分两场，避免一场塞满）

**第一场 — 锁定专区清单 + 状态机**

- 0. 背景同步：D31 + D32.a 触发链路（业务方 PR #129 签 D 类 4 条复活 → 既存 plan v1 接管 → F9 准入）
- 1. 首批 3 个山东共享专区优先级 + 每个专区策展的目录清单
- 2. 发布状态机含义对齐（含 `offline_pending` 必要性 + 预填默认值）

**第二场 — 可见性 + 复活边界**

- 3. 三维可见性矩阵（组织 + 角色 + 消费面）
- 4. 复活边界 — 只做 / 不做清单确认

两场全部签完，才触发 §5 的 sign-off label。

## 0. 背景速览（开会前先读）

- **D31（2026-05-27）**：业务方在 PR #129 对 50 条不复刻清单逐条签字，D 类 4 条
  （主题库 / 专题库 / 数购车）从 ❌ 改判为 ✅ 复活。本次启动是 D31 兑现。
- **D32.a（2026-05-27）**：D 类复活归属由「待定三选一（Wave 2.x / Wave 3+ / 外部
  能力包）」改判为「既存 reconstruction plan v1 接管 + 归 Wave 2 P7 共享专区」。
- **现在要做的（F9）**：按 plan v1 §3.1 / §四 / §6 把 P7 共享专区 + TopicPackage
  落地（schema + capability + 山东 fixture + 5 消费面投影 + e2e），按里程碑拆多个 PR。
- **F9 启动硬前置（sequencing — 务必在 §1 sign-off 时一并定）**：Z2 医保码 / Z3 异地
  就医引用的目录在真实 dump 里**有**、但**尚未进 seed**（详见 §1.1）。专区只引用目录、
  不造目录 → 这些目录必须先由 **catalog 线补种进 seed**，F9 才能做对应 fixture。二选一：
  **(a)** Z1（已在 seed）先做、Z2/Z3 待补种后做；或 **(b)** 把「catalog 线补种目录」
  作为 F9 的阻塞前置任务先排。**不定这条 = 签下去的 worker 第二天就 blocked。**
- **本次签字范围**：业务可感知的 4 项（专区优先级 + 目录清单 / 状态机含义 / 可见性策略 / 复活边界）。
  技术 schema / capability slug 命名 / preflight 段号细节由开发侧承担。

---

## 1. 首批 3 个山东共享专区 + 每个专区策展的目录清单 sign-off

> **概念定位（开会前先读 §1.0）**：本节签的是 3 个**共享专区（专题包）**——运营方
> 策展的命名容器，每个专区**挑选关联 N 个目录** + 指定可见组织 + 资源授权 + 走上线
> 审核。专区是**策展（挑选）**，不是"全部目录"，也不是"按主题自动聚类目录"。

### 1.0 共享专区 ≠ 主题分类（边界澄清，避免理解漂移）

旧平台 `share_zone*` 系列表（`old/12-datastructure/dsp_catalog.xml`，plan v1 §2.1）
证明专区的承重语义是**运营方策展的目录/资源集合**，与"目录自带的主题分类"是两条线：

| | 共享专区 / 专题包（本节 F9 范围） | 主题 / 分类（**不在本节**，归 catalog 线） |
|---|---|---|
| 本质 | 运营方**手动挑选**目录的命名容器 | 每个目录**自带**的分类/领域标签（元数据 facet） |
| 旧表 | `share_zone` + `share_zone_catalog_link` + `_org_link` + `_org_auth` + `_approve` + `_statistics` | `data_catalog_category`（≈773 节点）/ `data_catalog_group` |
| zw-brain 落点 | `topic_package` 6 表（F9）；`topic_package_item` 引用 `catalog_entry` | `catalog_entry.subject_tags`（catalog 模型，`dsp-catalog3-metadata3` plan） |
| 是否穷举 | **否**——策展，少而精 | 是——每个目录都带，全集 |

> **真实数据事实**：`old/10示例数据` 中 `share_zone*` 实例数 = **0**（仅 schema 有
> 定义，无导出数据），即旧平台示例库**没有真实专区实例可镜像**——sd-default 首批专区
> 由运营方**新建策展**。真实存在的是**目录**（`data_catalog` ≈216 条 / `data_basic_elem_catalog`
> ≈37 条）；专区只**引用**这些目录，不持有目录事实（plan v1 §1.2 / §3.1）。

### 1.1 3 个专区候选 + 每个专区策展的目录清单

来源：`docs/deployment/m0-site-migration.md` §M0-D6（核心 catalog 已进入 sd-default
catalog_entry 真实数据）+ `zw_brain/domain/seed_snapshot.json` 相关 entry / asset 拣取
+ `docs/customer-demo-j1.md` L10-12 J1 demo 已命中目标。

> **每个专区 = 1 个容器 + 挑选关联的多个目录**（不是「1 目录 = 1 专区」）。下表每个
> 专区的目录清单即 `topic_package_item → catalog_entry` 引用。**前置（catalog 线，
> 非 F9）**：标「seed 真实」的目录已在 `seed_snapshot.json`；标「真实 dump 待入 seed」
> 的目录在 `data_catalog`（≈216 条真实数据）中存在但尚未进 seed，需 catalog 侧先灌入，
> F9 专区再引用——**不在 F9 内造目录**。

**Z1 — 医疗救助共享专区**

| 策展关联的目录 / 资源 | 数据真实性 | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|---|
| 医疗救助信息（seed URN `basic-elem:0b26783950004ed882ec9309fae73310`；旧平台真实 code `003601020201001`；PR #168 更正：原记 seed URN `370000307013000000/000045` 为漂移码，DB / dump 均无，已校正为真 basic-elem 码） | seed 真实 catalog_entry（真实 dump 命中 ✅） | **必含** — 核心、已在 seed、demo 命中 | ☐ 必含 / ☐ 排除 |
| 低保主题分析汇总（asset） | seed asset | **含** — 救助强相关，复用价值高 | ☐ 含 / ☐ 排除 |
| 特困人员救助供养信息 | 真实 dump **未命中**（"特困"仅见于医疗救助申请材料文本，无独立目录；段 53 校验后更正） | **排除** — 无真实独立目录，D11 禁 Mock；有源再加 | ☐ 含 / ☐ 排除 |
| 残疾人两项补贴信息 | 真实 dump **未命中**（候选，需确认数据源） | **排除** — 无真实数据，D11 禁 Mock；有源再加 | ☐ 含 / ☐ 排除 |

**Z2 — 医保码共享专区**

| 策展关联的目录 / 资源 | 数据真实性 | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|---|
| 医保码信息 | 真实 dump 命中 ✅（m0 L39 高频目录），待入 seed | **必含** — 专区主题本体 | ☐ 必含 / ☐ 排除 |
| 山东省社会保险参保人员基本信息 | seed 真实 catalog_entry（owner 11370000MB284651XL，真实 dump 命中 ✅） | **含** — 已在 seed，参保是医保码前置 | ☐ 含 / ☐ 排除 |
| 职工 / 城乡居民基本医疗保险状态信息 | 真实 dump 命中 ✅，待入 seed | **含** — 同域高频，真实数据有 | ☐ 含 / ☐ 排除 |
| 青岛市医保局订阅记录（关联 evidence） | seed subscriber 数据 | **关联** — 复用证据强，撑 J1 找数叙事 | ☐ 关联 / ☐ 不关联 |

**Z3 — 异地就医统筹区开通共享专区**

| 策展关联的目录 / 资源 | 数据真实性 | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|---|
| 异地就医统筹区开通信息 | 真实 dump 命中 ✅（m0 L39 + customer-demo-j1 命中），待入 seed | **必含** — 专区主题本体，demo 命中 | ☐ 必含 / ☐ 排除 |
| 异地就医定点医疗机构信息 | 真实 dump 命中 ✅，待入 seed | **含** — 异地就医闭环必需 | ☐ 含 / ☐ 排除 |
| 异地就医经办机构信息 | 真实 dump 命中 ✅，待入 seed | **含** — 异地就医闭环必需 | ☐ 含 / ☐ 排除 |
| 国家平台异地就医上报 receipt（关联 evidence） | adapter.national.topic.report 数据 | **关联** — 国家平台上报证据，撑跨域叙事 | ☐ 关联 / ☐ 不关联 |

### 1.2 专区优先级排序

| 共享专区 | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|
| Z1 医疗救助共享专区 | **P0** — 目录已全在 seed，无上游依赖，可立即开工（即 §0 硬前置路径 (a)） | ☐ P0 / ☐ P1 / ☐ 砍 |
| Z2 医保码共享专区 | **P1** — 目录需 catalog 线补种后才能做 fixture | ☐ P0 / ☐ P1 / ☐ 砍 |
| Z3 异地就医统筹区开通共享专区 | **P1** — 同 Z2 需补种；但 demo 命中度高，补种后优先于 Z2 | ☐ P0 / ☐ P1 / ☐ 砍 |

### 1.3 开放确认点

- **Q1.1**：上述 3 个专区是否需要调换次序，或第 4 个高频跨部门场景应取代某个？
  （plan v1 §九 T1 允许 sign-off 替换；replan 不算 scope creep）
  - **建议**：不调换、不加第 4 个。三个都在医保 / 民政高频域、demo 已验证；新场景待真实客户需求出现再 replan。
- **Q1.2**：「一表通 / 基层报表减负」明确不进首批（plan v1 §〇 + §九 T1 已写死，
  仍降级为 Wave 2 候选可选 adapter；研究文档 `docs/approved/research-yibiaotong.md`
  保留作为未来重启入口），业务方是否仍认可此降级？
  - **建议**：认可降级。一表通是另一条产品线，塞进首批会稀释专区的复用叙事。
- **Q1.3**：每个专区的目录清单是否完整（专区是策展，挑漏 / 挑多都可在 §1.1 表内
  增删行）；标「真实 dump **未命中**」的候选项（如残疾人两项补贴）若必含，需业务方
  指明真实数据源，否则按 D11 禁 Mock 默认排除。
  - **建议**：按 §1.1 建议列定稿（残疾人两项补贴排除）。其余增删请当场在表内圈改。

### 1.4 sign-off 形式

见 §5 — 统一 PR label `signoff:e3.F9` + body 机读块，实质内容（P0/P1/砍 + 每个专区的
目录清单选择 + Q1.1/Q1.2/Q1.3 答案）写进 PR 评论 body（统一模板，见 §5.2）。

---

## 2. 发布状态机含义对齐（含 `offline_pending` 必要性）

### 2.1 状态机流转图（语言化）

来源：plan v1 §3.3 L180-189 + §3.3 L191-196 推进规则。

```
  ┌─ draft（运营方刚创建，未配置）
  │     │ 选 catalog/resource/model/案例
  │     ▼
  │   configuring（正在选目录、资源、可见组织）
  │     │ 选齐了
  │     ▼
  │   configured（待提交审核）
  │     │ 提交（topic.package.submit）
  │     ▼
  │   submitted（审核中）
  │     │ 审核通过                  │ 审核驳回
  │     ▼                             ▼
  │   published（对外可见）       rejected（保留意见）
  │     │ 申请下线
  │     ▼
  │   offline_pending（下线申请待审核）
  │     │ 下线审核通过
  │     ▼
  │   offline（不再对消费面展示，历史可审计）
```

### 2.2 8 项预设默认值对齐（业务方勾选 / 改判）

每行预填**开发推荐默认值**；业务方默认接受全部 ✅，仅就需要改判的行勾「☐ 改判」+ 留批注。

每行的「推荐默认值」即开发侧建议；「建议」列是 Jobs 视角对该默认是否该接受的判断。

| # | 项 | 推荐默认值（开发建议） | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|---|---|
| 1 | `draft` 协作编辑范围 | 仅创建人可见可编辑 | **接受** — 草稿态最小可见面 | ☐ 接受 / ☐ 改判：________ |
| 2 | `configuring` 同组织 reviewer 范围 | 含 `ROLE_ORGAN_MANAGER`，不含 `ROLE_BUSIAUDIT` | **接受** — 配置期不该惊动审核线 | ☐ 接受 / ☐ 改判：________ |
| 3 | `configured` 与「待提交」是否分两态 | 不分（合并为 `configured` 一态） | **接受** — 多一态无业务收益，徒增复杂度 | ☐ 接受 / ☐ 改判：________ |
| 4 | `submitted` 审核人范围 | 单级 = `ROLE_BUSIAUDIT`（不做部门→大数据局二级审核） | **接受** — 多级审批走 D25 流程引擎（下期），本期勿内建 | ☐ 接受 / ☐ 改判：________ |
| 5 | `published` 生效时机 | 即时（审核通过即对消费面可见） | **接受** — 审核已是关卡，无需再加生效延迟 | ☐ 接受 / ☐ 改判：________ |
| 6 | `rejected` 通知方式 | 系统内审批中心查看（不发邮件 / 工单） | **接受** — 邮件 / 工单是外部集成，本期不背 | ☐ 接受 / ☐ 改判：________ |
| 7 | **`offline_pending` 是否保留**（关键） | 保留（防止误下线高使用量专题包） | **接受保留** — 误下线高用量专区代价高，这一态是安全垫 | ☐ 接受保留 / ☐ 简化去掉 / ☐ 另议：________ |
| 8 | `offline` 重新上线流程 | 必须重走全套审核（draft → submitted → published） | **接受** — 重新上线等同新发布，复用审核链路最简 | ☐ 接受 / ☐ 改判：________ |

### 2.3 推进规则（仅同步，业务方可质疑）

plan v1 §3.3 L191-196 锁定 4 条状态推进规则，业务方如有质疑可在评论留意见，
否则视为默认接受：

1. `published` 前必须至少绑定一个 canonical 引用项 + 一条可见性策略
2. 发布/下线/策略变更必须写 `topic_package_review_record` + `audit_event` + `capability_call`
3. 删除旧引用只能标记 retired/removed，不删 canonical 对象
4. `published` 后目录 / 资源状态变化由读模型反映，专题包不反向覆盖源状态

- **建议**：无质疑、默认接受。4 条都是「审计落库 + 只投影不反向覆盖源」的硬纪律，与 D4 审计总线 / plan v1「专区不持有目录事实」一致。

### 2.4 sign-off 形式

见 §5 — 8 项默认值勾选结果 + Q2.1 三选一 + 推进规则质疑（如有）写进 PR 评论 body。

---

## 3. 三维可见性矩阵（组织 + 角色 + 消费面）

### 3.1 三维定义

来源：plan v1 §6.1 + §九 T2。策略输入维度（首版）：

- **组织（org_snapshot）**：sd-default 内的部门 / 委办厅局（如「省民政厅」「省医保局」）
- **角色（role_codes）**：7 角色码集合（plan v1 §〇 + roles.md 表）
- **消费面（surface）**：`webui / api / cli / mcp / a2a` 5 选项

### 3.2 默认岗位授权矩阵 + 跨组织默认（示例 — Z1 医疗救助共享专区）

> **建议（Jobs 视角）**：整体接受本矩阵作为默认——它沿用旧 `share_zone_org_auth` 的
> 部门授权语义、收敛到统一租户策略；唯一从严点是 `policy.update` 双签（见 Q3.1）。

| 角色码 | 同组织（省民政厅）行为 | 跨组织（如省人社厅员工）默认 | webui | api | cli | mcp | a2a |
|---|---|---|---|---|---|---|---|
| `ROLE_ORGAN_OPERATER` 部门操作员 | 看 + 申请 | ✅ 可见但需申请 | ✅ | ✅ subscribe | — | — | — |
| `ROLE_ORGAN_MANAGER` 部门管理员 | 看 + 申请 + 配置 | ✅ 可见但需申请 | ✅ | ✅ subscribe/configure | ✅ list/curate | — | — |
| `ROLE_BUSIAUDIT` 业务运营员（大数据局） | 看 + 审核 + 发布 | ✅ 全域可见（审核职责） | ✅ | ✅ review/publish；policy.update **需双签** | ✅ list/approve | ✅ query/metric.query | ✅ 外部 evidence 审核 |
| `ROLE_SYSTEM` 平台运维员 | 不进 P7 主导航 | — | ❌ | ✅ 仅运维 query | ✅ list | — | — |
| `ROLE_SECURITY_ADMIN` 安全管理员 | 不进 P7 | — | ❌ | — | — | — | — |
| `ROLE_SECURITY_AUDIT` 安全审计员 | 不进 P7 主导航 | ✅ 全域 metric.query 审计 | ❌ | ✅ 仅 metric.query | — | — | — |

### 3.3 业务方需对齐

- **Q3.1**：上述矩阵 ✅/❌ 分布 + 跨组织默认是否符合实际岗位职责？
  - 关键点（默认从严）：可见性策略写权限 `policy.update` **默认收紧为「`ROLE_BUSIAUDIT`
    + 大数据局领导双签」**；业务方是否需要放开为 `ROLE_BUSIAUDIT` 独立配置？
    （政务安全产品：敏感写权限默认收紧、由业务方主动放开，而非默认放开再问要不要收）
  - **建议**：保持双签默认。可见性策略一改影响全域可见面，单人可改风险偏高；要放开，等真实运营压力出现再放。
- **Q3.2**：分级授权（如同 catalog 不同字段分级别授权）首版**不做**（plan v1
  §〇 + §九 T2 + 基线 §5.6 #3 已写死延后到 R14 表单 schema 化引擎 Wave 2 后再
  评估）。业务方是否仍认可此延后？
  - **建议**：认可延后。分级授权依赖表单 schema 引擎（R14），现在做会造一套一次性的临时实现。
- **附注**：「未授权 UI 入口不渲染」原则已在系统层确立（CLAUDE.md MEMORY
  `feedback_no_permission_invisible`），不在本次签字范围；如业务方质疑可在评论
  留意见。

### 3.4 sign-off 形式

见 §5 — 矩阵接受 / amendments + Q3.1/Q3.2 答案写进 PR 评论 body。

---

## 4. 复活边界 — 只做 / 不做清单确认

### 4.1 zw-brain F9 做的事

| 项 | 形态 | 真值源章节 |
|---|---|---|
| P7 共享专区主入口 + 专题包列表 / 详情页 | 1 个 Vue 页面 | plan v1 §四 L217 + plan v1 §五 |
| TopicPackage 投影表 | 物理表（Base.metadata.create_all，不进 alembic） | plan v1 §3.1 |
| capability slug | Registry manifest（清单见 plan v1 §四） | plan v1 §四 + plan v1 §三 |
| 5 消费面（webui / api / cli / mcp / a2a） | 投影，统一 contract 生成 | plan v1 §四 L217 |
| sd-default 山东标杆 fixture | tests/fixtures/topic_package/*.json | plan v1 §四 |
| e2e 测试 | J1 找数 + J2 运营 + D7 守护 | plan v1 §六 |

### 4.2 zw-brain F9 不做的事（业务方逐条确认 ✅ 不做 / ⚠ 需改判）

> **建议（Jobs 视角）**：8 行全部 **✅ 接受不做**。每一行不是"省事砍掉"，而是已有 D-编号 /
> 禁区决策托底（见「原因」列）；任一行改判 = 推翻既有架构边界，需走 R13 重新立项，本次勿动。

| 旧平台形态 | 默认 | 建议 | 业务方判定 | 原因 |
|---|---|---|---|---|
| 旧专区后台独立 UI（菜单导航形态） | ❌ 不做 | ✅ 接受 | ☐ ✅ 接受 / ☐ ⚠ 需改判 | D8 P7 共享专区是 J1+J2 入口，不复刻菜单导航 |
| 旧示范应用门户独立站点 | ❌ 不做 | ✅ 接受 | ☐ ✅ 接受 / ☐ ⚠ 需改判 | plan v1 §1.3 L48 + §八 #5 |
| 旧基础主题库页面引擎 | ❌ 不做 | ✅ 接受 | ☐ ✅ 接受 / ☐ ⚠ 需改判 | plan v1 §1.3 L49 + §八 #6 |
| `dsp_basesubject` 81 张独立表 | ❌ 不做 | ✅ 接受 | ☐ ✅ 接受 / ☐ ⚠ 需改判 | 基线 §5.6 #13 + D7 forbidden-zone（preflight 段 10 硬保护） |
| catalog/resource/model 权威状态镜像 | ❌ 不做 | ✅ 接受 | ☐ ✅ 接受 / ☐ ⚠ 需改判 | plan v1 §1.2 + §3.1 L159-163（只投影不持有） |
| 旧 `share_zone_appkey.app_key` 服务密钥 | ❌ 不做 | ✅ 接受 | ☐ ✅ 接受 / ☐ ⚠ 需改判 | plan v1 §八 #3 |
| 评论社区 / 收藏系统 | ❌ 不做 | ✅ 接受 | ☐ ✅ 接受 / ☐ ⚠ 需改判 | plan v1 §八 #5 |
| 国家平台 / 上级平台上报协议（在 P7 内实现） | ❌ 不做 | ✅ 接受 | ☐ ✅ 接受 / ☐ ⚠ 需改判 | plan v1 §八 #7（统一交由 adapter） |

### 4.3 sign-off 形式

见 §5 — 8 行勾选结果写进 PR 评论 body。如有 ⚠ 需改判项，本次 review 不签，
回退修改 plan v1 后下次 review。

---

## 5. F9 启动条件清单（review 结束后落盘）

### 5.1 业务方 sign-off 的标准载体（与项目惯例对齐）

业务方对 §1 / §2 / §3 / §4 全部 sign-off 后，**统一以单一 PR label `signoff:e3.F9`
+ PR body `<!-- signoff ... -->` 机读块触发**（D46.d：合并时 `signoff-ledger.yml` 调
`signoff_from_pr.py` 把签字落成 `.testing/signoff/e3.F9.signoff.yaml` 账本，scope=`eN.FX` 模式）。

label 是开关；机读块声明 `scope`/`kind`/`covers`，实质内容（4 项决策结果）写进 **PR 评论 body**，按 §5.2 模板。

### 5.2 PR 评论 body 推荐模板（业务方填空即可）

```
[F9 launch sign-off | by <角色> | <日期>]

§1 共享专区优先级 + 每个专区策展的目录清单：
  - Z1 医疗救助专区：P? | 目录含: <列表> | excluded: <列表>
  - Z2 医保码专区：P? | 目录含: <列表>
  - Z3 异地就医专区：P? | 目录含: <列表>
  - Q1.1 调换/替换：<无 | 改为：...>
  - Q1.2 一表通降级：<认可 | 反对：...>
  - Q1.3 目录清单完整性 / 未命中候选数据源：<完整 | 增删：... | 数据源：...>

§2 状态机：
  - 8 项默认值：<全接受 | 改判：第 N 项 = ...>
  - offline_pending：<保留 | 简化去掉 | 另议：...>
  - 推进规则质疑：<无 | ...>

§3 可见性矩阵：
  - 接受现状 | amendments: ...
  - Q3.1 BUSIAUDIT policy.update: <双签（默认）| 放开为独立>
  - Q3.2 分级授权延后：<认可 | 反对：...>

§4 复活边界 8 行：
  - <全 ✅ 接受 | ⚠ 改判：第 N 行 = ...>
```

**若全部采纳本文「建议」列，可直接贴以下已填版（再就个别分歧改动即可）：**

```
[F9 launch sign-off | by <角色> | <日期>] 全采纳建议

§1 专区：Z1=P0（目录全含、排除残疾人两项补贴）；Z2=P1；Z3=P1（补种后优先于 Z2）
   Q1.1 不调换不加 | Q1.2 认可一表通降级 | Q1.3 按 §1.1 建议定稿
   启动路径：采纳 §0 硬前置 (a) — Z1 先做，Z2/Z3 待 catalog 补种
§2 状态机：8 项默认值全接受 | offline_pending 保留 | 推进规则无质疑
§3 可见性：接受矩阵 | Q3.1 policy.update 双签 | Q3.2 认可分级授权延后
§4 复活边界：8 行全 ✅ 接受不做
```

### 5.3 落盘 4 项（reviewer 责任 + 机械守卫）

业务方 sign-off 后，本工作区按以下顺序落盘：

- [ ] **A**：vehicle PR 加 label `signoff:e3.F9` + PR body `<!-- signoff ... -->` 机读块
      （`scope: e3.F9` / `kind: 决策签字` / `covers`: 被签 .feature 列表 / `decision_only: false`）。
      合并时 `signoff-ledger.yml` 调 `signoff_from_pr.py` 自动生成 `.testing/signoff/e3.F9.signoff.yaml`
      账本（`signed_by`=approvers，`date`=merged_at，`evidence`=PR#）。
- [ ] **B**：本文 frontmatter `status: approved`。
- [ ] **C**：CLAUDE.md 追加 `D<编号>` 决策条（编号 = sign-off 当天最大 D + 1，
      不预设；当前最大 D33.d，故下个为 D34，但若本次 review 与他 D 并发以实际为准）。
- [ ] **D**：新 worktree 启动 F9 worker（按 reconstruction plan v1 §四 起手）。

**机械守卫**（确定性自动化运营和运维）：

- A 项账本由 `signoff-ledger.yml` + `signoff_from_pr.py` 在 PR 合并时自动生成（D46.d，GitHub 是录入口、账本是真相）；账本 schema / `covers` 的 .feature 存在 / `evidence` 非空由 **段 63 `check_signoff_ledger.py`** 校验
- A+B 一致性由 **段 54 `check_signoff_landed.py`** 机械校验：本文 `status: approved` 时，`scope: e3.F9` 必须在 `.testing/signoff/e3.F9.signoff.yaml` 账本有对应记录；缺则 FAIL。**「C/D 靠人记忆」债已由 D46.b 账本单源关闭**（不再 debt 化）
- 本材料包内容质量由 **段 53 `check_signoff_package.py`**（D35）守卫：数据真实性标签
  （seed/dump 命中校验）+ 禁过程数字 + 强制「启动硬前置」节 + 每个判定表配「建议」列

review 中任一项业务方未签字 / 改判 / 需进一步澄清 → F9 不启动，回 R13 元规则
等下次 review。

## 6. 议程外补充材料（业务方按需）

| 文档 | 对应议程节 | 阅读价值 |
|---|---|---|
| `docs/customer-demo-j1.md` L10-12, L61 | §1 Q1.1 | Z1/Z2/Z3 专区引用的核心目录在 J1 demo 已 verified 命中 |
| `docs/customer-demo-j2.md` L151 | §1 边界 | J1/J2 互不重叠的目录角色分工说明 |
| `docs/approved/zw-brain-roles.md` | §3 角色矩阵 | 7 角色码定义详情（适合质疑 §3.2 矩阵时查阅） |
| `docs/approved/zw-brain-architecture.md` §5.2 P7 + §5.6 #13 + §3.4 C | §4 复活边界 | P7 产品形态边界 + basesubject 不复造原因 + 一表通降级原因 |
| `docs/legacy-not-reproduce-signoff.md` | §4 边界回潮风险 | 业务方 PR #129 D 类 ✅ 复活原文（避免边界理解漂移） |
| `docs/approved/research-yibiaotong.md` | §1 Q1.2 | 一表通保留作未来重启的研究材料 |
