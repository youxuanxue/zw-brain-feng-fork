---
doc_id: testing-cross-cutting-role-matrix
status: navigation
driven_by:
  - docs/approved/zw-brain-architecture.md §5.1 / §11 R10/R11
  - docs/approved/zw-brain-roles.md §七 角色→旅程任务地图
---

# 角色 × 旅程 / 支撑面 任务覆盖矩阵

> **目的**：保证每个 7 角色码在 J1 / J2 / B1.1 / B1.2 中应当承担的高频任务都被 .feature 文件覆盖。

## 角色总览（基线 R10）

| 角色码 | 中文名 | 旧菜单数 | 主要参与 |
|---|---|---|---|
| `ROLE_SYSTEM` | 平台运维员 | 49 | B1.2 接入扩展中心 + 运维 |
| `ROLE_BUSIAUDIT` | 业务运营员（数据主管部门） | 132 | J1 审批 / J2 复核 / B1.1 合规 / B1.2 |
| `ROLE_ORGAN_MANAGER` | 部门管理员 | 138 | J1 申请审批 / J2 资源管理审核 |
| `ROLE_ORGAN_OPERATER` | 部门操作员 | 78 | J1 申请发起 / J2 资源编目挂接 |
| `ROLE_SECURITY_ADMIN` | 安全管理员 | 17 | B1.1 数据安全独立模块 |
| `ROLE_SECURITY_AUDIT` | 安全审计员 | 11 | B1.1 审计督查段 |
| tag `tag_lead_dept` | 牵头部门标签 | 2 | 依附 ORGAN_MANAGER；基础主题分类审核 |

## 覆盖矩阵

> ✓ = 该角色 × 该面 至少有 1 个 .feature 覆盖；空 = 该角色与该面**不**应交叉（基线 R1/R11 约束）
> 数字 = .feature 文件数

| 角色 \ 面 | J1 找数→用数 | J2 挂数→维数 | B1.1 合规运营 | B1.2 接入扩展 |
|---|---|---|---|---|
| `ROLE_ORGAN_OPERATER` | ✓ Wave 0 (6) / Wave 1 (5) / Wave 2 (1) | ✓ Wave 1 (2) | — | — |
| `ROLE_ORGAN_MANAGER` | ✓ Wave 0 (1, 有条件分支) / Wave 1 (5) | ✓ Wave 1 (1) | — | — |
| `ROLE_BUSIAUDIT` | ✓ Wave 0 (1, 无条件分支) / Wave 1 (3) / Wave 2 (1) | ✓ Wave 1 (1) | ✓ Wave 2 (2) | ✓ Wave 2 (1, 协同) |
| `ROLE_SECURITY_ADMIN` | — | — | ✓ Wave 2 (1, b1-1-compliance-audit 合作面) | — |
| `ROLE_SECURITY_AUDIT` | — | — | ✓ Wave 2 (2) / Wave 4 (1) | ✓ Wave 2 (协同 trust_level 升级) |
| `ROLE_SYSTEM` | — | — | — | ✓ Wave 2 (2) / Wave 3 (1) |
| `tag_lead_dept` | — | ✓ Wave 1 (j2-online-catalog-compile 牵头审核 Scenario) | — | — |

**说明**：

- **空格子**不是 bug，是设计：基线 R1 普通用户首屏不见 B1；R11 方向由运行时计算（同一角色既可发起也可审批），不通过角色拆分。
- `ROLE_SYSTEM` 不在 J1/J2 主旅程：R2 / 基线 §5.1。
- `ROLE_SECURITY_*` 不在 J1/J2 主旅程：基线 §5.1 / `zw-brain-roles.md` §三。

## .feature 反向索引（角色 → 文件）

### ROLE_ORGAN_OPERATER

- waves/wave-0-golden-path/features/j1-resource-discovery.feature
- waves/wave-0-golden-path/features/j1-application-draft.feature
- waves/wave-0-golden-path/features/j1-credential-issue.feature
- waves/wave-0-golden-path/features/j1-api-call-monitoring.feature
- waves/wave-1-j1-j2-closed-loop/features/j2-online-catalog-compile.feature
- waves/wave-1-j1-j2-closed-loop/features/j2-resource-mount.feature
- waves/wave-1-j1-j2-closed-loop/features/j1-objection-*.feature（部分）
- waves/wave-1-j1-j2-closed-loop/features/j1-credential-revoke.feature（申请人主动撤销）
- waves/wave-2-engines-b1-zones/features/engine-recommend-prefer.feature
- waves/wave-2-engines-b1-zones/features/adapter-yibiaotong.feature（基层补差）

### ROLE_ORGAN_MANAGER（含 tag_lead_dept）

- waves/wave-0-golden-path/features/j1-approval-conditional.feature
- waves/wave-1-j1-j2-closed-loop/features/j1-objection-*.feature（提供方部门视角）
- waves/wave-1-j1-j2-closed-loop/features/j2-department-review.feature
- waves/wave-1-j1-j2-closed-loop/features/j2-online-catalog-compile.feature（含 tag_lead_dept Scenario）

### ROLE_BUSIAUDIT

- waves/wave-0-golden-path/features/j1-approval-unconditional.feature
- waves/wave-0-golden-path/features/j1-approval-conditional.feature（第二步平台复核）
- waves/wave-1-j1-j2-closed-loop/features/j1-objection-use.feature
- waves/wave-1-j1-j2-closed-loop/features/j1-supply-demand-meta-merge.feature
- waves/wave-1-j1-j2-closed-loop/features/j1-credential-revoke.feature
- waves/wave-1-j1-j2-closed-loop/features/j2-platform-publish.feature
- waves/wave-2-engines-b1-zones/features/engine-approval-flow.feature
- waves/wave-2-engines-b1-zones/features/engine-form-schema.feature（协同）
- waves/wave-2-engines-b1-zones/features/b1-1-compliance-audit.feature
- waves/wave-2-engines-b1-zones/features/b1-1-anomaly-detection.feature

### ROLE_SECURITY_ADMIN

- waves/wave-2-engines-b1-zones/features/b1-1-compliance-audit.feature（含其作为协同方）
- _注_：完整的 "数据安全中心独立模块"（17 菜单）是**外部依赖**（基线 §3.4 集团数据安全中心），不在 zw-brain 内重造。

### ROLE_SECURITY_AUDIT

- waves/wave-1-j1-j2-closed-loop/features/j1-objection-use.feature（参与 use 异议协同）
- waves/wave-2-engines-b1-zones/features/b1-1-compliance-audit.feature（审计督查段）
- waves/wave-2-engines-b1-zones/features/b1-2-trust-level-upgrade.feature（协同确认）
- waves/wave-4-legacy-retirement/features/b1-compliance-coverage.feature

### ROLE_SYSTEM

- waves/wave-0-golden-path/features/infra-agentruntime-embedded.feature（运维内置 Agent）
- waves/wave-2-engines-b1-zones/features/b1-2-package-registration.feature
- waves/wave-2-engines-b1-zones/features/b1-2-trust-level-upgrade.feature
- waves/wave-3-protocol-tenant-national/features/agentruntime-standalone-http.feature
- waves/wave-3-protocol-tenant-national/features/observability-cost-quota.feature
- waves/wave-4-legacy-retirement/features/legacy-write-entry-deprecation.feature

## 维护原则

- 新增 .feature → 同时更新本矩阵
- 角色码新增 → 必须先在 `docs/approved/zw-brain-roles.md` sign-off（R10 + R13 元规则）
- 任意 .feature 含角色断言时 actor_role 必须用 7 角色码字面值
