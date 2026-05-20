# AgentRuntime 产品集成与声明式 Agent 开发指南

本文面向两类读者：

- **Agent 开发者**：需要编写一个 `AGENT.yaml`，声明模型、指令、工具、workspace、skills、subagents、acceptance，并在 AgentRuntime 中跑起来。
- **产品 / BFF / 平台接入方**：需要把 AgentRuntime 嵌入产品或作为 HTTP 服务接入，处理会话、任务、事件流、workspace、鉴权、多租户和上线 gate。

如果你是新接入者，推荐先完成第 1-6 节的开发闭环，再看第 7 节之后的产品集成与生产化内容。

## 1. AgentRuntime 中一个声明式 Agent 是什么

AgentRuntime 推荐用 `AGENT.yaml` 描述 Agent，而不是在业务代码里硬编码模型、工具和执行流程。

一个 Agent 至少包含：

```yaml
schema_version: anp-agent/v1.2
kind: Agent
metadata:
  id: demo-agent
  name: DemoAgent
  version: 1.0.0
  trust_level: verified
model:
  provider: dashscope
  model: qwen3-max
instructions: |
  你是一个简洁的项目助理。根据用户输入输出结构化结果。
```

核心原则：

- `AGENT.yaml` 声明“Agent 需要什么能力”。
- Runtime 根据 trust level、部署配置、policy、workspace、sandbox 和调用方权限决定“实际授予什么能力”。
- Task 启动时会冻结 manifest snapshot、middleware snapshot、effective tool snapshot、workspace 信息和上下文包，便于审计和排障。
- 文件型任务必须落到 workspace / artifact，不能只让模型回复“已生成”。

## 2. 声明式 Agent schema 速查

当前 Runtime 接受 `anp-agent/v1.1` 和 `anp-agent/v1.2`，新建 Agent 推荐使用 `anp-agent/v1.2`。权威 schema 见 [`schemas/agent.schema.json`](../schemas/agent.schema.json)。

### 2.1 顶层必填字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `schema_version` | 是 | 当前支持 `anp-agent/v1.1`、`anp-agent/v1.2`。新建使用 `anp-agent/v1.2`。 |
| `kind` | 是 | 固定为 `Agent`。 |
| `metadata` | 是 | Agent 身份、版本、信任等级和发现信息。 |
| `model` | 是 | 模型 provider、model name、温度、token、超时和 fallback。 |
| `instructions` / `instructions_template` | 二选一 | 静态系统指令或带动态变量的指令模板。两者互斥。 |

### 2.2 常用顶层字段

| 字段 | 用途 | 开发建议 |
| --- | --- | --- |
| `metadata` | `id`、`name`、`version`、`trust_level`、`capabilities`、`labels`、是否暴露 A2A / chat。 | `id` 使用小写短横线；`capabilities` 只用于发现，不是权限。 |
| `model` | 配置模型 provider、模型名、采样参数、超时、重试和 fallback。 | provider 可由部署默认值补齐，但生产 Agent 建议显式声明。 |
| `instructions` | Agent 的稳定行为约束。 | 写职责、边界、输出要求，不要写运行时才能确定的工具可用性。 |
| `instructions_template` + `required_caller_keys` | 需要调用方传动态上下文时使用。 | 缺少 required caller key 时由 `missing_context_policy` 决定等待或失败。 |
| `tools` | 声明 Runtime/API/A2A 工具。 | MCP 放 `mcp_servers`，Skill 放 `skills`，不要混进 `tools`。 |
| `mcp_servers` | 声明 MCP server 依赖。 | Task 启动时发现并冻结工具 schema。 |
| `skills` | 声明可复用能力包，例如 docx、pptx、pdf。 | 适合办公文档、垂直流程、可复用 SOP。 |
| `subagents` | 声明 DeepAgents 子 Agent，由 `task(subagent_type=...)` 调用。 | 可本地 path，也可 `ref: registry://...`；path 不能逃逸当前 Agent 目录。 |
| `resources` | 打包静态资源目录。 | 路径相对 `AGENT.yaml`。 |
| `prompt` | 声明运行态 prompt profile 和静态 section。 | MainAgent 推荐 `runtime_profile: main_agent_default`。 |
| `context` | 声明上下文通道、session history、优先级和压缩策略。 | 大模型上下文不是无限的，优先级应覆盖用户请求、worker/agent 目录和 recent history。 |
| `tool_policy` | 声明工具全集和默认 allowlist。 | 这是 Agent 侧意图，最终可见工具仍由 Runtime 裁剪。 |
| `session_state` | 声明会话状态隔离策略。 | 多租户场景应避免共享 Agent 状态污染。 |
| `workspace` | 声明 workspace 需求和访问能力。 | 文件读写、artifact、sandbox 都围绕 workspace 工作。 |
| `memory` | 声明 memory 读写需求。 | 合规场景默认更保守。 |
| `permissions` | 声明需要审批或受限操作。 | destructive / 高风险工具建议进入 approval。 |
| `limits` / `budgets` | 声明工具调用、subagent、时间、文件大小等预算建议。 | Runtime 可能按部署策略收紧。 |
| `capabilities` | 声明 workspace、code、network、artifacts、delegation 等能力需求。 | 这是 Runtime 授权和 sandbox 选择的重要输入。 |
| `acceptance` | 声明完成条件，例如必须生成哪些文件。 | 文件型任务必须配置或通过 task metadata 指定验收条件。 |
| `orchestration` | 声明执行模式、委托和输出装配偏好。 | MainAgent 可用 `planner_first` + capability routing。 |

