# Wave: 1
# Journey: Cross (导航 / 路由)
# Pages: P2 | B1.2 | B13
# Consumer-faces: WebUI
# Roles: All
# Trace: 基线 §7.3 ≤10 场景页（不留 dead link）, R12 UI 不暴露半成品, D38
# Priority: P1
# Owner: e5
# Pytest: tests/e2e/twin_browser_pages.spec.ts

Feature: WebUI 子路由去占位 + 预览门禁
  As a WebUI 用户
  I want 导航里不出现点进去是空占位的 dead link，半成品页面有明确预览标识
  So that 界面是诚实的——能点的都可用，未完成的不假装可用（精品意识）

  Background:
    Given WebUI 路由表已收敛主旅程页面
    And 仅 login / profile / migration / iam-governance 保留为非主旅程 PagePlaceholder

  Scenario: 正向 — P2 目录浏览子路由可达且有内容
    When 访问 P2 catalog-browse 子路由
    Then 页面展示真实目录浏览内容（P2CatalogBrowse.vue），非占位

  Scenario: 正向 — B1.2 能力包详情可从列表钻取
    Given B1.2 接入扩展中心列表展示能力包
    When 点击列表中能力包名称
    Then 跳转到 package 详情页（B12PackageDetail.vue）展示该包详情

  Scenario: 正向 — B13 引擎管理页带 Wave2 预览门禁
    When 访问 /engines-admin（B13）
    Then 页面顶部展示 Wave 2 预览 banner（诚实标注预览态）

  Scenario: 负向 — 导航不含 dead link
    Then 主导航中每个可点入口都解析到真实页面
    And 不存在"点进去是空占位 / 功能建设中"的导航项（dead link 已移除）
