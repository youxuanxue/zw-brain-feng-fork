# Wave: 1
# Journey: J1
# Pages: P2 / P3 / P5
# Consumer-faces: WebUI
# Roles: ROLE_ORGAN_OPERATER (申请方) | ROLE_ORGAN_MANAGER (编目部门) | ROLE_BUSIAUDIT
# Trace: 基线 §3.3 异议 5 维度 (data_objection_catalog 74 表), §9.2 ObjectionAggregate
# Priority: P1
# Status: Draft

Feature: J1 目录异议（catalog 维度独立状态机）
  As a 部门操作员（任意用户）
  I want 对目录信息描述错误 / 分类错误 / 元数据缺失提出异议
  So that 编目部门能修正描述，下次申请人不再被误导

  Background:
    Given 资源 C601 已发布，但 catalog_name 写错（"户籍信息" 实际应为 "户籍登记信息"）
    And 我以任意 ROLE_ORGAN_OPERATER 登录
    And 编目部门 U_DEPT_A_MGR (部门A) 已存在

  Scenario: 正向 — 在 P2 资源详情页提交目录异议
    When 我在 C601 资源详情页点击 "目录信息有问题"
    And 选择问题类型 "目录名错误"，填写建议 "应为：户籍登记信息"
    Then 创建 ObjectionCase O601，dimension=catalog，status=已提交
    And 推送到编目部门管理员（基线 §3.3：catalog 异议归属编目部门）
    And 审计 capability_call=objection.submit

  Scenario: 正向 — 编目部门修正描述 + 异议关闭 + 资源元数据更新
    When U_DEPT_A_MGR 处理 O601，选择 "接受异议 + 修正"
    And 修改 catalog_name="户籍登记信息"
    Then catalog 表更新 + audit_event 一条 catalog.update
    And ObjectionCase O601 status=已处理，process_result=已修正
    And 后续在 P2 检索"户籍登记信息" 命中 C601

  Scenario: 正向 — 多人对同一目录提同样异议自动合并
    Given U1 已提 O601 异议
    When U2 对 C601 提交同类异议（dimension=catalog，同问题类型）
    Then 系统提示 "已有相同异议，您是否加入？"
    And U2 选择加入后，O601 的 supporters 列表新增 U2
    And 不创建新 ObjectionCase

  Scenario: 负向 — 编目部门拒绝异议（描述实际正确）
    When U_DEPT_A_MGR 处理 O601，选择 "拒绝异议"，备注 "现有描述符合 GB/T XXXX 标准"
    Then ObjectionCase O601 status=已处理，process_result=拒绝
    And 资源 catalog 不修改
    And 申请人侧可对处理结果进行评价或申诉到 BUSIAUDIT

  Scenario: 负向 — 异议过程中目录被撤销（catalog.status 联动）
    Given catalog C601 在异议处理中被编目部门撤销，catalog.status=5 下线
    When 申请人查询 O601
    Then O601 状态仍为已提交，但显示警示 "关联目录已下线"
    And 处理路径自动切换为 "无需处理（目录已下线）"
    And 业务方 R13 sign-off：本场景默认不自动关闭异议，由 BUSIAUDIT 复核决定

  Scenario: 回归 — 编目部门通过异议路径修正不绕过 J2 审批
    Then catalog 字段变更经过 J2 审批最小路径（部门内审 → 平台复核），不直接进 catalog 表
    And 异议路径的修正写入 catalog 字段触发 catalog.status 从 4 发布 → 重新进入 1 待审，由 BUSIAUDIT 重新发布
