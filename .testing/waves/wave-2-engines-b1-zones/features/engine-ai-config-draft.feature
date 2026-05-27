# Wave: 2
# Journey: Cross (三引擎共享反约束)
# Pages: B1.2
# Consumer-faces: WebUI
# Roles: ROLE_SYSTEM | ROLE_BUSIAUDIT
# Trace: R14, 基线 §4.4 第 4 类 AI 配置生成, §5.4.4 P3/B1.2 反约束, §10.3
# Priority: P1
# Status: Draft
# Owner: e3
# Pytest: tests/integration/test_wave2_three_engines_acceptance.py
# Twin-F: e3.F3 + e3.F5

Feature: 三引擎共享 — AI 配置草稿生成 (草稿 → 预览 → 确认入库)
  As a 平台运维员 / 业务运营员
  I want 任意三引擎配置（流程 / 表单 / 推荐规则）都走"AI 草稿 → 结构化预览 → 管理员确认入库"三步
  So that AI 不直接修改生产配置，但能减少 SQL / JSON / 代码改动摩擦

  Background:
    Given 我以 ROLE_SYSTEM 登录，进入 B1.2 任意一个引擎编辑器

  Scenario: 正向 — 三引擎共享的草稿 → 预览 → 入库流程
    When 我输入自然语言需求
    Then AI 助手生成 schema 草稿
    And 草稿展示在编辑器画布上，**带"待入库"标签**
    When 我点击"预览"
    Then 显示运行时模拟器 / mock 渲染（流程引擎是节点跑通；表单引擎是字段渲染；推荐引擎是输入 + 输出对照）
    And 预览**不**改生产数据
    When 我点击"确认入库 + 生效到 scope=XX"
    Then 写入对应 *_def 表
    And 审计 capability_call=<engine>.config_change, audit_class=write-critical
    And 入库前的草稿状态可在编辑器历史中查询

  Scenario: 正向 — 草稿与生效隔离（config_change_class 字段）
    Given Capability 契约层新增 config_change_class 字段（基线 附录 C R14 / Wave 2）
    Then 字段可选值：
      | live      | 直接生效（仅基础设施级，禁止用户配置）  |
      | preview   | 仅预览，不入库                       |
      | draft     | 草稿，可入库但未生效                 |
    And 三引擎所有用户操作必须经 draft / preview，禁止 live

  Scenario: 负向 — 跳过"确认入库"直接生效被拒
    When 我尝试通过 API 把 form_schema_def.status=active，跳过 preview 步骤
    Then 拒绝
    And 错误信息明示 "必须经过 preview 状态"

  Scenario: 负向 — AI 草稿不能含可执行代码 / 直连第三方 API
    When AI 助手生成的草稿含 JavaScript / Python eval / openai.com URL
    Then 入库前白名单校验拦截
    And 错误信息明示哪一条违规

  Scenario: 负向 — 跨 scope 误覆盖防护
    Given form_schema vX 已生效于 project=sichuan
    When 我尝试入库 vX+1 但忘了选 scope
    Then 拒绝（必填字段）
    And **不**误生效到所有 project

  Scenario: 回归 — AI 草稿的证据可追溯
    Then 任意 AI 草稿生成事件都记录：actor / inputprompt / inference_id / generated_at / inference_model
    And 入库后写入审计 metadata，便于事后回放
    And 一票否决：AI 草稿不替代管理员判断（§5.4.5）
