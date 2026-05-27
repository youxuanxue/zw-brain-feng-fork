# Wave: 1
# Journey: J1
# Pages: P2 / P4
# Consumer-faces: WebUI | API
# Roles: ROLE_ORGAN_OPERATER (申请方) | ROLE_ORGAN_MANAGER (提供方部门)
# Trace: 基线 §3.3 异议 5 维度 (data_objection_resource 132 表), §9.2 ObjectionAggregate
# Priority: P1
# Status: Draft
# Owner: e1
# Pytest: tests/test_wave1_objection_5dim_state.py + tests/test_wave1_objection_lifecycle.py
# Twin-F: e1.F2

Feature: J1 资源异议（resource 维度独立状态机）
  As a 部门操作员（申请方或浏览方）
  I want 对资源可用性问题（接口不可达 / 接口契约不符 / 字段映射错）提交异议
  So that 提供方能修复资源，避免下次申请人踩同一坑

  Background:
    Given 资源 C801 已发布，materialization=api，url=https://internal/api/c801
    And 我以 ROLE_ORGAN_OPERATER 登录

  Scenario: 正向 — 接口不可达异议
    When 我调用 C801 接口，连续 5 次返回 5xx
    Then UI 自动检测并在 P4 弹出 "对资源可用性提交异议" 按钮
    When 我点击提交异议，附上最近 3 次 request_id
    Then 创建 ObjectionCase O801，dimension=resource，子类型=availability
    And 推送到 owner_org_code 提供方管理员

  Scenario: 正向 — 接口契约不符（schema drift）
    When 我提交异议，附上 "实际响应缺少 字段 X / 字段 Y 类型变化"
    Then ObjectionCase O801 sub_type=schema_drift
    And UI 提示提供方："需重新挂接资源（J2 流程）"
    When 提供方在 J2 重新挂接资源后，ObjectionCase O801 自动检测最新 schema
    And 若 schema 修正生效，O801 status 自动 → 待评价

  Scenario: 正向 — 资源彻底下线（提供方决定不再提供）
    When 提供方处理 O801，选择 "资源不再提供 + 下线"
    Then resource.status → 下线
    And catalog.status 联动决策由 BUSIAUDIT 复核（基线 §3.3 6+2 态）
    And 所有现存活跃凭据自动 revoked
    And 现有未结申请单 application 自动转 "已撤回 due to resource decommission"

  Scenario: 负向 — 资源异议不能修改字段口径（边界）
    When 提供方在 resource 异议处理中尝试改字段值映射
    Then 拒绝
    And UI 提示 "请通过 J2 资源维护流程"
    And 维度状态机独立性

  Scenario: 负向 — 一个资源多人异议合并
    Given U1 已提 O801
    When U2 对同一资源提同子类型异议
    Then 加入 O801 supporters；不创建新 case
    And 提供方处理一次能解决多个 supporters

  Scenario: 回归 — resource 异议必须留 request_id 链路用于回放
    Then ObjectionCase O801 metadata 含 涉及的 request_id 至少 1 个
    And 用户可在异议详情页一键回放 audit_event 链路
    And 回放视图脱敏处理（不显示原始凭据）
