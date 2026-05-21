---
wave: 3
title: 协议扩展硬化 + 多租户深化 + 国家通道独立子旅程
driven_by: docs/approved/zw-brain-architecture.md §10.4
---

# Wave 3 — 协议扩展硬化 + 多租户深化 + 国家通道

## 目标

- MCP / A2A 生产级硬化（前两 wave 仅"同契约可生成"）
- 多租户 / 多部门 / 多区域策略深化
- 成本、性能、调用配额、观测告警
- **国家数据直达**独立子旅程实现（优先级 P2，本期不立项）
- **国家扩展要素目录编制**独立子旅程
- AgentRuntime Standalone HTTP 形态评估

## Scope

| Feature | 类型 | 优先级 | 主要角色 / 消费面 |
|---|---|---|---|
| mcp-hardening | 协议 | P1 | IDE/Claude/Cursor × MCP |
| a2a-hardening | 协议 | P1 | 外部 Agent 平台 × A2A |
| multi-tenant-policy | 多租户 | P1 | All × All |
| national-direct | 国家通道 | P2 | BUSIAUDIT |
| national-ext-elements | 国家通道 | P2 | ORGAN_MANAGER |
| agentruntime-standalone-http | 协议 | P2 | ROLE_SYSTEM |
| observability-cost-quota | 观测 | P1 | ROLE_SYSTEM |

## 完成判据

- MCP / A2A 在生产场景下与 WebUI / API 投影一致（与 Wave 0 contract-projection 一致性回归）
- 多租户场景下租户隔离、跨部门策略、区域策略可证
- 国家通道子旅程独立可用，**不**渗透 J1 主链路心智
- 观测面（cost / latency / quota / 告警）面向 ROLE_SYSTEM 可用

## 不在 Wave 3 内

- legacy 完整退役（Wave 4）

## Trace 索引

- 基线 §10.4 Wave 3 必做清单
- 基线 §6 五消费面 + R3
- 基线 §8.2 AgentRuntime Standalone HTTP "留 Wave 3+ 评估"
- 基线 §10.4 国家直达 / 国家扩展要素 "本期不实施"
