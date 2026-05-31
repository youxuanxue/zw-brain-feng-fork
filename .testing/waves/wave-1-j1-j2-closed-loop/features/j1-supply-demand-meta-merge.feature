# Wave: 1
# Journey: J1
# Pages: P3 (供需对接段)
# Consumer-faces: WebUI
# Roles: ROLE_BUSIAUDIT (主管部门需求汇总)
# Trace: 基线 §3.2 供需对接 36 页, §10.2 (供需对接子流程，meta 合并非数据合并)
# Priority: P1
# Owner: e1
# Pytest: tests/test_wave1_j1_supply_demand.py

Feature: J1 供需对接子流程（meta 合并 6 步）
  As a 业务运营员 ROLE_BUSIAUDIT（主管部门）
  I want 把多部门相似需求合并后统一对提供方发起
  So that 不让同一提供方部门被 10 个不同部门重复打扰

  Background:
    Given 单租户 sd-default 已初始化
    And 申请单 A101 / A102 / A103 由 部门A / 部门B / 部门C 分别提交，都对 C700 户籍数据有相似申请用途
    And 我以 ROLE_BUSIAUDIT 登录

  Scenario: 正向 — 6 步供需对接流程（meta 合并）
    When 我在 P3 供需对接段打开"待汇总申请"列表
    Then 系统按相似度（资源 + 用途 + 时间窗）聚类
    And A101 / A102 / A103 同一簇
    When 我点击 "原始需求梳理" → 选择 A101/A102/A103 → 点击"合并为业务需求"
    Then 创建 BusinessRequirement BR701，含 3 个原始申请引用
    And **不**复制申请数据；BR701 仅持 meta（引用 + 合并理由）
    When 我点击 "业务需求清单 → 发布工作任务" → 工作任务 T701 派发给提供方部门 C
    Then T701 状态=已派发，关联 BR701
    When 提供方处理完成 T701 → 通知 BUSIAUDIT 反馈
    Then BR701 status=已反馈
    When BUSIAUDIT 对反馈做评价
    Then BR701 status=已评价（最后一步）
    And 三个原始 application 各自的 status 不被合并改写

  Scenario: 负向 — 申请人本人不能合并申请（防止申请方串谋）
    When ROLE_ORGAN_OPERATER 尝试访问 "原始需求梳理" 操作
    Then 拒绝
    And 仅 BUSIAUDIT 可访问

  Scenario: 负向 — 合并不复制具体数据（meta 合并 = 元数据合并）
    Given 合并 A101 / A102 / A103
    Then BR701.payload 中不含申请单 A* 的 purpose / period / files 等业务字段拷贝
    And BR701 仅含 application_id 列表 + 合并理由 + 时间戳
    And 任意 A* 改动不引起 BR701 数据 drift

  Scenario: 负向 — 合并后撤销其中一个原始申请，BR701 自动剔除
    When A102 被申请人撤回
    Then BR701.application_ids 自动剔除 A102
    And BR701 留下事件记录 "A102 已撤回 at <time>"

  Scenario: 正向 — 国家通道占位（基线 §10.4 Wave 3 延后）
    Given 部门 X 提交 "需求 - 国家直达"
    Then 该需求自动归入 "国家通道" 类别
    And Wave 1 不实现国家直达完整流程；仅在 UI 留占位提示 "本期不支持国家通道，请联系运维"
    And 业务方 R13 sign-off 后才能进 Wave 3 实施

  Scenario: 回归 — 供需对接不是申请审批的替代
    Then BR701 处理路径**不影响** A101 / A102 / A103 各自的审批状态机
    And 申请单审批仍按 J1 主链路 5 节点进行
    And 供需对接是"主管部门让数据生态健康运作"的补充面
