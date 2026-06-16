# AgentRuntime API 接入文档

本文面向接入 AgentRuntime 的客户端、BFF、业务后端和平台服务，说明如何通过 HTTP API 或 Python 嵌入式 SDK 创建会话、启动任务、订阅事件流、处理等待态、读写 workspace、调用 A2A、本地运维与排障。

当前 Runtime 接受 `anp-agent/v1.1` 和 `anp-agent/v1.2` Agent manifest；新建 Agent 推荐使用 `anp-agent/v1.2`。旧的 `anp-agent/v1`、`tools.kind=mcp/skill`、Agent-authored `code_execution` / `permissions.code_execution` 和 `acceptance.required_artifacts` 不再作为当前 API/loader 契约支持。

权威契约以源码中的 Pydantic model 和 FastAPI route 为准：

- [src/agent_runtime/runtime/models.py](../src/agent_runtime/runtime/models.py)：请求、响应和记录模型。
- [src/agent_runtime/runtime/events.py](../src/agent_runtime/runtime/events.py)：RuntimeEvent 事件模型。
- [src/agent_runtime/api/routes_sessions.py](../src/agent_runtime/api/routes_sessions.py)：Session API。
- [src/agent_runtime/api/routes_tasks.py](../src/agent_runtime/api/routes_tasks.py)：Task API 与 SSE。
- [src/agent_runtime/api/routes_agents.py](../src/agent_runtime/api/routes_agents.py)：Agent registry 与资源文件 API。
- [src/agent_runtime/api/routes_workspaces.py](../src/agent_runtime/api/routes_workspaces.py)：Workspace 文件 API。
- [src/agent_runtime/api/routes_a2a.py](../src/agent_runtime/api/routes_a2a.py)：本地 A2A API。
- [src/agent_runtime/api/routes_callbacks.py](../src/agent_runtime/api/routes_callbacks.py)：外部 callback API。
- [src/agent_runtime/api/routes_runtime.py](../src/agent_runtime/api/routes_runtime.py)：Runtime 健康、诊断和运维 API。
- [src/agent_runtime/api/routes_logs.py](../src/agent_runtime/api/routes_logs.py)：日志查询 API。
- [src/agent_runtime/api/routes_ui.py](../src/agent_runtime/api/routes_ui.py)：内置 Web 聊天 UI 路由（不包含在 OpenAPI 文档中）。
- [src/agent_runtime/runtime/service.py](../src/agent_runtime/runtime/service.py)：Python SDK 入口与运行时服务。

## 1. 接入模型总览

AgentRuntime 的调用链通常由 5 个对象组成：

| 对象 | 说明 | 常见调用方关心点 |
| --- | --- | --- |
| Agent | 由 `AGENT.yaml` 声明的执行单元，包含模型、指令、工具、权限、workspace、skills、MCP、A2A、acceptance 等配置。 | 业务系统传入 `agent_id` 选择能力。 |
| Session | 会话容器，保存会话状态、消息投影和默认 workspace 归属。 | 一个用户会话、一个工单或一次业务流程通常对应一个 session。 |
| Task | 一次 Agent 执行。Task 启动时冻结 manifest、middleware、workspace 和工具快照。 | 调用方通过 task 追踪执行状态、订阅事件和获取最终输出。 |
| RuntimeEvent | Task 执行过程中的统一事件。 | 前端/BFF 用于展示流式回答、工具调用、等待用户输入和终态。 |
| Workspace | Runtime 管理的文件空间。 | 上传输入文件、读取 Agent 产物、下载报告或中间文件。 |

推荐最小链路：

1. 调用 `POST /sessions` 创建 session。
2. 调用 `POST /tasks` 启动 task。
3. 调用 `POST /tasks/{task_id}/stream-token` 获取短期 SSE token。
4. 连接 `GET /tasks/{task_id}/stream` 订阅 RuntimeEvent。
5. 如果收到 `task_waiting`，调用 `POST /tasks/{task_id}/resume` 恢复 task。
6. 完成后读取 `TaskRecord.final_output`、`GET /sessions/{session_id}/messages` 或 workspace 文件。

## 2. 基础约定

### 2.1 Base URL 与内容类型

假设服务地址为：

```bash
export RUNTIME_URL="http://localhost:8000"
```

JSON 请求统一使用：

```http
Content-Type: application/json
```

响应中的时间字段为 ISO 8601 字符串，Runtime 内部按 UTC 生成。

### 2.2 身份与权限

AgentRuntime 支持多种 API 鉴权模式，包括本地 `none`、静态 API key、JWT/JWKS 和 trusted gateway。实际模式由 `RuntimeSettings.api_auth` / 部署环境决定。

常见凭据：

| 模式 | 客户端凭据 |
| --- | --- |
| `none` | 不需要凭据，Runtime 使用固定 dev principal。仅用于本地开发/测试。 |
| `static_api_key` | `Authorization: Bearer <api_key>` 或 `X-API-Key: <api_key>`。 |
| `jwt_jwks` | `Authorization: Bearer <jwt>`。 |
| `trusted_gateway` | 网关注入 principal、签名和时间戳头；默认头名为 `X-Runtime-Principal`、`X-Runtime-Principal-Signature`、`X-Runtime-Principal-Timestamp`，也可由 `ApiAuthSettings.trusted_gateway` 配置。 |

权限由 principal scopes 决定。标准 scope 定义见 [src/agent_runtime/security/scopes.py](../src/agent_runtime/security/scopes.py)：

| Scope | 用途 |
| --- | --- |
| `sessions:create` | 创建 session。 |
| `sessions:read` | 读取 session 和 session state。 |
| `sessions:update` | 更新或恢复 session。 |
| `sessions:delete` | 删除 session。 |
| `messages:read` | 读取 session messages。 |
| `tasks:start` | 启动 task 或本地 A2A 调用。 |
| `tasks:start:any_user` | 代表其他 `subject_user_id` 启动 task。 |
| `tasks:read` | 读取 task。 |
| `tasks:stream` | 订阅 task SSE 或换取 stream token。 |
| `tasks:resume` | 恢复等待中的 task。 |
| `tasks:cancel` | 取消 task。 |
| `events:read` | 读取持久化 RuntimeEvent。 |
| `workspaces:read` | 读取 workspace 文件。 |
| `workspaces:write` | 写入或删除 workspace 文件。 |
| `agents:read` | A2A 调用所需的 agent 读取权限。 |
| `callbacks:deliver` | 标准 callback delivery scope。（当前 `/callbacks/{wait_id}` 使用签名验证，路由层不直接依赖该 scope。） |
| `admin:runtime` | 运维接口、Agent 动态管理（上传/删除/reload）和跨 owner 访问。 |

生产环境不要使用 `mode=none`。在非 `none` 模式下，session、task 和 workspace API 会校验 owner：普通调用方只能访问自己创建或代表的用户资源，`admin:runtime` 可绕过 owner 检查。

### 2.3 统一错误格式

Runtime 抛出的业务错误统一返回：

```json
{
  "error": {
    "type": "validation_error",
    "message": "Request validation failed",
    "retryable": false,
    "task_id": null,
    "trace_id": null,
    "details": {}
  }
}
```

常见错误类型与 HTTP 状态码：