### 2.3 trust level 的含义

| `trust_level` | 适用对象 | 典型限制 |
| --- | --- | --- |
| `platform` | 平台内置或强信任 Agent。 | 可获得更高权限，但仍受部署 policy 限制。 |
| `verified` | 经团队审核的业务 Agent。 | 常用默认值；可申请 workspace、code、network、subagents。 |
| `untrusted` | 外部或未审核 Agent。 | 默认最小能力，不能假定 code execution、subagents 或高风险工具可用。 |

Runtime 可以按 Session 或调用方降低有效信任等级，但不会把 Agent 提升到高于 manifest 声明的 trust level。

## 3. 从零开发一个最小 Agent

假设产品配置中的 `agents_dir` 指向 `agents/`，创建目录：

```bash
mkdir -p agents/demo-agent
```

写入 `agents/demo-agent/AGENT.yaml`：

```yaml
schema_version: anp-agent/v1.2
kind: Agent
metadata:
  id: demo-agent
  name: DemoAgent
  description: 生成项目摘要和待办建议的示例 Agent。
  version: 1.0.0
  trust_level: verified
  exposes_chat: true
  capabilities: [summary, planning]
model:
  provider: dashscope
  model: qwen3-max
  temperature: 0.2
  max_tokens: 4000
instructions: |
  你是项目助理。
  根据用户输入，输出：
  1. 关键进展
  2. 风险与阻塞
  3. 下一步建议
  保持简洁，不编造未提供的信息。
```

校验：

```bash
agent-runtime validate --config agent-runtime.yaml --product
```

`validate` 会加载 product config，并通过其中的 `agents_dir` 与 `schema_path` 校验可加载性；如果只想快速发现运行依赖问题，继续运行 `doctor`。

启动本地服务后，最小 HTTP 调用链路是：

```bash
export RUNTIME_URL="http://localhost:8000"

SESSION_ID=$(curl -s -X POST "$RUNTIME_URL/sessions" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"demo-agent","title":"demo"}' | jq -r .session_id)

TASK_ID=$(curl -s -X POST "$RUNTIME_URL/tasks" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"agent_id\":\"demo-agent\",\"input\":\"本周完成权限接口开发和联调，请生成摘要\"}" | jq -r .task_id)

curl "$RUNTIME_URL/tasks/$TASK_ID"
```

浏览器或 BFF 应使用 SSE：

1. `POST /tasks/{task_id}/stream-token` 获取短期 token。
2. `GET /tasks/{task_id}/stream` 订阅事件。
3. 收到 `task_waiting` 时调用 `POST /tasks/{task_id}/resume`。
4. 完成后读取 `TaskRecord.final_output`、`GET /sessions/{session_id}/messages` 或 workspace 文件。

## 4. 开发一个会生成真实文件的 Agent

文件型 Agent 需要显式声明 workspace、code/artifacts 能力和 acceptance。示例：

