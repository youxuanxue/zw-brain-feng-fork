# Wave: 0
# Journey: Cross
# Pages: None (infrastructure)
# Consumer-faces: All
# Roles: All
# Trace: D4 / R4 / 基线 §2.3 合规内建 / §10.1
# Priority: P0
# Owner: e4
# Pytest: tests/test_wave0_infra.py
# InTest-Scope: tests/test_wave0_infra.py 覆盖 D4 核心判据 5 项（写入失败熔断 raise / 未配置 sink raise /
#   必填字段缺失 raise / 成功落 sink + 缓冲 / 区块链锚定异步 outbox 表结构）；
#   audit_event 12 富字段 + actor_role 7 角色码 CHECK 约束属富 schema 目标态（富字段现落 capability_call 表），
#   字段集对齐归 W0-07/Wave1 审计富化。

Feature: Infra — 审计总线同步落库 + 写入失败熔断
  As a 平台架构师
  I want 所有写操作必须先成功写审计，再继续业务流程
  So that 政务场景的"写操作可审计、可回放、可追责"硬约束不被悄悄丢失

  Background:
    Given audit_event 表已建
    And Capability `application.submit` audit_class=write-critical

  Scenario: 正向 — write-critical 操作同步落审计后才提交业务事务
    When 用户提交申请 A201
    Then 系统按顺序执行：
      | 步骤                  | 状态                              |
      | 1. 写 audit_event     | success（同一事务）                |
      | 2. 写 application 表  | success                          |
      | 3. 返回 HTTP 200       | success                          |
    And 失败发生在步骤 1 时，步骤 2/3 不执行
    And application 表与 audit_event 表事务一致

  Scenario: 正向 — audit_event 字段齐全
    When 提交 A201 触发审计写入
    Then audit_event 一条记录包含：
      | 字段                | 必填 | 说明                            |
      | event_id            | Y   | 唯一                             |
      | tenant_id           | Y   | sd-default                       |
      | actor_id            | Y   | 用户 IAM sub                     |
      | actor_org_code      | Y   | 当前部门                          |
      | actor_role          | Y   | ROLE_* 枚举                      |
      | capability_call     | Y   | application.submit               |
      | audit_class         | Y   | write-critical / write / read / read-sensitive |
      | resource_ref        | Y   | application_id / catalog_id 等  |
      | request_id          | Y   | 用于回放                          |
      | occurred_at         | Y   | UTC timestamp                    |
      | result              | Y   | success / reject / error         |
      | reason              | N   | reject/error 必填                |

  Scenario: 负向 — 审计写入失败必须熔断业务（D4）
    Given audit_event 表 mock 抛出 IntegrityError
    When 用户尝试提交 A201
    Then HTTP 返回 5xx
    And application 表**未**新增记录
    And 终端 / 监控看到 "audit_bus_write_failed" 告警
    And **不允许**"审计失败但业务继续"的静默降级路径

  Scenario: 负向 — 区块链锚定外链 down **不阻塞**业务（D4 异步可插拔）
    Given audit_event 表写入正常
    And 区块链 adapter 调用 mock 抛 ConnectionError
    When 用户提交 A201
    Then HTTP 返回 200（业务继续）
    And audit_event 表写入正常
    And 区块链锚定进入异步重试队列（不在同事务内）
    And 监控看到 "blockchain_anchor_retry" 计数

  Scenario: 负向 — 跨 Capability 调用必须各自落审计
    When 一次 HTTP 请求触发：application.submit → 内部调 catalog.read → 内部调 user.check_permission
    Then audit_event 表生成 3 条记录
    And 3 条记录通过 request_id 关联

  Scenario: 回归 — read 类 Capability 落审计但不阻塞
    Given Capability `resource.search` audit_class=read
    When 用户搜索 100 次
    Then audit_event 表新增 100 条 read 类记录
    And read 类记录的写入失败**可以**降级（不熔断业务）
    And 失败降级也要发监控告警（不静默吞错）

  Scenario: 回归 — actor_role 必须用 7 角色码（R10）
    Then audit_event.actor_role 字段值必须属于：
      | ROLE_SYSTEM | ROLE_BUSIAUDIT | ROLE_ORGAN_MANAGER | ROLE_ORGAN_OPERATER | ROLE_SECURITY_ADMIN | ROLE_SECURITY_AUDIT |
    And 任何 r1-r8 字面值写入被 CHECK 约束拒绝
