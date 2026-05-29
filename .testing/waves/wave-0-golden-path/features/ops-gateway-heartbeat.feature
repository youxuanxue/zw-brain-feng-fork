# Wave: 0
# Journey: B1.1
# Pages: B1.1（网关运行只读面板 — /compliance-ops 第 5 个 tab）
# Consumer-faces: WebUI | API | CLI | MCP | A2A
# Roles: ROLE_SYSTEM | ROLE_BUSIAUDIT
# Trace: D31 / D32 / 业务反馈 #PR129 / 基线 §3.4 / dsp-dataservice-reconstruction-plan-v1.md §3.3 / §3.5 / §六 Wave 0 / 旧 xlsx 行 [63..70]（A 类批次锚定，非业务面对照）
# Priority: P0
# Status: Draft
# Owner: e6
# Pytest: tests/test_wave0_ops_gateway.py
# Twin-F: e6.F12

Feature: Wave 0 网关运行状态投影（ops.gateway.heartbeat.ingest）
  As a 平台守门人 / 运营审计 (ROLE_SYSTEM / ROLE_BUSIAUDIT)
  I want 网关实例的心跳能以可重算投影形态进入 zw-brain 只读运营面
  So that 旧系统最高频接口 `/openapi/report`（362,407 次）在 zw-brain 中有权威读面，且不复刻旧网关后台

  Background:
    Given 单租户 sd-default 已初始化
    And 7 角色码 CHECK 约束已生效
    And 集团推理平台 gateway mock 已就绪（基线 §6 / D14）
    And 物理表 `gateway_runtime_status_projection` 已通过 `Base.metadata.create_all` 建出（基线 §9.6 不进 alembic）
    And `gateway_runtime_status_projection` UNIQUE (tenant_id, gateway_instance_id) + INDEX (tenant_id, status, last_reported_at DESC)
    And Capability `ops.gateway.heartbeat.ingest` 已注册（audit_class=read-trace；plan §3.5）
    And 单租户假设：跨租户隔离的回归用例见 wave-3-protocol-tenant-national/features/multi-tenant-policy.feature

  Scenario: 正向 — 网关每分钟上报心跳，projection 写入并标 online（旧 xlsx 行 65 创建代理服务派生）
    Given 不存在 (tenant_id="sd-default", gateway_instance_id="gw-zone-a-001") 的投影记录
    When 网关实例 `gw-zone-a-001` 携带 gateway_address_ref=`10.0.x.x:8080` / runtime_profile=`zone-a-prod` 通过 `ops.gateway.heartbeat.ingest` 上报心跳
    Then `gateway_runtime_status_projection` 出现一条记录：
      | 字段                  | 期望                          |
      | tenant_id            | sd-default                    |
      | gateway_instance_id  | gw-zone-a-001                 |
      | gateway_address_ref  | 10.0.x.x:8080                 |
      | runtime_profile      | zone-a-prod                   |
      | status               | online                        |
      | source_ref           | 形如 adapter:dsp_dataservice_gateway_runtime 或 redis:GATEWAY_REPORT |
    And `last_reported_at` 不晚于当前时刻
    And `generated_at` 同步写入
    And 审计总线记录一条 `capability_call=ops.gateway.heartbeat.ingest`，`audit_class=read-trace`，actor 含 ROLE_SYSTEM

  Scenario: 正向 — 同一实例 1 分钟内重复上报，UNIQUE 约束触发覆盖更新而非新增
    Given (tenant_id="sd-default", gateway_instance_id="gw-zone-a-001") 已有一条 status=online，last_reported_at=T0
    When 同一实例在 T0+30s 再次上报心跳
    Then 投影中 (tenant_id, gateway_instance_id) 仍只有 1 条记录（UNIQUE 约束生效）
    And `last_reported_at` 推进到 T0+30s
    And `generated_at` 推进到当前时刻
    And `status` 保持 online

  Scenario: 正向 — 心跳超时 → status 自动转 offline（B1.1 在线/离线判定）
    Given (tenant_id="sd-default", gateway_instance_id="gw-zone-b-002") 上一次心跳在 T0；超时阈值 = 3 分钟
    When 时间推进到 T0+5min 且该实例未再上报
    Then 在 B1.1 读侧查询时，projection 中该实例 `status=offline`
    And 该实例 `last_reported_at` 仍为 T0（不被人为修改，只是 status 派生失效）
    And `INDEX (tenant_id, status, last_reported_at DESC)` 能直接按 status=offline 命中

  Scenario: 正向 — B1.1 网关运行只读面板展示在线/降级/离线计数与实例列表（③ 闭合到人）
    Given 授权角色（ROLE_ORGAN_MANAGER / ROLE_BUSIAUDIT / ROLE_SECURITY_AUDIT 之一，policy.py ops.service.report.query.execute）
    And `gateway_runtime_status_projection` 已有若干实例（在线 / 降级 / 离线混合）
    When 该角色进入 B1.1 合规与运营页（`/compliance-ops`）并切到「网关运行」tab
    Then 顶部计数条显示 在线 / 降级 / 离线 三类数量（由 `ops.service.report.query` 返回的 gateways[] 派生）
    And 只读实例列表逐行显示 网关实例 / 运行模式 / 状态（中文）/ 最近心跳 / 来源
    And 面板无任何写操作入口（read model，与 S9 一致）
    And 后端不可达时面板回退 fixture 切片并标注数据来源 pill = fixture

  Scenario: 负向 — 缺 tenant_id 的上报被拒（无主投影）
    When 网关实例上报心跳但 payload 不含 tenant_id 字段
    Then 上报被拒：HTTP 400 或 capability 返回 schema validation error
    And `gateway_runtime_status_projection` 无新增记录
    And 审计总线记录 `policy decision=reject`，原因 `missing tenant_id`

  Scenario: 负向 — 跨租户 gateway_instance_id 冲突上报被隔离（不共享投影）
    Given (tenant_id="sd-default", gateway_instance_id="gw-shared-01") 已有 status=online
    When 第二个租户 tenant_id="other-tenant" 以同名 gateway_instance_id="gw-shared-01" 上报心跳
    Then `gateway_runtime_status_projection` 新增独立 (tenant_id="other-tenant", gateway_instance_id="gw-shared-01") 记录
    And 不影响 sd-default 的同名实例 status / last_reported_at
    And 跨租户隔离回归见 wave-3-protocol-tenant-national/features/multi-tenant-policy.feature

  Scenario: 负向 — 未授权角色看不到网关运行状态只读面（无权限即不可见）
    Given 当前 actor 角色 ∉ {ROLE_SYSTEM, ROLE_BUSIAUDIT}（例：ROLE_ORGAN_OPERATER）
    When 该角色加载 B1.1 只读面或经任一消费面请求网关运行状态读路径
    Then WebUI 不渲染网关运行状态入口（不是"可见但禁用"，也不是"可见点击后 403/静默失败"）
    And API / CLI / MCP / A2A 对该读路径返回 policy decision=deny，响应体不含任何 `gateway_runtime_status_projection` 数据
    And 审计总线记录一条 policy decision=deny，actor 含该角色

  Scenario: 回归 — Capability `ops.gateway.heartbeat.ingest` 投影到 5 消费面一致（R15 桥接面 / plan §〇）
    When 我导出 WebUI 路由表 / OpenAPI / CLI commands / MCP tool manifest / A2A agent card
    Then 五份导出文件中**同一业务能力**指向同一 capability slug `ops.gateway.heartbeat.ingest`
    And 五消费面的 input_schema 字段集合一致（含 tenant_id / gateway_instance_id / gateway_address_ref / runtime_profile）
    And `export_agent_contract.py --check` 无 drift

  Scenario: 回归 — 工程术语黑名单（R12 / 基线 §5.5）
    Then B1.1 只读面 DOM / OpenAPI summary / CLI help 文本均**不出现**：
      | term                         |
      | projection                   |
      | capability                   |
      | write-with-audit             |
      | gateway_runtime_status_projection |
    But 后端字段名（如审计断言中引用 `gateway_runtime_status_projection`）允许以代码引号包裹出现

  Scenario: 回归 — 投影是 read model，不允许作为业务事实源被外部回写
    When 任何 adapter / Capability 试图直接 INSERT/UPDATE/DELETE `gateway_runtime_status_projection` 而不经 `ops.gateway.heartbeat.ingest` Capability
    Then preflight 段 25 (adapter-write-ban) 在 `zw_brain/adapters/legacy/` 之外的写 token 直接拦下
    And 真正的网关路由 / 认证 / 限流策略仍回到 `resource_channel_binding.gateway_policy_json` 或外部网关策略系统（plan §3.3 末段）
