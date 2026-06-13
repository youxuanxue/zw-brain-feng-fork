# Wave: 1
# Journey: J1
# Pages: P3 / P4
# Consumer-faces: WebUI | API
# Roles: ROLE_BUSIAUDIT | ROLE_ORGAN_OPERATER (申请人)
# Trace: 基线 §10.2, R10/R11
# Priority: P1
# Owner: e1
# Pytest: tests/test_wave1_j1_credential.py + tests/test_wave0_j1_credential_call.py + tests/test_wave1_j1_grant_revoke.py

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

  Scenario: 正向 — BUSIAUDIT 暂停授权（短期措施，状态可被 revoke 终结）
    # 诚实边界（R-008）：定时自动恢复（resume）当前未实现——application_grant.py:86 明写
    # "恢复/resume 能力待后续 PR"，全仓零 resume 测试。本场景只断言**已实装**的暂停语义
    # （落 status、调用期内 403、可被 revoke 终结），不再声称 "7 天后自动恢复"，避免 Done
    # 覆盖未实现承诺。自动恢复见下方 Deferred 占位场景。
    When 我点击 "暂停授权"
    Then application.status 6 → 已暂停（应用层计算态，真落 status 列）
    And 凭据 K_A1501 临时 disabled（不删）
    And 调用方在暂停期内调用返回 403 + reason="credential_suspended"
    And 该暂停态可被后续 revoke 终结（不可静默复活）

  Scenario: 占位（Deferred）— 暂停后定时自动恢复
    # Deferred-Scenario：触发=排期实装 resume 能力（定时器 / 到期扫描）→ 暂停设恢复时间 +
    # 到点自动解 disabled + 通知申请人。当前 application_grant.py:86 明写待后续 PR，
    # 不在测量轴覆盖（无 resume 测试），故本场景仅作意图占位、不参与绿判定。
    Given resume 能力本期未实装（待后续 PR）
    When 排期实装后设置 "恢复时间 = 7 天后"
    Then 7 天后凭据自动重新可用 + 通知申请人（本期不验证）

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
