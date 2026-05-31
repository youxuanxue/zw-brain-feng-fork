# Wave: 1
# Journey: Cross (写操作角色绑定)
# Pages: All
# Consumer-faces: WebUI
# Roles: All
# Trace: 基线 §六 角色 ≠ 方向, R10 7 角色码, D38 (e5 WebUI 投影验收)
# Priority: P0
# Owner: e5
# Pytest: tests/e2e/permission_invisibility.spec.ts

Feature: WebUI 写操作角色绑定 — invokeActionStub 跟随顶栏岗位
  As a 多角色用户（如部门管理员 ROLE_ORGAN_MANAGER）
  I want WebUI 发起的写操作（POST /api/skills/*）以顶栏当前岗位（getProductRole）发起
  So that 我在某岗位下能执行该岗位有权的操作，不被硬编码岗位错误拦截

  Background:
    Given 用户已登录且顶栏展示当前岗位（useProductRole）
    And 写操作经 zw-brain-web/src/composables/useActionStub.ts 发起

  Scenario: 正向 — 部门管理员以本岗位审批成功
    Given 用户顶栏岗位为 ROLE_ORGAN_MANAGER
    When 在审批页点击审批
    Then invokeActionStub 以 ROLE_ORGAN_MANAGER 发起 POST /api/skills/*
    And 审批成功（不再因硬编码 ROLE_ORGAN_OPERATER 而 403）

  Scenario: 负向 — 角色与操作不匹配仍被后端策略拒
    Given 用户顶栏岗位对该 capability 无权
    When 发起该写操作
    Then 后端策略返回 403（角色绑定正确但权限不足，非前端伪绿）
    And 审计记录 actor_role = 顶栏真实岗位

  Scenario: 回归 — 防"假绿"（旧缺陷）
    Then 写操作 role 不得硬编码 ROLE_ORGAN_OPERATER
    And useActionStub.ts 必须 import getProductRole / useProductRole
    And 岗位失败不得静默 exit 0（test_headless_j1_demo 曾暴露的假绿已修）
