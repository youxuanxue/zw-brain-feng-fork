# Wave: 0
# Journey: B1.1
# Pages: None (infrastructure / B1.1 only-read)
# Consumer-faces: WebUI | API | CLI | MCP | A2A
# Roles: ROLE_SYSTEM | ROLE_BUSIAUDIT
# Trace: D31 / D32 / 业务反馈 #PR129 / 基线 §3.4 / dsp-dataservice-reconstruction-plan-v1.md §3.4 / §3.5 / §六 Wave 0 / 旧 xlsx 行 [63..70]（A 类批次锚定，非业务面对照）
# Priority: P0
# Owner: e6
# Pytest: pending
# Deferred: 触发=首次真实生产部署 + 网关供 res→api_id 映射 + 真实 API 调用流量（同兄弟 j1-api-call-monitoring / D47.a 网关域缺供）→ service_invocation_metric_projection 派生场景非空可验。当前零真实 API 调用流量，派生器无可派生输入，规模前不抬状态（与 j1-api-call-monitoring 同一触发；debt ac7）

Feature: Wave 0 服务调用统计投影（ops.service.invocation.query）
  As a 平台守门人 / 运营审计 (ROLE_SYSTEM / ROLE_BUSIAUDIT)
  I want 旧 `/openapi/getServiceInvokedBySystemStatisticInfos`（173,072 次）以可重算运营投影承接
  So that 调用量、错误归因、延迟可在 zw-brain 中按服务 / 提供方 / 调用方 / 区划 / 时间维度回放，且不复刻旧服务统计后台

  Background:
    Given 单租户 sd-default 已初始化
    And 7 角色码 CHECK 约束已生效
    And 集团推理平台 gateway mock 已就绪（基线 §6 / D14）
    And 物理表 `service_invocation_metric_projection` 已通过 `Base.metadata.create_all` 建出（基线 §9.6 不进 alembic）
    And `service_invocation_metric_projection` UNIQUE (tenant_id, metric_scope, resource_id, provider_org_id, consumer_org_id, provider_region_code, consumer_region_code, bucket_granularity, time_bucket) + 多个 INDEX（plan §3.4 约束）
    And Capability `ops.service.invocation.query` 已注册（audit_class=read-trace；plan §3.5）
    And 资源种子已注入：resource_asset R201（resource_kind=api，owner_org=部门A_公安）；R201 通过 plan §3.5 已注册的 `resource.api.test` 暴露调用能力，capability_slug 不引入 per-resource 派生 slug（R3 / R8）
    And 单租户假设：跨租户隔离的回归用例见 wave-3-protocol-tenant-national/features/multi-tenant-policy.feature

  Scenario: 正向 — capability_call 触发后调用计数派生进 projection（运营运维派生 / 非业务面 xlsx 锚点）
    Given 不存在 (tenant_id="sd-default", metric_scope="service", resource_id="R201", time_bucket=T0, bucket_granularity="minute") 的投影记录
    When 在 T0 分钟内对 resource R201 通过 `resource.api.test` 发生 3 次成功调用 + 1 次提供方错误调用
    Then `service_invocation_metric_projection` 出现一条记录：
      | 字段                    | 期望                          |
      | tenant_id              | sd-default                    |
      | metric_scope           | service                       |
      | resource_id            | R201                          |
      | capability_slug        | resource.api.test             |
      | bucket_granularity     | minute                        |
      | time_bucket            | T0                            |
      | invoke_count           | 4                             |
      | success_count          | 3                             |
      | failed_count           | 1                             |
      | provider_error_count   | 1                             |
      | consumer_error_count   | 0                             |
      | gateway_error_count    | 0                             |
      | source_event_ref       | 形如 capability_call:* 或 audit_event:* |
    And `generated_at` 同步写入
    And 审计总线记录一条 `capability_call=ops.service.invocation.query`（当 B1.1 读侧查询时），`audit_class=read-trace`

  Scenario: 正向 — 同一数据可按 provider_org / consumer_org / provider_region / consumer_region 聚合维度重复派生
    Given 一次调用：provider_org_id=部门A_公安, consumer_org_id=部门X_民政, provider_region_code=370000, consumer_region_code=370100
    When projection 派生器以 5 个 metric_scope 同时运行：service / provider_org / consumer_org / provider_region / consumer_region
    Then `service_invocation_metric_projection` 各派生出 1 条记录（共 5 条），各自 UNIQUE 约束不冲突
    And 任一记录的 `metric_scope` 字段标注派生粒度
    And `INDEX (resource_id, time_bucket DESC)` 能命中 service 粒度的单服务趋势
    And `INDEX (provider_org_id, time_bucket DESC)` 能命中 provider_org 粒度的提供方维度
    And `INDEX (consumer_org_id, time_bucket DESC)` 能命中 consumer_org 粒度的调用方维度

  Scenario: 正向 — 多桶粒度（minute / hour / day）可重算覆盖且 UNIQUE 不冲突（plan §3.4 "可重算覆盖，不累积重复口径"）
    Given T0 分钟内有 4 次调用记录
    When projection 派生器先以 bucket_granularity=minute 派生，再以 hour / day 派生
    Then `service_invocation_metric_projection` 出现 3 条记录，bucket_granularity 分别为 minute / hour / day
    And UNIQUE (tenant_id, metric_scope, resource_id, provider_org_id, consumer_org_id, provider_region_code, consumer_region_code, bucket_granularity, time_bucket) 约束保证同一窗口可重算覆盖（rerun 不新增）

  Scenario: 负向 — 调用引用的 capability_slug 未注册 → 不进投影（防孤儿派生）
    Given 任意 capability_slug=`resource.api.ghost-unregistered` 不在 capability registry
    When 一条 capability_call 携带该未注册 slug
    Then `service_invocation_metric_projection` 无新增记录
    And 派生器日志（或 audit_event）记录 `unknown_capability_slug` 跳过
    And 不污染 service / provider_org / consumer_org 任何粒度的统计

  Scenario: 负向 — 跨租户调用统计被隔离（不共享 projection）
    Given (tenant_id="sd-default", resource_id="R201") 已有 invoke_count=4 (T0, minute)
    When 第二个租户 tenant_id="other-tenant" 也对同名 resource_id="R201" 在 T0 发生 2 次调用
    Then `service_invocation_metric_projection` 新增独立 (tenant_id="other-tenant", ..., resource_id="R201", T0, minute) 记录，invoke_count=2
    And 不影响 sd-default 的同名记录 invoke_count=4
    And 跨租户隔离回归见 wave-3-protocol-tenant-national/features/multi-tenant-policy.feature

  Scenario: 负向 — 未授权角色看不到服务调用统计只读面（无权限即不可见）
    Given 当前 actor 角色 ∉ {ROLE_SYSTEM, ROLE_BUSIAUDIT}（例：ROLE_ORGAN_OPERATER）
    When 该角色加载 B1.1 只读面或经任一消费面请求 `ops.service.invocation.query`
    Then WebUI 不渲染服务调用统计入口（不是"可见但禁用"，也不是"可见点击后 403/静默失败"）
    And `ops.service.invocation.query` 在 API / CLI / MCP / A2A 返回 policy decision=deny，响应体不含任何 `service_invocation_metric_projection` 数据
    And 审计总线记录一条 policy decision=deny，actor 含该角色

  Scenario: 负向 — 业务状态不允许由 projection 反推（plan §5.2 输出纪律）
    When 任何 Capability / adapter / WebUI 试图基于 `service_invocation_metric_projection.invoke_count` 改写 `resource_asset.status`
    Then preflight 段 25 (adapter-write-ban) 与 §5.2 输出纪律拦下任何业务状态回写
    And 投影只允许重算（plan §5.2：业务状态不允许由统计表反推）

  Scenario: 回归 — Capability `ops.service.invocation.query` 投影到 5 消费面一致（R15 桥接面 / plan §〇）
    When 我导出 WebUI 路由表 / OpenAPI / CLI commands / MCP tool manifest / A2A agent card
    Then 五份导出文件中**同一业务能力**指向同一 capability slug `ops.service.invocation.query`
    And 五消费面的 query schema 字段集合一致（含 tenant_id / metric_scope / resource_id / time_bucket / bucket_granularity）
    And `export_agent_contract.py --check` 无 drift

  Scenario: 回归 — 工程术语黑名单（R12 / 基线 §5.5）
    Then B1.1 只读面 DOM / OpenAPI summary / CLI help 文本均**不出现**：
      | term                                   |
      | projection                             |
      | capability                             |
      | write-with-audit                       |
      | service_invocation_metric_projection   |
    But 后端字段名（如审计断言中引用 `service_invocation_metric_projection`）允许以代码引号包裹出现

  Scenario: 回归 — 统计查询必须能解释来源（plan §七.4 验收）
    When B1.1 读侧返回任一统计行
    Then 该行携带 `source_event_ref`，指向审计事件、网关日志 adapter 或旧统计表快照之一
    And 来源不为空时可回放原始 capability_call / audit_event 链路
