# Wave: 2
# Journey: J1 (基层补差路径)
# Pages: P3 (申请草稿 + 预填)
# Consumer-faces: WebUI | API
# Roles: ROLE_ORGAN_OPERATER (基层归口)
# Trace: 基线 §3.4 C 一表通边界 + research-yibiaotong.md, project_integration_yibiaotong_bridge (memory)
# Priority: P2
# Status: Draft

Feature: 一表通可选预填 adapter（基层补差任务出现时）
  As a 部门操作员（基层归口）
  I want 当上级派发了一表通补差任务给我时，新建申请草稿能自动预填来自一表通的字段
  So that 不需要在 zw-brain 和一表通之间来回切

  Background:
    Given 一表通对接配置已就绪（adapter mode = "可选预填"）
    And 我以 ROLE_ORGAN_OPERATER 登录，属于基层归口部门（如镇街）
    And 上级派发了一份补差任务 T_5101，关联一表通数据项 X / Y / Z

  Scenario: 正向 — 接到补差任务后，申请草稿自动预填
    When 我打开 T_5101 任务详情
    And 点击 "为此任务发起申请"
    Then P3 申请草稿打开
    And 字段 X / Y / Z 由一表通 adapter 自动预填
    And 预填字段标记 "来自一表通"（可见来源）
    And 我可修改预填值（不是只读）

  Scenario: 正向 — 没有补差任务时，adapter 不出现
    Given 我以普通 ROLE_ORGAN_OPERATER 登录（非基层归口或无 T 任务）
    When 我打开 P3 新建申请草稿
    Then 一表通 adapter **不**出现
    And UI 上无"来自一表通"标记
    And 立项会议 R7 / 一表通"降级为可选预填"决策生效（基线 §3.4 C）

  Scenario: 正向 — 一表通服务不可达时降级
    Given 一表通服务 timeout / 5xx
    When 我打开补差任务的申请草稿页
    Then UI 显示 "一表通暂时不可达，可手动填写"
    And 主任务**仍可独立完成**（一票否决，§5.4.5 AI 不夺权同理）

  Scenario: 负向 — adapter 不能成为新的写入口（基线 §9.5 adapter 规则）
    When 业务代码尝试通过 adapter 写回一表通数据
    Then 拒绝
    And 任何对一表通的写动作只能走一表通自己的入口
    And zw-brain 是只读消费者

  Scenario: 负向 — adapter 不能跨租户预填
    Given 一表通返回 other-province 的数据
    When zw-brain adapter 读取
    Then 数据被 tenant filter 过滤掉
    And 申请草稿不预填 other-province 数据

  Scenario: 回归 — adapter 不进 J1/J2 主链路硬依赖
    Then J1/J2 主链路在一表通完全不可用时仍能完成所有 happy path
    And adapter 是"减摩"组件，不是"必备"组件（基线 §3.4 C 决策）
    And 客户上线时若不需要基层补差路径，adapter 可关闭，不影响主旅程
