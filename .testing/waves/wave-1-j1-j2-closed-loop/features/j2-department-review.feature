# Wave: 1
# Journey: J2
# Pages: P5
# Consumer-faces: WebUI
# Roles: ROLE_ORGAN_MANAGER
# Trace: 基线 §10.2 J2 部门审, 旧 xlsx 行 [43..44] 目录审核 (批量+单条), [62..63] 资源审核 (提交审核+发布审核)
# Priority: P1
# Status: Draft

Feature: J2 部门内审（catalog / resource）
  As a 部门管理员 ROLE_ORGAN_MANAGER
  I want 对本部门编目员提交的目录 / 资源进行审核
  So that 在数据上架前把好部门内合规关

  Background:
    Given 我以 ROLE_ORGAN_MANAGER 登录，org_code=部门A_公安
    And 编目员已在部门A 提交 catalog C1301 + resource R1301 进入 1 待审

  Scenario: 正向 — 部门审通过 + 推送平台复核
    When 我打开 P5 部门审核列表
    Then 看到 C1301 + R1301
    When 我审核 C1301 → 通过，备注 "信息项完整，符合部门内目录规范"
    Then catalog.status 从 1 待审 → 2 部门审批通过（中间态，等平台发布）
    And 审计 capability_call=catalog.dept_approve
    And BUSIAUDIT 端 P5 平台复核列表新增 C1301

  Scenario: 正向 — 同一审核会话内批量审核
    Given 列表含 C1301 / C1302 / C1303 三条
    When 我批量选中并点击 "全部通过"
    Then 三条 catalog 都 status=2 + 三条审计记录
    And 批量操作有二次确认弹窗（基线 §5.4.4 责任性操作不自动）

  Scenario: 正向 — 资源审核同步联动 catalog 审核
    When R1301 审核 → 通过
    Then resource.status 从 待审 → 部门审批通过
    And UI 显示 "Resource R1301 已通过部门审，等待平台发布"

  Scenario: 负向 — 部门审驳回 → 编目员收到补正建议
    When 我对 C1302 审核 → 驳回，备注 "缺少分类编码 + 信息项 X 描述不准"
    Then catalog.status 从 1 待审 → 3 驳回
    And 编目员侧 P1 工作台收到补正通知（含具体驳回原因）
    And 编目员补正后重新提交，status 重回 1 待审 + round 计数 +1

  Scenario: 负向 — 不能审核其他部门的目录（R11）
    When 我（部门A）尝试审核 部门B 的 catalog
    Then 列表中**不**出现 部门B 的 catalog
    And 直接 URL 访问返回 403

  Scenario: 负向 — 不能审核自己提交的目录（自审拦截）
    Given 我作为 ROLE_ORGAN_MANAGER 同时也以 ORGAN_OPERATER 身份提交了 C1399
    When 我尝试审核 C1399
    Then 拒绝
    And 审计 reject + reason="self_review_not_allowed"

  Scenario: 回归 — 部门审通过后**不**自动发布到 P2（必须经平台复核）
    Given C1301 部门审通过，status=2
    When 申请人在 P2 检索关键词
    Then C1301 不出现在结果中
    And 仅 status=4 发布后才进 P2