| `error.type` | HTTP | 说明 | 客户端处理建议 |
| --- | --- | --- | --- |
| `unauthenticated` | 401 | 缺少凭据、凭据无效或 callback 签名无效。 | 重新登录、刷新凭据或检查 callback 签名。 |
| `forbidden` | 403 | scope 不足或非 owner 访问。 | 检查 principal scope、owner 和租户映射。 |
| `policy_denied` | 403 | Runtime 策略拒绝，例如 workspace 路径、网络或命令策略。 | 展示可读原因，必要时调整 Agent 配置。 |
| `validation_error` | 400 / 422 | 请求格式或业务参数不合法。 | 修正请求体；FastAPI 422 的校验细节在 `details.errors`。 |
| `agent_not_found` | 404 | `agent_id` 不存在。 | 刷新 agent 列表或检查部署配置。 |
| `license_error` | 402 | Runtime license/manifest 校验失败。 | 检查 runtime manifest/license。 |
| `session_busy` | 409 | 同一 session 已有互斥执行中的 task。 | 等待、取消当前 task，或新建 session。 |
| `idempotency_conflict` | 409 | 幂等键或 callback nonce 冲突。 | 查询已有 task，避免重复提交。 |
| `rate_limited` | 429 | 达到限流。 | 按退避策略重试。 |
| `runtime_not_ready` | 503 | Runtime preflight 未通过或不可执行任务。 | 调用 `/runtime/ready`、`/runtime/preflight` 排查。 |
| `timeout` | 500 | 执行超时。 | 检查 task timeout 配置或模型响应时间。 |
| `tool_error` | 500 | 工具调用异常。 | 检查工具配置和返回值。 |
| `sandbox_error` | 500 | 沙盒执行异常。 | 检查 sandbox 后端和策略配置。 |
| `model_error` | 500 | 模型 API 异常。 | 检查模型配置和 provider 状态。 |
| `internal_error` | 500 | Runtime 内部未预期错误。 | 记录 `trace_id`，读取 task error 和日志。 |

## 3. Session API

Session 是业务会话容器。业务系统应先创建 session，再在 session 内启动 task。

### 3.1 创建 Session

```http
POST /sessions
```

请求体 `CreateSessionRequest`：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `title` | <code>string &#124; null</code> | 否 | `null` | 会话标题。 |
| `trust_level` | <code>platform &#124; verified &#124; untrusted</code> | 否 | `verified` | 会话信任等级。 |
| `workspace_id` | <code>string &#124; null</code> | 否 | `null` | 复用已有 workspace；不传则 Runtime 按策略生成。 |
| `agent_id` | <code>string &#124; null</code> | 否 | `null` | 可选，创建时校验 agent 是否存在，并写入 metadata。 |
| `metadata` | `object` | 否 | `{}` | 业务侧透传元数据。 |

示例：

```bash
curl -X POST "$RUNTIME_URL/sessions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RUNTIME_TOKEN" \
  -d '{
    "title": "合同审查 #2026-001",
    "trust_level": "verified",
    "agent_id": "contract-review-agent",
    "metadata": {"case_id": "2026-001"}
  }'
```

响应 `SessionRecord`：

```json
{
  "session_id": "35a1c4f5-5f20-40f9-bd91-ea9dcbf2d122",
  "title": "合同审查 #2026-001",
  "status": "active",
  "trust_level": "verified",
  "workspace_id": null,
  "metadata": {"case_id": "2026-001", "agent_id": "contract-review-agent"},
  "last_task_id": null,
  "last_agent_id": null,
  "last_task_at": null,
  "owner_user_id": "u_123",
  "owner_principal_id": "principal_123",
  "tenant_id": "tenant_a",
  "created_by_principal_id": "principal_123",
  "created_by_auth_method": "jwt_jwks",
  "created_at": "2026-05-11T08:00:00Z",
  "updated_at": "2026-05-11T08:00:00Z"
}
```

### 3.2 查询 Session 列表

```http
GET /sessions?agent_id=<agent_id>&include_deleted=false
```

参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `agent_id` | `string` | 无 | 只返回 metadata 中关联指定 agent 的 session。 |
| `include_deleted` | `boolean` | `false` | 是否包含软删除 session。 |

普通用户只返回自己拥有的 session；管理员返回全部。

### 3.3 获取、更新、删除和恢复 Session

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/sessions/{session_id}?include_deleted=false` | 获取单个 session。 |
| `PATCH` | `/sessions/{session_id}` | 更新 `title`、`status`、`workspace_id`、`metadata`。 |
| `DELETE` | `/sessions/{session_id}?purge=false` | 删除 session。默认软删除；`purge=true` 物理删除。 |
| `POST` | `/sessions/{session_id}/restore` | 恢复软删除 session。 |
| `POST` | `/sessions/{session_id}/thread-bindings/{agent_id}/reset` | 重置该 Agent 在 Session 内的 LangGraph thread binding；下次 Task 使用新 checkpoint 线（不删除 workspace 文件）。 |

### 3.4 读取 Session State 和 Messages

```http
GET /sessions/{session_id}/state
GET /sessions/{session_id}/messages?limit=50&before_message_id=<cursor>
```

Session 状态枚举为 `active`、`archived`、`deleted`。`/state` 返回 session、task 投影和 message 投影。`tasks[]` 会额外包含：

- `resumable`：当前 task 是否可调用 `/resume`，由 `status == waiting_input` 决定。
- `resume_after_restart`：等待态是否承诺按持久化策略跨服务重启恢复；投影为 `status == waiting_input` 且 `persistence == persisted` 且部署具备 durable checkpoint（`database_url` + `runtime_core == deepagents`）。
- `run_kind`：Task 来源，例如 `session_run`、`scheduled_run` 或 `manual_shortcut`。
- `persistence`：Task 持久化策略，例如 `none`、`session` 或 `persisted`。

Message 只存会话级投影，流式 `message_delta` 原始增量默认不作为最终消息保存。页面刷新时优先用 `/messages` 恢复对话历史。`MessageRecord` 字段包括：`message_id`、`session_id`、`task_id`、`agent_id`、`role`、`content_type`、`content`、`resource_refs`、`status`、`created_at`、`metadata`；`role` 可为 `user`、`assistant`、`tool_summary`、`system_status`，`status` 可为 `final`、`failed`、`cancelled`、`waiting`、`streaming`。

## 4. Task API

Task 是一次 Agent 执行。客户端通过 Task API 启动、查询、取消、恢复和订阅执行。

### 4.1 启动 Task

```http
POST /tasks
```

请求体 `StartTaskRequest`：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | `string` | 是 | 无 | 已创建的 session ID。 |
| `agent_id` | `string` | 是 | 无 | 要执行的 Agent。 |
| `run_kind` | <code>session_run &#124; scheduled_run &#124; manual_shortcut</code> | 否 | `session_run` | Task 来源/触发类型。 |
| `persistence` | <code>none &#124; session &#124; persisted &#124; null</code> | 否 | `null` | 持久化策略；未传时按 Runtime 默认策略归一化，通常为 `session`。 |
| `missing_context_policy` | <code>fail_fast &#124; wait_for_input &#124; null</code> | 否 | `null` | 缺少必填 dynamic context 时的策略；交互式 session task 默认等待输入，后台/调度任务默认快速失败。 |
| `input` | <code>string &#124; object</code> | 是 | 无 | 用户输入或结构化业务输入。 |
| `metadata` | `object` | 否 | `{}` | 业务透传元数据。可包含业务侧 acceptance、trace 或 UI 元信息。 |
| `files` | `UploadedFileSpec[]` | 否 | `[]` | 随 task 上传的文件。 |
| `workspace_id` | <code>string &#124; null</code> | 否 | `null` | 指定 task workspace。 |
| `workspace_isolation` | <code>session_shared &#124; task_isolated &#124; null</code> | 否 | `null` | 覆盖 workspace 隔离策略。 |
| `timeout` | <code>integer &#124; null</code> | 否 | `null` | 执行超时时间，单位秒。 |
| `system_prompt_append` | <code>string &#124; null</code> | 否 | `null` | 追加系统提示，最多 500000 字符。 |
| `system_prompt_override` | <code>string &#124; null</code> | 否 | `null` | 覆盖系统提示，最多 500000 字符。 |
| `dynamic_context` | <code>object &#124; null</code> | 否 | `null` | 传给 Agent instructions template 的动态上下文。 |
| `idempotency_key` | <code>string &#124; null</code> | 否 | `null` | 幂等键，最多 200 字符。 |
| `subject_user_id` | <code>string &#124; null</code> | 否 | `null` | 代表哪个用户执行（最长 200 字符）；不同于当前 principal 时需要 `tasks:start:any_user`。 |

`files` 中每项 `UploadedFileSpec`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `filename` | `string` | 是 | 文件名，1-255 字符。 |
| `content_base64` | `string` | 是 | 文件内容 base64。 |
| `mime_type` | <code>string &#124; null</code> | 否 | MIME 类型。 |
| `target_path` | <code>string &#124; null</code> | 否 | 写入 workspace 的相对路径，最长 1024 字符。 |

示例：

```bash
curl -X POST "$RUNTIME_URL/tasks" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RUNTIME_TOKEN" \
  -d '{
    "session_id": "35a1c4f5-5f20-40f9-bd91-ea9dcbf2d122",
    "agent_id": "contract-review-agent",
    "input": {
      "instruction": "审查附件合同，输出风险摘要和修改建议",
      "language": "zh-CN"
    },
    "metadata": {"case_id": "2026-001"},
    "idempotency_key": "case-2026-001-review-v1"
  }'
