# Wave: 1
# Journey: J1
# Pages: P3 (供需对接段)
# Consumer-faces: WebUI
# Roles: ROLE_ORGAN_OPERATER (登记) | ROLE_ORGAN_MANAGER (提供方响应) | ROLE_BUSIAUDIT (meta 合并)
# Trace: 基线 §3.2 供需对接 36 页, §10.2 (供需对接子流程，meta 合并非数据合并)
# Priority: P1
# Owner: e1
# Pytest: tests/test_wave1_j1_supply_demand.py

Feature: J1 供需对接子流程（提供方响应三态 + meta 合并）
  As a 需求方 / 提供方 / 主管部门
  I want 登记缺口、由提供方部门响应、并在必要时合并相似需求
  So that 供需对接既闭环又不重复打扰提供方

  Background:
    Given 单租户 sd-default 已初始化
    And 我以 ROLE_ORGAN_OPERATER 登录

  Scenario: 正向 — 提供方响应三态（登记 → 响应 → 关闭）
    When 我在 P3 供需对接段登记一条数据缺口
    Then 需求 response_status=pending_response
    When 提供方部门管理员提交 provide/reject/need_fix 结论
    Then 需求 response_status=responded 且保留 provider_decision / provider_response_note
    When 需求方确认关闭
    Then 需求 response_status=closed

  Scenario: 正向 — meta 合并仍为 meta-only（BUSIAUDIT）
    Given 申请单 A101 / A102 / A103 由部门 A/B/C 分别登记相似需求
    And 我以 ROLE_BUSIAUDIT 登录
    When 我合并为 BusinessRequirement BR701
    Then BR701 仅持 application_ids + merge_reason，不复制业务字段
    And 原始 demand 的 response_status 不被合并改写

  Scenario: 负向 — 申请人本人不能合并业务需求
    When ROLE_ORGAN_OPERATER 尝试合并业务需求
    Then 拒绝，仅 BUSIAUDIT 可合并

  Scenario: 负向 — provide 决策必须关联资源
    Given 一条 pending_response 需求
    When 提供方提交 decision=provide 但未给 resource_ref
    Then 拒绝

  Scenario: 回归 — 供需对接不是申请审批的替代
    Then 需求登记/响应/关闭路径不影响 J1 主链路申请审批状态机
