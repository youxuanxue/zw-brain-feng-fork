# 政务数据大脑 v4 高保真 Prototype

> **这不是生产代码**。这是用于评审 `zw-brain` v4 方案的高保真可点击原型：保留 8+1 页面边界，用真实角色链路验证“先复用模板、再差异补录、结果回流共享、最后进入减负治理”的首条黄金旅程。
> 交付形态：**真 UI、无后端、mock 数据、双击即开**。

## 怎么打开

直接双击 `prototype/ui/index.html`。

不需要：
- `npm install`
- `pip install`
- 启动本地服务

## 这次评审要回答什么

这版原型不是再讲一遍抽象平台，而是要现场回答 5 个问题：

1. **R1–R8 真实角色是否被正确表达**
   - 不是抽象的“申请方 / 平台管理员”
   - 而是要数的人、控准入的人、填差异的人、审异常的人、做模板治理的人、做减负治理的人

2. **首条黄金旅程是否真能走通**
   - 主案例固定为“法人单位基础信息台账模板”
   - 主链固定为：**发现模板 → 复用判断 → 受控准入 → 预填补录 → 审核汇总 → 回流共享 → 减负治理**

3. **AI 是否只减摩、不越权**
   - AI 负责解析、解释、草拟、摘要、预填说明
   - AI 不负责提交、审批、汇总确认、回流生效、能力包生效

4. **页面之间是否有连续状态，而不是一组静态说明页**
   - 关键动作必须真实改变状态
   - 列表页、详情页、时间线、治理页和大屏指标必须同步变化

5. **负面流是否诚实表达失败与边界**
   - 退回补正、驳回、审计阻断、回流未满足门槛、能力包越权都必须被明确展示

## 页面范围

本版原型维持 **8 个主页面 + 1 个独立大屏**：

| 页面 | 作用 | 对应旅程 |
|------|------|---------|
| P1 工作台 | 不同角色的待办、提醒、推荐与异常摘要 | 主入口 |
| P2 资源发现 | 先发现资源与模板，再决定是否新增采集 | Journey 1 / 2 |
| P3 申请 / 审批 / 跟踪 | 复用申请、准入判断、预填补录、审核汇总 | Journey 3 / 4 / 5 |
| P4 交付 / 交换 / 回流 | 任务下发、自动汇总、回流候选与回执 | Journey 6 |
| P5 提供方管理 | 模板、目录、服务与版本治理 | Journey 6 |
| P6 合规与运营 | 重复要数、绕行、争议、减负证据与审计回放 | Journey 7 |
| P7 共享专区 / 专题包 | 将高价值模板以 zw-brain 前台专题资产形态组织出来 | Journey 1 / 2 / 6 |
| P8 平台接入与扩展中心 | 仅 R7 使用；能力包审核、注册、暴露治理 | S2 |
| K12 指挥中心大屏 | 只读消费主链路事实，查看减负与异常态势 | 独立部署面 |

## 路由

- `#/p1-workbench`
- `#/p2-discovery`
- `#/p2-discovery/resource/:id`
- `#/p3-request-flow`
- `#/p3-request-flow/request/:id`
- `#/p3-request-flow/review/:id`
- `#/p4-delivery-exchange`
- `#/p4-delivery-exchange/task/:id`
- `#/p5-provider`
- `#/p6-compliance-ops`
- `#/p6-compliance-ops/dispute/:id`
- `#/p7-zones-pack`
- `#/p7-zones-pack/zone/:id`
- `#/p8-integration-admin`
- `#/p8-integration-admin/package/:id`
- `#/dashboard`
- `#/dashboard/alert/:id`

## 角色口径

- R1 上级业务需求发起人
- R2 审批承接人员
- R3 镇街填报人员
- R4 村社区填报人员
- R5 审核汇总人员
- R6 台账管理员
- R7 目录管理员
- R8 合规与减负治理

## 推荐评审顺序（30–45 分钟）

