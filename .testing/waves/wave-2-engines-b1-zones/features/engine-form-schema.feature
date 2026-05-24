# Wave: 2
# Journey: Cross (B1.2 → J1)
# Pages: B1.2 (配置) / J1 P3 (运行时)
# Consumer-faces: WebUI
# Roles: ROLE_SYSTEM | ROLE_BUSIAUDIT
# Trace: R8 / R14, 基线 §10.3 表单 schema 化引擎, 业务反馈 #17 (四川 / 荆州都改表单)
# Priority: P1
# Status: InTest
# Unfreeze-Note: PR #92 (2026-06-X) — Wave-2 三引擎落地：表单 schema 化引擎 + NL 起草。
#   pytest:
#     tests/integration/test_form_schema_engine.py   — form_schema commit / promote / revert + field/validation/layout 校验
#     tests/integration/test_form_schema_nl_draft.py — NL → form schema 起草路径
#     tests/integration/test_wave2_three_engines_acceptance.py — 三引擎端到端 acceptance
#   (注：业务反馈 #17 四川/荆州都改表单，由 schema 配置驱动，无需改代码 / 改库)

Feature: 三引擎 #2 — 表单 schema 化引擎
  As a 平台运维员
  I want 配置项目级申请表单（字段、校验、布局）而不改代码 / 改库
  So that 四川 / 荆州等项目改表单不需要发版

  Background:
    Given 默认表单 schema 已内置（含 数据用途 / 业务系统 / 办事场景 / 使用期限 / 附件 等基础字段）
    And 我以 ROLE_SYSTEM 登录，进入 B1.2 → 表单 schema 编辑器

  Scenario: 正向 — 增加项目特定字段
    When 我加入字段 "省厅项目编号"，type=text，校验=正则 ^SC\d{8}$，必填=true，分组="基础信息"
    And 点击 "预览"
    Then 渲染出申请表单含新字段
    And 校验规则在表单内生效（输入不符正则提示错误）
    When 我点击 "确认入库 + 生效到 project=sichuan"
    Then form_schema_def 写入 + scope=sichuan
    And sichuan 项目下的 J1 P3 申请表单包含该字段
    And 其他 project 不受影响

  Scenario: 正向 — 修改字段布局 / 分组
    When 我把"使用期限"从"基础信息"组移到"使用方信息"组
    Then 预览中字段位置变化
    And **不**触发数据迁移（表单 schema 只控渲染 + 校验，不改 application 表）

  Scenario: 正向 — 自然语言生成字段定义（R14 AI 落点）
    When 我输入 "加一个字段叫'数据接入业务模块编号'，是 8 位数字"
    Then AI 助手生成草稿字段：name="data_module_no"，type="number"，pattern="^\d{8}$"
    And 草稿仅显示，**不入库**
    When 我点击 "采纳 + 确认入库"
    Then 字段生效

  Scenario: 负向 — 字段名 / 校验规则冲突时拦截
    Given 已有字段 "省厅项目编号"
    When 我尝试再添加同名字段
    Then 拒绝 + UI 提示冲突
    And **不**入库

  Scenario: 负向 — 表单字段不能与 R12 工程术语黑名单冲突
    When 我尝试加字段 name="capability_id"
    Then 拒绝
    And UI 提示 "字段名不能使用工程术语"（R12）

  Scenario: 负向 — 必填字段后置变更不能影响在飞申请的已提交状态
    Given application A2001 已提交，使用 schema vX
    When 我把字段 X 从可选改为必填，发布 schema vX+1
    Then A2001 不被强制补字段
    And A2001 显示按 vX 的字段集；后续重新提交按 vX+1
    And 审计 schema_version 字段可追溯

  Scenario: 回归 — 表单 schema 是声明式数据，不是 JS / 代码
    Then form_schema_def.payload 内只能含 schema 定义 (JSON schema 风格)
    And 不允许出现 JavaScript 表达式 / Python eval / 任意可执行代码
    And 入库前 schema 经过白名单校验
