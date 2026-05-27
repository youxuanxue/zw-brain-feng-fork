# Wave: 1
# Journey: J1
# Pages: P4 (调用数据后) / P3
# Consumer-faces: WebUI | API
# Roles: ROLE_ORGAN_OPERATER (申请方) | ROLE_ORGAN_MANAGER (提供方部门)
# Trace: 基线 §3.3 异议 5 维度 (data_objection_content 89 表), §9.2 ObjectionAggregate
# Priority: P1
# Status: Draft
# Owner: e1
# Pytest: tests/test_wave1_objection_5dim_state.py + tests/test_wave1_objection_lifecycle.py
# Twin-F: e1.F2

Feature: J1 数据内容异议（content 维度独立状态机）
  As a 部门操作员（已获得授权的使用方）
  I want 对实际调用返回的数据内容错误（脏数据 / 字段值不准 / 缺失）提交异议
  So that 提供方能修正数据，使用方业务不被脏数据拖垮

  Background:
    Given 申请单 A701 已通过授权，凭据 K_A701 已签发
    And 资源 C701 owner_org_code=部门C_民政
    And 我以申请人 ROLE_ORGAN_OPERATER (部门A) 登录，已调用 C701 一次

  Scenario: 正向 — 调用后基于具体记录提交内容异议
    When 我在 P4 调用监控段选择一条具体响应（含 request_id），点击 "数据有问题"
    And 选择问题字段 "出生日期"，填写问题描述 "返回值与户籍底册不一致"
    Then 创建 ObjectionCase O701，dimension=content
    And ObjectionCase 引用 request_id + 涉及字段 + 涉及记录（脱敏后）
    And 推送到 owner_org_code=部门C_民政 的管理员

  Scenario: 正向 — 提供方修正数据 + 异议关闭 + 通知使用方
    When U_DEPT_C_MGR 处理 O701，确认数据错误，备注 "底册数据已订正"
    And 选择处理结果 "已修正"
    Then ObjectionCase O701 status=已处理，process_result=已修正
    And 后台触发使用方端通知（应用层）
    And 申请人侧可在 P3 跟踪页看到处理结果

  Scenario: 正向 — 内容异议触发 BUSIAUDIT 抽查（合规底线）
    Given O701 反复出现（同 catalog 30 天内 3 次以上 content 异议）
    Then 自动在 B1.1 合规与运营段（Wave 2 入口）打标记 "数据质量风险"
    And BUSIAUDIT 工作台出现该 catalog 的督查任务（Wave 2 实施）
    And Wave 1 仅做标记，不做完整 B1.1（避免越界）

  Scenario: 负向 — 内容异议不能修改 catalog / resource 元数据
    When U_DEPT_C_MGR 尝试在 content 异议处理中改 catalog_name
    Then 拒绝
    And UI 提示 "请通过目录异议路径"
    And 5 维度状态机互不串扰

  Scenario: 负向 — 未获得授权的用户不能对该资源提内容异议
    Given U_NO_AUTH 未对 C701 持有有效凭据
    When U_NO_AUTH 尝试访问 P4 提交内容异议
    Then 拒绝
    And 审计 reject + reason="no_active_credential"

  Scenario: 回归 — 涉及具体数据记录的脱敏与最小可见
    Then ObjectionCase O701 存储 request_id + 涉及字段
    And 不**全量**存储响应内容（避免敏感数据泄漏放大）
    And 提供方查看时仅展示脱敏定位信息（如哈希 / 主键值的最后 4 位）
