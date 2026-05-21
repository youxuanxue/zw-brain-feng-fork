# Wave: 1
# Journey: J1
# Pages: P3 / P4
# Consumer-faces: WebUI | API
# Roles: ROLE_BUSIAUDIT | ROLE_ORGAN_OPERATER (申请人)
# Trace: 基线 §10.2, R10/R11
# Priority: P1
# Status: Draft

Feature: J1 凭据撤回 / 暂停
  As a 业务运营员 ROLE_BUSIAUDIT 或 申请人本人
  I want 撤回 / 暂停已签发的凭据
  So that 在违规、误授权、申请人不再需要时能及时收回

  Background:
    Given 申请单 A1501 已 application.status=6 已授权
    And 凭据 K_A1501 已签发，scope=C1501，有 20 天剩余
    And 我以 ROLE_BUSIAUDIT 登录（场景默认）

  Scenario: 正向 — BUSIAUDIT 撤回授权（合规驱动）
    When 我在 P3 跟踪页打开 A1501，点击 "撤回授权"
    And 备注 "近期对该资源调用合规风险高"
    Then application.status 6 → 已撤回
    And 凭据 K_A1501 status=revoked
    And 审计 capability_call=application.revoke + credential.revoke 两条
    And 申请人侧 P1 工作台红色通知 + 原因

  Scenario: 正向 — BUSIAUDIT 暂停授权（短期措施，可恢复）
    When 我点击 "暂停授权 + 设置恢复时间 = 7 天后"
    Then application.status 6 → 已暂停（应用层计算态）
    And 凭据 K_A1501 临时 disabled（不删，到时间自动恢复）
    And 调用方在暂停期内调用返回 403 + reason="credential_suspended"
    And 7 天后自动恢复，凭据重新可用 + 通知申请人

  Scenario: 正向 — 申请人主动放弃授权
    Given 我以 申请人 ROLE_ORGAN_OPERATER (A1501 申请人) 登录
    When 我在 P3 跟踪页点击 "我不再需要" + 二次确认
    Then application.status → 已撤回 (initiated_by=applicant)
    And 凭据立即 revoked
    And 不触发申请人侧"通知"（自己主动）

  Scenario: 负向 — 申请人不能撤回**他人**的授权
    When 我（非 A1501 申请人）尝试访问 A1501 撤回接口
    Then 拒绝
    And 审计 reject + reason="not_owner_of_application"

  Scenario: 负向 — 部门管理员（提供方）不能直接撤回
    Given U_DEPT_C_MGR 是 C1501 资源提供方部门管理员
    When U_DEPT_C_MGR 尝试撤回 A1501
    Then 拒绝（提供方不直接撤回；走 J1 use 异议路径）
    And UI 提示 "请通过提交使用异议路径"

  Scenario: 负向 — 撤回不可逆（区别于暂停）
    Given application A1501 已撤回
    When 我尝试再"恢复"已撤回的凭据
    Then 拒绝
    And UI 提示 "请重新提交申请"

  Scenario: 回归 — 撤回 / 暂停的审计链完整可追溯
    Then audit_event 含字段：actor / actor_role / reason / from_status / to_status / occurred_at
    And BUSIAUDIT 与申请人撤回的 actor_role 字段不同（可区分发起方）
