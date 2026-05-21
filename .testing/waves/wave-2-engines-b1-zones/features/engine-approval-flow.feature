# Wave: 2
# Journey: Cross (B1.2 后台配置 → J1 / J2 运行时)
# Pages: B1.2 (配置) / J1 / J2 (运行时)
# Consumer-faces: WebUI
# Roles: ROLE_SYSTEM (配置) | ROLE_BUSIAUDIT (复核)
# Trace: R8 / R14, 基线 §10.3 审批流可视化引擎, 业务反馈 #4 (鞍山"编制→二级部门审→一级部门审→发布")
# Priority: P1
# Status: Draft

Feature: 三引擎 #1 — 审批流可视化引擎
  As a 平台运维员 / 业务运营员
  I want 配置项目级审批流（节点 + 选人规则 + 条件分支）而不改代码
  So that 鞍山 / 四川 / 荆州等项目差异通过配置承接（R8 反 per-tenant fork）

  Background:
    Given 默认基线流程已内置：
      - flow-unconditional: 1 步（BUSIAUDIT 平台审）
      - flow-conditional: 2 步（部门审 → 平台复核）
    And 我以 ROLE_SYSTEM 登录，进入 B1.2 接入扩展中心 → 审批流编辑器

  Scenario: 正向 — 可视化编辑流程节点
    When 我点击"新建流程：编制→二级部门审→一级部门审→发布"
    And 拖拽节点：
      | 节点编号 | 节点名         | 选人规则                              | 退回行为      |
      | 1       | 编制           | 提交人                                | 草稿           |
      | 2       | 二级部门审      | applicant_org.parent_org 的 MANAGER  | 退回编制       |
      | 3       | 一级部门审      | applicant_org.root_org 的 MANAGER    | 退回二级部门审 |
      | 4       | 发布           | BUSIAUDIT 全部                        | 退回一级部门审 |
    And 点击"保存为草稿"
    Then 创建 approval_flow_def 记录，status=draft

  Scenario: 正向 — 草稿 → 预览 → 确认入库（基线 §5.4.4 §10.3）
    Given 我已保存流程草稿
    When 我点击"预览"
    Then 弹出运行时模拟器，展示 1 条 mock 申请走过该流程的全过程
    And 显示每个节点的 actor 解析结果（不只显示节点名）
    When 我点击"确认入库 + 生效到 项目=anshan"
    Then 写入 approval_flow_def，status=active，scope=tenant.project=anshan
    And J1 运行时对 project=anshan 的申请使用此流程
    And 其他 project 不受影响

  Scenario: 正向 — 自然语言生成流程草稿（R14 AI 落点）
    When 我在编辑器中输入 "我们项目需要先编制，然后部门管理员审，然后大数据局审，最后发布"
    Then AI 助手解析为 4 节点流程草稿
    And 草稿带证据来源 "基于解析提示词输入"
    And **不直接生效**（仍需走"预览 → 确认入库"）
    And 我可修改草稿后再确认

  Scenario: 负向 — 流程草稿未"确认入库"时**不**影响生产
    Given 我已保存流程草稿但未确认入库
    When J1 运行时新建申请
    Then 仍使用旧的活跃流程
    And 草稿仅在编辑器中可见

  Scenario: 负向 — 流程节点 actor 解析失败必须早发现
    Given 流程节点选人规则引用了不存在的角色字段
    When 我点击 "预览"
    Then 弹出错误提示，列出 actor 解析失败的节点
    And **拒绝**入库直到修正

  Scenario: 负向 — 不能配置绕过审计 / 跨租户 / 模型直连（R8 / R14 / D6 边界）
    When 我尝试配置节点跳过审计落库
    Then 拒绝
    And 错误信息明示约束来源（"audit 总线为内建强约束，不可配置"）

  Scenario: 回归 — 流程定义有版本与回滚目标
    Given approval_flow_def vX 已运行 30 天，产生大量在飞申请
    When 我切到 vX+1
    Then 在飞申请继续按 vX 走完
    And 新创建申请用 vX+1
    And 任意时刻可回滚到 vX
    And 审计 capability_call=approval_flow.activate / approval_flow.rollback
