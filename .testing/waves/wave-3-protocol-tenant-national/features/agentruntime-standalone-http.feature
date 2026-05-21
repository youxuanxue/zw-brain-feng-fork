# Wave: 3
# Journey: Cross
# Pages: None
# Consumer-faces: A2A | MCP (远程 Agent)
# Roles: ROLE_SYSTEM
# Trace: R15, 基线 §8.2 决策表 "Standalone HTTP 留 Wave 3+ 评估", §10.4
# Priority: P2
# Status: Draft

Feature: AgentRuntime Standalone HTTP 形态评估
  As a 平台运维员
  I want 评估 Standalone HTTP 形态是否在 Wave 3+ 上线
  So that 外部 Agent 需要独立服务部署时有路径，但默认仍是 Embedded SDK

  Background:
    Given Embedded SDK 形态在 Wave 0/1/2 已充分验证
    And R4「控制面纤薄」+ §8.2 决策 "Phase 1 默认 Embedded SDK" 维持

  Scenario: 正向 — Standalone HTTP 形态 PoC
    When 我搭建 Standalone HTTP 形态的 1 个外部 Agent (industry-news-summarizer-standalone)
    Then Agent 以独立进程启动，监听 HTTP 端口
    And AgentRuntime gateway 路由 zw-brain 到该 Agent 的 HTTP 接口
    And 鉴权使用 trusted_gateway 模式
    And 审计依然回到 zw-brain audit_event

  Scenario: 正向 — Standalone 与 Embedded 共存
    Given 同一 Capability 路径可由 Embedded SDK Agent 或 Standalone HTTP Agent 服务
    When Registry 切换 runtime_binding = standalone-http
    Then 流量自动切到 Standalone HTTP
    And 业务调用方**完全无感**（投影一致）

  Scenario: 负向 — Standalone HTTP 不能绕过审计 / 推理 gateway
    When Standalone Agent 试图直连 OpenAI
    Then 出站规则拒绝（preflight 段 10 + 网络层 deny）
    And model.provider 仍必须经集团推理 gateway

  Scenario: 负向 — Standalone HTTP 默认关闭
    Then 仓库默认 runtime_binding = embedded（不强制）
    And Standalone HTTP 形态需要 ROLE_SYSTEM 在 B1.2 显式启用 + 安全审查记录

  Scenario: 回归 — Standalone HTTP 评估结果可回滚到 Embedded
    Given 已切换 5 个 Agent 到 Standalone HTTP 形态
    When 评估发现稳定性问题，决定回滚
    Then 通过 Registry 切回 runtime_binding=embedded
    And 业务调用方无感切回
    And R4 / R7 (长尾外部化的可逆性)
