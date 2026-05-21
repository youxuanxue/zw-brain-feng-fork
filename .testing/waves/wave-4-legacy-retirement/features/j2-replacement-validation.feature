# Wave: 4
# Journey: J2
# Pages: P5
# Consumer-faces: All
# Roles: ORGAN_OPERATER / ORGAN_MANAGER / BUSIAUDIT
# Trace: 基线 §1.5 成功标准, §10.5 退役判据
# Priority: P0
# Status: Draft

Feature: J2 替代验证（90 天真实编目 + 发布）
  As a 客户成功 / 产品负责人
  I want 用 90 天真实编目数据验证 J2 已稳定替代 legacy
  So that 可以下达 legacy J2 退役决定

  Background:
    Given 客户已正式上线 90 天

  Scenario: 正向 — 每周新目录发布数达标
    Then 最近 90 天每周**至少** 3 次新 catalog 发布（status=4）
    And 涉及 owner_org_code 覆盖 ≥10 个部门
    And 含 3 种物化形式（table / file / api）至少各 1 例

  Scenario: 正向 — 部门内审 → 平台复核 全链路成功率
    Then 进入 1 待审 的 catalog 中 ≥80% 在 7 天内进入 4 发布 或 3 驳回
    And 平均流转时长可基线化

  Scenario: 正向 — 反向编目使用率
    Given 反向编目工具已上线
    Then 反向编目产生的 catalog 草稿占总草稿 ≥30%（说明工具被真实使用）

  Scenario: 正向 — 牵头部门标签真实使用（tag_lead_dept）
    Then 至少 5 例 "基础主题分类审核" 由 tag_lead_dept=true 的 ORGAN_MANAGER 处理
    And 牵头标签**不**触发独立角色码（R10 / R11）

  Scenario: 负向 — 重复率检测提醒**不**变成硬拦
    Then 重复率提醒过的 catalog 中**仍有**部分发布（说明软提醒不阻业务）
    And 未发布的有明确原因记录

  Scenario: 回归 — J2 状态机迁移完整覆盖
    Then 6 态 catalog（0/1/2/3/4/5）所有合法迁移路径都至少跑过 5 次
    And 非法迁移触发 audit reject 累计 0 例
