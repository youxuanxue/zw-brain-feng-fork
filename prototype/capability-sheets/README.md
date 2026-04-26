# 能力边界与外部建设输入

> 本目录不是 6 个对等的“外部 ANP 能力包”清单，而是给评审方和外部建设方使用的**领域能力边界说明 + 外部建设输入入口**。
> 
> v4 的前提很明确：**核心高频内建，长尾默认外部化；AI 只加速，不越权；控制面必须存在，但要保持纤薄。**
> 
> 外部辅助能力只能增益体验，不得成为进入主旅程的前置依赖。

## 为什么要先划清边界

如果不先划清边界，`zw-brain` 很容易重新滑回两种旧问题：

1. 把平台自己的主状态机和控制面，误写成可外包的能力包。
2. 把外部包的草拟、解释、摘要、预检查，误写成拥有提交、审批、注册、策略生效权的主体。

这两种误读都会让产品边界失真。

因此，本目录先回答两件事：

- 哪些能力**必须由 zw-brain 平台内建并掌握写权**
- 哪些能力**适合由外部 ANP 构建，再以统一 Capability 契约回注册**

## 能力归属判定规则

### 1. 默认属于平台内建的能力

凡是满足以下任一条件，默认由 `zw-brain` 内建：

- 推进核心状态机
- 属于 `confirm-required` 或 `write-with-audit`
- 写入申请、审批、交付、发布、注册、租户策略等事实状态
- 生成或消费证据链事实源
- 让 package / version / exposure / tenant policy 正式生效

典型动作：`submit`、`review-and-decide`、`track-status`、`reconcile-receipt`、`publish-or-suspend`、`register-version`、`apply-tenant-policy`。

### 2. 默认适合外部化的辅助能力

凡是以减摩、解释、预检查、适配为主，且**不拥有主状态写权**，默认可作为外部辅助包候选：

- `draft`
- `explain`
- `summarize`
- `validate`
- `recommend`
- `adapter`

这些能力可以提升体验和复用度，但不能替平台执行责任动作。

### 3. 更强约束：外部只增益，不得成为前置依赖

即使这些外部辅助能力全部失效，核心业务仍必须能通过平台内建交互完成。最低要求包括：

- 发现阶段至少保留目录浏览、条件筛选、资源详情和进入申请流按钮
- 申请 / 审批阶段至少保留结构化表单、显式确认按钮、时间线和回执
- 交付 / 合规 / 注册阶段至少保留事实源查询、状态字段、审核字段和人工确认动作

### 4. 明确禁止外部包拥有的范围

外部包不得直接拥有以下权力：

- 提交申请或推进申请状态
- 替审批人写入最终决定
- 确认交付回执或推进交付状态
- 发布 / 下线目录、资源、服务
- 覆盖原始审计证据或写入最终调查结论
- 批准 / 驳回 / 生效 package 注册与 tenant policy

## 六个领域面总览

| 领域面 | 归属 | 写权 | 平台 baseline 是否可独立闭环 | 外部 ANP 首批必要性 | 外部允许范围 |
|---|---|---|---|---|---|
| CP-01 发现与意图收敛 | 平台 baseline + 外部增强 | none | yes | P0 | 意图解析、追问补齐、推荐理由、下一步建议 |
| CP-02 申请与审批 | 平台内建为主 | platform-only | yes | P1 | 申请草拟、审批意见草稿、状态解释 |
| CP-03 交付与交换 | 平台内建为主 | platform-only | yes | P1 | 状态解释、外部通道适配、恢复建议 |
| CP-04 供给侧治理与发布 | 平台内建为主 | platform-only | yes | P1 | 治理优先级建议、发布前检查、主题投影建议 |
| CP-05 合规、证据与运营 | 平台内建为主 | platform-only | yes | 不建议首批 | 摘要、告警串联、知识建议 |
| CP-06 接入管理与注册中心 | 平台内建为主 | platform-only | yes | P1 | manifest / schema 预检查、审核意见草稿 |

## 如何阅读这 6 份文档

这 6 份文档描述的是 **6 个领域面**，不是 **6 个对等外部包**。

阅读方式应当是：

1. 先看每份文档里的 **归属判定 / Ownership boundary**
2. 再看 **平台内建能力**
3. 最后看 **外部 ANP 可建设的辅助能力**

其中：

- `CP-01` 是平台 baseline + 外部增强，可作为首批外部辅助包输入，但不能让发现入口依赖外部在线
- `CP-02/03/04/05/06` 以平台内建能力说明为主，同时给出外部允许范围

## 目录内容

- `CP-01-discovery-and-intent-refinement.md`
- `CP-02-application-and-approval-flow.md`
- `CP-03-delivery-exchange-and-direct-link.md`
- `CP-04-provider-governance-and-publishing.md`
- `CP-05-compliance-evidence-and-ops.md`
- `CP-06-integration-admin-and-package-registry.md`

## 这批文档回答什么

- 哪些能力必须由 `zw-brain` 平台自身内建
- 哪些能力值得优先外部化到 ANP，再通过统一契约回注册
- 平台 baseline 在没有外部辅助时如何独立闭环
- 每个领域面的页面归属、写权边界、审计与 ACL 约束是什么
- 外部建设方在回注册前，最少需要准备哪些 manifest / schema / side effects / ACL 信息

## 这批文档不回答什么

- 不代表当前仓内 runtime 已完成全部 REST / CLI / MCP / A2A 实现
- 不把 P3 / P4 / P5 / P6 / P8 的主状态机整体外包给 ANP
- 不替代 `docs/approved/zw-brain-architecture-v4-gpt55.md` 作为架构总基线；当前评审以该提案与 prototype 一并收敛
- 不提供最终技术实现细节，只提供产品边界与外部建设输入