```

响应为 `TaskRecord`，核心字段包括：

| 字段 | 说明 |
| --- | --- |
| `task_id` / `session_id` / `agent_id` | 标识字段。 |
| `agent_manifest_snapshot` | Task 启动时冻结的 Agent manifest，含 `_runtime` 诊断投影。 |
| `metadata` | 业务透传元数据。 |
| `effective_trust` | 本次执行实际 trust level。 |
| `workspace_id` | 本次执行 workspace。 |
| `run_kind` | Task 来源/触发类型（`session_run` / `scheduled_run` / `manual_shortcut`）。 |
| `persistence` | Task 持久化策略（`none` / `session` / `persisted`）。 |
| `status` | `pending`、`running`、`waiting_input`、`completed`、`failed`、`cancelled`。 |
| `input_summary` | 输入摘要。 |
| `final_output` | 最终输出，任务完成后可读。 |
| `error` | 失败信息。 |
| `started_at` / `finished_at` | 实际开始和结束时间。 |
| `wait_type` / `interrupt_payload` | 等待态类型和提示信息；`interrupt_payload` 只保留可安全返回给客户端的公开字段。 |
| `input_message_id` / `output_message_id` | 会话消息投影 ID。 |
| `deepagents_thread_id` / `thread_binding_id` | DeepAgents thread 与 Runtime thread binding 标识。 |
| `idempotency_key` / `request_hash` | 幂等信息。 |
| `owner_user_id` / `owner_principal_id` / `actor_principal_id` / `subject_user_id` | 归属与操作者信息。 |
| `middleware_snapshot` | 本次执行的 middleware / policy / limits / runtime notes 快照。 |
| `output_refs` | 路由层从 `agent_manifest_snapshot._runtime.output_refs` 提升出来的产物引用列表；仅当存在时返回。 |

### 4.2 查询 Task 与诊断

| 方法 | 路径 | Scope | 说明 |
| --- | --- | --- | --- |
| `GET` | `/tasks?session_id=<id>&status=<status>&limit=50&before_task_id=<cursor>` | `tasks:read` | 分页查询 task。`limit` 范围 1-200。 |
| `GET` | `/tasks/{task_id}` | `tasks:read` | 获取单个 task。 |
| `GET` | `/tasks/{task_id}/diagnostics` | `tasks:read` | 获取 task 级诊断投影，用于排查执行、模型、工具、context 或 workspace 问题。 |

普通 principal 只能读取自己拥有的 task；`admin:runtime` 可跨 owner 查询。`GET /tasks/{task_id}/diagnostics` 返回 `TaskDiagnostics` 投影，包含 `task`、`session`、`agent`、`effective_trust`、`policy`、`tools`、`subagents`、`sandbox`、`workspace`、`model`、`context`、`artifacts`、`events`、`errors`、`runtime`、`suggested_actions`，其中 `artifacts.output_refs` 可用于定位公开产物引用。

列表响应：

```json
{
  "items": [{"task_id": "9d2f...", "status": "completed"}],
  "limit": 50,
  "session_id": "35a1...",
  "status": null,
  "next_cursor": null
}
```

### 4.3 取消 Task

```http
POST /tasks/{task_id}/cancel
```

取消成功后返回更新后的 `TaskRecord`。

### 4.4 恢复等待中的 Task

当 task 状态为 `waiting_input`，或 SSE 收到 `task_waiting` 时，调用：

```http
POST /tasks/{task_id}/resume
```

请求体 `ResumeTaskRequest`：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `input` | <code>string &#124; object</code> | 是 | 无 | 恢复输入、审批结果或外部结果。 |
| `system_prompt_append` | <code>string &#124; null</code> | 否 | `null` | 恢复时追加系统提示，最多 500000 字符。 |
| `system_prompt_override` | <code>string &#124; null</code> | 否 | `null` | 恢复时覆盖系统提示，最多 500000 字符。 |
| `dynamic_context` | <code>object &#124; null</code> | 否 | `null` | 恢复时动态上下文。 |
| `actor` | <code>object &#124; null</code> | 否 | `null` | 实际操作人信息（如 `user_id`、`display_name` 等）。 |
| `idempotency_key` | <code>string &#124; null</code> | 否 | `null` | 恢复请求幂等键，最多 200 字符。 |
| `metadata` | `object` | 否 | `{}` | 业务透传元数据。 |

调用方不能直接指定内部 `resume_type`。Runtime 会以 task 当前 `wait_type` 作为唯一依据归一化为内部 `ResumeEnvelope`，并把请求体中的 `input`、`dynamic_context`、`actor`、`idempotency_key` 和 `metadata` 投影到恢复上下文。

## 5. RuntimeEvent 与 SSE

### 5.1 获取历史事件

```http
GET /tasks/{task_id}/events?after_sequence=0&limit=200
```

参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `after_sequence` | <code>integer &#124; null</code> | `null` | 只返回 sequence 大于该值的事件。 |
| `limit` | `integer` | `200` | 每页数量，1-1000。 |

响应包含：`task_id`、`items`、`limit`、`after_sequence`、`last_sequence`。`items[]` 中每个 `RuntimeEvent` 字段包括：`event`、`task_id`、`agent_id`、`event_id`、`sequence`、`correlation_id`、`audit_event_id`、`message_id`、`session_id`、`workspace_id`、`langgraph_thread_id`、`langgraph_namespace`、`timestamp`、`payload`。

### 5.2 订阅实时 SSE

推荐先换短期 stream token：

```bash
curl -X POST "$RUNTIME_URL/tasks/$TASK_ID/stream-token" \
  -H "Authorization: Bearer $RUNTIME_TOKEN"
```

响应：

```json
{
  "stream_url": "/tasks/9d2f.../stream?stream_token=...",
  "expires_at": "2026-05-11T08:05:00Z",
  "token_id": "st_..."
}
```

然后连接：

```bash
curl -N "$RUNTIME_URL/tasks/$TASK_ID/stream?stream_token=$STREAM_TOKEN"
```

也可以直接使用具备 `tasks:stream` scope 的 principal 访问：

```bash
curl -N "$RUNTIME_URL/tasks/$TASK_ID/stream" \
  -H "Authorization: Bearer $RUNTIME_TOKEN"
```

SSE 编码：

```text
id: <sequence>
event: <event-name>
data: <RuntimeEvent JSON>

