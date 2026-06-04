# Wave: 1
# Journey: J1 (办共享申请 — 角色投影 + 数据呈现规范化)
# Pages: P1 | P3 | P5
# Consumer-faces: WebUI
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER | ROLE_BUSIAUDIT | ROLE_SECURITY_AUDIT
# Trace: 基线 §六 角色≠方向, D23 (7 角色码 + tag_lead_dept), D28 (角色/流程/状态机须业务方 sign-off), D47 (凭据诚实化)
# Priority: P0
# Owner: e5
# Pytest: tests/e2e/role_projection_views.spec.ts

Feature: 办共享申请按岗位投影三视图 + 真实导入数据呈现规范化
  As a 政务数据使用者（部门操作员 / 部门管理员 / 业务运营员）
  I want 「办共享申请」按我的当前岗位拆成清晰视图，且真实导入单的脏数据不裸奔
  So that 一个视图只回答一个问题，我不再在一锅炖的列表里分不清「我的申请 / 待我办 / 我的授权」

  # 客户试用反馈（0604，业务方试用反馈 + 截图实证）：
  #   缺陷 1（反馈 14）：「是看我的已办？还是我的申请？我的授权，里面的数据没分角色，建议分开」
  #   缺陷 2（反馈 11 部分）：业务运营员待办「不对路」——应是待发布目录/待发布资源/待受理申请
  #   缺陷 3（截图横切）：用途列「测试」「167」脏值裸奔；历史导入单与在产单无区分

  Background:
    Given 单租户 sd-default 已装载真实库数据（含旧平台历史导入申请单）
    And 顶栏展示当前岗位（useProductRole），dev bypass 下可切换
    And 角色投影源 = zw-brain-web/src/lib/{roleProjection,roleTodoRegistry,dataQuality}.ts
    And 后端诚实信号源 = zw_brain/domain/{data_quality,discovery_snapshot_projection,provider_snapshot_projection}.py

  Scenario: 缺陷1 — 三视图拆分（我的申请 / 待我办理 / 我的授权）
    Given 用户进入「办共享申请」P3
    Then 「我的申请」「我的授权」两视图对所有岗位恒在
    And 「待我办理」仅对有审批/复核队列的岗位（部门管理员 / 业务运营员）渲染
    And 纯需方岗位（部门操作员）的「待我办理」入口完全不在 DOM（无权=不可见）
    And 每个视图只回答一个问题（我发起的 / 该我办的 / 我已获授权的）

  Scenario: 缺陷2 — 业务运营员待办语义正确（数据驱动注册表）
    Given 用户顶栏岗位为业务运营员 ROLE_BUSIAUDIT
    When 打开工作台 P1
    Then 待办类目来自角色待办注册表（roleTodoRegistry，数据驱动非散落 if-else）
    And 待办落在「待受理 / 待发布目录 / 待发布资源 / 数据质量」语义内
    And 不出现与该岗位不相关的错配内容（如能力包审核类）
    And 每类待办给出标题（政务白话）+ 真实库现算计数 + 深链目标

  Scenario: 缺陷3 — 脏用途值不裸奔（降级 + 供方质量队列）
    Given 真实导入单的用途列存在脏值（「测试」「167」「169,167」「空」）
    When 需方在「我的申请」查看列表
    Then 用途列脏值降级显示「未填写用途」次要样式，原始脏串不出现在用途列
    And 脏值判定走机械化分类器（data_quality 单源 + dataQuality.ts 镜像）
    And 「用途缺失/无效」的单子计入供方数据质量队列（业务运营员待办，非需方噪音）
    And 供方数据质量队列仅业务运营员可见（无权=不可见）

  Scenario: 缺陷3 — 历史导入单 vs 在产单克制区分（仅呈现层）
    Given 列表混有 2023-2025 历史导入单与在产单
    Then 列表给出次要标识「历史导入」/「在产」帮助用户理解来源
    And 来源信号取 payload source_ref / legacy_object_ref（诚实，不捏造）
    # D47.b：历史导入单在线动作混合门控是已记账债（债主负责），本组只做呈现层区分

  # 状态：本 feature 属角色/流程/状态机变更（D28），须业务方 sign-off 才翻 Done（D46）。
  # sign-off 包：docs/decisions/role-projection-views-business-review-package.md（pending，签字人=业务方试用代表）。
