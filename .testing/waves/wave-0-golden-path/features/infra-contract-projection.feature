# Wave: 0
# Journey: Cross
# Pages: None (infrastructure)
# Consumer-faces: WebUI | API | CLI | MCP | A2A
# Roles: All
# Trace: R3 / R6 / 基线 §6 统一能力契约 / §10.1
# Priority: P0
# Status: InTest
# InTest-Scope: tests/test_wave0_infra.py 数据层覆盖 4 项（J1 skill 五面 slug 一致 / input_schema 单一源 /
#   export_agent_contract.py --check 无 drift / 单一 capability registry 目录）；
#   human_confirmation 五面统一标注的 WebUI 二次弹窗渲染归 W0-07 浏览器侧。

Feature: Infra — 单一能力契约 → 五消费面投影一致性
  As a 平台架构师 / Wave 0 守门人
  I want 同一 Capability 在 WebUI / API / CLI / MCP / A2A 五消费面投影一致
  So that 任何一处投影变更必须回头改 registry，不允许五处手维护

  Background:
    Given Capability registry 已初始化
    And 三类 P0 Capability 已注册：resource.search / application.submit / credential.view

  Scenario: 正向 — Capability slug 在五消费面命名一致
    When 我导出 WebUI 路由表 / OpenAPI / CLI commands / MCP tool manifest / A2A agent card
    Then 五份导出文件中**同一业务能力**指向同一 capability slug
      | face   | 标识例                              |
      | WebUI  | route 标签 capability=resource.search |
      | API    | OpenAPI x-capability=resource.search   |
      | CLI    | resource search ...                    |
      | MCP    | tool.name=resource.search              |
      | A2A    | skill.id=resource.search               |

  Scenario: 正向 — input_schema / output_schema 跨消费面 schema 一致
    Given Capability `application.submit` 已定义 input_schema 含 resource_id / purpose / period
    When 我对比 WebUI 表单字段 / OpenAPI request schema / CLI flag 列表 / MCP input / A2A skill input
    Then 字段集合完全一致（顺序可不同）
    And 必填标记一致
    And 字段类型一致

  Scenario: 正向 — 同一契约改字段，五消费面同步生效
    When 我在 contract 增加可选字段 evidence_file
    And 重跑契约生成器
    Then 五消费面的 schema 都新增了 evidence_file 字段（无需手改）

  Scenario: 负向 — 任意消费面手维护引发 drift 必须被拦截
    When 我尝试在 OpenAPI 手动加一个 capability=foo.bar，但 registry 中无此 capability
    Then `export_agent_contract.py --check` 失败
    And 失败信息明确指出 drift 来源 (file + line)

  Scenario: 负向 — Capability `human_confirmation_required=true` 在五消费面统一标注
    Given Capability `application.submit` human_confirmation_required=true
    Then WebUI 提交按钮带"确认"二次弹窗
    And API OpenAPI 标 x-requires-confirmation=true
    And CLI 默认进入交互确认，必须显式 --yes 绕过
    And MCP tool 描述含 "Requires user confirmation"
    And A2A skill metadata.requires_confirmation=true

  Scenario: 负向 — exposure 字段裁剪生效
    Given Capability `admin.runtime` exposure=["webui","cli"]（不暴露 API/MCP/A2A）
    When 我在 OpenAPI / MCP manifest / A2A card 查找 admin.runtime
    Then 三处都查不到
    And WebUI 与 CLI 中正常可见

  Scenario: 回归 — registry 是单一事实源（OPC 模式约束）
    Then 仓库中**仅有一个**目录用于定义 Capability（zw_brain/skill_registration/registered/*.json）
    And 任何 entry/*/ 下的 schema 文件都应由生成器输出，不在 git 历史中手编辑
    And preflight 段对 entry/*/ 下手编辑做反向探测
