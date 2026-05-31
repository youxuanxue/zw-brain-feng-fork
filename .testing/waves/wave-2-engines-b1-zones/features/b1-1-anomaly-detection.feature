# Wave: 2
# Journey: B1.1
# Pages: B1.1
# Consumer-faces: WebUI
# Roles: ROLE_BUSIAUDIT
# Trace: 基线 §5.6 业务反馈 #14 (B1 后台旁路抽查 "长期无人申请的目录"诊断), §10.3
# Priority: P1
# Deferred: catalog.dormant.diagnose 能力 + B1.1 面板立项延后（preflight-debt.md 2026-05-27）
# Owner: e4
# Pytest: pending (preflight-debt.md 2026-05-27 — catalog.dormant.diagnose skill + B1.1 panel 立项延后)

Feature: B1.1 长期无人申请目录诊断（旁路抽查）
  As a 业务运营员
  I want 自动识别"发布了但长期无人申请"的目录
  So that 评估资源价值密度，决定下线 / 重新推广

  Background:
    Given catalog 已发布 50 个 (status=4)
    And 30 个 catalog 在 180 天内有 ≥1 次申请
    And 20 个 catalog 在 180 天内 0 申请（含 5 个发布 ≥365 天）
    And 我以 ROLE_BUSIAUDIT 登录

  Scenario: 正向 — 诊断报表展示长期无人申请目录
    When 我打开 B1.1 → "长期无人申请目录诊断"
    Then 报表按 "发布时长 + 申请数" 二维展示：
      | catalog | 发布时长   | 180 天申请数 | 建议       |
      | C_3001  | 380 天    | 0           | 建议下线    |
      | C_3002  | 220 天    | 0           | 建议推广    |
      | C_3003  | 90 天     | 0           | 继续观察    |
    And 报表区分"建议下线" / "建议推广" / "继续观察"
    And 报表可一键导出 CSV

  Scenario: 正向 — 从诊断报表跳到具体目录详情
    When 我点击 C_3001
    Then 跳转 P2 目录详情（管理视角）
    And 详情页显示 owner_org / 发布日期 / 完整 audit_event 链路（发布 → 0 次申请）

  Scenario: 正向 — BUSIAUDIT 决策"建议下线" → 通知 owner_org
    When 我对 C_3001 选择 "建议提供方下线"
    Then 推送通知到 owner_org 部门管理员
    And 不**直接**下线（由 owner_org 决定）
    And BUSIAUDIT 的判断写入 audit_event

  Scenario: 负向 — 不能直接下线他人目录（边界）
    When 我尝试通过 API 直接 POST C_3001/decommission
    Then 拒绝（基线 §六 角色 ≠ 方向 + R11）
    And 任何下线必须由 owner_org 或经 J1 use 异议 → 撤销路径
    And BUSIAUDIT 只能做建议

  Scenario: 负向 — 诊断不进数据治理范畴（基线 §1.3 不做的事）
    Then 诊断**不**包含数据质量评分 / 血缘分析 / 敏感识别（这些属于集团数据治理中心 + 数据安全中心）
    And 仅基于 zw-brain 自有的"申请数 + 发布时长"二维事实

  Scenario: 回归 — 诊断是只读，零写操作
    Then 诊断段不创建 / 修改任何业务实体
    And 仅基于 audit_event 与 catalog status 派生
    And 即使 B1.1 down，主旅程 J1/J2 不受影响
