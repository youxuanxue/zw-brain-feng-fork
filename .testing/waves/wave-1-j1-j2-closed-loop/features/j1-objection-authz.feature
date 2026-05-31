# Wave: 1
# Journey: J1
# Pages: P3 (异议嵌入)
# Consumer-faces: WebUI | API
# Roles: ROLE_ORGAN_OPERATER (申请方) | ROLE_ORGAN_MANAGER (提供方部门)
# Trace: 基线 §3.3 异议 5 维度 (data_objection_authz 54 表), §9.2 ObjectionAggregate, §10.2
# Priority: P1
# Owner: e1
# Pytest: tests/test_wave1_objection_5dim_state.py + tests/test_wave1_objection_lifecycle.py

Feature: J1 授权异议（authz 维度独立状态机）
  As a 部门操作员（申请方）
  I want 对授权决策（驳回 / 撤销 / 收回）提交异议
  So that 不公正的授权决定能被纠错，无需通过线下渠道

  Background:
    Given 单租户 sd-default 已初始化
    And 申请单 A402 已被 ROLE_BUSIAUDIT 驳回，application.status=3 驳回
    And 我以 申请人 ROLE_ORGAN_OPERATER 登录
    And 提供方部门管理员 U_DEPT_B_MGR 已存在

  Scenario: 正向 — 提交授权异议 + 提供方响应
    When 我在 A402 详情页点击 "对授权决策提出异议"
    And 填写异议主体 / 异议理由 / 附件
    Then 创建 ObjectionCase O501，dimension=authz，status=已提交
    And 推送通知到 dept_owner_admin（基线 §3.3：authz 异议归属提供方部门）
    And 审计 capability_call=objection.submit，audit_class=write-critical
    When U_DEPT_B_MGR 登录，在异议工作台打开 O501
    Then 显示完整异议链 + 原审批轨迹
    When U_DEPT_B_MGR 选择 "重新审批"，备注 "重新审视后同意授权"
    Then ObjectionCase O501 status=已处理，process_result=重新审批
    And 原 application A402 status 从 3 驳回 → 1 待审（联动重新进入审批流）
    And audit_event 中包含 objection.process → application.resubmit_via_objection 串接

  Scenario: 正向 — 异议处理评价（evaluate 流程辅助表）
    Given O501 status=已处理，process_result=重新审批
    When 申请人在通知中点击 "评价处理结果"
    And 选择满意度=满意，备注 "感谢及时处理"
    Then 写入 data_objection_evaluate 等价投影表
    And O501 含 evaluate_score / evaluate_at

  Scenario: 负向 — 异议提交后超 X 工作日未响应，自动升级
    Given O501 status=已提交，提交时间 = now - 5 工作日
    And 配置 SLA=3 工作日
    When 后台 SLA 巡检触发
    Then O501 升级到 BUSIAUDIT 督查队列（不是改 status 而是新增 escalate 事件）
    And 通知 BUSIAUDIT 抓办

  Scenario: 负向 — 申请方对自己的异议进行响应（自处理拦截）
    When 我以申请人身份尝试以"处理者"身份关闭 O501
    Then 拒绝 + 审计 reject
    And UI 提示 "异议处理者必须是原审批方"

  Scenario: 负向 — 异议处理过程不能改写原 application 字段（边界）
    When U_DEPT_B_MGR 尝试通过 objection 路径修改 application A402 的 applicant_org_code
    Then 拒绝
    And 原 application 字段只能通过申请人 resubmit 路径变化（基线 §9.5 adapter 写入边界 + objection 处理边界一致）

  Scenario: 回归 — 5 维度状态机独立（基线 §3.3）
    Given O501 dimension=authz status=已处理
    Then 其它 4 维度（catalog / content / resource / use）的同一 ObjectionAggregate 实例**互不影响**
    And 跨维度查询 O501 只在 authz 列表显示