### 0. 先读主线脚本
- 打开 `prototype/storyboards/00-core-journey-e2e.md`
- 先确认这次评审讲的是一条主链，而不是 8 个孤立页面

### 1. R1：先发现模板，再发起复用申请
- 角色切到 **R1**
- 依次进入：
  - `#/p1-workbench`
  - `#/p2-discovery`
  - `#/p2-discovery/resource/res-jbxx-ledger`
  - `#/p3-request-flow`
- 现场要看见：
  - “法人单位基础信息台账模板”被排到前面
  - 已识别“先复用模板、只补差异字段”
  - 申请不是裸提新表，而是结构化复用申请

### 2. R2：受控准入，不让重复要数直接过
- 角色切到 **R2**
- 进入：`#/p3-request-flow/review/REQ-2026-04-25-0011`
- 先点：**通过并下发补录**
- 现场要看见：
  - 状态从待审批进入补录阶段
  - P3 / P4 的状态与时间线同步变化
  - AI 只给建议，不替人点击批准

### 3. R3 / R4：只补差异字段，不再整表录入
- 角色切到 **R3** 或 **R4**
- 进入：`#/p3-request-flow/request/REQ-2026-04-25-0011`
- 点：**提交差异补录**
- 现场要看见：
  - 已预填字段与待补录字段分离
  - 提交后进入“待汇总确认”
  - P4 任务状态同步进入汇总阶段

### 4. R5：只处理异常与自动汇总确认
- 角色切到 **R5**
- 回到：`#/p3-request-flow/review/REQ-2026-04-25-0011`
- 点：**确认自动汇总**
- 现场要看见：
  - 状态进入已汇总
  - 回流候选从“待确认”变成供给侧待判断对象
  - 时间线新增汇总确认节点

### 5. R6 / R7：让本次补录变成下次默认复用能力
- 先看：`#/p4-delivery-exchange/task/DLV-2026-04-25-0011`
- 点：**确认回流共享**
- 再看：
  - `#/p5-provider`
  - `#/p7-zones-pack/zone/business`
- 现场要看见：
  - 回流状态变为已确认
  - 模板版本、供给侧摘要、专题入口信任信息同步变化
  - 说明“这次补录沉淀成了下次可直接复用的模板能力”

### 6. R8：看治理结果，而不是看后台日志
- 角色切到 **R8**
- 依次看：
  - `#/p6-compliance-ops`
  - `#/p6-compliance-ops/dispute/DSP-2026-04-25-0003`
  - `#/dashboard`
- 现场要看见：
  - 重复要数率、补录字段数、自动汇总覆盖率
  - 绕行告警、争议调查、审计回放和知识建议能串起来
  - 大屏只读消费主链路事实，不进入办理态

### 7. R7：审核外部能力包，但不把写权交出去
- 角色切到 **R7**
- 进入：
  - `#/p8-integration-admin`
  - `#/p8-integration-admin/package/PKG-2026-04-25-001`
- 可分别点：**批准** / **退回补充** / **驳回**
- 现场要看见：
  - 状态变化真实反映在列表与详情
  - 审核意见同步变化
  - 平台坚持 capability 统一契约与写权边界

### 8. 最后走负面流
- 对照：`prototype/storyboards/08-negative-flows-and-guardrails.md`
- 重点核查：
  - 退回补正不会被伪装成成功
  - 驳回会终止主链
  - 未满足汇总确认前不能确认回流
  - 越界能力包不能变成可注册态
  - K12 故障切换只进入快照模式，不接管主办理

## Storyboards

- `prototype/storyboards/00-core-journey-e2e.md`
- `prototype/storyboards/01-discovery-to-apply.md`
- `prototype/storyboards/02-review-and-approval.md`
- `prototype/storyboards/03-delivery-and-direct.md`
- `prototype/storyboards/04-provider-lifecycle.md`
- `prototype/storyboards/05-compliance-ops.md`
- `prototype/storyboards/06-integration-admin.md`
- `prototype/storyboards/07-leader-dashboard.md`
- `prototype/storyboards/08-negative-flows-and-guardrails.md`

