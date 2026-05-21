# Wave: 2
# Journey: J1
# Pages: P2 / P3
# Consumer-faces: WebUI
# Roles: ROLE_ORGAN_OPERATER
# Trace: R14, 基线 §10.3 智能推荐前置, 业务反馈 #6 (一开始不确定要哪些目录时应有推荐)
# Priority: P1
# Status: Draft

Feature: 三引擎 #3 — 智能推荐前置
  As a 部门操作员（潜在申请人）
  I want 在不确定要哪份数据时，得到基于"我类似需求"的目录推荐
  So that 不再走"线下问 → 平台没有 → 提需求登记"长链路

  Background:
    Given 申请历史已积累至少 100 条（含资源 + 用途 + 部门）
    And J2 资源元数据已注入（catalog / shared_type / 部门标签）
    And 我以 ROLE_ORGAN_OPERATER (新部门 X) 登录

  Scenario: 正向 — 自然语言描述需求，得到推荐
    When 我在 P2 输入 "我想做一个'省内人员就业流动'分析"
    Then AI 推荐引擎返回：
      | 推荐目录 | 推荐理由                          | 命中相似申请数 |
      | C_2401  | 人社部 - 就业登记表                | 8             |
      | C_2402  | 民政部 - 户籍迁移记录              | 5             |
      | C_2403  | 公安部 - 户籍信息（用作交叉验证）   | 3             |
    And 推荐理由含证据（命中相似申请数 + catalog 元数据匹配维度）
    And 推荐结果按相似度排序

  Scenario: 正向 — 推荐结果可直接发起申请
    When 我对 C_2401 点击 "用此推荐发起申请"
    Then 跳转 J1 P3 申请草稿页，资源 C_2401 自动填入
    And 草稿带追溯标记 "来自推荐 + 推荐 ID + 输入语义摘要"

  Scenario: 正向 — 推荐失败 → 转人工需求登记（基线 §10.3 设计意图）
    When 我输入 "我想要 跨部门税务 - 物业的关联分析"
    And 推荐引擎找不到相似匹配
    Then UI 显示 "未找到匹配目录，是否登记需求？"
    When 我点击 "登记需求"
    Then 创建 BusinessRequirement，自动归入 BUSIAUDIT 供需对接队列
    And 我的输入语义摘要作为需求背景

  Scenario: 负向 — 推荐不能跨部门暴露 shared_type=3 不予共享资源
    Given 部门Z 的 catalog C_2499 shared_type=3 不予共享
    When 我（部门A 用户）输入需求触发推荐
    Then 推荐结果不含 C_2499
    And 推荐引擎的相似申请数仅来自 J1 已授权样本
    And 注：跨租户（不同 tenant_id）推荐隔离回归见 wave-3-protocol-tenant-national/features/multi-tenant-policy.feature

  Scenario: 负向 — 推荐结果不能绕过 J1 主流程
    When AI 推荐看似确定性高的资源 C_2401
    Then UI **不**直接为我提交申请
    And 我必须主动点击"用此推荐发起申请"才进入 J1 P3
    And 一票否决：AI 推荐不直接触发写操作（§5.4.5）

  Scenario: 负向 — 推荐引擎不可达时主任务降级
    Given 推理 gateway 不可达 60s
    When 我输入需求
    Then UI 显示 "AI 推荐暂不可用"
    And 主检索框 / 目录树**仍可独立用**
    And 触发主任务降级路径（见 infra-inference-gateway.feature）

  Scenario: 回归 — 推荐质量随历史申请数增长（不是凭空构造）
    Then 推荐结果可追溯到具体历史申请 + catalog 元数据
    And 0 历史申请数时不返回推荐（不假装智能）
    And 推荐覆盖率与历史数据量正相关
