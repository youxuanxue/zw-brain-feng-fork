# Wave: 0
# Journey: J1
# Pages: P3
# Consumer-faces: WebUI
# Roles: ROLE_BUSIAUDIT | ROLE_ORGAN_MANAGER
# Trace: R10 / R11, 基线 §10.1（有条件共享审批分支）, 旧 xlsx 行 [86..90] 服务审核 + [91] 申请变更复用主审批流, 业务反馈 #4, D55/P21（受理/审核两级，改 D49 关联）
# Priority: P0
# Owner: e1
# Pytest: tests/test_wave0_j1_approval.py + tests/test_wave0_j1_approval_conditional.py + tests/test_wave0_j1_approval_conditional_runtime.py
# Unfreeze-Note: D55/P21 受理/审核两级运行时已落地（受理在前、部门审核在后，与旧序对调）——
#   platform_approve(受理,业务运营员)→dept_approve(部门审核,部门管理员) handler
#   + ConditionalApprovalService 状态机（submitted→dept_approved 受理通过待审→granted/rejected,
#   rejected→submitted round+1）+ 部门审核级保留 self_approval / R11 方向 guard（受理级不适用）。
#   capability key 不改名（D33 先例）：受理复用 application.platform_approve、部门审核复用
#   application.dept_approve；中间态字符串 dept_approved 不改名（含义=已受理待部门审）。
#   ExchangeMapper.data_apply_dept_approve 灌入 sd-default 真实 department step（数据底座层）。
#   pytest 覆盖：test_wave0_j1_approval_conditional_runtime.py 驱动真实 handler 真写库断言
#   状态迁移 / step / decision / 审计；test_wave0_j1_approval_conditional.py 断数据底座。
#   留债：e2e 两级点击穿透（P3 受理队列→部门审核队列）超本次成本，未覆盖。

Feature: J1 有条件共享分支 — 受理（业务运营员）+ 部门审核（部门管理员）两级
  As a 业务运营员 (ROLE_BUSIAUDIT 省大数据局，受理第一级) + 部门管理员 (ROLE_ORGAN_MANAGER 提供方部门，审核第二级)
  I want 对有条件共享资源走"业务运营员受理 → 提供方部门审核"两级
  So that 主管部门先做初级受理，提供方部门保有最终数据使用决定权

  Background:
    Given 单租户 sd-default 已初始化
    And 资源 C102 已发布，shared_type=2 有条件共享，owner_org_code=部门B_市场监管
    And 申请单 A301 已由 ROLE_ORGAN_OPERATER (部门A_公安) 对 C102 提交，application.status=1 待审
    And 用户 U_BUSIAUDIT 持 ROLE_BUSIAUDIT × 省大数据局
    And 用户 U_DEPT_B_MGR 持 ROLE_ORGAN_MANAGER × 部门B_市场监管

  Scenario: 正向 — 第一级业务运营员受理（初级审核，平台级动作无方向约束）
    Given 我以 U_BUSIAUDIT 登录
    When 我打开 P3 "待我办理" 受理队列
    Then 我能看到 A301，shared_type 中文名="有条件共享"
    When 我受理 A301，备注 "材料齐全，予以受理"
    Then application.status 从 1 待审 → 4 已受理待审核（中间态）
    And 申请单上记录 platform_reviewer_id=U_BUSIAUDIT
    And 审计总线记录 capability_call=application.platform_approve

  Scenario: 正向 — 第二级提供方部门管理员审核（终审，R11 方向计算）
    Given A301 已由 U_BUSIAUDIT 受理，application.status=4 已受理待审核
    And 我以 U_DEPT_B_MGR 登录
    When 我打开 P3 "待我办理" 部门审核队列
    Then 我能看到 A301
    When 我点击 "审核通过"，备注 "用途合理，限期 90 天"
    Then application.status 转 6 已授权
    And 审计事件链：application.submit → application.platform_approve → application.dept_approve 三条
    And 申请人侧出现"通过"通知 + 凭据领取入口

  Scenario: 正向 — 第一级受理驳回 + 申请人补件后重新提交（5 节点 业务反馈 #4）
    Given 我以 U_BUSIAUDIT 登录
    When 我受理驳回 A301，备注 "缺少业务场景说明"
    Then application.status 从 1 待审 → 3 驳回
    And 申请人侧 P1 工作台出现"补件提醒"
    Given 申请人补充字段并点击 "重新提交"
    Then application.status 从 3 驳回 → 1 待审
    And 申请单 round 计数 +1（追踪重提次数）

  Scenario: 负向 — 受理通过后部门审核驳回（提供方部门否决路径）
    Given A301 已 U_BUSIAUDIT 受理，application.status=4 已受理待审核
    And 我以 U_DEPT_B_MGR 登录
    When 我点击 "驳回"，备注 "本部门数据近 6 个月调用合规风险高，本次拒绝"
    Then application.status 从 4 已受理待审核 → 3 驳回
    And 申请人侧 P3 跟踪页显示"部门审核驳回"+ 部门备注
    And 受理通过的记录**仍保留**（不回退到受理前）

  Scenario: 负向 — 提供方部门外的 ORGAN_MANAGER 不能审核此申请（R11 方向，第二级）
    Given A301 已 U_BUSIAUDIT 受理，application.status=4 已受理待审核
    And 用户 U_DEPT_C_MGR 持 ROLE_ORGAN_MANAGER × 部门C_自然资源
    When U_DEPT_C_MGR 访问 P3 部门审核队列
    Then 看不到 A301（owner_org_code=部门B ≠ U_DEPT_C_MGR.current_org_code）
    And R11：方向由 owner_org_code 计算

  Scenario: 负向 — 申请人本人不能审核自己的申请
    Given A301 已受理进入第二级，application.status=4 已受理待审核
    And 我以 ROLE_ORGAN_MANAGER (部门A，与 A301 申请人同部门) 登录
    When 我尝试访问 A301 部门审核接口
    Then 拒绝
    And 审计总线记录 policy decision=reject，原因="self_approval_not_allowed"

  Scenario: 回归 — 状态机迁移合法性（基线 §3.3）
    Then application.status 仅允许：
      | from | to               | actor                 |
      | 0 草稿 | 1 待审         | applicant.submit       |
      | 1 待审 | 3 驳回         | accept.reject(受理驳回) |
      | 1 待审 | 4 已受理待审核   | accept(受理,业务运营员) |
      | 1 待审 | 6 已授权        | accept(无条件受理即终)  |
      | 3 驳回 | 1 待审         | applicant.resubmit     |
      | 4 已受理待审核 | 3 驳回   | dept_review.reject(部门审核驳回) |
      | 4 已受理待审核 | 6 已授权  | dept_review(部门审核终审) |
      | 6 已授权 | 已收回         | grant.revoke           |
    And 任何非法迁移返回 409 + audit reject
