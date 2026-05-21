---
doc_id: testing-cross-cutting-role-task-skill-trace
status: navigation
driven_by:
  - docs/approved/zw-brain-roles.md §七 角色→旅程任务地图
  - docs/approved/zw-brain-architecture.md §5 + §6 (Capability) + §8 (AgentRuntime)
---

# 角色 → 旅程任务 → Capability/Skill 追溯表

> **目的**：把"角色 §七 角色→任务地图"延伸到具体 Capability slug 与 .feature，便于：
>
> 1. 实施 PR 时知道每个任务背后调用哪些 Capability
> 2. 业务方 review 时按"任务"维度审视而不是按"接口"维度
> 3. 三引擎可配置化时，定位哪些任务受影响

## 1. `ROLE_ORGAN_OPERATER` 部门操作员

### 旅程 J1 找数→用数

| 任务 | Capability slug | .feature |
|---|---|---|
| 检索目录 | `resource.search` | wave-0 j1-resource-discovery |
| 提交申请 | `application.draft` + `application.submit` | wave-0 j1-application-draft |
| 查看自家申请进度 | `application.view_own` | wave-0 j1-approval-conditional (Scenario: 申请人侧通知) |
| 领取凭据 | `credential.view` | wave-0 j1-credential-issue |
| 调用 API | （凭据 + 业务接口）`resource.fetch` | wave-0 j1-api-call-monitoring |
| 提交服务评价 | `application.evaluate` | wave-1 j1-objection-authz (评价类比) |

### 旅程 J2 挂数→维数

| 任务 | Capability slug | .feature |
|---|---|---|
| 在线编制目录 | `catalog.draft` | wave-1 j2-online-catalog-compile |
| 反向编目 | `catalog.reverse_compile` | 同上 |
| 批量导入 | `catalog.batch_import` | 同上 (Scenario: 批量导入) |
| 资源挂接 | `resource.mount` | wave-1 j2-resource-mount |
| 提交审核 | `catalog.submit_review` / `resource.submit_review` | wave-1 j2-department-review |

### 基层补差（仅基层归口部门）

| 任务 | Capability slug | .feature |
|---|---|---|
| 接收补差任务 | `task.view_assigned` | wave-2 adapter-yibiaotong |
| 字段补录 | `task.fill_back` | 同上 |
| 异常回传 | `task.report_anomaly` | 同上 |

## 2. `ROLE_ORGAN_MANAGER` 部门管理员（含可选 `tag_lead_dept`）

### 旅程 J1 找数→用数

| 任务 | Capability slug | .feature |
|---|---|---|
| 审批本部门申请 | `application.dept_approve` / `application.dept_reject` | wave-0 j1-approval-conditional |
| 暂停/收回授权 | `application.suspend` / `application.revoke_via_dept` (仅经 use 异议) | wave-1 j1-credential-revoke + wave-1 j1-objection-use |

### 旅程 J2 挂数→维数

| 任务 | Capability slug | .feature |
|---|---|---|
| 部门内目录审核 | `catalog.dept_approve` | wave-1 j2-department-review |
| 资源挂接审核 | `resource.dept_approve` | 同上 |
| 资源维护 | `resource.update` | wave-1 j2-resource-mount + wave-1 j1-objection-resource |
| 目录撤销 | `catalog.dept_decommission_request` | wave-1 j2-platform-publish (Scenario: 下线) |
| 目录上报 | （仅 Wave 3）国家通道相关 | wave-3 national-direct |

### 牵头部门（仅持 `tag_lead_dept`）

| 任务 | Capability slug | .feature |
|---|---|---|
| 基础主题分类审核 | `lead_dept.theme_classification_approve` | wave-1 j2-online-catalog-compile (Scenario: 牵头部门审核) |
| 基础主题分类撤销 | `lead_dept.theme_classification_revoke` | 同上 (变体) |

## 3. `ROLE_BUSIAUDIT` 业务运营员（数据主管部门 = 大数据局）

### 旅程 J1 找数→用数

| 任务 | Capability slug | .feature |
|---|---|---|
| 平台侧申请受理 | `application.platform_approve` (无条件) / `application.platform_reject` | wave-0 j1-approval-unconditional + wave-0 j1-approval-conditional |
| 异议受理（use 维度 + 升级） | `objection.escalate_handle` | wave-1 j1-objection-use |
| 凭据撤回 / 暂停 | `application.revoke` / `application.suspend` | wave-1 j1-credential-revoke |