```

断线重连支持：

```http
Last-Event-ID: <sequence>
```

或：

```http
GET /tasks/{task_id}/stream?after_sequence=<sequence>
```

流会在以下情况结束：

- 收到 `task_completed`、`task_failed`、`task_cancelled` 或 `policy_denied`。
- 打开连接时 task 已处于 `waiting_input`，或当前打开的流观察到新的 `task_waiting`。

如果最后事件是 `task_waiting`，客户端应该展示等待态并调用 `/resume`，不要继续等待同一条 SSE 连接。

### 5.3 事件类型

事件词汇表由 [src/agent_runtime/runtime/events.py](../src/agent_runtime/runtime/events.py) 定义：

| 事件 | 含义 | 客户端建议 |
| --- | --- | --- |
| `task_started` | Task 开始执行。 | 展示运行中状态。 |
| `message_delta` | Assistant 文本流式增量。 | 追加到当前 assistant 消息。 |
| `model_thinking` | 模型 thinking/reasoning 增量。 | 更新 reasoning 面板；是否展示由产品策略决定。 |
| `tool_call_started` | 工具调用开始。 | 展示工具卡片 pending。 |
| `tool_call_completed` | 工具调用成功完成。 | 展示工具摘要、产物或引用。 |
| `tool_call_failed` | 工具调用失败。 | 展示失败原因，允许用户重试或调整输入。 |
| `policy_denied` | 策略拒绝。 | 展示明确阻断原因，不应自动绕过。 |
| `workspace_update` | workspace 文件状态变化。 | 刷新文件树或 artifact 列表。 |
| `runtime_update` | Runtime 级状态更新。 | 用于诊断或 UI 状态提示。 |
| `task_waiting` | Task 等待输入、审批或 callback。 | 关闭流，展示等待控件，并调用 resume。 |
| `task_resumed` | Task 已恢复。 | 重新订阅 stream 或继续展示运行中。 |
| `task_completed` | Task 完成。 | 固化最终消息，读取 `final_output` 或 messages。 |
| `task_failed` | Task 失败。 | 展示错误并提供重试入口。 |
| `task_cancelled` | Task 取消。 | 展示取消状态。 |

事件持久化注意事项：

- `message_delta` 和 `model_thinking` 默认不保留原始 delta/thinking 文本，会写入 `delta_persisted=false`、`delta_size`；`message_delta` 还会补 `content_type="text"`。
- `task_completed.payload.final_output` 默认不在持久化事件中保留完整值，会写入 `final_output_persisted=false` 和 `final_output_summary`，完整结果以 `TaskRecord.final_output` 和 message projection 为准。
- 客户端应使用 `(task_id, sequence)` 去重，不应使用 `event_id` 排序或作为主游标。

## 6. Workspace API

Workspace API 用于读写 Runtime 管理的文件空间。路径均为 workspace 相对路径。

| 方法 | 路径 | Scope | 说明 |
| --- | --- | --- | --- |
| `GET` | `/workspaces/{workspace_id}/files?path=<dir>` | `workspaces:read` | 列目录。 |
| `GET` | `/workspaces/{workspace_id}/files/content?path=<file>&download=false` | `workspaces:read` | 读取文件内容或下载二进制。 |
| `PUT` | `/workspaces/{workspace_id}/files/content?path=<file>` | `workspaces:write` | 写入文件（已配置时同步至 Daytona）。 |
| `DELETE` | `/workspaces/{workspace_id}/files/content?path=<file>` | `workspaces:write` | 删除文件，成功返回 204。 |

列目录响应：

```json
{
  "workspace_id": "session_35a1...",
  "path": "output",
  "entries": [
    {"path": "output/report.md", "is_dir": false, "size": 1024, "modified_at": "2026-05-11T08:10:00Z"}
  ]
}
```

读取文本文件响应：

```json
{
  "workspace_id": "session_35a1...",
  "path": "output/report.md",
  "encoding": "utf-8",
  "content": "# 报告\n...",
  "size": 1024
}
```

读取二进制文件时 `encoding` 为 `base64`。如果 `download=true`，直接返回 `application/octet-stream`。

写入文件请求体：

```json
{
  "encoding": "utf-8",
  "content": "项目背景..."
}
```

二进制写入使用：

```json
{
  "encoding": "base64",
  "content": "UEsDB..."
}
```

仅支持 `utf-8` 和 `base64`。其他 encoding 返回 400。

Workspace 访问控制：

- `mode=none` 或 `admin:runtime` 可直接访问。
- 普通 principal 只能访问自己 session 或 task 关联的 workspace。
- Runtime 会阻止路径穿越和越权访问，失败通常返回 `policy_denied`、403 或 FastAPI 404/400。

## 7. Agent API

### 7.1 读取 Agent

| 方法 | 路径 | Scope | 说明 |
| --- | --- | --- | --- |
| `GET` | `/agents` | `agents:read` | 返回可展示的 Agent summary 列表。summary 字段为 `agent_id`、`name`、`version`、`trust_level`、`description`。 |
| `GET` | `/agents/{agent_id}` | `agents:read` | 返回按 discovery policy 过滤后的 Agent manifest 视图。 |
| `GET` | `/agents/{agent_id}/files/content?virtual_path=<path>&download=false` | `agents:read` | 读取 Agent 声明 resource mount 下的文件。 |

Runtime 会按 discovery policy 过滤可见 Agent；读取资源文件时还会要求目标 Agent 对当前 principal 可见并允许 chat/A2A 发现。

Agent resource 文件读取规则：

- `virtual_path` 必须以 `/` 开头。
- Runtime 选择最长匹配的 directory resource mount。
- 路径穿越返回 403。
- `download=true` 返回 `application/octet-stream`。
- 非下载响应包含 `agent_id`、`virtual_path`、`encoding`、`content`、`size`。

### 7.2 动态 Agent 管理

以下接口需要 `admin:runtime` scope，用于在 Runtime 运行期间动态注册、删除和重载 Agent，无需重启服务。

| 方法 | 路径 | Scope | 说明 |
| --- | --- | --- | --- |
| `POST` | `/agents` | `admin:runtime` | 上传 Agent 压缩包（`.zip` 或 `.tar.gz`），解压到 `agents_dir`，校验并触发 registry reload。 |
| `POST` | `/agents/{agent_id}/delete` | `admin:runtime` | 删除 `agents_dir` 下对应的 agent 目录，触发 registry reload。 |
| `POST` | `/agents/reload` | `admin:runtime` | 手动触发 registry reload，返回当前 agent 列表和 load diagnostics。 |

**上传 Agent（POST /agents）：**

- 请求体：`multipart/form-data`，字段名为 `file`，上传 `.zip` 或 `.tar.gz` 文件。
- 查询参数：`overwrite`（`boolean`，默认 `false`）— 是否覆盖同名已有 agent。
- 压缩包内必须包含一个 `AGENT.yaml`（可位于任意子目录深度）。
- 成功响应：

```json
{
  "agent_id": "my-agent",
  "message": "agent my-agent registered successfully"
}
```

- 错误场景：
  - 不支持的格式 → 400
  - 缺少 AGENT.yaml 或校验失败 → 400
  - agent_id 已存在且未传 `overwrite=true` → 400

**删除 Agent（POST /agents/{agent_id}/delete）：**

- 直接删除 `agents_dir/<agent_id>/` 目录，随后触发 reload。
- 若被删 agent 被其他 agent 的 manifest 以 `registry://` 或 `agent:` 引用为子 agent，reload 阶段会检测到引用断裂并拒绝此次操作（保持当前 registry 不变），API 返回 409 及冲突详情。
- 成功响应：

