# Wave: 3
# Journey: Cross (面向 ROLE_SYSTEM)
# Pages: B1.2 (运维) + 外部监控平台
# Consumer-faces: WebUI | API
# Roles: ROLE_SYSTEM
# Trace: 基线 §10.4 观测告警, §3.4 集团统一运维监控（外部依赖）
# Priority: P1
# Owner: e6
# Pytest: tests/test_wave3_protocol_tenant.py

Feature: 观测 / 成本 / 性能 / 调用配额 / 告警
  As a 平台运维员 ROLE_SYSTEM
  I want zw-brain 暴露给集团运维监控平台的标准指标
  So that 不在 zw-brain 内复造监控平台（基线 §3.4 外部依赖）

  Background:
    Given 集团统一运维监控平台已就位（外部依赖，不在本仓）
    And zw-brain 暴露 metrics endpoint（Prometheus 风格或集团约定 schema）

  Scenario: 正向 — Metrics 暴露
    When 集团运维监控 scrape /metrics
    Then 返回标准指标：
      | metric                              | 类型     |
      | capability_call_total               | counter |
      | capability_call_duration_seconds    | histogram|
      | capability_call_failed_total         | counter |
      | credential_active_total              | gauge   |
      | quota_remaining_per_credential       | gauge   |
      | inference_call_total                 | counter |
      | inference_token_total                 | counter |
      | audit_event_write_failed_total       | counter |
      | external_agent_invoke_total          | counter |

  Scenario: 正向 — 调用配额监控
    When 凭据 K_X 的日调用数接近配额上限（80%）
    Then 集团监控触发告警（zw-brain 不发邮件，只暴露指标）
    And ROLE_SYSTEM 可在外部监控查看具体凭据

  Scenario: 正向 — 推理调用成本可观测
    Then inference_token_total 按 model_id × tenant_id × capability 维度可分组
    And 集团成本平台可基于此做 chargeback

  Scenario: 负向 — zw-brain 不内嵌告警规则
    Then 仓库代码不包含 alertmanager 配置 / 邮件 / IM 通知逻辑
    And 这些**全部**由集团运维监控承担
    And R7 长尾外部化在监控领域的体现

  Scenario: 负向 — Metrics endpoint 鉴权
    When 未携带 service account token 访问 /metrics
    Then 返回 401
    And 集团监控 service account 有专用 token

  Scenario: 回归 — 观测面不影响业务路径
    When /metrics endpoint 偶发 5xx
    Then 业务主旅程 J1/J2/B1 不受影响
    And 仅监控数据有缺口（集团监控自身告警）
