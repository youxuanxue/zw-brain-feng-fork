# Wave: 0
# Journey: J1
# Pages: P3
# Consumer-faces: WebUI
# Roles: ROLE_ORGAN_MANAGER | ROLE_BUSIAUDIT
# Trace: R10 / R11, 基线 §10.1（有条件共享审批分支）, 旧 xlsx 行 [16..24] 服务审核, 业务反馈 #4
# Priority: P0
# Status: Draft

Feature: J1 有条件共享分支 — 部门审 + 平台复核两步
  As a 部门管理员 (ROLE_ORGAN_MANAGER 提供方部门) + 业务运营员 (ROLE_BUSIAUDIT)
  I want 对有条件共享资源走"部门同意 → 平台复核"两步
  So that 提供方部门保有数据使用决定权，主管部门保有合规复核权

  Background:
    Given 单租户 sd-default 已初始化
    And 资源 C102 已发布，shared_type=2 有条件共享，owner_org_code=部门B_市场监管
    And 申请单 A301 已由 ROLE_ORGAN_OPERATER (部门A_公安) 对 C102 提交，application.status=1 待审
    And 用户 U_DEPT_B_MGR 持 ROLE_ORGAN_MANAGER × 部门B_市场监管
    And 用户 U_BUSIAUDIT 持 ROLE_BUSIAUDIT × 省大数据局

  Scenario: 正向 — 第一步部门管理员审核（提供方视角，R11 方向计算）
    Given 我以 U_DEPT_B_MGR 登录
    When 我打开 P3 "我作为提供方" 队列
    Then 我能看到 A301，shared_type 中文名="有条件共享"
    When 我审批 A301 通过，备注 "用途合理，限期 90 天"
    Then application.status 从 1 待审 → 4 部门同意（中间态）
    And 申请单上记录 dept_approver_id=U_DEPT_B_MGR，dept_decided_at=now
    And 审计总线记录 capability_call=application.dept_approve

  Scenario: 正向 — 第二步平台运营员复核（数据主管部门视角）
    Given A301 已由 U_DEPT_B_MGR 通过，application.status=4 部门同意
    And 我以 U_BUSIAUDIT 登录
    When 我打开 P3 "平台复核" 队列
    Then 我能看到 A301
    When 我点击 "通过"
    Then application.status 转 6 已授权
    And 审计事件链：application.submit → application.dept_approve → application.platform_approve 三条
    And 申请人侧出现"通过"通知 + 凭据领取入口

  Scenario: 正向 — 第一步驳回 + 申请人补件后重新提交（5 节点 业务反馈 #4）
    Given 我以 U_DEPT_B_MGR 登录
    When 我审批 A301 驳回，备注 "缺少业务场景说明"
    Then application.status 从 1 待审 → 3 驳回
    And 申请人侧 P1 工作台出现"补件提醒"
    Given 申请人补充字段并点击 "重新提交"
    Then application.status 从 3 驳回 → 1 待审
    And 申请单 round 计数 +1（追踪重提次数）

  Scenario: 负向 — 部门审通过后平台驳回（合规复核驳回路径）
    Given A301 已 dept_approve 通过，application.status=4 部门同意
    And 我以 U_BUSIAUDIT 登录
    When 我点击 "驳回"，备注 "申请部门近 6 个月调用合规风险高，本次拒绝"
    Then application.status 从 4 部门同意 → 3 驳回
    And 申请人侧 P3 跟踪页显示"平台复核驳回"+ BUSIAUDIT 备注
    And 部门审通过的记录**仍保留**（不回退到第一步前）

  Scenario: 负向 — 提供方部门外的 ORGAN_MANAGER 不能审批此申请（R11 方向）
    Given 用户 U_DEPT_C_MGR 持 ROLE_ORGAN_MANAGER × 部门C_自然资源
    When U_DEPT_C_MGR 访问 P3 申请列表
    Then 看不到 A301（owner_org_code=部门B ≠ U_DEPT_C_MGR.current_org_code）
    And R11：方向由 owner_org_code 计算

  Scenario: 负向 — 申请人本人不能审批自己的申请
    Given 我以 ROLE_ORGAN_OPERATER (部门A，A301 申请人) 登录
    When 我尝试访问 A301 审批接口
    Then 拒绝
    And 审计总线记录 policy decision=reject，原因="self_approval_not_allowed"

  Scenario: 回归 — 状态机迁移合法性（基线 §3.3）
    Then application.status 仅允许：
      | from | to               | actor                 |
      | 0 草稿 | 1 待审         | applicant.submit       |
      | 1 待审 | 3 驳回         | dept_or_platform.reject |
      | 1 待审 | 4 部门同意      | dept.approve           |
      | 1 待审 | 6 已授权        | platform.approve(unconditional) |
      | 3 驳回 | 1 待审         | applicant.resubmit     |
      | 4 部门同意 | 3 驳回      | platform.reject        |
      | 4 部门同意 | 6 已授权    | platform.approve       |
      | 6 已授权 | 已收回         | platform.revoke        |
    And 任何非法迁移返回 409 + audit reject
