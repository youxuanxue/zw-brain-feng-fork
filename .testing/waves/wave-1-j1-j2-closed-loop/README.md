---
wave: 1
title: J1 闭环深化 + J2 挂数→维数最小闭环 + 首个外部 Agent
driven_by: docs/approved/zw-brain-architecture.md §10.2
---

# Wave 1 — J1 闭环深化 + J2 最小闭环 + 首个外部 Agent

## 目标

- J1 异议处理子流程（5 维度独立状态机：authz / catalog / content / resource / use）
- J1 供需对接子流程（meta 合并，非数据合并；6 步流程）
- J2 在线编制 → 资源挂接 → 部门审 → 平台发布 核心 4 步
- 凭据撤回 / 暂停（J1 收口）
- **首个外部 Agent 接入端到端验证**：选 1 个低风险长尾 Agent，跑通基线 §8.4 注册流水线 7 步

## Scope

| Feature | 类型 | 优先级 | 主要角色 |
|---|---|---|---|
| j1-objection-authz | J1 业务 | P1 | 申请方 + 提供方部门 |
| j1-objection-catalog | J1 业务 | P1 | 申请方 + 提供方部门 + BUSIAUDIT |
| j1-objection-content | J1 业务 | P1 | 申请方 + 提供方部门 |
| j1-objection-resource | J1 业务 | P1 | 申请方 + 提供方部门 |
| j1-objection-use | J1 业务 | P1 | 申请方 + 提供方部门 |
| j1-supply-demand-meta-merge | J1 业务 | P1 | BUSIAUDIT |
| j2-online-catalog-compile | J2 业务 | P1 | ORGAN_OPERATER |
| j2-resource-mount | J2 业务 | P1 | ORGAN_OPERATER |
| j2-department-review | J2 业务 | P1 | ORGAN_MANAGER |
| j2-platform-publish | J2 业务 | P1 | BUSIAUDIT |
| j1-credential-revoke | J1 业务 | P1 | BUSIAUDIT + ORGAN_OPERATER |
| ext-agent-pilot | 外部 Agent | P1 | ROLE_SYSTEM + 内部业务调用方 |
| infra-agentruntime-embedded | Infra | P1 | Internal Agent（Wave0 降级而来，与 ext-agent-pilot 同期）|

## 完成判据

- 任意一类异议都能从"申请人提交异议 → 提供方部门响应 / 评价"独立闭环
- 部门可独立完成 J2 编制 → 挂接 → 部门审 → 平台发布
- 至少 1 个外部 Agent 通过 §8.4 七步流水线进入 Registry 并被业务调用
- BUSIAUDIT 可对已授权申请执行撤回 / 暂停
- 至少 1 个内置 Agent 用 `AGENT.yaml` 描述并通过 `agentruntime validate` + `doctor`（Wave0 降级而来）

## 不在 Wave 1 内

- 三引擎可配置化（Wave 2）
- B1.1 / B1.2 完整能力（Wave 2 起）
- MCP / A2A 生产硬化（Wave 3）
- 国家直达独立子旅程（Wave 3）

## Trace 索引

- 基线 §10.2 Wave 1 必做清单
- 基线 §3.3 5 维度异议 + §9.2 ObjectionCase / DeliveryAggregate
- 基线 §8.4 注册流水线 7 步
- R2 / R7 / R15 / D11
- 旧 xlsx 行 [40..64] 目录管理 + [65..76] 资源管理 + [77..89] 供需系统 + [90..98] 申请审核
