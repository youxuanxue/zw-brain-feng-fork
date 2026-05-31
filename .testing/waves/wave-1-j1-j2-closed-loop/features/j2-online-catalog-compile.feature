# Wave: 1
# Journey: J2
# Pages: P5
# Consumer-faces: WebUI
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER (含 tag_lead_dept — 牵头标签依附 MANAGER，per docs/approved/zw-brain-roles.md §三)
# Trace: 基线 §3.2 目录管理 23 页, §3.3 CatalogModel 双轨编制, §10.2 J2 在线编制, 旧 xlsx 行 [35..38] 反向编目+在线编制+导入+编辑 (45-53 国家目录治理 ⏸ Wave 3)
# Priority: P1
# Owner: e2
# Pytest: tests/test_wave1_j2_pipeline.py

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
    When 我点击 "反向编目"
    Then 系统解析 schema，自动生成信息项清单候选
    And 候选含字段名 / 类型 / 是否敏感等，**等待人工确认**（不自动入库）
    When 我修订并点击 "确认入库"
    Then catalog C1002 创建，status=0 草稿
    And 反向编目工具产生的 metadata 标记 origin=reverse-compile

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

  Scenario: 负向 — 草稿必填字段不全不能提交审核
    When 我尝试 "提交审核" 但 信息项清单为空
    Then 拒绝 + UI 列出具体缺字段
    And catalog 仍处于 0 草稿

  Scenario: 回归 — 编制阶段不发布到 P2（基线 §3.3 6 态约束）
    Then catalog.status 在 0 草稿 / 1 待审 / 3 驳回 中**不**在 P2 资源发现页可见
    And 仅 status=4 发布后才进入 P2 检索结果

  Scenario: 回归 — 工程术语黑名单（R12）+ 草稿持续可恢复
    Then 编制页面不出现 "package" / "projection" 等工程术语
    And 任何时刻 P5 刷新草稿都能完整恢复（无意外丢字段）