```yaml
schema_version: anp-agent/v1.2
kind: Agent
metadata:
  id: weekly-report-agent
  name: WeeklyReportAgent
  version: 1.0.0
  trust_level: verified
  capabilities: [office, docx, pptx]
model:
  provider: dashscope
  model: qwen3-max
instructions: |
  你是办公文档助理。
  当用户要求生成 Word、PPT、Excel 或 PDF 时，必须产出真实文件，不能只返回大纲。
  生成物写入 /output/，最终回复只引用实际创建或注册过的文件路径。
capabilities:
  workspace:
    required: true
    access:
      read: true
      write: true
      delete: false
  code:
    required: true
    languages: [python, bash]
    commands:
      patterns:
        allow:
          - python *
          - mkdir *
  artifacts:
    required: true
    output_paths: [/output]
tool_policy:
  capabilityToolUniverse:
    - kind: runtime
      name: read_file
    - kind: runtime
      name: write_file
    - kind: runtime
      name: execute
    - kind: runtime
      name: artifact_validate
    - kind: runtime
      name: artifact_register
  defaultAllowlist:
    - read_file
    - write_file
    - execute
    - artifact_validate
    - artifact_register
acceptance:
  required_files:
    - path: /output/*
      type: any
      min_size_bytes: 1024
```

开发注意事项：

- `capabilities.code.commands` 是 Agent 侧申请；最终是否允许执行由 Runtime policy 和 sandbox backend 决定。
- 生产环境不要让 Agent 依赖任意 `pip install` 或任意 shell；优先使用预置镜像、受控 command allowlist 或专用 Runtime 工具。
- 最终答复中的文件路径必须来自真实工具结果、`artifact_register` 或 `artifact_validate`。
- `acceptance.required_files` 是防止“文本说完成但文件不存在”的关键机制。

## 5. 使用 Skill、MCP、Subagent 和 A2A

这四类扩展能力解决的问题不同：

| 能力 | 写在哪里 | 调用方式 | 适用场景 |
| --- | --- | --- | --- |
| Skill | `skills[]` | Runtime 激活资源和说明，由 Agent 按 Skill 文档执行。 | 办公文档、垂直 SOP、可复用流程。 |
| MCP | `mcp_servers` | Task 启动时发现工具 schema，模型按工具调用。 | 外部工具服务、浏览器、检索、内部系统。 |
| Subagent | `subagents[]` | DeepAgents `task(subagent_type=...)`。 | 同一 Runtime graph 内的静态 worker。 |
| A2A / Runtime Agent | `tools` / `agent_catalog` | `delegate_agent(agent_id=...)` 或 `/a2a/invoke`。 | 跨 Agent 协作、外部业务 Agent、审批专员。 |

### 5.1 声明 Skill

参考 [`examples/skill-agent/AGENT.yaml`](../examples/skill-agent/AGENT.yaml)：

```yaml
skills:
  - id: docx
    description: Word .docx：创建、编辑、批注、模板、格式化和校验。
    path: ./skills/docx
    activation:
      mode: auto
      required_when: [docx, DOCX, Word, word文档, 文档]
```

Skill 适合沉淀“怎么做”的知识和资源。Agent instructions 中只需要说明何时必须使用 Skill，不要把 Skill 文档复制到主 prompt。

### 5.2 声明 Subagent / Worker

Subagent 适合 MainAgent 规划后委托静态 worker。可以直接声明本地子 Agent，也可以复用 registry 中的 Agent：

```yaml
subagents:
  - id: office-document-worker
    ref: registry://skill-agent
    name: 通用办公任务助手
    description: 根据用户需求创作、编辑、转换和处理常见办公文档。
    metadata:
      capabilityTags: [office, document, docx, xlsx, ppt, pptx, pdf]
      entrypoint: subagent://office-document-worker
      supportedFormats: [docx, xlsx, pptx, pdf, txt, markdown]
```

约束：

- `path` 型 subagent 必须在当前 Agent 目录边界内，不能用 `../` 逃逸到兄弟目录。
- 复用其他 Agent 时优先用 `ref: registry://<agent-id>`。
- 带 `metadata.capabilityTags` / `entrypoint` 的声明式 worker 会进入 `workers_catalog`，模型应使用 `task(subagent_type=<worker_id>)`。
- 对 Runtime 动态 Agent，不走 `task`，而是使用 `delegate_agent(agent_id=...)`。

### 5.3 MainAgent 的目录与委托规则

企业办公 MainAgent 推荐从 [`examples/main-agent/AGENT.yaml`](../examples/main-agent/AGENT.yaml) 开始。关键配置：

```yaml
prompt:
  runtime_profile: main_agent_default
  runtime_profile_overrides:
    agent_catalog:
      policy:
        top_k: 100
        include_reason: true
context:
  session_history:
    enabled: true
    scope: same_session_all_agents
    max_messages: 20
  channels:
    message:
      prependUserContextReminder: true
      sources:
        - project_instructions
        - current_date
        - user_profile
        - task_constraints
        - workers_catalog
        - agent_catalog
tool_policy:
  defaultAllowlist:
    - task
    - delegate_agent
    - artifact_validate
    - artifact_register
```

