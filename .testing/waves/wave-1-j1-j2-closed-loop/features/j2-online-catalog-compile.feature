# Wave: 1
# Journey: J2
# Pages: P5
# Consumer-faces: WebUI
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER (含 tag_lead_dept — 牵头标签依附 MANAGER，per docs/approved/zw-brain-roles.md §三) | ROLE_BUSIAUDIT (仅反向编目平台审，D57⑧)
# Trace: 基线 §3.2 目录管理 23 页, §3.3 CatalogModel 双轨编制, §10.2 J2 在线编制, 旧 xlsx 行 [35..38] 反向编目+在线编制+导入+编辑 (45-53 国家目录治理 ⏸ Wave 3)
# Priority: P1
# Owner: e2
# Pytest: tests/test_wave1_j2_pipeline.py tests/test_inline_catalog_required_fields.py

Feature: J2 在线编制目录（含国家扩展要素双轨）
  As a 部门操作员 ROLE_ORGAN_OPERATER（编目员）
  I want 在 P5 提供方管理页在线编制目录
  So that 不需要离开平台、不用 Excel 导入也能完成目录梳理

  Background:
    Given 单租户 sd-default 已初始化
    And CatalogModel 模板已预置（政务目录默认模板 + 国家扩展要素模板）
    And 我以 ROLE_ORGAN_OPERATER 登录，org_code=部门A_公安

  Scenario: 正向 — 在线编制政务目录（最常用路径）
    When 我在 P5 点击 "在线编制 → 新建目录"
    And 选择模板 "政务目录默认模板"
    And 填入基础元数据：名称 / 分类 / owner_org / 信息项清单
    And 点击 "保存为草稿"
    Then 创建 catalog C1001，status=0 草稿
    And catalog 不在 P2 检索结果中可见
    And 审计 capability_call=catalog.draft

  Scenario: 正向 — 反向编目（基于已有 schema 生成草稿）
    Given 我已上传库表 schema（CSV / DDL 形式）
    When 我点击 "反向编目"（供数首屏主卡入口，与 "在线编制目录" 并列，D57⑧ 同级展示）
    Then 系统解析 schema，自动生成信息项清单候选
    And 候选含字段名 / 类型 / 是否敏感等，**等待人工确认**（不自动入库）
    When 我修订并点击 "确认入库"
    Then catalog C1002 创建，status=0 草稿
    And 反向编目工具产生的 metadata 标记 origin=reverse-compile

  Scenario: 正向 — 反向编目两级审核（D57⑧：管理员部门审 → 业务运营员平台审）
    Given 反向编目草稿 C1002 处于 0 草稿（source=reverse）
    When 部门管理员在 "反向编目审核" 收件箱对 C1002 部门审 → 通过（字段口径裁决随部门审落账）
    Then C1002 进入平台待审 pending_platform_review，汇入正向 "目录审核" 平台档（不另造第二套审核状态机；命名与 "目录审核" 并存不撞名，D54 GATE-2）
    When 业务运营员在 "目录审核" 收件箱平台档对 C1002 审核 → 通过
    Then C1002 进入待发布队列，由业务运营员发布后 status=4
    And 平台审退回（return_for_fix）时 C1002 回 0 草稿、重新出现在 "反向编目审核" 收件箱（source=reverse ∧ draft 口径）

  Scenario: 负向 — 反向编目审核拒下放操作员（做的人不审自己，D57⑧）
    When 部门操作员尝试对反向编目草稿 confirm / reject
    Then 拒绝（AccessDenied），且 "反向编目审核" 收件箱入口对操作员不可见（无权=不可见）
    And 业务运营员不再持有 draft 阶段确认权（替换原仅 BUSIAUDIT 一级）；其落到反向编目审核路由时跳转 "目录审核" 收件箱（平台审对位下一站）

  Scenario: 正向 — 国家扩展要素目录双轨编制（基线 §3.3 双轨）
    When 我新建目录时选择模板 "国家扩展要素目录模板"
    Then 编制流程进入 data_ext_elem_catalog_compile_task 独立流程
    And 状态机与政务目录**独立**（双轨）
    And UI 明确提示 "本目录走国家通道编制路径，Wave 3 才能发布"
    And catalog 草稿存在但无法 advance 到发布（占位流程）

  Scenario: 正向 — 牵头部门审核（tag_lead_dept 标签位）
    Given 我以 ROLE_ORGAN_MANAGER + tag_lead_dept=true 登录
    When 一份 "基础主题分类关联" 目录草稿被某子部门提交
    Then 我在 P5 看到 "基础主题分类审核" 入口（仅本标签持有人可见）
    When 我点击审核 → 通过
    Then 目录进入 1 待审 → 部门正常审批流
    And 牵头部门审核记录写入审计

  Scenario: 负向 — 不能在他人 org 下编制目录
    When 我尝试创建 catalog 时改 owner_org_code=部门B
    Then 拒绝
    And R11：方向由 actor.current_org_code 决定

  Scenario: 负向 — 基本信息必填项不全不能提交审核（0611 口径确认单 §A，2026-06-12 确认）
    When 我尝试 "提交审核" 但 数据资源分类 / 来源系统 / 所属领域 / 应用场景 / 数据资源摘要 等必填项未填
    Then 拒绝 + 中文提示列出具体缺失的必填项名
    And 共享类型为 "有条件共享" 时 共享条件 同为必填（其余共享类型选填）
    And 内部部门 为选填，不出现在缺失清单
    And 存量导入目录（非在线编制新铸）不回溯此校验，流转不受影响
    And catalog 仍处于 0 草稿

  Scenario: 回归 — 编制阶段不发布到 P2（基线 §3.3 6 态约束）
    Then catalog.status 在 0 草稿 / 1 待审 / 3 驳回 中**不**在 P2 资源发现页可见
    And 仅 status=4 发布后才进入 P2 检索结果

  Scenario: 回归 — 工程术语黑名单（R12）+ 草稿持续可恢复
    Then 编制页面不出现 "package" / "projection" 等工程术语
    And 任何时刻 P5 刷新草稿都能完整恢复（无意外丢字段）
