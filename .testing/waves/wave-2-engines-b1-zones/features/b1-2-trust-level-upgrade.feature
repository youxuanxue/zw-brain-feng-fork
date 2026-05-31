# Wave: 2
# Journey: B1.2
# Pages: B1.2
# Consumer-faces: WebUI
# Roles: ROLE_SYSTEM | ROLE_SECURITY_AUDIT (协同)
# Trace: R15, 基线 §8.2 trust_level 三级 + "可覆盖收紧不可放宽", §10.3
# Priority: P1
# Owner: e4
# Pytest: tests/integration/test_b12_intake.py
# Unfreeze-Note: PR #91 (E4 B1.2 后端) — trust_level 升降级 capability + 「可收紧不可放宽」
#   约束 + Registry 字段守恒（trust_level 是 Registry 字段，不进 AgentRuntime）。
#   pytest:
#     tests/integration/test_b12_intake.py::test_package_trust_level_update_changes_metadata
#     tests/integration/test_b12_intake.py::test_package_trust_level_rejects_unknown_level
#     tests/integration/test_b12_intake.py::test_trust_level_is_NOT_agentruntime_registry_field
#     tests/integration/test_b12_intake.py::test_package_trust_levels_enum_stable
#   (注：「可收紧不可放宽」是基线 §8.2 硬约束 — 测试覆盖三级 trust_level 转换 + 4 个守恒点)

Feature: B1.2 trust_level 升降级（"可收紧不可放宽"硬约束）
  As a 平台运维员 + 安全审计员
  I want 对外部 Agent 的 trust_level 做升降级 + Registry 可收紧不可放宽
  So that 政务场景默认收紧不被任何路径绕过

  Background:
    Given 外部 Agent industry-news-summarizer 已注册，trust_level=untrusted
    And 我以 ROLE_SYSTEM 登录

  Scenario: 正向 — untrusted → verified（需协同确认）
    When 我提交升级到 verified，附理由 "已通过安全审查 + 数据流梳理"
    Then 状态机：pending_security_review
    When SECURITY_AUDIT 协同确认（另一会话）+ 录入审查报告引用
    Then trust_level=verified
    And exposure 现在可启用 A2A
    And 审计 capability_call=registry.trust_level_upgrade

  Scenario: 正向 — verified → untrusted 收紧（无需协同）
    When 我发现某 Agent 调用异常，点击 "收紧到 untrusted"
    Then 立即生效（收紧不需要 SECURITY_AUDIT 协同）
    And 该 Agent 的 A2A 投影立刻禁用
    And 在飞调用按 grace_period（如 30 秒）平滑结束
    And 审计记录收紧理由

  Scenario: 负向 — AGENT.yaml 内反向声明放宽被拒
    Given AGENT.yaml 内声明 trust_level=platform（试图越权）
    When 我注册该 Agent
    Then Registry 按基线 §8.2 "可收紧不可放宽"裁剪到 untrusted
    And 任何尝试通过编辑 Registry 字段直接设 platform 被拒
    And 仅 zw-brain 内置 Agent 可为 platform

  Scenario: 负向 — 升级到 platform 完全禁止
    When 我尝试升级 industry-news-summarizer 到 platform
    Then 拒绝
    And 错误信息 "platform 仅限 zw-brain 内置 Agent" (基线 §8.2)

  Scenario: 负向 — SECURITY_AUDIT 协同前 verified 状态不可用
    Given 我提交升级到 verified，但 SECURITY_AUDIT 未确认
    Then 状态停留在 pending_security_review
    And A2A 投影**未**启用
    And 30 天未确认自动 expire 回 untrusted

  Scenario: 负向 — admin:runtime scope 仅授予 ROLE_SYSTEM (基线 §8.2)
    When 我尝试给 verified 级外部 Agent 授予 admin:runtime
    Then 拒绝
    And admin:runtime 仅 zw-brain 内置 Agent 可拥有

  Scenario: 回归 — trust_level 变更全链路审计
    Then 任意 trust_level 变更：
      - audit_event 一条
      - 含 from_level / to_level / reason / actor_id / occurred_at
      - 收紧操作含 grace_period 记录
    And 审计回放可重现变更时间线
