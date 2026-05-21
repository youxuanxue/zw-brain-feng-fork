# Wave: 4
# Journey: B1.1 + B1.2
# Pages: B1.1 / B1.2
# Consumer-faces: WebUI
# Roles: BUSIAUDIT / SECURITY_AUDIT / SECURITY_ADMIN / SYSTEM
# Trace: 基线 §10.5 退役判据
# Priority: P1
# Status: Draft

Feature: B1 合规底线覆盖验证
  As a 客户成功 / 安全审计员
  I want 验证 B1.1 / B1.2 合规底线无 P0/P1 阻断 bug
  So that legacy 合规审计模块可以一并退役

  Background:
    Given 客户已正式上线 90 天

  Scenario: 正向 — B1.1 异常发现持续工作
    Then 最近 30 天 B1.1 异常发现段产生 ≥5 类异常（含具体异常实例）
    And 每类异常都有 BUSIAUDIT 处理记录或主动 review

  Scenario: 正向 — B1.1 合规抽查执行
    Then 最近 90 天合规抽查 ≥6 次
    And 抽查覆盖申请 / 审批 / 凭据签发 / 调用监控 4 类
    And 抽查结论 100% 写入 audit_event

  Scenario: 正向 — B1.2 接入扩展中心使用
    Then 最近 90 天通过 B1.2 注册的外部 Agent ≥3 个
    And 至少 1 个完成"untrusted → verified"升级
    And §8.4 七步流水线 UI 化路径被真实使用

  Scenario: 正向 — 审计存证完整链
    Then 任意 J1/J2 写操作可通过 audit_event 完整回放
    And SECURITY_AUDIT 视角下可一键回放任意 application 全生命周期

  Scenario: 负向 — 合规底线在 90 天内零 P0 阻断
    Then 90 天内合规阻断类 bug 数 = 0
    And P1 bug 数 ≤2

  Scenario: 回归 — B1 不抢占 J1/J2 主导航（R1）
    Then 普通 ROLE_ORGAN_OPERATER 视角下主导航**不**包含 B1.1 / B1.2 入口
    And B1.1 / B1.2 入口仅 BUSIAUDIT / SECURITY_* / SYSTEM 角色可见
