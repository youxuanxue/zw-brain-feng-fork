# Wave: 1
# Journey: J1
# Pages: B1.1 (Wave 2 后台入口) / 提供方部门工作台
# Consumer-faces: WebUI
# Roles: ROLE_ORGAN_MANAGER (提供方部门) | ROLE_BUSIAUDIT (合规) | ROLE_SECURITY_AUDIT
# Trace: 基线 §3.3 异议 5 维度 (data_objection_use 155 表), §9.2 ObjectionAggregate
# Priority: P1
# Status: Draft

Feature: J1 使用异议（use 维度独立状态机）
  As a 部门管理员（提供方）或合规审计员
  I want 对使用方违规使用、超范围调用、滥用数据提交异议
  So that 平台能制裁违规使用，保护数据资产

  Background:
    Given 申请单 A901 已通过授权，使用方=部门A_公安，凭据 K_A901 已签发
    And 资源 C901 owner_org_code=部门C_民政
    And 我以 U_DEPT_C_MGR (提供方部门管理员) 登录

  Scenario: 正向 — 提供方发现使用方超范围调用，提交使用异议
    When 我观察到 部门A 在 K_A901 上调用频次远超声明（500/天 vs 申报 100/天）
    And 我在 P4 调用监控段（提供方视角）点击 "对此使用提交异议"
    And 填写异议主体 "调用频次远超声明值" + 附证据 request_id 列表
    Then 创建 ObjectionCase O901，dimension=use
    And 推送到 BUSIAUDIT 队列（基线 §3.3：use 异议归属合规面）

  Scenario: 正向 — BUSIAUDIT 复核 + 处置（限流 / 撤销）
    When U_BUSIAUDIT 处理 O901
    Then 可选处置：
      | 处置             | 后果                                         |
      | 警告             | 通知使用方 + 异议状态=已处理                    |
      | 限流（强制）      | 临时下调使用方配额（如 100/天 → 50/天）         |
      | 撤销授权          | 撤销凭据 K_A901，application.status → 已撤回 |
    When U_BUSIAUDIT 选择 "撤销授权"
    Then 凭据 K_A901 立即 revoked
    And application A901 status=已撤回 due to use objection
    And 申请人侧 P1 工作台出现"授权被撤回"红色通知 + 原因

  Scenario: 正向 — 使用方异议处理评价 + 评估流程辅助表
    Given O901 status=已处理，process_result=警告
    When U_DEPT_A_MGR (使用方部门) 对处理结果评价 "处理公正"
    Then 写入 data_objection_evaluate 投影表

  Scenario: 负向 — 使用方不能为自己的"使用"行为代为发起 use 异议
    When U_DEPT_A_OPERATER (使用方本人) 尝试创建 use 异议
    Then 拒绝
    And UI 提示 "use 异议由提供方或合规审计发起"

  Scenario: 负向 — use 异议处置不能跨越 5 维度边界
    When U_BUSIAUDIT 尝试在 O901 处理中改 catalog 字段
    Then 拒绝（5 维度独立）

  Scenario: 回归 — use 异议处理后审计链可回放
    Then audit_event 中 use 异议从提交到处置形成完整链路：
      objection.submit → objection.escalate_to_busiaudit → objection.process → credential.revoke
    And BUSIAUDIT 决策的合规理由保留在 audit_event metadata 中