```json
{
  "agent_id": "my-agent",
  "message": "agent my-agent deleted successfully"
}
```

- agent_id 不存在 → 404。
- 删除前会创建备份目录；若 reload 失败则自动恢复。

**手动 Reload（POST /agents/reload）：**

- 立即触发一次全量 registry 扫描（等价于文件系统变更后的自动 reload）。
- 响应包含当前 agent 数量、agent 列表和 load 诊断信息：

```json
{
  "agent_count": 5,
  "agents": [
    {"agent_id": "agent-a", "name": "Agent A", "version": "1.0.0"}
  ],
  "diagnostics": []
}
```

**文件系统自动监控：**

Runtime 默认启用文件系统监控（可通过 `AGENT_RUNTIME_WATCH_AGENTS=false` 关闭）。当 `agents_dir` 下发生文件变更（新建、修改、删除目录或 AGENT.yaml），会在 0.5 秒防抖后自动触发 registry reload。无需手动调用 `/agents/reload`。

**对运行中任务的影响：**

动态加载不影响已在运行的任务——`TaskRecord.agent_manifest_snapshot` 在任务创建时已冻结 manifest，新任务使用 reload 后的新 manifest。

## 8. Agent Teams（多 Agent 团队）

Agent Teams 是声明式多 Agent 协作模式。主 Agent 通过 `subagents` 声明团队成员（使用 `path: ./agents/<name>` 相对路径），在 Task 执行时通过 `task(subagent_type=...)` 将子任务委托给团队成员。

Agent Teams 的使用方式与普通 Agent 完全一致：
- 创建 Session 并指定主 Agent 的 `agent_id`
- 启动 Task 后，主 Agent 自动规划并调度子 Agent
- 子 Agent 的执行事件通过主 Task 的 SSE 流统一输出
- Workspace 文件、产物等与普通 Agent Task 一致

Agent Teams 的 API 接入不引入新的端点和请求格式，现有 Session/Task/Workspace API 完全适用。

## 9. Runtime Context、资源化与回滚

AgentRuntime 默认使用 refs-first Runtime Context：TaskRunner 会在冻结 manifest 后解析模型与 runtime 配置，使用 LangChain/local token counting 估算预算，读取 summary/history/memory/resource refs，并把受控的 `## Runtime Context` 追加到 `instructions_effective`。ContextPackage 和 middleware snapshot 只保存引用、checksum、token stats、trim decision 类型等安全元数据，不保存 prompt 正文、history 大正文、memory 大正文或 stdout/stderr 原文。

常用 manifest 配置：

```yaml
context:
  engineering:
    mode: refs_first  # 默认；回滚可设为 legacy_runtime_context
  session_history:
    enabled: true
    scope: same_session_all_agents  # 或 same_session_same_agent
    max_messages: 20
  summary:
    enabled: true
    auto_update: true
    mode: hierarchical_summary
    target_tokens: 800
  large_tool_results:
    mode: summary_resource_ref
    target: workspace://.runtime/context/
```

关键语义：

- 内网模式默认不调用 OpenAI、Anthropic 等 provider token API；token source/confidence 会写入 Runtime Context stats、ContextPackage 和 metrics。
- 大 stdout/stderr、长 history、G4-approved 大 memory 会写入 workspace `.runtime/context/`，模型只看到 preview/ref/checksum/read hint。
- G4-denied memory 不进入 prompt，也不会生成可读 resource ref。
- `context.engineering.mode=legacy_runtime_context` 会跳过 refs-first Runtime Context 注入，用于灰度回滚；ContextPackage 的基础 message/resource 引用仍保留。
- `.runtime/context/` 是 Runtime 内部上下文资源区，不会满足普通用户产物 acceptance 校验，也不会出现在用户 workspace artifact 列表中。

运维与审计定位：

- `TaskRecord.agent_manifest_snapshot._runtime` 保存本次执行的安全诊断投影，常见字段包括 `resolved_model_profile`、`runtime_resolution_explanations`、`context_package`、`runtime_context_snapshot`、`effective_tool_snapshot`、`agent_catalog`、`deepagents`、`thread_binding_id`、`run_kind`、`persistence`、`workspace_id`、`session_id`、`task_id`、`owner_user_id`、`owner_principal_id`、`subject_user_id`、`mcp_stdio_profiles`、`daytona_url`、`skill_activation`、`memory_snapshot`、`prompt_cache`、`output_refs`。
- `TaskRecord.agent_manifest_snapshot._runtime.context_package.checksum` 用于确认本次模型请求使用的 ContextPackage 投影；`context_package` 还包含 message/summary/resource/dynamic context ref 计数、trim decisions 和 runtime context 安全摘要。
- `TaskRecord.agent_manifest_snapshot._runtime.runtime_context_snapshot` 保存当前 effective runtime config 投影，包括 capability request、预算、声明式 main agent、effective permissions/limits、执行 profile、workspace isolation、subagent policy、model router、orchestration、preset MCP、warnings 和 resolution explanations；不含 selected message ids 或正文。
- `TaskRecord.middleware_snapshot.notes` 可包含 `context_package`、`skill_activation`、`memory_snapshot`、`runtime_diagnostics` 等安全摘要。
- `output_refs` 可出现在 `agent_manifest_snapshot._runtime.output_refs`、Task API 顶层响应和 diagnostics `artifacts.output_refs` 中，用于暴露最终输出提取到的产物引用。
- `runtime_context_budget` metric 记录 `context_window`、section budgets、used tokens、`final_prompt_estimated_tokens`、`token_count_source` 和 shadow adaptive action。
- `runtime_context_summary` metric 记录 summary 自动更新的 updated/skipped/failed 状态。
- `runtime_task` metric 会在 LangChain usage metadata 可用时记录 `actual_input_tokens`、`output_tokens`、`total_tokens` 和 `usage_metadata_source`。
- `sandbox.policy_decision` audit 记录 code execution backend 选择、trust、workspace/sandbox、allowlist/env 计数；不记录命令正文或 env 明文。
- `sandbox.execute` audit 记录 exit code、timeout、output refs/checksum 和 redaction metadata。

上线验收与回滚：

1. 运行计划中的 context、summary、artifact、sandbox、workspace、audit、TaskRunner 回归测试，以及 `git diff --check`。
2. 验证部署环境没有启用外部 provider token counting；内网默认应使用 LangChain/local/heuristic source。
3. 验证 secret/env 明文不出现在 prompt、RuntimeEvent、AuditEvent、snapshot、logs 和 resource preview。
4. 验证 backend unavailable、workspace mismatch、required backend missing 进入 `platform_recovery`。
5. 灰度建议按 agent/session/workspace 维度逐步开启；若发现 token 低估、resource read failure、summary 质量问题，可将目标 Agent 配置为 `context.engineering.mode=legacy_runtime_context` 回滚。

## 10. A2A API

A2A API 用于本地 Agent-to-Agent 调用。

```http
POST /a2a/invoke
```

请求体 `LocalA2AInvokeRequest`：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `agent_id` | `string` | 是 | 无 | 被调用 Agent。该 Agent 必须声明 `exposes_a2a=true`。 |
| `input` | <code>string &#124; object</code> | 是 | 无 | 传给目标 Agent 的输入。 |
| `workspace_id` | <code>string &#124; null</code> | 否 | `null` | 指定 A2A workspace。 |
| `caller_task_id` | <code>string &#124; null</code> | 否 | `null` | 调用方 task，用于继承信任等级和 agent path。 |
| `requested_trust` | <code>platform &#124; verified &#124; untrusted &#124; null</code> | 否 | `null` | 请求的目标信任等级。 |
| `metadata` | `object` | 否 | `{}` | 调用方元数据。 |
| `timeout` | <code>integer &#124; null</code> | 否 | `null` | 等待目标 Agent 完成的秒数。超时会取消 task。 |
| `system_prompt_append` | <code>string &#124; null</code> | 否 | `null` | 追加系统提示。 |
| `system_prompt_override` | <code>string &#124; null</code> | 否 | `null` | 覆盖系统提示。 |
| `dynamic_context` | <code>object &#124; null</code> | 否 | `null` | 动态上下文。 |

