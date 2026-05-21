# Wave: 1
# Journey: J2
# Pages: P5
# Consumer-faces: WebUI | CLI
# Roles: ROLE_ORGAN_OPERATER
# Trace: 基线 §3.3 3 物化形式 (data_resource_table / file / api), §10.2 J2 资源挂接, 旧 xlsx 行 [57..61] 资源注册 (库表/链接/文件/文件夹/库表-视图) + [66] 目录物化
# Priority: P1
# Status: Draft

Feature: J2 资源挂接（3 物化形式：table / file / api）
  As a 部门操作员 ROLE_ORGAN_OPERATER
  I want 将一份数据资源以 表 / 文件 / 接口 任一形式挂接到已发布目录下
  So that 申请人能通过 J1 路径获得该资源的具体数据

  Background:
    Given catalog C1101 已发布，owner_org_code=部门A_公安
    And 我以 ROLE_ORGAN_OPERATER (部门A) 登录

  Scenario: 正向 — 挂接库表资源（data_resource_table）
    When 我在 P5 资源管理 → "为 C1101 挂接资源" → 选择 "库表"
    And 填写：数据库连接 / 表名 / 字段映射（catalog 信息项 → 表字段）
    And 点击 "保存"
    Then 创建 resource R1101，materialization=table，status=待审
    And 自动校验数据库连接 + 字段类型一致性
    And UI 显示字段映射的完整性 ✓ / ✗

  Scenario: 正向 — 挂接接口资源（data_resource_api）
    When 我选择 "接口"
    And 填写：URL / method / 鉴权方式 / 请求样例 / 响应样例
    Then 创建 resource R1102，materialization=api
    And 自动 dry-run 接口一次，验证返回 schema 与 catalog 信息项一致
    And dry-run 失败时**仍允许保存草稿**，但提交审核被拦截

  Scenario: 正向 — 挂接文件资源（data_resource_file）
    When 我选择 "文件"
    And 上传文件 / 设置访问路径 / 描述更新频次
    Then 创建 resource R1103，materialization=file
    And 系统记录文件指纹（hash）用于后续完整性校验

  Scenario: 正向 — 同一目录可以挂接多个资源（不同物化形式）
    Given C1101 已挂接 R1101 (table) + R1102 (api)
    When 我再挂接 R1103 (file)
    Then 三个资源都关联到 C1101，互不冲突
    And 申请人在 P3 申请时可选择"用哪种物化形式"

  Scenario: 负向 — 不能为其他部门的 catalog 挂接资源
    Given catalog C1201 owner_org_code=部门B
    When 我（部门A）尝试为 C1201 挂接资源
    Then 拒绝
    And 审计 reject + reason="catalog.owner_org ≠ session.org"

  Scenario: 负向 — 字段映射缺失或类型冲突时提交被拦截
    When 我尝试提交 R1101 审核，但 catalog 信息项 "身份证号"未映射到任何表字段
    Then 拒绝
    And UI 列出未映射的具体信息项

  Scenario: 负向 — 挂接后不能在 J2 流程外直接改 owner_org_code（R11 边界）
    When 我尝试通过 API 直接 PATCH R1101.owner_org_code=部门C
    Then 拒绝
    And 任何 owner_org 迁移必须走目录迁移审核流程（基线 §九 ResourceAggregate 边界）

  Scenario: 回归 — 重复率检测提醒（不硬拦，基线 §5.2 P5 提示）
    Given 部门 B 在 1 个月内已发布过类似 catalog
    When 我新建相似 catalog（高重复率）并尝试挂接资源
    Then UI 显示橙色提示 "检测到 部门B 已有相似目录，是否复用？"
    And **不硬拦**提交（让人决定）
    And 决定不复用时审计记录 reason 便于后续审视
