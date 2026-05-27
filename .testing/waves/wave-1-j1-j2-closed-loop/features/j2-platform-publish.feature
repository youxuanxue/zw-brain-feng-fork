# Wave: 1
# Journey: J2
# Pages: P5
# Consumer-faces: WebUI
# Roles: ROLE_BUSIAUDIT
# Trace: 基线 §10.2 J2 平台发布, 基线 §5.2 P5 重复率检测提醒, 旧 xlsx 行 [40..42] 目录发布 (发布+批量+删除/下线) + [64..65] 资源发布 (单条+批量)
# Priority: P1
# Status: Draft
# Owner: e2
# Pytest: tests/test_wave1_j2_pipeline.py
# Twin-F: e2.F3

Feature: J2 平台发布（目录 + 资源最终上架）
  As a 业务运营员 ROLE_BUSIAUDIT（数据主管部门）
  I want 对部门内审通过的目录与资源进行最终复核并发布
  So that 数据真正进入 P2 资源发现，被申请人能找到

  Background:
    Given catalog C1401 + resource R1401 已经 status=2 部门审批通过，等待平台发布
    And 我以 ROLE_BUSIAUDIT 登录，org_code=省大数据局

  Scenario: 正向 — 平台复核 + 发布
    When 我打开 P5 平台复核列表
    Then 看到 C1401 / R1401
    When 我审核 C1401 → 通过 + 发布
    Then catalog.status 从 2 → 4 发布
    And resource.status 同步 → 已发布
    And C1401 进入 P2 资源发现页可被检索
    And 审计 capability_call=catalog.publish，audit_class=write-critical
    And owner_org_code=部门A 收到"目录已发布"通知

  Scenario: 正向 — 重复率检测提醒（基线 §5.2 P5：不硬拦）
    Given C1401 与已发布 C0701 catalog_name / 信息项重叠 > 70%
    When 我打开 C1401 复核详情
    Then UI 顶部显示橙色提示 "检测到与 C0701 重复率 78%，建议复用 C0701"
    And **仍可发布**（不硬拦）
    When 我点击 "仍然发布"
    Then 写入审计 reason "BUSIAUDIT 已知重复仍发布：<原因文本>"

  Scenario: 正向 — 发布后立即在 P2 / P3 / P4 投影一致（5 消费面）
    When C1401 发布完成
    Then WebUI P2 检索可见
    And API GET /catalogs/C1401 返回 200
    And CLI `zw-brain-cli catalog show C1401` 返回数据
    And MCP catalog.get 工具返回数据（同 capability 投影）

  Scenario: 负向 — 平台复核驳回 → 退回部门审
    When 我审核 C1402 → 驳回，备注 "缺少跨部门协调记录"
    Then catalog.status 从 2 部门审批通过 → 3 驳回（不退回 1 待审）
    And 推送通知到 owner 编目员 + 部门管理员
    And 编目员补正后必须**重走**完整流程（重新部门审 → 平台复核），不能跳到平台复核

  Scenario: 负向 — 下线（4 发布 → 5 下线）必须留下原因 + 通知申请人
    Given C1401 已发布，已有 5 个活跃凭据
    When 我对 C1401 点击 "下线"，备注 "对应资源接口已变更"
    Then catalog.status 4 → 5 下线
    And resource.status 同步 → 下线
    And 5 个活跃凭据自动 revoked
    And 5 个申请人侧 P1 工作台收到红色通知 "您所申请的目录已下线"
    And 不能在 P2 检索到 C1401

  Scenario: 负向 — 不能跳过部门审直接发布
    When 我尝试通过 API 直接 POST /catalogs/C9999/publish，但 C9999.status=0 草稿
    Then 返回 409 Conflict
    And 审计 reject + reason="invalid_state_transition"

  Scenario: 回归 — catalog 6 态完整迁移路径
    Then 完整状态机：
      | from           | to              | actor          |
      | 0 草稿         | 1 待审           | 编目员 submit    |
      | 1 待审         | 2 部门审批通过    | 部门管理员通过    |
      | 1 待审         | 3 驳回           | 部门管理员驳回    |
      | 2 部门审批通过  | 3 驳回           | BUSIAUDIT 驳回   |
      | 2 部门审批通过  | 4 发布           | BUSIAUDIT 发布   |
      | 3 驳回         | 1 待审           | 编目员重新提交    |
      | 4 发布         | 5 下线           | BUSIAUDIT 下线   |
    And 应用层另含 2 计算态："国家通道转报中"/"撤销中"（基线 §3.3 6+2）
