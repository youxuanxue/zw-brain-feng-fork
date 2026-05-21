# Wave: 1
# Journey: Cross
# Pages: B1.2 (Wave 1 仅 manage 入口最小化)
# Consumer-faces: A2A | MCP
# Roles: ROLE_SYSTEM (注册) | 业务调用方
# Trace: R7 / R15, 基线 §8.4 注册流水线 7 步, §10.2 首个外部 Agent 接入端到端验证
# Priority: P1
# Status: Draft

Feature: 首个外部 Agent 接入端到端（§8.4 流水线 7 步）
  As a 平台运维员 ROLE_SYSTEM + 业务方
  I want 选 1 个低风险长尾 Agent 跑通"AGENT.yaml → validate → 审核 → Registry → 投影 → 调用 → 审计"
  So that Wave 2 大规模外部 Agent 接入前，桥接路径已经被验证

  Background:
    Given 单租户 sd-default 已初始化
    And 外部 Agent 候选：industry-news-summarizer（长尾、只读、无写操作）
    And 它由 Cursor / ANP 平台手工构造的 AGENT.yaml（runtime_spec_version=anp-agent/v1.2）

  Scenario: 正向 — §8.4 七步流水线
    # Step 1: 外部 Agent 在源工具构建 → 产出 AGENT.yaml
    Given AGENT.yaml 文件已就绪，含 tools / mcp_servers / skills / permissions

    # Step 2: zw-brain 侧 validate + doctor
    When 我执行 `agentruntime validate AGENT.yaml`
    Then validate 通过
    When 我执行 `agentruntime doctor AGENT.yaml`
    Then doctor 通过，model.provider 指向集团推理平台

    # Step 3: 声明租户、权限、审计、确认边界（zw-brain Capability 映射）
    When 我声明 tenant_scope=sd-default，auth_policy=service，audit_class=read，human_confirmation_required=false
    Then 这些声明写入 Registry record 的 capability mapping

    # Step 4: 审核：默认 untrusted → verified，由 B1.2 管理员决策
    Given trust_level 默认 untrusted
    When ROLE_SYSTEM 在 B1.2 接入扩展中心提交升级到 verified（含安全审查记录）
    Then trust_level=verified
    And 审计 capability_call=registry.trust_level_upgrade

    # Step 5: 注册进 Registry
    When 提交注册
    Then Registry 新增一条 record，slug=industry-news-summarizer，version=1.0.0，review_status=approved

    # Step 6: 投影到允许的消费面（默认 A2A / MCP；WebUI / API / CLI 由 Capability 投影机制承接）
    Then exposure 字段含 ["mcp","a2a"]
    And MCP manifest 自动新增 tool industry-news-summarizer.fetch
    And A2A agent card 自动新增对应 skill

    # Step 7: 调用回到统一审计与观测面
    When 一个内部业务调用方通过 A2A 调用该 Agent
    Then 调用经过 AgentRuntime 内核
    And audit_event 表记录一条 capability_call=industry-news-summarizer.fetch + actor + tenant_id

  Scenario: 负向 — runtime_spec_version 不是 anp-agent/v1.2 拒绝注册
    Given AGENT.yaml runtime_spec_version=anp-agent/v1.0
    When 我提交注册
    Then 拒绝 + 错误信息 "runtime_spec_version must be anp-agent/v1.2" (R15)

  Scenario: 负向 — 外部 Agent 声明禁止外部化的能力被裁剪（§8.5 边界）
    Given AGENT.yaml permissions 含 "audit_bus.write"（属于禁止外部化）
    When 我提交注册
    Then 注册成功，但 Registry 对该 permission 进行**裁剪**（不放宽）
    And Runtime 调用时跳过该 permission，业务尝试用该 permission 触发 reject + 审计
    And §8.5 "禁止外部化" 边界生效

  Scenario: 负向 — model.provider 指向第三方 API 被拒
    Given AGENT.yaml model.provider="https://api.openai.com"
    When 我执行 doctor
    Then doctor 失败（D6 / D14 硬约束）

  Scenario: 负向 — 未升级到 verified 的外部 Agent 不能进入生产投影
    Given trust_level=untrusted
    Then exposure 默认仅在 [mcp]（dev / 受限 surface）
    And A2A 投影**不启用**
    And 调用尝试返回 "trust_level_not_sufficient_for_production"

  Scenario: 回归 — 外部 Agent 不能绕过 Registry 自主注入消费面
    Then 仓库代码中**仅**通过 Registry 派生 exposure 列表
    And 任意 entry/*/ 下没有手编辑的 "外部 Agent 工具列表"
    And preflight 段对此做反向探测
