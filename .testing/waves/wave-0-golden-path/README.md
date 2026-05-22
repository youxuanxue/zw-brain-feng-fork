---
wave: 0
title: 机械守卫 + 首条黄金链路（J1 找数→用数）
driven_by: docs/approved/zw-brain-architecture.md §10.1
---

# Wave 0 — 机械守卫 + 首条黄金链路

## 目标

> 先做成一个真能用的最小产品，不先做一个看起来完整的平台。 — 基线 §10.1

证明三件事：

1. **统一能力契约** 能让 WebUI / API / CLI 同源投影
2. **合规边界** 能让审计总线同步落库 + 推理走集团平台
3. **一条真实旅程**（J1 找数→用数）能让客户在真实数据上跑通

## Scope

| Feature | 类型 | 优先级 | 主要角色 / 消费面 |
|---|---|---|---|
| j1-resource-discovery | J1 业务 | P0 | ROLE_ORGAN_OPERATER × WebUI/API |
| j1-application-draft | J1 业务 | P0 | ROLE_ORGAN_OPERATER × WebUI |
| j1-approval-unconditional | J1 业务 | P0 | ROLE_BUSIAUDIT × WebUI |
| j1-approval-conditional | J1 业务 | P0 | ROLE_ORGAN_MANAGER + ROLE_BUSIAUDIT × WebUI |
| j1-credential-issue | J1 业务 | P0 | ROLE_ORGAN_OPERATER × WebUI/CLI |
| j1-api-call-monitoring | J1 业务 | P0 | ROLE_ORGAN_OPERATER × API |
| infra-contract-projection | Infra | P0 | All × WebUI/API/CLI |
| infra-audit-bus | Infra | P0 | All × Backend |
| infra-inference-gateway | Infra | P0 | All × Backend |
| infra-agentruntime-embedded | Infra | ~~P0~~ → **Deferred Wave1** | Internal Agent |

## 完成判据

- 客户能用**真实数据**跑通：检索 → 申请草稿 → 提交审批（无条件 / 有条件任一分支）→ 通过后凭据领取 → curl 调用样例 → 调用监控看到记录
- `pytest tests/test_wave0_*.py -q` 全部 green
- 审计总线写入失败时业务**熔断**（不静默吞错）
- 任意模型调用都走集团推理平台（preflight 段 10 强制）

## 不在 Wave 0 内

- 内置 Agent（AgentRuntime Embedded：`AGENT.yaml` + `validate`/`doctor` CLI）（Wave 1，产品负责人 sign-off 2026-05-22；J1 黄金链路不依赖，与 ext-agent-pilot 同期立项）
- 异议 5 维度（Wave 1）
- 供需对接（Wave 1）
- J2 提供方旅程（Wave 1）
- 三引擎可配置化（Wave 2）
- B1 合规与运营（Wave 2）
- MCP / A2A 生产硬化（Wave 3）
- 国家直达（Wave 3）

## Trace 索引

- 基线 §1.2 J1 旅程
- 基线 §10.1 Wave 0 必做清单
- R1 / R3 / R4 / R6 / R9 / R10 / R12 / R15
- D11（旧平台真实数据回归）
- 旧 xlsx 行 1-12（资源申请）+ 16-24（服务审核）+ 26-34（我的申请）