## 能力边界与外部建设输入

这里的能力文档描述的是 **领域面与能力边界**，不是把主状态机外包给外部辅助。

`zw-brain` 自身的内建 WebUI / API 已经构成普通用户主旅程 baseline；管理员与运维侧可通过 API / CLI 完成交付、调查与注册治理；MCP 继续作为同一 Capability 契约的投影供 Agent 使用。外部能力包只负责在统一 Capability 契约下做解析、草拟、解释、摘要、预检查与适配，不得接管 `submit`、`review-and-decide`、`reconcile-receipt`、`register-version`、`apply-tenant-policy` 等责任写动作。

阅读顺序建议：
- 先看 `prototype/capability-sheets/README.md` 的平台内建 / 外部辅助边界
- 再看每个领域面的平台必备能力
- 最后看外部 ANP 适合建设的增益能力范围

- 总览：`prototype/capability-sheets/README.md`
- `prototype/capability-sheets/CP-01-discovery-and-intent-refinement.md`
- `prototype/capability-sheets/CP-02-application-and-approval-flow.md`
- `prototype/capability-sheets/CP-03-delivery-exchange-and-direct-link.md`
- `prototype/capability-sheets/CP-04-provider-governance-and-publishing.md`
- `prototype/capability-sheets/CP-05-compliance-evidence-and-ops.md`
- `prototype/capability-sheets/CP-06-integration-admin-and-package-registry.md`

## 验证 checklist

| # | 要验证的主张 | 对应页面/场景 | 验证 |
|---|-------------|--------------|------|
| 1 | 页面仍收敛为 8 个主页面 + 1 个独立大屏 | P1–P8 + K12 | ☐ |
| 2 | 前台角色已切换为 R1–R8，而不是抽象平台角色 | 全局 | ☐ |
| 3 | P2 能把“法人单位基础信息台账模板”以前台可发现资产呈现出来 | P2 / P7 | ☐ |
| 4 | P3 能表达“先复用模板，再进入受控准入” | P3 | ☐ |
| 5 | P3 能表达“已预填字段 + 差异补录字段 + 退回修改” | P3 request detail | ☐ |
| 6 | P3 审核详情能表达“异常项 + 自动汇总 + 人工确认边界” | P3 review detail | ☐ |
| 7 | P4 能表达“补录结果如何回流共享资产池” | P4 | ☐ |
| 8 | P5 能表达“模板版本、字段口径、服务治理”三者联动 | P5 | ☐ |
| 9 | P6 能直接展示重复要数、绕行、减负指标与证据链 | P6 | ☐ |
| 10 | P7 仍是前台专题资产入口，而不是后台标准管理页 | P7 | ☐ |
| 11 | P8 只服务 R7 管理员，不扩张成普通用户主叙事 | P8 | ☐ |
| 12 | 所有关键写动作仍保留人工确认边界 | P3 / P4 / P8 | ☐ |
| 13 | 外部辅助全部失效时，主流程仍可通过结构化页面闭环 | 全局 / 负面流 | ☐ |
| 14 | K12 体现减负治理与异常钻取，但保持只读投影 | `#/dashboard` | ☐ |
| 15 | 全局始终符合“AI 只减摩，不越权” | 全局 | ☐ |

## 自检与质量

- 路由与多角色冒烟：`node prototype/scripts/smoke.js`
- GATE-1 原型门禁：`python3 scripts/check_gate1_prototype.py`

## 原型边界

本原型**不做**：
- 真实后端 / 数据库 / 推理调用
- 持久化写入
- 完整表单校验
- 移动端适配

本原型**重点回答**：
- v4 的 8+1 IA 是否能承载真实角色链路
- “先复用模板，再差异补录”是否成立
- “审核汇总 → 回流共享 → 减负治理”是否被产品前台真正表达出来
- 关键失败路径是否被诚实表达，而不是被 toast 掩盖