调用方需要具备 `tasks:start` 和 `agents:read` scope。Runtime 未就绪时返回 503。

响应 `A2AInvokeResponse`：

```json
{
  "task_id": "a2a-task-id",
  "status": "completed",
  "output": "风险评估结果...",
  "requires_input": false,
  "interrupt": null
}
```

目标 Agent 进入等待态时：

```json
{
  "task_id": "a2a-task-id",
  "status": "requires_input",
  "output": null,
  "requires_input": true,
  "interrupt": {"prompt": "需要用户确认是否继续", "reason": "human_input_required"}
}
```

## 11. Callback API

外部系统可通过 callback 恢复等待中的 task。

```http
POST /callbacks/{wait_id}
```

当前 route 不读取 principal scope，而是由 `RuntimeService.deliver_external_callback()` 校验 Runtime 生成的 callback binding 和签名头。请求需要携带：

| Header | 说明 |
| --- | --- |
| `X-AgentRuntime-Timestamp` | 签名时间戳。 |
| `X-AgentRuntime-Nonce` | 一次性 nonce。 |
| `X-AgentRuntime-Signature` | HMAC 签名。 |

Runtime 会读取原始 body；若 body 是 JSON，则作为 JSON 传入恢复输入，否则以文本传入。成功响应：

```json
{
  "task_id": "9d2f...",
  "status": "running"
}
```

若 callback binding 不存在、过期、签名缺失或签名错误，返回 `unauthenticated`；nonce 重复使用返回 `idempotency_conflict`。

## 12. Runtime 运维 API

### 12.1 健康与就绪

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/runtime/health` | 进程存活检查，返回 `{"status":"ok"}`。 |
| `GET` | `/runtime/ready` | 就绪检查。返回 preflight report，并额外包含 `production_ready`；ready=false 时返回 503。 |
| `GET` | `/runtime/preflight` | 完整 preflight report。 |
| `GET` | `/runtime/production-readiness` | 生产就绪检查；未通过时返回 503。 |
| `GET` | `/runtime/capability-health` | 仅返回 capability checks。 |
| `GET` | `/runtime/deployment` | 返回不含密钥的部署配置快照。 |
| `GET` | `/runtime/diagnostics` | 面向 operator 的诊断投影。 |

`/runtime/production-readiness` 返回 `ready_for_production`、`deployment_profile`、`runtime_core`、`preflight_ready`、`validation_issues`、`production_safety_checks`、`blocking_profiles`、`suggested_actions`。

`/runtime/deployment` 是结构化配置快照，常见字段包括 `runtime_version`、`deployment_profile`、`runtime_core`、`session_runtime_model`（统一 Session 模型 v1 常量）、`database_configured`、`daytona_configured`、`observability`、`stores`（含 `task_store`、`session_store`、`event_store`、`checkpoint`、`durable_checkpoint`）、`task_lifecycle`（含 `task_persistence`、`resume_waiting_task`、`resume_after_restart`、`checkpoint_backend`）、`capabilities`（含 `code_execution`、`memory`、`observability`）、`config_refs`、`settings_checksum`、`paths`、`logging`、`default_model_configured`、`data_retention`。

`/runtime/diagnostics` 包含：`deployment`（完整的 deployment snapshot）、`preflight_ok`、`preflight_ready`、`ready_for_production`、`deployment_profile`、`runtime_core`、`database_configured`、`task_lifecycle`、`skip_auto_migrate`、数据库迁移状态、`checks`、`capability_checks`、`validation_issues`、`production_safety_checks`。Task snapshot 中的 `_runtime.resolved_model_profile` 与 `_runtime.runtime_resolution_explanations` 可用于 operator 侧追踪模型解析结果，以及 Runtime 如何将 Agent capability request 解析为 effective grants。

### 12.2 数据保留与清理

以下接口需要 `admin:runtime` scope：

```http
POST /runtime/maintenance/purge-soft-deleted-sessions?limit=100
POST /runtime/maintenance/run-data-retention?scope=all&session_limit=100
```

`run-data-retention.scope` 可选：

| scope | 行为 |
| --- | --- |
| `all` | 执行 session、runtime event、memory 三类清理。 |
| `sessions` | 物理清理超过保留窗口的软删除 session。 |
| `events` | 删除超过保留窗口且属于终态 task 的 RuntimeEvent。 |
| `memory` | 调用 memory store 清理过期 memory record。 |

清理是否生效由环境变量或 `RuntimeSettings` 中的数据保留配置决定。

## 13. Logs API

日志查询接口默认关闭，仅当 `AGENT_RUNTIME_ENABLE_LOG_QUERY=true` 或 `RuntimeSettings.enable_log_query=True` 时可用。

```http
GET /logs/search?log_type=tool&task_id=<task_id>&limit=100
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `log_type` | <code>tool &#124; llm &#124; audit &#124; metrics &#124; app &#124; error &#124; lifecycle</code> | 要查询的日志类型。 |
| `request_id` | `string` | 按请求 ID 过滤。 |
| `trace_id` | `string` | 按 trace ID 过滤。 |
| `correlation_id` | `string` | 按 correlation ID 过滤。 |
| `tenant_id` | `string` | 按租户过滤。 |
| `session_id` | `string` | 按 session 过滤。 |
| `task_id` | `string` | 按 task 过滤。 |
| `agent_id` | `string` | 按 agent 过滤。 |
| `level` | `string` | 精确日志等级。 |
| `level_gte` | `string` | 最低日志等级。 |
| `from` / `to` | `string` | 时间范围。 |
| `limit` | `integer` | 返回条数，1-500。默认 100。 |
| `offset` | `integer` | 偏移。默认 0。 |
| `scan_max` | `integer` | 最多扫描行数，1-50000。默认 5000。 |

响应：

```json
{
  "items": [],
  "total_approx": 0,
  "log_type": "tool",
  "scanned": 0
}
```

若日志查询关闭，返回 404。

## 14. Python 嵌入式 SDK

AgentRuntime 也可作为 Python 库嵌入业务服务。公共入口：

```python
from agent_runtime import RuntimeService, RuntimeSettings
from agent_runtime.runtime.models import CreateSessionRequest, StartTaskRequest
```

### 14.1 从显式设置创建 RuntimeService

```python
from pathlib import Path
from agent_runtime import RuntimeService, RuntimeSettings

settings = RuntimeSettings(
    agents_dir=Path("examples"),
    schema_path=Path("schemas/agent.schema.json"),
    workspace_root=Path("workspaces"),
    deployment_profile="embedded_library",
    runtime_core="fake",
)

runtime = RuntimeService.from_settings(settings)
await runtime.initialize()
```

### 14.2 从环境变量创建 FastAPI App

```python
from agent_runtime.api.app import create_app

app = create_app()
```

`create_app()` 会调用 `runtime_settings_from_environment()` 构造 `RuntimeSettings`，并在 FastAPI lifespan 中执行 `runtime.initialize()`。

### 14.3 直接调用 RuntimeService

```python
from agent_runtime.runtime.models import CreateSessionRequest, StartTaskRequest

session = await runtime.create_session(
    CreateSessionRequest(
        title="嵌入式调用示例",
        trust_level="verified",
        agent_id="anp-default-agent",
    )
)

task = await runtime.start_task(
    StartTaskRequest(
        session_id=session.session_id,
        agent_id="anp-default-agent",
        input="总结 workspace 中的文件",
    )
)

async for event in runtime.stream_task(task.task_id):
    print(event.event, event.payload)

completed = await runtime.get_task(task.task_id)
print(completed.final_output)
```

