# Wave: 4
# Journey: J1
# Pages: All J1 pages
# Consumer-faces: All
# Roles: All
# Trace: 基线 §1.5 成功标准, §10.5 退役判据
# Priority: P0
# Status: Draft

Feature: J1 替代验证（客户上线 90 天真实使用）
  As a 客户成功 / 产品负责人
  I want 用 90 天真实使用数据验证 J1 已稳定替代 legacy
  So that 可以下达 legacy J1 退役决定

  Background:
    Given 客户已正式上线 zw-brain（first_customer_onboarded_at = T0）
    And 现在 = T0 + 90 天

  Scenario: 正向 — 每日申请数达标
    When 我查询 audit_event 中 capability_call=application.submit
    Then 最近 90 天内每日**至少** 10 次申请（基线 §1.5）
    And 申请人覆盖 ≥5 个部门
    And 资源覆盖 ≥30 个 catalog

  Scenario: 正向 — 主链路 happy path 通过率
    Then 申请→审批→凭据→调用 全链路 success rate ≥98%
    And 失败原因可归类（quota / credential_expired / scope_mismatch 等）

  Scenario: 正向 — 异议 5 维度都至少跑通 1 次真实闭环
    Then dimension=authz / catalog / content / resource / use 5 类异议各至少有 1 条 ObjectionCase 状态=已处理
    And 处理时长 SLA 达标

  Scenario: 正向 — 项目个性化通过配置完成（R14）
    Then 客户没有提出"改代码"需求
    And 所有项目特定需求经审批流引擎 / 表单引擎 / 推荐规则承接

  Scenario: 负向 — 演示功能使用频度低于真实使用
    Then 大屏 / 国家直达 / 共享专区订阅 等"演示"功能调用占总申请 <10%（基线 §1.5）
    And 占比 ≥10% 触发 review：可能客户视角与设计不符

  Scenario: 负向 — 0 角色困惑（基线 §1.5）
    Given 业务方培训 + 上线 60 天
    Then 客户反馈中"我是哪个角色"类问题数 = 0
    And 角色困惑触发 R13 元规则反思（基线 §11）

  Scenario: 回归 — 90 天真实使用不依赖临时补丁
    Then 客户上线后没有 hotfix 类 PR 持续不断（每 90 天 hotfix PR <5）
    And 主旅程在零定制代码情况下达成
