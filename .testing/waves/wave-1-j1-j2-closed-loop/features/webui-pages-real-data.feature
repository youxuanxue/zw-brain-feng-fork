# Wave: 1
# Journey: Cross (J1 + J2 + B1)
# Pages: P1-P5 | P7 | B1.1 | B1.2
# Consumer-faces: WebUI
# Roles: All
# Trace: 基线 §7.3 ≤10 场景页, §10.3 WebUI 投影, D8 (UI 仅保留场景页), D38 (e5 WebUI 投影验收)
# Priority: P0
# Owner: e5
# Pytest: tests/e2e/customer_acceptance_checklist.spec.ts

Feature: WebUI 8 主页面成品化 — 装载 sd-default 真实数据
  As a 政务数据使用者 / 部门操作员 / 业务运营员
  I want 8 个核心场景页（P1 工作台 / P2 发现 / P3 申请 / P4 交付 / P5 提供 / P7 专区 / B1.1 合规 / B1.2 接入）
       展示来自 sd-default 真实库的数据，而非占位或 mock
  So that WebUI 是真端到端可用的产品而非骨架演示

  Background:
    Given 单租户 sd-default 已初始化真实库数据
    And 8 主页面组件 zw-brain-web/src/pages/{P1-P5,P7,B11,B12}*.vue 就位
    And 5 消费面投影派生自单一 capability registry（段 29 守卫）

  Scenario: 正向 — P2 发现页展示真实可复用资源
    Given 部门操作员 ROLE_ORGAN_OPERATER 登录
    When 访问 #/discovery
    Then 页面展示"可复用资源"标题与真实资源卡片
    And 不出现"功能建设中"占位文案
    And 卡片信息来自真实库（资源名 / 责任方 / 共享类型）

  Scenario: 正向 — 8 主页面均无占位、装载真实数据
    Then P1 工作台 / P2 发现 / P3 申请 / P4 交付 / P5 提供 / P7 专区 / B1.1 合规 / B1.2 接入
         8 页面各自展示对应真实库数据
    And router 不保留非主旅程空占位路由

  Scenario: 回归 — 真实数据投影与 5 消费面契约一致
    Then WebUI 渲染的能力与 registry 投影零漂移（段 29 / 段 52 守卫）
    And 业务方验收清单 A/B/C 逐条通过（docs/acceptance/e5-acceptance-package.md）

  Scenario: 负向 — 无权限角色不渲染越权页面入口
    Given 某角色对某场景页无权限
    Then 该页面入口（导航 / 链接）不渲染（非"可见+禁用"或"可见+403"）