常用 SDK 方法：

| 方法 | 说明 |
| --- | --- |
| `RuntimeService.from_settings(settings)` | 构建 runtime、registry、stores、workspace manager、task runner。 |
| `initialize()` | 检查 license、执行 preflight 启动策略、加载 agent registry。 |
| `create_session(request)` | 创建 session。 |
| `list_sessions(...)` / `get_session(...)` | 查询 session。 |
| `update_session(...)` / `delete_session(...)` / `restore_session(...)` | 修改、删除、恢复 session。 |
| `get_session_state(...)` | 获取 session 状态（含 tasks、messages 投影）。 |
| `list_session_messages(...)` | 查询 session 消息。 |
| `start_task(request)` | 启动 task。 |
| `stream_task(task_id, after_sequence=None)` | 返回异步 RuntimeEvent 迭代器。 |
| `list_task_events(task_id, after_sequence=None, limit=200)` | 查询持久化事件。 |
| `get_task(task_id)` / `list_tasks(...)` | 查询 task。 |
| `get_task_diagnostics(task_id)` | 获取 task 级诊断信息。 |
| `resume_task(task_id, request)` | 恢复等待中的 task。 |
| `cancel_task(task_id)` | 取消 task。 |
| `list_agents()` / `get_agent(agent_id)` | 查询 agent registry。 |
| `agent_manager.upload_agent(file_path, overwrite=False)` | 上传并注册 Agent 压缩包。 |
| `agent_manager.delete_agent(agent_id)` | 删除 Agent 目录并 reload registry。 |
| `agent_manager.reload()` | 手动触发 registry reload，返回 agent 列表。 |
| `invoke_local_agent(request)` | 本地 A2A 调用。 |
| `delegate_agent_from_tool(...)` | 工具调用中创建委托子 task。 |
| `resume_delegated_agent_from_tool(...)` | 恢复委托子 task。 |
| `deliver_external_callback(wait_id, ...)` | 投递外部 callback。 |
| `preflight_report()` | 获取 preflight report。 |
| `deployment_config_snapshot()` | 获取部署快照。 |
| `purge_soft_deleted_sessions_for_retention(...)` | 清理软删除 session。 |
| `purge_runtime_events_for_retention(...)` | 清理过期 RuntimeEvent。 |
| `purge_expired_memory_records_for_retention(...)` | 清理过期 memory record。 |
| `run_data_retention_maintenance(...)` | 执行统一数据保留维护。 |
| `backfill_workspace_ownership(...)` | 回填 workspace 所有权记录。 |

## 15. 环境变量配置

`runtime_settings_from_environment()` 会按以下顺序查找 deployment YAML 配置文件，再叠加环境变量：

1. `AGENT_RUNTIME_CONFIG_PATH` 环境变量
2. `<AGENT_RUNTIME_ROOT>/agent-runtime.yaml`
3. `<AGENT_RUNTIME_ROOT>/configs/dev.yaml`
4. `~/.config/agent-runtime/config.yaml`

未找到任何配置文件时使用全默认值（输出 warning 日志）。整体优先级为：显式构造参数 > 环境变量 > deployment YAML > 默认值。

常用环境变量：

| 环境变量 | 对应设置 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `AGENT_RUNTIME_ROOT` | 根目录 | `Path.cwd()` | 其他默认路径的基准。 |
| `AGENT_RUNTIME_CONFIG_PATH` | `runtime_config_path` | 无 | deployment YAML 路径。未设置时按自动发现顺序查找（见上方说明）。 |
| `AGENT_RUNTIME_AGENTS_DIR` | `agents_dir` | `$ROOT/agents` | Agent manifest 目录。 |
| `AGENT_RUNTIME_SCHEMA_PATH` | `schema_path` | `$ROOT/schemas/agent.schema.json` | Agent schema 路径。 |
| `AGENT_RUNTIME_WORKSPACE_ROOT` | `workspace_root` | `$ROOT/workspaces` | workspace 根目录。 |
| `AGENT_RUNTIME_DEPLOYMENT_PROFILE` | `deployment_profile` | `local_dev` | 部署形态。 |
| `AGENT_RUNTIME_CORE` | `runtime_core` | `deepagents` | `fake` 或 `deepagents`。 |
| `AGENT_RUNTIME_STORE_BACKEND` | store backend | deployment 配置 | `memory` 或 `postgres`；为 `postgres` 时读取数据库连接串。 |
| `AGENT_RUNTIME_DATABASE_URL` / `DATABASE_URL` | `database_url` | 无 | Postgres 连接串。 |
| `AGENT_RUNTIME_DAYTONA_URL` | `daytona_url` | 无 | Daytona 服务地址。 |
| `AGENT_RUNTIME_OBSERVABILITY` | `observability` | `noop` | `noop`、`otel`、`langfuse`。 |
| `AGENT_RUNTIME_LOGGING` | `logging` | `auto` | 日志模式。 |
| `AGENT_RUNTIME_LOG_DIR` | `log_dir` | `$ROOT/logs` | 日志目录。 |
| `AGENT_RUNTIME_LOG_LEVEL` | `log_level` | `INFO` | 日志等级。 |
| `AGENT_RUNTIME_ENABLE_LOG_QUERY` | `enable_log_query` | `false` | 是否启用 `/logs/search`。 |
| `AGENT_RUNTIME_LOG_JSON` | `log_json` | deployment 配置 | 是否输出 JSON 日志。 |
| `AGENT_RUNTIME_LOG_RETENTION_DAYS` | `log_retention_days` | deployment 配置 | 通用日志保留天数。 |
| `AGENT_RUNTIME_LOG_RETENTION_AUDIT_DAYS` | `log_retention_audit_days` | deployment 配置 | audit 日志保留天数。 |
| `AGENT_RUNTIME_LOG_RETENTION_ERROR_DAYS` | `log_retention_error_days` | deployment 配置 | error 日志保留天数。 |
| `AGENT_RUNTIME_LOG_FULL_PROMPT` | `log_full_prompt` | local_dev 默认为 true | 是否记录完整 prompt。生产环境不建议开启。 |
| `AGENT_RUNTIME_LOG_FULL_OUTPUT` | `log_full_output` | local_dev 默认为 true | 是否记录完整输出。生产环境不建议开启。 |
| `AGENT_RUNTIME_LOG_MAX_FIELD_CHARS` | `log_max_field_chars` | deployment 配置 | 单字段日志截断长度。 |
| `AGENT_RUNTIME_LOG_ALL_LLM_REQUESTS` | `log_all_llm_requests` | local_dev 默认为 true | 是否记录所有 LLM 请求日志。 |
| `AGENT_RUNTIME_MANIFEST_PATH` | `runtime_manifest_path` | `$ROOT/runtime/manifest.json` | Runtime license/manifest 路径。 |
| `AGENT_RUNTIME_WATCH_AGENTS` | `watch_agents` | `true` | 是否启用 `agents_dir` 文件系统监控，变更后自动 reload agent registry。 |
| `AGENT_RUNTIME_DEFAULT_MODEL_PROVIDER` | `default_model_provider` | 无 | 默认模型 provider；manifest `model.provider` 省略时可由 Runtime 补齐。 |
| `AGENT_RUNTIME_DEFAULT_MODEL` | `default_model` | 无 | 默认模型名。 |
| `AGENT_RUNTIME_DEFAULT_MODEL_MAX_INPUT_TOKENS` | `default_model_max_input_tokens` | deployment 配置 | 默认模型输入 token 上限。 |
| `AGENT_RUNTIME_DEFAULT_MODEL_MAX_OUTPUT_TOKENS` | `default_model_max_output_tokens` | deployment 配置 | 默认模型输出 token 上限。 |
| `AGENT_RUNTIME_AVAILABLE_MODEL_PROVIDERS` | `available_model_providers` | 空 | 逗号分隔 provider 列表。 |
| `AGENT_RUNTIME_PROVIDER_ALIAS_JSON` | `provider_alias` | `{}` | provider alias JSON。 |
| `AGENT_RUNTIME_MODEL_CATALOG_PATH` | `model_catalog_path` | 无 | 部署模型目录。 |
| `AGENT_RUNTIME_MODEL_HEALTHCHECK_ENABLED` | `model_healthcheck_enabled` | `false` | 是否启用模型健康检查。 |
| `AGENT_RUNTIME_MAX_MODEL_OUTPUT_RETRIES` | `max_model_output_retries` | `3` | 模型输出重试次数。 |
| `AGENT_RUNTIME_MCP_STDIO_PROFILES_JSON` | `mcp_stdio_profiles` | `{}` | MCP stdio profile JSON。 |
| `AGENT_RUNTIME_FAIL_STARTUP_ON_PREFLIGHT` | 启动策略 | `false` | preflight 失败时是否中止启动。 |
| `AGENT_RUNTIME_FAIL_STARTUP_ON_PRODUCTION_READINESS` | 启动策略 | deployment 配置 | production readiness 未通过时是否中止启动。 |
| `AGENT_RUNTIME_SKIP_AUTO_MIGRATE` | 迁移策略 | `false` | 是否跳过启动时 DB 自动迁移。 |
| `AGENT_RUNTIME_SESSION_DELETED_PURGE_DAYS` | session 保留 | 未设置 | 软删除 session 多少天后可物理清理。 |
| `AGENT_RUNTIME_RUNTIME_EVENT_RETENTION_DAYS` | event 保留 | 未设置 | RuntimeEvent 保留天数。 |
| `AGENT_RUNTIME_MEMORY_RECORD_PURGE_DAYS` | memory 清理 | 未设置 | 是否启用过期 memory 清理。 |

