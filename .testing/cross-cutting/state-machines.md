---
doc_id: testing-cross-cutting-state-machines
status: navigation
driven_by:
  - docs/approved/zw-brain-architecture.md §3.3 / §9.2
  - docs/approved/zw-brain-data-model.md
---

# 状态机覆盖矩阵

> **目的**：基线 §3.3 列出的"强状态领域"是后台不能简化的硬约束（"前台收敛激进，后台领域不简化"）。本表确保每个状态机都有 .feature 覆盖完整迁移路径。

## 1. Catalog 6 态 + 2 计算态（基线 §3.3）

| from | to | actor | 覆盖 .feature |
|---|---|---|---|
| 0 草稿 | 1 待审 | 编目员 submit | wave-1 j2-online-catalog-compile + wave-1 j2-department-review |
| 1 待审 | 2 部门审批通过 | 部门管理员通过 | wave-1 j2-department-review |
| 1 待审 | 3 驳回 | 部门管理员驳回 | 同上 |
| 2 部门审批通过 | 3 驳回 | BUSIAUDIT 驳回 | wave-1 j2-platform-publish |
| 2 部门审批通过 | 4 发布 | BUSIAUDIT 发布 | 同上 |
| 3 驳回 | 1 待审 | 编目员重新提交 | wave-1 j2-department-review (round 计数) |
| 4 发布 | 5 下线 | BUSIAUDIT 下线 | wave-1 j2-platform-publish |
| 应用层计算：4 发布 → "国家通道转报中" | — | application.escalate_national | wave-3 national-direct |
| 应用层计算：任意 → "撤销中" | — | 撤销窗口 grace_period | wave-1 j1-credential-revoke (类比) |

## 2. shared_type 3 态

| 值 | 含义 | 覆盖 |
|---|---|---|
| 1 无条件 | 平台单步审 | wave-0 j1-approval-unconditional |
| 2 有条件 | 部门审 + 平台复核两步 | wave-0 j1-approval-conditional |
| 3 不予共享 | 不进 J1 申请流 | wave-0 j1-resource-discovery (负向：不显示) |

## 3. 资源 3 物化形式（基线 §3.3）

| materialization | 旧表 | 覆盖 |
|---|---|---|
| table | data_resource_table | wave-1 j2-resource-mount |
| file | data_resource_file | 同上 |
| api | data_resource_api | 同上 |

## 4. Application 5 业务节点 / 7 态序列（基线 §3.3）

| business_node | XML status (data_business.status) | 覆盖 |
|---|---|---|
| 1 编制 | 0 草稿 | wave-0 j1-application-draft |
| 1 编制 | 1 待审 | wave-0 j1-application-draft (提交后) |
| 2 校核 | 4 部门同意 | wave-0 j1-approval-conditional |
| 3 汇总 | (合并到 supply-demand 流程) | wave-1 j1-supply-demand-meta-merge |
| 4 响应 | 5 提供方处置 | wave-0 j1-approval-conditional (变体) |
| 5 反馈 | 6 已授权 | wave-0 j1-approval-unconditional / wave-0 j1-credential-issue |
| 应用层 | 已撤回 / 已暂停 | wave-1 j1-credential-revoke |

完整状态机迁移表 → wave-0 j1-approval-conditional "Scenario: 回归"。

## 5. Objection 5 维度独立状态机（基线 §3.3）

| dimension | 旧表 | 覆盖 |
|---|---|---|
| authz | data_objection_authz | wave-1 j1-objection-authz |
| catalog | data_objection_catalog | wave-1 j1-objection-catalog |
| content | data_objection_content | wave-1 j1-objection-content |
| resource | data_objection_resource | wave-1 j1-objection-resource |
| use | data_objection_use | wave-1 j1-objection-use |

辅助表：

| 辅助表 | 用途 | 覆盖 |
|---|---|---|
| data_objection_evaluate | 处理结果评价 | wave-1 j1-objection-authz (评价 Scenario) |
| data_objection_process | 处理过程链路 | 各 j1-objection-*.feature 审计回放 Scenario |

## 6. 双轨编制（政务目录 vs 国家扩展要素）

| 轨道 | 状态机 | 覆盖 |
|---|---|---|
| 政务目录主线 | catalog 6+2 态 | wave-1 j2-online-catalog-compile |
| 国家扩展要素 | data_ext_elem_catalog_compile_task 独立流程 | wave-1 j2-online-catalog-compile (Scenario: 国家扩展要素) + wave-3 national-ext-elements |

## 7. trust_level 三级（基线 §8.2）

| level | 含义 | 覆盖 |
|---|---|---|
| untrusted | 外部 Agent 默认 | wave-1 ext-agent-pilot + wave-2 b1-2-trust-level-upgrade |
| verified | 经 B1.2 管理员升级 | wave-2 b1-2-trust-level-upgrade |
| platform | 仅限 zw-brain 内置 Agent | wave-0 infra-agentruntime-embedded |

降级（verified → untrusted）：wave-2 b1-2-trust-level-upgrade (收紧 Scenario)
拒绝（× → platform）：同上 (负向 Scenario)

## 维护原则

- 任何 .feature 含状态机断言时必须**列出**该断言对应的迁移行
- 新增状态机 → 必须更新本表 + 经业务方 sign-off（R13）
- 状态机不能在 UI 简化为"状态徽标"，必须可在审计回放重现完整路径
- 非法迁移**必须** 409 + audit reject（覆盖在各对应 .feature 负向 Scenario）
