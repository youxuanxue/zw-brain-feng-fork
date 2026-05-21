# Wave: 0
# Journey: J1
# Pages: P3
# Consumer-faces: WebUI
# Roles: ROLE_BUSIAUDIT
# Trace: R10 / R11, 基线 §10.1（必含有条件/无条件两种分支）, 旧 xlsx 行 [16..24] 服务审核
# Priority: P0
# Status: Draft

Feature: J1 无条件共享分支 — 平台直接审批
  As a 业务运营员 (ROLE_BUSIAUDIT，省/市大数据局)
  I want 对无条件共享资源的申请进行平台侧审批
  So that 客户能在最短路径走完"申请 → 审批 → 凭据"

  Background:
    Given 单租户 sd-default 已初始化
    And 资源 C101 已发布，shared_type=1 无条件共享
    And 申请单 A201 已由 ROLE_ORGAN_OPERATER (部门A) 对 C101 提交，application.status=1 待审
    And 我以 ROLE_BUSIAUDIT 登录，org_code=省大数据局

  Scenario: 正向 — 平台直接审批通过（无条件共享单步审批）
    When 我打开 P3 审批列表
    Then 我能看到申请单 A201
    And 列表显示：申请人 / 申请部门 / 资源 / shared_type=无条件共享 / 进入时间 / 距离超时
    When 我打开 A201 详情，点击 "通过"
    Then application.status 转 6 已授权（无条件分支无部门审 = 跳过 2-5）
    And 审计总线记录 capability_call=application.approve，approver_role=ROLE_BUSIAUDIT，audit_class=write-critical
    And 申请人侧 P1 工作台出现"通过"通知

  Scenario: 正向 — 列表按"超时 > 临期 > 普通"排序（基线 §5.2 P1 + P3 列表）
    Given 我的待办包含 3 条申请：
      | A301 | 进入 25h，SLA 24h，超时         |
      | A302 | 进入 18h，SLA 24h，临期(<24h)    |
      | A303 | 进入 2h，SLA 24h，普通          |
    Then 列表排序为 A301 → A302 → A303
    And A301 显示红色"已超时"徽标
    And A302 显示橙色"临期"徽标

  Scenario: 正向 — 审批人备注 + 审批回执
    When 我审批 A201 通过，备注 "无条件共享，符合公开目录"
    Then ApprovalTask 记录 decision=通过 / comment / actor_id / decided_at
    And 审计回执可由申请人在 P3 跟踪页查看

  Scenario: 负向 — 非 BUSIAUDIT 角色不能在无条件分支独立审批
    Given 我以 ROLE_ORGAN_MANAGER (部门B) 身份登录
    When 我访问 A201 审批
    Then 不显示"通过 / 驳回"按钮
    And 列表中 A201 不出现在"我的待审"

  Scenario: 负向 — 已撤回申请不能再被审批
    Given 申请人已撤回 A201，application.status=已撤回
    When 我尝试点击 "通过"
    Then 操作被拒，UI 显示 "该申请已撤回"
    And 审计总线记录 policy decision=reject，原因="invalid state transition"

  Scenario: 负向 — 跨部门方向校验（R11）
    Given 申请 A202 owner_org_code=部门A，applicant_org_code=部门B
    Then BUSIAUDIT 视角看到 A202 在"我的受理"队列
    And ORGAN_MANAGER (部门B) 视角看到 A202 在"我的发起"队列
    And ORGAN_MANAGER (部门A) 视角看到 A202 在"我作为提供方"队列（仅 conditional 才出现，本场景为 unconditional 不出现）

  Scenario: 回归 — 审批操作必须留审计 + 凭据自动签发触发
    When 我通过 A201
    Then application.status=6 已授权
    And 后台异步触发 credential.issue（详见 j1-credential-issue.feature）
    And 审计事件链：application.submit → application.approve → credential.issue 三条记录在 audit_event 表内顺序连贯
