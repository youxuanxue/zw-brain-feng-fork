# Wave: 4
# Journey: Cross
# Pages: None
# Consumer-faces: legacy 系统接口
# Roles: ROLE_SYSTEM
# Trace: 基线 §10.5 退役判据 #4 "legacy 是否仍承担唯一写入口"
# Priority: P0
# Owner: e6
# Pytest: pending

Feature: legacy 写入口关闭
  As a 平台运维员
  I want 关闭 legacy 的写入口（仅保留只读窗口或全部下线）
  So that legacy 不再是任何业务实体的唯一 source of truth

  Background:
    Given 客户已上线 90 天 + J1/J2 替代验证已通过
    And legacy 平台在以下入口曾承担写：
      - legacy 门户：申请提交 / 目录编制 / 资源挂接 / 异议提交
      - legacy API：第三方系统的提交接口
      - legacy 数据库：直接 SQL 写入（非常规）

  Scenario: 正向 — legacy 门户写入口关闭
    When 我对 legacy 门户做"只读" 切换
    Then 申请提交按钮置灰，提示 "请到 zw-brain 提交"
    And 目录编制按钮置灰
    And 资源挂接按钮置灰
    And 异议提交按钮置灰
    And 普通用户登录 legacy 看到"系统已退役" banner

  Scenario: 正向 — legacy API 写入口关闭
    When 我关闭 legacy 写 API
    Then 任意 POST/PUT/DELETE 返回 410 Gone + 引导到 zw-brain API
    And 读 API 仍开放（兼容历史报表）

  Scenario: 正向 — legacy 数据库写访问关闭
    When 我把 legacy DB 用户权限改为只读
    Then 任意非选择语句执行失败
    And legacy 自身的报表 / 历史查询仍可工作

  Scenario: 负向 — 关闭过程中数据写发生在 zw-brain 而非 legacy
    Given 切换窗口 = 凌晨 2 点
    When 切换窗口期内有用户尝试提交申请
    Then 申请落到 zw-brain，**不**落到 legacy
    And 切换窗口期审计完整（任何"被拒"请求记录）

  Scenario: 负向 — 唯一性验证（没有遗漏写入口）
    Then 客户运维做"全网 grep" 验证：
      - legacy 应用代码中所有 INSERT/UPDATE/DELETE 业务实体的入口都已关闭
      - 没有"灰色"任务定时 cron 仍在写 legacy 业务表
      - 没有第三方系统仍在通过 legacy API 写
    And 任意遗漏入口由 SECURITY_AUDIT review + 业务方 sign-off 后才能关闭

  Scenario: 回归 — 关闭可回滚（应急路径）
    Given 关闭后第 7 天发现客户某项 P1 缺失
    Then 可临时开启 legacy 读窗口（不开写）
    And 待 zw-brain 补完该项再彻底关闭
    And 不允许"应急再开 legacy 写"（避免双写漂移）
