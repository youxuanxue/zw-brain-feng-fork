# Wave: 0
# Journey: J1
# Pages: P4
# Consumer-faces: API | WebUI
# Roles: ROLE_ORGAN_OPERATER
# Trace: R1 / R3, 基线 §5.2 P4 调用监控入口, 基线 §10.1
# Priority: P0
# Status: Ready
# Owner: e1
# Pytest: tests/test_wave0_j1_credential_call.py + tests/test_wave1_p4_delivery_explain.py
# Twin-F: e1.F8
# InTest-Scope: 3 个 Scenario 由 tests/test_wave0_j1_credential_call.py 数据层覆盖（按 actor 过滤 /
#   最小字段集 schema 探测 / 真数据 status 分布 ≥744 行 succeeded）；
#   curl 实调端到端 / 配额耗尽 429 / QPS 限流 / 过期 401 + scope 403 / AI 不替代时间线 + 工程术语黑名单
#   归 W0-07 浏览器侧（UI 层 R12 黑名单：capability_call.skill_id legitimately 含 register-version /
#   package / projection / apply-tenant-policy canonical 名 — 此约束在 UI 渲染层而非 DB 内部）。
#   配额 / 限流引擎本期不实现，归 Wave 1+。

Feature: J1 API 调用监控（P4 调用监控段）
  As a 部门操作员 (ROLE_ORGAN_OPERATER)
  I want 看到我的凭据在最近的调用记录与配额消耗
  So that 出问题时能自己定位（不联系技术支持）

  Background:
    Given 单租户 sd-default 已初始化
    And 凭据 K_A201_xxx 已签发，scope=C101，配额：峰值 100/分，平均 500/天
    And 我以 ROLE_ORGAN_OPERATER (申请人) 登录

  Scenario: 正向 — 调用 1 次后能在 P4 看到记录
    When 我用 curl 调用：
      curl -H "Authorization: Bearer K_A201_xxx" https://api/resource/C101?id=110000
    Then API 返回 200 + 数据
    And 后台审计总线记录 1 条 capability_call=resource.fetch，audit_class=read
    When 我打开 P4 调用监控段
    Then 显示最近 1 次调用：时间 / 请求 ID / 调用结果（成功）/ 响应字节数
    And 配额用量：今日 1 / 500

  Scenario: 正向 — 配额耗尽返回 429
    Given 今日已调用 500 次（达到日配额）
    When 我再次调用同一接口
    Then API 返回 429
    And 响应体含 quota_exceeded + retry_after 秒
    And P4 调用监控段显示"今日配额已用尽"红色徽标

  Scenario: 正向 — 峰值频次超限触发限流
    When 我在 1 分钟内并发 200 次调用
    Then 后 100+ 次返回 429 + rate_limited
    And 审计总线 200 条记录（含 success + rate_limited 状态）

  Scenario: 负向 — 凭据过期后调用被拒
    Given 凭据 K_A201_xxx 已过期（expires_at < now）
    When 我用该凭据调用
    Then API 返回 401 + reason="credential_expired"
    And 审计总线记录 reject + credential_id

  Scenario: 负向 — 凭据 scope 不匹配
    Given 凭据 K_A201_xxx scope=C101
    When 我用该凭据调用 C102 的接口
    Then API 返回 403 + reason="scope_mismatch"

  Scenario: 回归 — 调用监控**只显示本人凭据的记录**（隔离）
    Given 同部门另一用户 U_PEER 持有凭据 K_PEER_yyy
    When 我打开自己的 P4 调用监控段
    Then 不显示 U_PEER 的调用记录
    And 审计总线查询时 actor_id 过滤生效

  Scenario: 回归 — 工程术语黑名单 + AI 不替代时间线（R12 / 基线 §5.4.4 P4 反约束）
    Then P4 调用监控段不显示 "package" / "projection" / "policy_decision"
    And 时间线 / 配额徽标 / 回执 视觉权重高于"AI 状态解释助手"
    And AI 助手关闭后，调用记录主表仍可独立工作