### 旅程 J2 挂数→维数

| 任务 | Capability slug | .feature |
|---|---|---|
| **目录发布** | `catalog.platform_publish` | wave-1 j2-platform-publish |
| **资源发布** | `resource.platform_publish` | 同上 |
| 字段口径裁决 | （含在挂接审核中） | wave-1 j2-platform-publish |
| 挂接审核驳回复核 | `resource.platform_review` | 同上 |

### B1.1 合规与运营

| 任务 | Capability slug | .feature |
|---|---|---|
| 目录质量人工检测 | `audit.manual_quality_check` | wave-2 b1-1-compliance-audit |
| 自动检测任务管理 | `audit.auto_check_task` | wave-2 b1-1-anomaly-detection |
| 统计分析 | `audit.stat_analysis` | wave-2 b1-1-compliance-audit |

### B1.2 接入扩展中心

| 任务 | Capability slug | .feature |
|---|---|---|
| 共享专题 / 能力包注册（管理员后台） | `registry.register` | wave-2 b1-2-package-registration |

### 供需对接

| 任务 | Capability slug | .feature |
|---|---|---|
| 原始需求梳理 / 业务需求汇总 / 评价 | `business_requirement.*` | wave-1 j1-supply-demand-meta-merge |

## 4. `ROLE_SECURITY_ADMIN` 安全管理员

| 任务 | Capability slug | .feature |
|---|---|---|
| 数据分类分级 | （集团数据安全中心，§3.4 外部） | wave-2 b1-1-compliance-audit (Scenario: 协同) |
| 识别规则管理 / 敏感数据管理 / 脱敏策略 / 密钥管理 / 风险告警处置 | 同上（外部依赖） | — |

**说明**：基线 §3.4 明确数据安全中心是外部依赖；ROLE_SECURITY_ADMIN 在 zw-brain 内**仅**作为 B1.1 协同角色。

## 5. `ROLE_SECURITY_AUDIT` 安全审计员

| 任务 | Capability slug | .feature |
|---|---|---|
| 审计日志查询 | `audit.search` | wave-2 b1-1-compliance-audit |
| 登录日志 | （IAM 外部依赖） | wave-3 observability-cost-quota |
| 数享链存证（用户/机构/系统/目录/资源/申请授权 6 类） | `blockchain.anchor` (adapter) | wave-0 infra-audit-bus (Scenario: 区块链锚定异步) |
| 接口调用溯源 | `audit.trace_invocation` | wave-2 b1-1-compliance-audit (Scenario: 回放) |
| 合规事件案件调查 | `audit.investigate` + AI 调查摘要 | wave-2 b1-1-compliance-audit (Scenario: AI 助手) |

## 6. `ROLE_SYSTEM` 平台运维员

| 任务 | Capability slug | .feature |
|---|---|---|
| 组织/用户/权限管理 | （IAM 外部 + 本地投影） | wave-0 infra-iam-session |
| 消息任务监控 | （集团消息中心外部） | — |
| 服务网关 / 流量控制 | （集团 API 网关或 IAF）外部 | — |
| 运维工单与巡检 | （集团运维监控） | wave-3 observability-cost-quota |
| 服务拨测 | （同上） | 同上 |
| AgentRuntime 注册 / Trust Level 升级 | `registry.register` / `registry.trust_level_upgrade` | wave-2 b1-2-package-registration + wave-2 b1-2-trust-level-upgrade |
| Standalone HTTP 评估 | `registry.runtime_binding_switch` | wave-3 agentruntime-standalone-http |

## 7. tag `tag_lead_dept` 牵头部门标签

见 #2（ROLE_ORGAN_MANAGER 的 "牵头部门" 段）。

## 维护原则

- Capability slug 由 registry 单一来源派生
- 新增任务 → 同步更新 `docs/approved/zw-brain-roles.md` §七 + 本表
- 任务命名用业务语义（R12），slug 字段用 dotted-name 工程命名（不进 UI）
- 三引擎可配置化时（Wave 2），任务"自动选人规则"对应到本表的 Capability slug 集
