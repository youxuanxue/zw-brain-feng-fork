# Wave: 0
# Journey: J1
# Pages: P2
# Consumer-faces: WebUI | API
# Roles: ROLE_ORGAN_OPERATER
# Trace: R1 / R9 / R12, 基线 §5.4.4 P2 反约束, 旧 xlsx 行 [1..12]
# Priority: P0
# Status: InTest
# Owner: e1
# Pytest: tests/test_wave0_j1_discover_draft.py + tests/test_wave1_p2_search_assistant.py
# Twin-F: e1.F6

Feature: J1 资源发现（P2 资源发现页）
  As a 部门操作员 (ROLE_ORGAN_OPERATER)
  I want 通过自然语言或目录树找到可申请的数据资源
  So that 不需要理解工程术语就能完成业务申请

  Background:
    Given 单租户 sd-default 已初始化
    And 7 角色码 CHECK 约束已生效
    And 集团推理平台 gateway mock 已就绪
    And 数据资源种子已注入：
      | catalog_id | catalog_name      | owner_org_code  | shared_type      | materialization |
      | C101       | 户籍基础信息       | 部门A_公安       | 1 无条件          | table           |
      | C102       | 法人单位登记信息    | 部门B_市场监管    | 2 有条件          | api             |
      | C103       | 不动产登记摘要     | 部门C_自然资源    | 2 有条件          | file            |
      | C104       | 内部专用统计基线    | 部门A_公安       | 3 不予共享        | table           |
    And 我以 ROLE_ORGAN_OPERATER 身份登录，org_code=部门A_公安
    And 单租户假设：跨租户隔离的回归用例见 wave-3-protocol-tenant-national/features/multi-tenant-policy.feature（Wave 3 才引入第二租户）

  Scenario: 正向 — 关键词检索命中目录（旧 xlsx 行 13 "查看数据目录"）
    When 我在 P2 检索框输入 "户籍"
    Then 返回结果列表至少包含 1 条
    And 第一条结果显示：
      | 字段              | 期望                |
      | catalog_name      | 户籍基础信息          |
      | owner_org_name    | 部门A_公安            |
      | shared_type_cn    | 无条件共享            |
      | materialization_cn | 数据库表              |
    And 不显示任何工程术语（不出现 "package" / "projection" / "policy_decision" / "write-with-audit"）
    And 审计总线记录一条 capability_call=resource.search，audit_class=read，actor 含 ROLE_ORGAN_OPERATER

  Scenario: 正向 — 自然语言意图解析（AI 减摩点，基线 §5.4.4 P2）
    When 我在 P2 检索框输入 "我要给公安做查询接口用的人口基础信息"
    Then AI 助手在主结果区**下方**显示建议筛选条件：
      | 维度        | 候选值                  |
      | 用途        | 业务系统查询接口         |
      | 物化形式    | api                    |
      | 部门标签    | 公安 / 民政             |
    And AI 建议带证据来源（"基于命中 2 个目录 + 历史 5 条相似申请"）
    And 主任务可以**不接受 AI 建议**继续走目录树检索（一票否决 §5.4.5：AI 不替代页面本体）

  Scenario: 正向 — 目录树筛选 + 资源详情进入申请页（J1 主链路衔接）
    When 我点击目录树 "部门A_公安 > 户籍基础信息"
    Then 进入资源详情页
    And 详情页显示 catalog / resource / 字段清单 / 共享类型 / 申请按钮
    When 我点击 "申请使用"
    Then 跳转到 P3 申请草稿页，资源 C101 已自动填入

  Scenario: 负向 — shared_type=3 不予共享资源不进 P2 检索（基线 §3.3 3 共享态）
    When 我在 sd-default 租户下检索 "内部专用统计基线"
    Then 不返回 C104
    And 审计总线记录 capability_call=resource.search 但结果集不含 C104
    And 注：跨租户场景（不同 tenant_id 隔离）见 wave-3-protocol-tenant-national/features/multi-tenant-policy.feature

  Scenario: 负向 — 未授权角色访问 P2 被拒
    Given 我以 ROLE_SECURITY_AUDIT 身份登录（不在 J1 主面）
    When 我访问 P2 资源发现页
    Then 返回 403 或 UI 显示"无访问权限"
    And 审计总线记录 policy decision=reject，缺少 ROLE_{ORGAN_OPERATER, ORGAN_MANAGER, BUSIAUDIT} 任一

  Scenario: 回归 — 工程术语黑名单（R12 / 基线 §5.5）
    When 我打开 P2 页面，DOM 完全渲染
    Then DOM 文本中不出现以下任一工程术语：
      | term                |
      | package             |
      | projection          |
      | capability          |
      | policy_decision     |
      | write-with-audit    |
      | register-version    |
      | apply-tenant-policy |
      | reconcile-receipt   |
      | submit-evidence     |

  Scenario: 回归 — AI 一票否决（基线 §5.4.5）
    Then P2 首屏不以聊天框作为默认主入口（结构化目录树 / 检索表单优先级高于 AI 助手）
    And AI 助手区域 z-index 不高于主结果列表
    And 关闭 AI 助手后主任务仍能完成

  Scenario Outline: 正向 — 跨消费面投影一致性（API 与 WebUI）
    When 我通过 <face> 调用资源检索接口，关键词="户籍"
    Then 返回的 catalog_id 列表与 WebUI 检索结果一致
    And 返回 schema 包含 catalog_id / catalog_name / owner_org_code / shared_type / materialization 字段

    Examples:
      | face |
      | API  |
      | CLI  |
