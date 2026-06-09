# Wave: 2
# Journey: J1 + J2
# Pages: P7
# Consumer-faces: WebUI
# Roles: All users
# Trace: D9 (从砍掉清单移出，升级为 K11 必保留功能), 基线 §5.2 P7 共享专区
# Priority: P1
# Owner: e3
# Pytest: tests/integration/test_wave2_topic_package_discovery.py + tests/integration/test_wave2_topic_package_curation.py
# Deferred: 专题包整面退出本期（D55/P6，业务方 2026-06-09 sign-off）。下线整面、保数据不删库——capability 注册保留、seed 数据保留，仅去 PERMISSION_ROLES 角色授权（全员 fail-closed）+ 前端 zones-pack 入口/路由。backing 测试已翻为退役不变量。待专题包重新立项时恢复角色授权与入口、撤本 Deferred。

Feature: P7 共享专区 / 专题包订阅
  As a 部门操作员 / 部门管理员
  I want 按主题（如 "民生", "营商环境"）订阅一组目录，统一管理
  So that 主题化场景下不需要单个目录逐一申请

  Background:
    Given 单租户 sd-default 已运行，已积累 50 个 catalog 分布在 8 个主题标签
    And 我以 ROLE_ORGAN_OPERATER 登录

  Scenario: 正向 — 浏览共享专区
    When 我打开 P7 共享专区
    Then 看到主题分类（"民生" / "营商环境" / "应急" / "环保" / 等）
    And 每个主题展示一组关联 catalog 卡片
    And 主题元数据含发布方 / 更新频次 / 订阅数

  Scenario: 正向 — 订阅主题包
    When 我对"营商环境"专题点击 "订阅"
    Then 创建 subscription 记录，user_id + theme_id + subscribed_at
    And 该专题下新增 catalog 时自动通知我

  Scenario: 正向 — 一键申请专题包内全部 catalog
    Given 我已订阅"营商环境"专题
    When 我点击 "申请此专题全部资源"
    Then 系统为专题内每个 catalog 自动建草稿（仍是独立 application）
    And 我可逐条审视 / 调整后批量提交
    And 申请方向 / 提供方部门 各自路由（按 J1 normal flow）

  Scenario: 正向 — 专题包由 BUSIAUDIT 维护（B1.2 入口）
    Given 我以 ROLE_BUSIAUDIT 登录
    When 我打开 B1.2 → "共享专区维护"
    Then 可创建专题包 / 关联 catalog / 设置主题元数据
    And 创建后即在 P7 可见
    And 专题维护操作落审计

  Scenario: 负向 — 未上架/已下线的专题包不在 P7 显示
    Given 专题 "试运行专题包" status=draft；专题 "已退役专题包" status=archived
    When 我（sd-default）打开 P7
    Then 不显示这两个专题包
    And 注：跨租户专题隔离（不同 tenant_id）见 wave-3-protocol-tenant-national/features/multi-tenant-policy.feature

  Scenario: 负向 — 订阅不绕过 J1 主审批流
    Given 我订阅了 "营商环境"
    When 该专题内新增 catalog C_4001
    Then 我**只**收到通知，**不**自动获得 C_4001 凭据
    And 使用 C_4001 仍需走 J1 申请 → 审批 → 凭据流程

  Scenario: 回归 — 专题包不复造"运营平台"形态（基线 §1.3）
    Then P7 设计目标 = "主题化聚合的发现入口"，不是另一套申请系统
    And **不**做"专题包后台 dashboard"等炫技
    And P7 入口浅，UX 服务 J1 的"发现"环节
