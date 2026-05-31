# Wave: 3
# Journey: Cross
# Pages: None (协议)
# Consumer-faces: MCP
# Roles: IDE/Claude/Cursor 类 Agent + 外部业务调用方
# Trace: R3, 基线 §6.1 五消费面, §10.4 MCP/A2A 生产级硬化
# Priority: P1
# Owner: e5
# Pytest: tests/test_wave3_protocol_tenant.py

Feature: MCP 投影生产级硬化
  As a IDE/Claude/Cursor 类 Agent 用户
  I want MCP 投影在生产场景下与 WebUI / API 一致并具备生产可观测性
  So that AI 工作流能稳定调用 zw-brain Capability

  Background:
    Given 所有 P0 + P1 Capability 已注册并在 Registry 中 exposure 含 mcp
    And MCP manifest 由 capability registry 自动生成
    And 推理平台 gateway 已就位

  Scenario: 正向 — MCP tool 列表与 OpenAPI 一致
    When 我对比 mcp_tools.json 与 OpenAPI 的 capability 列表
    Then 两者**完全**一致（slug + version + input_schema + output_schema + human_confirmation_required）
    And 任何 drift 由 export_agent_contract.py --check 报错

  Scenario: 正向 — MCP 工具调用经过 zw-brain 审计 + 鉴权
    When MCP 客户端调用 resource.search 工具
    Then 调用经过 Bearer token / API Key 鉴权
    And audit_event 一条 capability_call=resource.search, source=mcp
    And 与 WebUI / API 调用结果一致

  Scenario: 正向 — human_confirmation_required 工具在 MCP 调用前提示
    When MCP 客户端调用 application.submit 工具
    Then 工具描述含 "Requires user confirmation"
    And 调用前 zw-brain 返回"待确认"状态而非直接提交
    And 客户端必须在 IDE 内完成确认才能 commit
    And 反约束（§5.4.5）：AI 不能直接触发责任性写操作

  Scenario: 正向 — MCP 错误处理
    When MCP 调用因 quota_exceeded 失败
    Then 返回结构化错误 + retry_after
    And IDE / Agent 可识别该错误（不是 500 黑盒）

  Scenario: 负向 — exposure 不含 mcp 的 Capability 在 MCP 不可见
    Given Capability admin.runtime exposure=[webui, cli]
    Then MCP 工具列表不含 admin.runtime
    And 直接调用返回 "tool_not_found"

  Scenario: 负向 — MCP 不能绕过 trust_level 裁剪
    Given 外部 Agent (trust_level=untrusted) 试图通过 MCP 调用 application.approve
    Then 调用拒绝
    And 审计 reject + reason="trust_level_insufficient"

  Scenario: 回归 — MCP 投影从同一 registry 派生
    Then 仓库中无手编辑 MCP manifest 文件（zw_brain/entry/mcp/tools/*.json 是生成产物）
    And `export_agent_contract.py --check` 是 hook 入口
    And preflight 段对手编辑做反向探测
