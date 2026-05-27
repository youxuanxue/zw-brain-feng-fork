# Wave: 2
# Journey: B1.1
# Pages: B1.1
# Consumer-faces: WebUI
# Roles: ROLE_BUSIAUDIT | ROLE_SECURITY_AUDIT
# Trace: 基线 §10.3 B1.1 最小可用（异常发现 + 抽查 + 督查三段）, §5.4.4 B1.1 反约束
# Priority: P1
# Status: Draft
# Owner: e4
# Pytest: pending
# Twin-F: e4.F3

Feature: B1.1 合规与运营 — 异常 + 抽查 + 督查三段
  As a 业务运营员 / 安全审计员
  I want 在 B1.1 一站式发现异常、做合规抽查、对违规做督查
  So that 合规底线可证而不需要爬日志

  Background:
    Given 单租户 sd-default 已运行 30 天，audit_event 表已积累 ≥10000 条
    And 我以 ROLE_BUSIAUDIT 登录，进入 B1.1 合规与运营

  Scenario: 正向 — 异常段：自动检测违反主旅程的事件
    When 我打开"异常发现"段
    Then 系统自动展示最近 7 天的异常事件分类：
      | 异常类型                              | 实例数 |
      | 高频凭据滥用 (>1000 calls/day)        | 3     |
      | 申请超时未审批 (>SLA)                 | 12    |
      | 异议未响应 (>3 工作日)                 | 5     |
      | 长期无人申请目录 (>180 天 0 申请)      | 28    |
    And 每条异常带"开始调查"按钮 + 相关 audit_event 链路一键回放

  Scenario: 正向 — 抽查段：基于 RNG 的抽查
    When 我点击"发起合规抽查"
    And 选择抽查范围 "本周通过的申请 / 抽样 10 条 / 随机种子=auto"
    Then 系统随机抽 10 条
    And 抽查报告含：申请人 / 资源 / 审批人 / 审计链 / 凭据状态 / 调用记录摘要
    And 我可对每条标记 "合规" / "存疑" + 备注
    And 抽查结果写入 audit_event metadata 用于后续可追溯

  Scenario: 正向 — 督查段：对违规事件发起督查
    Given 抽查中我标记 A2501 "存疑"
    When 我点击 "发起督查"
    Then 创建 supervision_case + 通知相关部门 + 通知 SECURITY_AUDIT 协同
    And 督查 case 走"调查 → 处置（警告/限流/撤销）→ 评价"流程

  Scenario: 正向 — AI 调查摘要助手（基线 §5.4.4 B1.1 反约束）
    When 我打开一个调查 case 的详情
    Then AI 助手在侧边栏自动归纳证据 + 提示风险点
    And AI 输出**不替**审计员的结论（按钮"出具调查意见"由人工填）
    And AI 输出带证据来源（具体 audit_event ID 列表）
    And AI 关闭后原始证据仍可独立查阅

  Scenario: 负向 — 普通用户无权访问 B1.1
    Given 我以 ROLE_ORGAN_OPERATER 登录
    When 我访问 B1.1 任意 URL
    Then 返回 403
    And 主导航**不**显示 B1.1 入口（基线 R1 普通用户首屏不见 B1）

  Scenario: 负向 — 抽查不能修改原始数据
    When 我尝试在抽查中改 audit_event 字段
    Then 拒绝（audit_event 是 append-only）
    And 抽查结论只能附加到 metadata，不改原始事件

  Scenario: 回归 — B1.1 只是合规底线，不是产品差异化（基线 §1.2 / §10.3）
    Then B1.1 不抢占 J1/J2 主导航空间
    And B1.1 设计目标是 "异常可追、合规可证"，不追求图表炫技
    And 报告导出是基础能力，不做"大屏指挥中心"形态（基线 §1.3 不做大屏）