`main_agent_default` 会自动注入：

- `workers_catalog`：静态 DeepAgents worker 目录，用 `task(subagent_type=...)`。
- `agent_catalog`：Runtime 动态 Agent 目录，用 `delegate_agent(agent_id=...)`。
- `task_context`：文件交付、多交付物、匹配 worker 等结构化任务上下文。
- `session_guidance`：对文件交付任务提示模型完整传递用户需求，不要用“如上”“用户提供的内容”等占位描述。

Runtime 还会保留 `original_graph_input`，并通过 `DelegationInputGuardMiddleware` 拦截空壳委托：当原始请求是长文本文件交付任务时，`task(...)` 的 description 必须包含完整源内容和全部交付要求，不能只写“根据用户提供的详细内容生成文档”。

## 6. 本地运行与调试闭环

推荐开发闭环：

```bash
# 1. 初始化产品配置
agent-runtime init --profile local_dev --product-name "Agent Dev"

# 2. 校验 Agent manifest
agent-runtime validate --config agent-runtime.yaml --product

# 3. 运行 doctor，检查模型、数据库、workspace、sandbox、auth、retention 等配置
agent-runtime doctor --config agent-runtime.yaml --product

# 4. 启动服务
agent-runtime serve --config agent-runtime.yaml --product --require-doctor
```

如果你使用 deployment config 而不是 product config，可以在初始化时生成 deployment 形态：

```bash
agent-runtime init --profile standalone_internal_service --product-name "AgentRuntime" --deployment-config
```

开发时重点看：

- `GET /agents`：Agent 是否被 registry 发现。
- `GET /tasks/{task_id}/diagnostics`：task、session、agent、policy、tools、subagents、sandbox、workspace、model、context、artifacts、events、errors、runtime、suggested_actions。
- `GET /runtime/preflight`：运行前依赖是否可用。
- `GET /runtime/diagnostics`：部署快照、migration、validation issues、production safety checks。
- `GET /runtime/production-readiness`：生产上线 gate；未 ready 时返回 503。

## 7. Embedded SDK 集成

适合把 Runtime 作为产品内部执行内核：

```python
from agent_runtime import RuntimeService
from agent_runtime.runtime.product_config import ProductRuntimeConfig
from agent_runtime.runtime.models import CreateSessionRequest, StartTaskRequest

runtime = RuntimeService.for_product(ProductRuntimeConfig(
    product_name="Demo",
    profile="embedded_single_tenant",
    agents_dir="agents",
))
await runtime.initialize()

session = await runtime.create_session(CreateSessionRequest(
    agent_id="demo-agent",
    workspace_id="tenant-a/session-1",
))

task = await runtime.start_task(StartTaskRequest(
    session_id=session.session_id,
    agent_id="demo-agent",
    input="生成本周项目摘要",
))
```

`RuntimeService.for_product(...)` 接受 `ProductRuntimeConfig` 或 dict。Runtime 会先把产品意图映射到 `DeploymentConfig`，再生成 `RuntimeSettings`，因此产品侧优先维护 product config，不要手工拼底层 runtime settings。

验收点：

- `create_session` 写入 session ownership。
- `start_task` 写入 task ownership。
- 必要时可执行 workspace ownership backfill。
- `runtime.get_task_diagnostics(task_id)` 能看到 context、policy、workspace ownership、effective tools、recent events 和 runtime validation 信息。
- 文件型任务通过 workspace / artifact API 验收真实产物。

## 8. Standalone HTTP 集成

适合把 AgentRuntime 作为内部 HTTP 服务接入：

1. `POST /sessions` 创建 session。
2. `POST /tasks` 启动 task。
3. `POST /tasks/{task_id}/stream-token` 换取浏览器 EventSource token。
4. `GET /tasks/{task_id}/stream` 订阅 RuntimeEvent。
5. `GET /sessions/{session_id}/state` 恢复 UI 状态。
6. `GET /workspaces/{workspace_id}/files` / `GET|PUT /workspaces/{workspace_id}/files/content` 读写文件。
7. `GET /tasks/{task_id}/diagnostics` 排查失败。
8. `GET /runtime/ready`、`GET /runtime/preflight`、`GET /runtime/diagnostics`、`GET /runtime/production-readiness` 做运维和上线 gate。

推荐用 `agent-runtime contracts --config agent-runtime.yaml --product --output-dir contracts` 生成 Python / TypeScript SDK 模板封装这些路径。