鉴权配置本身位于 `RuntimeSettings.api_auth`，可在嵌入式模式中显式传入 `ApiAuthSettings`，或由部署层按项目约定装配。

## 16. 前端 / BFF 推荐集成模式

### 16.1 Web Chat / 控制台

推荐 BFF 负责：

1. 持有 Runtime 凭据，不把长期 API key 暴露给浏览器。
2. 创建 session 和 task。
3. 调用 `/stream-token` 获取短期 token，再把 `stream_url` 返回浏览器。
4. 浏览器直接订阅 SSE，或由 BFF 转发 SSE。
5. 收到 `task_waiting` 后关闭 SSE，展示审批/输入 UI。
6. 用户提交后由 BFF 调用 `/resume`。

### 16.2 幂等与重试

- `POST /tasks` 建议总是传 `idempotency_key`，可使用业务单号 + 操作版本。
- `POST /tasks/{task_id}/resume` 对审批类操作也建议传 `idempotency_key`。
- SSE 断线后先用 `GET /tasks/{task_id}/events?after_sequence=<last>` 补齐，再重连 `/stream`。
- 对 `retryable=false` 的错误不要自动重试；对 429、临时网络错误或 `retryable=true` 可退避重试。

### 16.3 UI 状态投影

| 后端信号 | UI 状态 |
| --- | --- |
| task `pending` / `running` | loading。 |
| `message_delta` | assistant 消息流式输出。 |
| `tool_call_started` | 工具卡片执行中。 |
| `tool_call_completed` | 工具卡片完成。 |
| `workspace_update` | 刷新产物列表。 |
| `task_waiting` | 展示等待输入、审批或 callback 状态。 |
| task `completed` | 停止 loading，固化最终消息。 |
| task `failed` | 展示错误，提供复制详情和重试入口。 |
| task `cancelled` | 展示已取消。 |

## 17. 典型端到端示例

```bash
# 1. 创建 session
SESSION_ID=$(curl -s -X POST "$RUNTIME_URL/sessions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RUNTIME_TOKEN" \
  -d '{"title":"Demo","trust_level":"verified","agent_id":"anp-default-agent"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')

# 2. 启动 task
TASK_ID=$(curl -s -X POST "$RUNTIME_URL/tasks" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RUNTIME_TOKEN" \
  -d "{\"session_id\":\"$SESSION_ID\",\"agent_id\":\"anp-default-agent\",\"input\":\"请给出下一步建议\",\"idempotency_key\":\"demo-001\"}" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["task_id"])')

# 3. 获取短期 stream token
STREAM_URL=$(curl -s -X POST "$RUNTIME_URL/tasks/$TASK_ID/stream-token" \
  -H "Authorization: Bearer $RUNTIME_TOKEN" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["stream_url"])')

# 4. 订阅 SSE
curl -N "$RUNTIME_URL$STREAM_URL"

# 5. 查看最终 task
curl "$RUNTIME_URL/tasks/$TASK_ID" \
  -H "Authorization: Bearer $RUNTIME_TOKEN"
```

## 18. 常见问题排查

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `POST /tasks` 返回 `runtime_not_ready` | preflight 未通过，模型、数据库、sandbox 或 manifest 配置异常。 | 调用 `/runtime/ready` 和 `/runtime/preflight` 查看失败 checks。 |
| DeepAgents 持久化任务失败 | `runtime_core=deepagents` 但未配置 `database_url`，无法执行 `persistence=persisted` 的跨重启恢复任务。 | 配置 Postgres，或将任务持久化策略改为 `session` / `none`；测试环境也可改用 `runtime_core=fake`。 |
| 读取别人的 session/task 返回 403 | owner 校验失败。 | 确认 principal `user_id` / `subject.user_id` 与资源 owner 一致，或使用 `admin:runtime`。 |
| SSE 连接立即结束 | task 已终态，或最后事件为等待态。 | 查询 task 状态；等待态调用 `/resume`。 |
| SSE 重连后重复消息 | 客户端未按 `(task_id, sequence)` 去重。 | 保存最后 sequence，重连时使用 `after_sequence` 或 `Last-Event-ID`。 |
| final output 不在事件中 | `task_completed` 持久化事件默认只保留摘要。 | 读取 `GET /tasks/{task_id}` 的 `final_output` 或 `/sessions/{session_id}/messages`。 |
| workspace 文件读取 403 | workspace 不属于当前 principal，或路径策略拒绝。 | 检查 task/session `workspace_id` 和 owner；避免路径穿越。 |
| `/logs/search` 返回 404 | 日志查询未启用。 | 设置 `AGENT_RUNTIME_ENABLE_LOG_QUERY=true` 并确认 `log_dir`。 |
| A2A 返回 `Agent is not exposed for A2A` | 目标 Agent manifest 未声明 A2A 暴露。 | 修改目标 Agent 配置或改用普通 task。 |
| manifest 加载失败提示 v1 | Runtime 只接受 `anp-agent/v1.1` / `anp-agent/v1.2`，不再接受旧 `anp-agent/v1`。 | 按 [Manifest schema 文档](manifest-schema.md) 迁移到 v1.2 原生布局。 |

## 19. 相关文档

- [SDK 使用文档](sdk.md)
- [RuntimeEvent / SSE 事件契约](runtime-events-sse.md)
- [Manifest schema 文档](manifest-schema.md)
- [A2A 工具接入](a2a-tools.md)
- [Artifact acceptance 示例](artifact-acceptance.md)
- [上线排障手册](troubleshooting.md)
