# Wave: 3
# Journey: Cross
# Pages: None (协议)
# Consumer-faces: A2A
# Roles: 外部 Agent 平台
# Trace: R3 / R15, 基线 §6.1, §10.4
# Priority: P1
# Status: Draft
# Owner: e5
# Pytest: tests/test_wave3_protocol_tenant.py
# Twin-F: e5.F6

Feature: A2A 投影生产级硬化（agent skill 模型）
  As a 外部 Agent 平台
  I want 通过 A2A 协议与 zw-brain Capability 互操作
  So that ANP / Cursor / 第三方 Agent IDE 平台能在生产中接入 zw-brain

  Background:
    Given Capability registry exposure 含 a2a 的项已就绪
    And A2A agent card 由 Capability registry 自动生成（zw_brain/entry/a2a/agent_card.json）

  Scenario: 正向 — A2A discover → invoke 端到端
    When 外部 Agent 通过 A2A 协议 discover zw-brain
    Then 返回 agent card，含 skills 列表 (= exposure 含 a2a 的 Capability)
    When 外部 Agent invoke skill=resource.search，输入 {keyword:"户籍"}
    Then zw-brain 经鉴权 + 审计返回结果
    And 调用与 WebUI / API 一致

  Scenario: 正向 — A2A 复杂会话（多轮）
    When 外部 Agent 发起一次 J1 申请草拟流程
    Then 多轮调用经过 A2A：
      1) resource.search → 返回候选
      2) application.draft → 返回草稿 ID
      3) application.submit → human_confirmation_required=true，返回"待用户确认"
      4) （用户确认）application.submit_confirm → 成功
    And 整体审计链可追溯

  Scenario: 正向 — A2A 工具裁剪与 trust_level 强联动
    Given 外部 Agent trust_level=verified
    When 它 invoke 工具 application.approve（仅 platform 级允许）
    Then 拒绝
    And 错误信息 "trust_level=verified 不允许调用 platform 级 Capability"

  Scenario: 负向 — A2A 必须经 AgentRuntime（基线 R15）
    Given 外部 Agent 试图通过私有协议（非 anp-agent/v1.2 schema）调 zw-brain
    Then 拒绝
    And 错误信息明示 "must use AgentRuntime AGENT.yaml"

  Scenario: 负向 — A2A 跨租户隔离
    Given 外部 Agent 在 sd-default 注册
    When 它 invoke skill 查询 yn-default 租户的数据（与 multi-tenant-policy.feature 命名一致）
    Then 返回空（tenant filter 生效）
    And 审计 reject + reason="cross_tenant_query_attempt"

  Scenario: 回归 — A2A 投影与 MCP 投影来自同一 registry
    Then mcp_tools.json 与 a2a/agent_card.json 中**同名 Capability**字段集合一致
    And `export_agent_contract.py --check` 同时校验两个投影
