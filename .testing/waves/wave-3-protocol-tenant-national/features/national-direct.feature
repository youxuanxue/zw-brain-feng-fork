# Wave: 3
# Journey: J1 (独立子旅程)
# Pages: P3 (国家通道 tab)
# Consumer-faces: WebUI
# Roles: ROLE_BUSIAUDIT
# Trace: 基线 §3.2 数据直达 36 页, §10.4 国家数据直达独立子旅程 (P2), §5.6 #8
# Priority: P2
# Owner: e6
# Pytest: tests/test_national_escalate.py + tests/test_national_channel_gate.py + tests/e2e/national_channel.spec.ts

Feature: 国家数据直达独立子旅程
  As a 业务运营员 ROLE_BUSIAUDIT
  I want 走"本级转报 → 国家平台衔接"独立流程，不污染 J1 主链路
  So that 普通申请人不被国家通道复杂性绑架（基线 §5.6 业务原话"用得最少"）

  Background:
    Given 国家通道 adapter 已就位（基线 §3.4 省市间数据通道）
    And 我以 ROLE_BUSIAUDIT 登录

  Scenario: 正向 — 国家通道独立子旅程入口
    When 我打开 P3 申请审批
    Then 顶部 tab 含"主流程"+"国家通道"两个分类
    And "国家通道" tab 仅 BUSIAUDIT 可见
    And 普通 ROLE_ORGAN_OPERATER 视角下"国家通道" tab 不显示

  Scenario: 正向 — 本级转报审核流程
    Given 一份来自 部门X 的"申请国家级数据"请求 A_7001
    When 我打开"国家通道" tab → A_7001
    And 我选择 "审核通过 + 转报到国家平台"
    Then application.status 进入应用层计算态 "国家通道转报中"
    And 调用国家通道 adapter，触发 outbound 请求
    And 审计 capability_call=application.escalate_national

  Scenario: 正向 — 国家平台响应回流
    When 国家通道 adapter 收到回应
    Then A_7001 status 由"国家通道转报中" → 6 已授权 / 或 3 驳回（视回应）
    And 申请人侧通知含国家通道返回的具体原因

  Scenario: 负向 — 国家通道 adapter 不可达时业务**不阻塞主链路**
    Given 国家通道 adapter 长时间不可达
    Then 只有 "国家通道" 子旅程受影响
    And J1 主链路（本省内共享）完全不受影响（一票否决式独立性）
    And UI 在国家通道 tab 显示 "国家通道暂不可用，请稍后"

  Scenario: 负向 — 国家通道流程不进 P1 工作台默认排序
    Given P1 工作台展示"今日待办"
    Then 国家通道相关待办**单独列出**或带"国家通道"标签
    And 不与本级共享待办混排
    And 普通用户 P1 工作台不见国家通道待办

  Scenario: 回归 — 国家通道是 P2 优先级，本期占位
    Then 国家通道独立子旅程开关由 feature flag 控制
    And 默认关闭（基线 §10.4 "本期不实施"）
    And 客户上线时按需启用