## 9. 鉴权、多租户与 workspace ownership

生产类 profile 禁止 `api_auth.mode=none`。这不是文档约定，而是 preflight / production-readiness 会检查的上线阻断项。

常见选择：

- 内部服务：`static_api_key` 或 `trusted_gateway`。
- 用户态 SaaS：`jwt_jwks`，claims 中包含 user、tenant、scopes。
- 平台网关统一鉴权：`trusted_gateway`，由上游注入并签名 principal。

Profile 默认倾向：

| Profile | 典型鉴权 |
| --- | --- |
| `local_dev` | `none`，仅限本地开发。 |
| `embedded_single_tenant` | 可使用本地或产品内鉴权。 |
| `standalone_internal_service` | 常用 `static_api_key`。 |
| `embedded_multi_tenant` | 常用 `trusted_gateway` 或 JWT/JWKS。 |
| `regulated_enterprise` | 强制显式 auth、db、sandbox、retention。 |

Workspace API 优先使用 ownership store 授权；没有 ownership 记录时再回溯 session/task 归属。普通用户只能访问自己拥有或代表的 session/task workspace，operator/admin 可旁路。

## 10. Context、Memory 与 Diagnostics

产品配置中的 `context_mode` 会映射到运行态上下文模式：

| 产品配置 | 运行态模式 | 说明 |
| --- | --- | --- |
| `minimal` | `regulated_minimal` | 最小上下文，默认禁用 memory write。 |
| `full` | `long_running_case` | 更多历史、summary、memory retrieval/write。 |
| 默认 | `session_memory` | 平衡 session history、summary 和 approved memory retrieval。 |
| `regulated_enterprise` profile | `regulated_minimal` | 合规优先。 |

多租户场景还会影响 session state isolation：`tenant_mode=multi` 倾向 `isolated_agent_state`，单租户可使用共享 workspace 模式。

Diagnostics 中重点看：

- `context.mode_resolution`
- `context.memory_snapshot`
- `context.runtime_context`
- `policy.denials[].reason_code`
- `tools.effective_tool_snapshot`
- `workspace.ownership`
- `artifacts.acceptance` / `artifacts.output_refs`
- `runtime.validation_issues` / `runtime.production_safety_checks`
- `suggested_actions`

## 11. Advisor Strategy（Model Router）

`model_router` 属于 runtime / deployment 配置层，不放在 `AGENT.yaml`。默认关闭，只有产品或部署配置显式启用才会进入 advisor 路径。

推荐策略为 `advisor_first`，advisor 固定 `replan_only`：

```yaml
model_router:
  enabled: true
  strategy: advisor_first
  advisor:
    provider: fake
    model: advisor-model
    mode: replan_only
  triggers:
    stall:
      tool_error_streak: 1
      no_progress_turns: 2
  governance:
    allow_multi_advisor_rounds: true
    limits: none
    high_risk_alert:
      enabled: true
      non_blocking: true
```

接入侧应消费 `runtime_update` 事件中的 `payload.kind`，至少覆盖：

- `advisor_triggered`
- `model_router_state_transition`（`advisor_pending` / `replan_applied`）
- `advisor_plan_generated`
- `advisor_plan_applied`
- `advisor_call_failed`
- `advisor_patch_rejected`
- `advisor_unavailable_single_model`

单模型场景会进入 `single_model_mode` 并继续 executor 路径，不中断任务。

## 12. 生产 readiness checklist

上线前最小检查：

- `agent-runtime validate --config agent-runtime.yaml --product`
- `agent-runtime doctor --config agent-runtime.yaml --product --strict-production`
- `GET /runtime/preflight` 无 blocker。
- `GET /runtime/production-readiness` 返回 ready；未 ready 时该接口返回 503。
- Postgres migrations 已执行。
- auth/scopes/tenant claims 覆盖 session、task、workspace、agents discovery。
- workspace ownership store 已接入并可回溯 session/task 归属。
- Daytona / sandbox backend 与 command policy 覆盖文件型任务。
- 文件型 Agent 使用 workspace / artifact / acceptance 验收真实产物。
- observability fields、dashboard 和日志查询已接入。

后续阅读：

- [AgentRuntime API 接入文档](agent-runtime-api-cn.md)
- [团队培训材料](agent-runtime-team-training.md)
- [配置矩阵与迁移指南](configuration-migration-guide.md)
- [MainAgent worker 委托修复计划](main-agent-runtime-worker-delegation-remediation-plan.md)
