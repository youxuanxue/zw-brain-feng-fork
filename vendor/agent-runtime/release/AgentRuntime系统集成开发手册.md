# AgentRuntime 系统集成开发手册

> 版本：v1.1.2 | 协议版本：anp-agent/v1.2 | 最后更新：2026-06-11

---

## 目录

- [第一章 系统总览](#第一章-系统总览)
- [第二章 快速开始](#第二章-快速开始)
- [第三章 Agent Manifest 声明式契约](#第三章-agent-manifest-声明式契约)
- [第四章 核心架构](#第四章-核心架构)
- [第五章 API 参考](#第五章-api-参考)
- [第六章 配置参考](#第六章-配置参考)
- [第七章 扩展机制与插件开发](#第七章-扩展机制与插件开发)
- [第八章 部署运维指南](#第八章-部署运维指南)
- [第九章 安全模型](#第九章-安全模型)
- [第十章 测试指南](#第十章-测试指南)
- [第十一章 故障排除](#第十一章-故障排除)
- [附录](#附录)

---

## 第一章 系统总览

### 1.1 什么是 AgentRuntime

AgentRuntime 是一个面向**声明式 Agent** 的执行引擎（harness），用于加载 `AGENT.yaml` 定义的 Agent、创建会话和任务、执行模型与工具循环、管理工作区和产物文件，并通过 RuntimeEvent/SSE 对外暴露可审计的执行过程。

核心设计原则：

- **声明式 Agent**：Agent 的能力和配置通过 `AGENT.yaml` 声明，而非硬编码在代码中。
- **关注点分离**：Agent 声明"需要什么能力"，Runtime 根据信任级别和部署策略决定"实际授予什么能力"。
- **可审计的持久化快照**：每次任务执行时冻结完整快照（manifest、中间件、工具、上下文），支持审计追溯和恢复。
- **协议化的扩展性**：核心抽象通过 Python `typing.Protocol` 定义，执行引擎、存储后端、内存、可观测性等均可插拔。

### 1.2 适用场景

- 构建平台默认 Agent 或业务专员 Agent。
- 执行文件型任务，以 workspace / artifact 作为真实成功条件。
- 通过 Skills 复用办公文档、业务流程或垂直能力。
- 通过 MCP 接入外部工具，通过 A2A（Agent-to-Agent）连接其他 Agent 或业务系统。
- 在 Daytona 沙箱中执行受控代码，生成 PPTX、PDF、DOCX、XLSX 等交付物。
- 为 BFF / 前端提供稳定的 Task、RuntimeEvent、SSE、workspace 和 artifact API。

### 1.3 核心对象

| 对象 | 说明 |
| --- | --- |
| **Agent** | 由 `AGENT.yaml` 声明的运行单元，包含模型、指令、工具、权限、工作区、代码执行、MCP、A2A、Skills 和验收配置。 |
| **Session** | 用户会话容器，保存会话级 workspace、消息投影和最近任务。 |
| **Task** | 一次 Agent 执行。启动时冻结 manifest 快照、中间件快照、有效工具快照和 workspace 信息。 |
| **RuntimeEvent** | Runtime 对外暴露的执行事件，覆盖流式文本、推理过程、工具调用、等待态、工作区更新和最终状态。 |
| **Workspace** | Runtime 管理的文件空间。模型工具、API、沙箱和产物验收都围绕 workspace 工作。 |
| **Artifact** | Agent 产出的文件交付物。Runtime 可以列出、注册、校验产物，并阻止缺少必需文件的任务误报完成。 |
| **Skill** | 随 Agent 声明挂载的可复用能力包。 |
| **MCP** | Model Context Protocol 工具接入方式。运行时在任务启动时发现并冻结可见工具 Schema。 |
| **A2A** | Agent-to-Agent 调用契约，支持本地 `/a2a/invoke` 和 manifest 中的外部 A2A 工具等待/恢复链路。 |
| **Daytona** | 受控代码执行沙箱后端，用于文件生成、测试、构建、转换和校验。 |

### 1.4 系统架构

AgentRuntime 采用分层架构设计，自底向上包括：

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI HTTP 层                    │
│  /sessions /tasks /agents /workspaces /a2a /runtime  │
│  鉴权 · Scope 校验 · SSE 流式推送 · 统一错误处理      │
├─────────────────────────────────────────────────────┤
│                 RuntimeService 编排层                 │
│  Session CRUD · Task 生命周期 · A2A 调用 · 恢复       │
│  事件总线 · 审计发布 · 重连补发                        │
├─────────────────────────────────────────────────────┤
│                    TaskRunner 执行层                   │
│  Manifest 解析 · 上下文打包 · 策略配置 · 快照冻结       │
│  Secret/Env/Credential 解析 · 核心引擎调用              │
├─────────────────────────────────────────────────────┤
│                   RuntimeCore 核心引擎                 │
│  DeepAgentsRuntimeCore / FakeRuntimeCore              │
│  模型路由 · 中间件管线 · 沙箱后端 · Workspace 路由      │
│  策略验证 · 预算控制 · 上下文管理                       │
├─────────────────────────────────────────────────────┤
│               存储与基础设施后端层                       │
│  Postgres / In-Memory Stores · Postgres checkpoint    │
│  Daytona 沙箱 · Subprocess 执行 · Langfuse / OTel     │
│  Mem0 / Record-Store 内存 · Preset MCP (Playwright)   │
└─────────────────────────────────────────────────────┘
```

### 1.5 执行生命周期

典型调用链路：

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌─────────────┐
│ 创建      │───>│ 启动     │───>│ 流式事件      │───>│ 处理等待/   │
│ Session   │    │ Task     │    │ (SSE/Event)  │    │ 恢复执行    │
└──────────┘    └──────────┘    └──────────────┘    └─────────────┘
                                                           │
                                                           v
                                                    ┌──────────────┐
                                                    │ 终端状态      │
                                                    │ (完成/失败/   │
                                                    │  取消)       │
                                                    └──────────────┘
                                                           │
                                                           v
                                                    ┌──────────────┐
                                                    │ 读取产物      │
                                                    │ (Workspace/  │
                                                    │  Artifact)   │
                                                    └──────────────┘
```

Task 状态转换：

```
PENDING ──> RUNNING ──> WAITING_INPUT ──> RUNNING ──> COMPLETED
                         (等待恢复)                    FAILED
                                                      CANCELLED
```

## 第二章 快速开始

### 2.1 环境准备

**系统要求**：
- Python >= 3.11（推荐 3.12）
- 推荐使用 `uv` 作为包管理器
- 可选：PostgreSQL 16（生产环境必需）
- 操作系统：Linux（推荐）/ macOS / Windows（通过 WSL2）

**Windows 用户须知**：

AgentRuntime 核心引擎（API 服务、Agent 执行）可以运行在 Windows 上，但以下功能需要 WSL2 环境：

| 功能 | Windows 原生 | WSL2 | 说明 |
| --- | --- | --- | --- |
| API 服务 + 内存存储 | ✅ | ✅ | `uvicorn` + `memory` 后端直接可用 |
| PostgreSQL 持久化 | ✅ | ✅ | Windows 版 Postgres 可用 |
| Daytona 沙箱 | ❌ | ✅ | 依赖 Docker 容器，需 WSL2 后端 |
| 启动脚本 (`start.sh` 等) | ❌ | ✅ | bash 脚本，需 Git Bash 或 WSL2 |
| 离线安装 (`install.sh`) | ❌ | ✅ | bash 安装脚本 |
| Playwright MCP 预设 | ❌ | ✅ | 预设引用 `.sh` 脚本 |

**推荐做法**：
- **开发/调试**：Windows 原生运行 API 服务（`uvicorn` 启动），搭配内存存储后端和本地 subprocess 执行器即可。
- **完整功能**：在 WSL2 中克隆仓库，安装 Docker Desktop（启用 WSL2 集成），使用 `./scripts/start.sh` 启动完整服务。
- **生产部署**：使用 Linux 服务器或 Docker 容器部署。

### 2.2 安装方式

AgentRuntime 支持两种安装方式：

#### 方式 A：离线安装包（推荐，无需源码）

适用于没有源码仓库访问权限、网络受限或需要固定版本部署的场景。

离线安装包位于 `release/v1.1.2/agent-runtime-1.1.2-py312-pyc-only.tar.gz`，包含预编译的 .pyc 字节码。

**安装步骤**：

```bash
# 1. 解压安装包
tar -xzf release/v1.1.2/agent-runtime-1.1.2-py312-pyc-only.tar.gz
cd agent-runtime-1.1.2-py312-pyc-only

# 2. 运行安装脚本
./install.sh

# 3. 验证安装
python -c "from agent_runtime import RuntimeService; print('ok')"
agent-runtime --help
```

**安装包结构说明**：

```
agent-runtime-1.0.7.1-py312-pyc-only/
├── install.sh              # 安装脚本（核心）
├── requirements.txt         # 运行时依赖（fastapi, httpx, jsonschema, pydantic>=2, pyyaml, uvicorn）
├── verify.py               # 安装后验证脚本
├── VERSION                  # 版本号: 1.1.2
├── PYTHON_VERSION           # 编译 Python 版本: 3.12.12
├── README.txt               # 安装说明
├── EXTRAS                   # 可选依赖说明（当前为空）
├── python/
│   └── agent_runtime/       # 预编译 .pyc 字节码（200+ 文件，完整模块树）
└── dist-info/               # Python dist-info 元数据
```

install.sh 的工作流程：

1. **版本校验** — 检查当前 Python 主次版本（3.12）是否与编译版本（3.12.12）兼容。
2. **依赖安装** — 若有 `wheelhouse/` 目录，从本地 wheel 离线安装依赖；否则从 PyPI 在线安装 `requirements.txt` 中的包。
3. **字节码部署** — 将 `python/agent_runtime/` 复制到 `site-packages`。
4. **CLI 入口** — 在 scripts 目录创建 `agent-runtime` 可执行脚本。
5. **验证** — 自动执行 `import` 验证。

> **注意**：当前包不包含 `wheelhouse/` 目录，因此依赖从 PyPI 在线安装。如需完全离线部署，可将依赖的 wheel 放入 `wheelhouse/` 目录后重新打包。

#### 方式 B：源码安装（需克隆仓库）

适用于开发调试场景，需要访问完整源码和测试：

```bash
# 克隆仓库
git clone <repo-url> agent-runtime
cd agent-runtime

# 创建虚拟环境并安装全部依赖
uv venv .venv
uv pip install -e '.[dev,deepagents,postgres,daytona,observability,memory]'

# 最小安装（仅 schema 校验）
uv pip install -e '.[dev]'
```

### 2.3 快速启动

**第一步：配置环境变量**

```bash
# 从模板创建 .env 文件
cp .env.example .env

# 编辑 .env，填入 API Key（其他配置由 configs/dev.yaml 兜底，无需修改）
# 必填项：OPENAI_COMPATIBLE_API_KEY
```

配置优先级：**环境变量 > configs/*.yaml > 代码默认值**。绝大部分配置（模型、路径、日志、策略）已在 `configs/dev.yaml` 中预设，`.env` 仅需覆盖 API Key 等机密信息。

**第二步：创建最小 Agent**

```bash
mkdir -p agents/hello-agent
```

创建 `agents/hello-agent/AGENT.yaml`：

```yaml
schema_version: anp-agent/v1.2
kind: Agent

metadata:
  id: hello-agent
  name: "Hello Agent"
  description: "A minimal demo Agent"
  version: "1.0.0"
  trust_level: verified

model:
  provider: openai_compatible
  model: deepseek-v4-flash
  temperature: 0.2
  max_tokens: 4000

instructions: |
  你是一个简洁的助手。根据用户输入输出清晰友好的回答。
```

> **注意**：`model.provider` 和 `model.model` 应与 `.env` 中的 `OPENAI_COMPATIBLE_BASE_URL` 匹配。以上示例使用 DeepSeek；若使用 DashScope，需将 provider 改为 `dashscope`。

**第三步：启动服务**

```bash
# dev 模式（内存存储，无需数据库，默认加载 configs/dev.yaml）
./scripts/start.sh

# 或手动指定配置文件
AGENT_RUNTIME_CONFIG_PATH=./configs/dev.yaml agent-runtime serve

# 生产模式：指定 prod.yaml（需 Postgres + Daytona）
AGENT_RUNTIME_CONFIG_PATH=./configs/prod.yaml agent-runtime serve
```

**第四步：创建 Session 并启动 Task**

```bash
export API="http://127.0.0.1:8877"

# 创建 Session
SESSION_ID=$(curl -s -X POST "$API/sessions" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"hello-agent","title":"demo"}' | jq -r .session_id)

# 启动 Task
TASK_ID=$(curl -s -X POST "$API/tasks" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"agent_id\":\"hello-agent\",\"input\":\"你好，请介绍一下你自己\"}" | jq -r .task_id)

# 流式订阅事件（实时）
curl -N "$API/tasks/$TASK_ID/stream"

# 或查询完成后的事件列表
curl -s "$API/tasks/$TASK_ID/events?after_sequence=0" | jq
```

### 2.4 校验工具

```bash
# 校验单个 manifest
python scripts/validate_agent.py agents/hello-agent/AGENT.yaml

# 校验全部
python scripts/validate_agent.py --all --strict

# 产品配置校验
agent-runtime validate --config agent-runtime.yaml --product

# 完整检查
agent-runtime doctor --config agent-runtime.yaml --product --strict-production
```

### 2.5 内置 Web UI

启动服务后，浏览器访问 `http://127.0.0.1:8877/chat` 即可使用内置 Web 聊天界面，无需额外前端开发。

---

## 第三章 Agent Manifest 声明式契约

### 3.1 概述

Agent Manifest（`AGENT.yaml`）是 AgentRuntime 的核心声明式契约。一个 Agent 的所有配置——模型、指令、工具、权限、工作区、技能、子代理——都通过 Manifest 定义。

**核心原则**：

- Manifest 声明"Agent 需要什么能力"（Request）。
- Runtime 根据信任级别、部署策略和调用方权限决定"实际授予什么能力"（Effective）。
- Manifest 不决定 runtime policy、sandbox backend、网络策略等运维配置。
- 每次 Task 启动时，Manifest 会被深度冻结（snapshot freeze），确保执行可追溯。

### 3.2 Schema 版本

| 版本 | 状态 | 说明 |
| --- | --- | --- |
| `anp-agent/v1.2` | **推荐** | 当前 Schema 版本。新建 Agent 使用此版本。 |
| `anp-agent/v1.1` | 兼容 | 仍可读取，但不支持 v1.x 已移除的旧字段。 |
| `anp-agent/v1` | **已移除** | 不再自动归一化，需要手动迁移到 v1.2。 |

### 3.3 最小 Manifest

```yaml
# yaml-language-server: $schema=../../schemas/agent.schema.json
schema_version: anp-agent/v1.2
kind: Agent

metadata:
  id: demo-agent
  name: "Demo Agent"
  version: "1.0.0"
  trust_level: verified

model:
  provider: fake
  model: fake-chat

instructions: |
  You are a concise assistant.
```

### 3.4 完整字段参考

#### 3.4.1 metadata

```yaml
metadata:
  id: demo-agent                # 必填。唯一标识，小写字母/数字/连字符，2-64 字符
  name: "Demo Agent"            # 必填。可读名称，最长 100 字符
  description: "..."            # 可选。描述，最长 1000 字符
  version: "1.0.0"              # 必填。语义化版本号
  trust_level: verified         # 必填。platform | verified | untrusted
  owner: team-a                 # 可选。所有者标识（纯透传）
  exposes_chat: true            # 可选。是否在 Agent 列表中可见
  exposes_a2a: true             # 可选。是否可通过 A2A 调用
  labels:                       # 可选。标签
    category: example
    language: zh-CN
```

**信任级别（trust_level）**：

| 级别 | 适用对象 | 典型限制 |
| --- | --- | --- |
| `platform` | 平台内置 Agent | 最高权限，但仍受部署策略限制 |
| `verified` | 经审核的业务 Agent | 可申请 workspace、code execution、network、subagents |
| `untrusted` | 未审核的外部 Agent | 最小能力，不能有 subagents 或 code execution |

#### 3.4.2 model

```yaml
model:
  provider: openai_compatible   # 模型 provider 名称
  model: deepseek-v4-flash       # 模型名称
  temperature: 0.2              # 可选。采样温度
  max_tokens: 8000              # 可选。最大输出 token
  timeout: 300                  # 可选。请求超时（秒）
  max_retries: 2                # 可选。失败重试次数
```

#### 3.4.3 instructions / instructions_template

`instructions` 和 `instructions_template` 二选一，不可同时使用。

**静态指令**：

```yaml
instructions: |
  你是一个项目助理。
  根据用户输入输出清晰的工作建议。
```

**模板指令**（支持动态变量）：

```yaml
instructions_template: |
  你正在为 {{caller.user_name}} 提供帮助。
  当前项目：{{caller.project_name}}
  请按以下要求执行：{{caller.task_constraint}}

required_caller_keys:
  - caller.user_name
  - caller.project_name
```

`instructions_template` 中的变量在 `StartTaskRequest.dynamic_context` 中提供。缺少 `required_caller_keys` 时，行为由 `MissingContextPolicy` 决定（`fail_fast` 或 `wait_for_input`）。

#### 3.4.4 tools

声明 Agent 可用的 Runtime/API/A2A 工具。注意：MCP 工具应写在 `mcp_servers`，Skill 应写在 `skills`。

```yaml
tools:
  - kind: runtime
    name: ask_user
    description: 向用户提问以获取额外信息。
    capability: interaction.ask_user
  - kind: runtime
    name: workspace_write
    description: 写入文件到工作区。
    capability: workspace.file_write
```

工具类型：

| kind | 说明 |
| --- | --- |
| `runtime` | Runtime 内置工具（文件操作、执行命令、交互等） |
| `api` | 通过 HTTP API 调用的工具 |
| `a2a` | Agent-to-Agent 调用工具 |

#### 3.4.5 mcp_servers

声明 MCP（Model Context Protocol）Server 依赖。Runtime 在 Task 启动时连接、发现并冻结工具 Schema。

```yaml
mcp_servers:
  fetch:
    description: "Fetch and parse web pages"
    transport: stdio
    command: mcp-fetch
  weather:
    description: "Weather API"
    transport: http
    server_url: "https://api.weather.example.com/mcp"
```

支持传输方式：

| transport | 说明 |
| --- | --- |
| `stdio` | 通过标准输入输出通信的子进程 |
| `http` / `sse` | HTTP Server-Sent Events |
| `websocket` | WebSocket 连接 |

#### 3.4.6 skills

声明随 Agent 打包的技能（可复用能力包）。Skill 包含 `SKILL.md` 文档和配套资源文件。

```yaml
skills:
  - id: docx
    description: Word .docx：创建、编辑、批注、模板、格式化和校验。
    path: ./skills/docx
    activation:
      mode: auto
      required_when: [docx, DOCX, Word, word文档, 文档]
```

激活模式：

| mode | 行为 |
| --- | --- |
| `auto`（默认）| Task 启动时根据输入匹配关键词自动激活 |
| `always` | 始终激活 |
| `manual` | 永不自动激活，仅由 Agent 指令显式引用 |

#### 3.4.7 subagents

声明 DeepAgents 子 Agent，由 `task(subagent_type=...)` 工具调用。

```yaml
subagents:
  - id: office-document-worker
    # 引用 Registry 中的 Agent
    ref: registry://skill-agent
    name: 通用办公任务助手
    description: 根据用户需求创作和处理办公文档。
    metadata:
      capabilityTags: [office, document, docx, xlsx, ppt, pptx, pdf]
      entrypoint: subagent://office-document-worker
```

引用方式：

| 方式 | 写法 | 说明 |
| --- | --- | --- |
| Registry 引用 | `ref: registry://<agent-id>` | 引用已注册的 Agent |
| 本地路径 | `path: ./subagents/worker` | 引用同目录下的子 Agent |
| Agent ID | `agent: <agent-id>` | 引用 Registry 中的 Agent |

限制：
- `path` 型 subagent 必须在当前 Agent 目录内，不能使用 `../` 逃逸。
- `untrusted` 级别的 Agent 不能声明 subagents。

#### 3.4.8 resources

随 Agent 打包的静态资源目录。默认为只读，路径相对于 `AGENT.yaml`。

```yaml
resources:
  - id: reference_docs
    type: directory
    path: ./docs
    mount: /references
    readonly: true
    include_in_export: true
```

**特别注意**：

- `/workspace` 和 `/output` 是 Runtime 管理的虚拟路径，**不能**在 `resources` 中声明。
- `/workspace` → 当前 Task 的工作区根目录。
- `/output` → 当前 Task 的产物输出目录（通常是 workspace 下的 `output/`）。

#### 3.4.9 capabilities

Agent 声明的能力需求。这是 **请求**（Request）而非授权（Grant）。Runtime 根据信任级别和策略决定最终授予的能力。

```yaml
capabilities:
  workspace:
    required: true
    access:
      read: true
      write: true
      delete: false
    isolation_minimum: session_shared
  code:
    required: false
    languages:
      - python
      - bash
      - node
    commands:
      patterns:
        allow:
          - '^(python|pytest|node) '
    needs_network: false
  network:
    required: true
    domains:
      - '*.example.com'
  artifacts:
    required: true
    output_paths:
      - /output
```

#### 3.4.10 budgets

针对工具调用、超时、工作区配额等的预算建议。Runtime 会根据部署策略进行限制（clamp）。

```yaml
budgets:
  suggested_max_tool_calls: 120
  suggested_timeout_seconds: 3600
  suggested_max_subagent_calls: 5
  workspace:
    suggested_quota_mb: 512
    suggested_max_file_size_mb: 32
```

#### 3.4.11 acceptance

任务完成条件——必需的文件产物及其校验规则。

```yaml
acceptance:
  required_files:
    - path: /output/report.pptx
      type: pptx
      min_size_bytes: 1024
    - path: /output/summary.json
      type: json
      min_size_bytes: 100
```

文件类型支持：`any`、`pptx`、`docx`、`xlsx`、`pdf`、`md`、`json`、`csv` 等。

#### 3.4.12 orchestration

执行模式与编排配置。

```yaml
orchestration:
  execution_mode: planner_first
  plan_approval:
    mode: risky_only
  governance:
    approval_required_actions:
      - execute
      - external_post
      - cross_system_write
      - high_risk_tool
```

#### 3.4.13 context

上下文管理策略。

```yaml
context:
  session_history:
    enabled: true
    scope: same_session_same_agent
  channels:
    message:
      prependUserContextReminder: true
      sources:
        - project_instructions
        - current_date
        - workers_catalog
  compaction:
    strategy: runtime_default
    preserveRecentTurns: 5
```

#### 3.4.14 prompt

Prompt Profile 配置。

```yaml
prompt:
  runtime_profile: main_agent_default
  runtime_profile_overrides:
    agent_catalog:
      policy:
        top_k: 100
        include_reason: true
  sections:
    static:
      - id: intro_identity
        content: |
          你是 MainAgent，负责理解用户目标、制定可执行计划。
```

#### 3.4.15 memory

内存配置。

```yaml
memory:
  enabled: true
  mode: session_scoped
```

#### 3.4.16 session_state

会话状态隔离策略。

```yaml
session_state:
  isolation: session_shared
```

| 策略 | 说明 |
| --- | --- |
| `session_shared` | 会话内共享工作区 |
| `task_isolated` | 每个 Task 独立工作区 |

### 3.5 Agent Teams（多 Agent 团队）

Agent Teams 是一种声明式多 Agent 协作模式，通过目录结构将多个 Agent 组织为一个团队，由主 Agent 负责规划调度，子 Agent 各司其职。

**目录结构示例**：

```
agent-teams/
├── software_company/          # 团队根目录
│   ├── AGENT.yaml             # 主 Agent（团队入口，负责编排调度）
│   ├── cases.md               # 测试用例 / 验收场景
│   └── agents/                # 子 Agent 目录
│       ├── product-manager/AGENT.yaml
│       ├── architect/AGENT.yaml
│       ├── frontend-engineer/AGENT.yaml
│       ├── backend-engineer/AGENT.yaml
│       ├── designer/AGENT.yaml
│       └── qa-engineer/AGENT.yaml
└── medias/                    # 另一个团队
    ├── AGENT.yaml
    ├── role.md
    ├── cases.md
    └── agents/
        ├── strategist/AGENT.yaml
        ├── content-planner/AGENT.yaml
        ├── data-analyst/AGENT.yaml
        ├── operations/AGENT.yaml
        ├── evaluator/AGENT.yaml
        └── video-director/AGENT.yaml
```

**主 Agent 配置要点**（`agent-teams/<team>/AGENT.yaml`）：

```yaml
subagents:
  - id: product-manager
    path: ./agents/product-manager
    name: 产品经理
    description: 负责需求分析和产品规划
  - id: architect
    path: ./agents/architect
    name: 架构师
    description: 负责系统架构设计
  - id: backend-engineer
    path: ./agents/backend-engineer
    name: 后端工程师
    description: 负责后端服务开发
```

**关键设计原则**：

- 主 Agent 作为团队入口，通过 `task(subagent_type=...)` 将子任务委托给团队成员。
- 子 Agent 通过 `path: ./agents/<name>` 相对路径引用，不依赖 Registry。
- 团队配置可附带 `cases.md`、`role.md` 等团队级文档，由 Runtime 在上下文构建时注入。
- Agent Teams 适用于需要多角色协作的复杂场景（软件开发、内容生产、数据分析等）。

### 3.6 完整示例

以下是一个典型的**文件型 Agent**（带工作区、代码执行和产物验收）：

```yaml
schema_version: anp-agent/v1.2
kind: Agent

metadata:
  id: weekly-report-agent
  name: "Weekly Report Agent"
  version: "1.0.0"
  trust_level: verified
  exposes_chat: true

model:
  provider: openai_compatible
  model: deepseek-v4-flash
  temperature: 0.2
  max_tokens: 8000

instructions: |
  你是办公文档助理。
  当用户要求生成报告时，必须产出真实文件，不能只返回大纲。
  生成物写入 /output/，最终回复只引用真实创建的文件路径。

capabilities:
  workspace:
    required: true
    access:
      read: true
      write: true
  code:
    required: true
    languages: [python, bash]
    commands:
      patterns:
        allow:
          - 'python *'
          - 'mkdir *'
  artifacts:
    required: true
    output_paths: [/output]

acceptance:
  required_files:
    - path: /output/*
      type: any
      min_size_bytes: 1024
```

---

## 第四章 核心架构

### 4.1 架构分层

AgentRuntime 的代码结构按职责分为以下层次：

```
api/              ← HTTP 接口层（FastAPI 路由）
runtime/          ← 运行时编排层（Service、TaskRunner、EventBus、OutputPathResolver）
core/             ← 核心引擎层（DeepAgents RuntimeCore）
loader/           ← Agent 加载与 Manifest 处理
policy/           ← 策略引擎
security/         ← 认证与授权
stores/           ← 数据存储层
checkpoint/       ← 检查点持久化
sandbox/          ← 沙箱执行
workspace/        ← 工作区管理
mcp/              ← MCP 工具集成
memory/           ← 内存后端
observability/    ← 可观测性后端
logging/          ← 结构化日志
tools/            ← 内置工具注册
db/               ← 数据库迁移
```

### 4.2 产出物路径解析（OutputPathResolver）

`OutputPathResolver`（`runtime/output_path_resolver.py`）是 Runtime 的解耦组件，负责从 Agent manifest 的 `capabilities.artifacts.output_paths` 动态派生产出物目录，替代早期版本中对 `/output/` 路径的硬编码依赖。

**核心原则**：
- Runtime 代码中**不硬编码** `/output/`、`/workspace/` 等具体路径作为特殊判断条件。
- 产出物路径由 Agent 在 manifest 中声明（如 `output_paths: [/output, /deliverables]`），Runtime 等同对待。
- 路径感知逻辑（路由、权限、前端展示、完成检测）统一通过 `OutputPathResolver` 查询。

```python
from agent_runtime.runtime.output_path_resolver import OutputPathResolver

resolver = OutputPathResolver.from_manifest(manifest)
# 查询某路径是否属于产出物目录
resolver.is_output_path("/output/report.pptx")  # True
# 获取所有产出物目录
resolver.output_paths  # ["/output", "/deliverables"]
```

### 4.3 启动与初始化流程

```
CLI (cli.py)
  │
  ├── load_deployment_config(path)          # 自动发现或加载部署 YAML 配置
  │     ├── 1. AGENT_RUNTIME_CONFIG_PATH 环境变量
  │     ├── 2. ./agent-runtime.yaml
  │     ├── 3. ./configs/dev.yaml
  │     ├── 4. ~/.config/agent-runtime/config.yaml
  │     └── 未找到 → 使用全默认值（输出 warning）
  │     └── DeploymentConfig (Pydantic)
  │
  ├── runtime_settings_from_deployment()    # 合并 YAML + 环境变量
  │     └── RuntimeSettings
  │
  ├── RuntimeService.from_settings()        # 构造运行时（工厂方法）
  │     ├── AgentLoader + AgentRegistry     # 加载 & 校验 Agent
  │     ├── PostgresStoreBundle             # 数据存储
  │     ├── WorkspaceManager                # 工作区管理
  │     ├── RuntimeCore (DeepAgents/Fake)   # 核心引擎
  │     ├── TaskRunner                      # 任务执行器
  │     ├── RuntimeEventBus                 # 事件总线
  │     └── AuthProvider                    # 认证
  │
  ├── runtime.initialize()                  # 初始化（preflight、migration、注册表加载）
  │
  └── create_app(runtime) → FastAPI         # 创建 HTTP 应用
        ├── lifespan event: initialize()
        ├── 9 个路由模块
        ├── CORS 中间件
        ├── 请求上下文中间件
        └── 统一错误处理器
```

### 4.4 RuntimeService 运行时服务

`RuntimeService` 是整个系统的中心编排器（文件：`runtime/service.py`）。

**构造方式**：

```python
# 方式1：从 DeploymentConfig 构造
from agent_runtime import RuntimeService
runtime = RuntimeService.from_settings(settings)
await runtime.initialize()

# 方式2：从 ProductRuntimeConfig 构造（推荐业务产品使用）
from agent_runtime.runtime.product_config import ProductRuntimeConfig
runtime = RuntimeService.for_product(ProductRuntimeConfig(
    product_name="Demo",
    profile="embedded_single_tenant",
    agents_dir="agents",
))
await runtime.initialize()
```

**核心职责**：

| 方法 | 说明 |
| --- | --- |
| `create_session()` / `get_session()` / ... | Session 全生命周期管理 |
| `start_task()` / `stream_task()` / `resume_task()` / `cancel_task()` | Task 全生命周期管理 |
| `delegate_agent_from_tool()` | A2A Agent 委托 |
| `invoke_local_agent()` | 本地 A2A 调用 |
| `deliver_external_callback()` | 外部回调投递（HMAC 签名验证） |
| `purge_*_for_retention()` | 数据保留策略清理 |

### 4.5 TaskRunner 任务执行器

`TaskRunner`（文件：`runtime/task_runner.py`）是执行引擎的核心，约 2500 行。负责 Task 从创建到终结的完整生命周期。

**执行流程**：

```
StartTaskRequest
     │
     ├── 校验 Session 状态 & 幂等性 & 前台任务冲突
     │
     ├── resolve_agent_manifest()
     │     ├── 解析 Manifest（capabilities → requested 请求）
     │     ├── 冻结资源依赖（snapfreeze）
     │     ├── 解析有效运行时配置（effective runtime config）
     │     │     ├── 网络策略解析
     │     │     ├── 文件系统限制
     │     │     ├── 执行后端选择（subprocess / daytona）
     │     │     ├── 工作区隔离策略
     │     │     └── 预算限制 (clamp)
     │     └── 生成 RuntimeResolutionExplanation 审计链
     │
     ├── 持久化 TaskRecord + 发布 task_started 事件
     │
     ├── asyncio.create_task(_run_task())
     │     │
     │     ├── resolve_manifest_refs()       # 解析 ${secret:} ${env:} ${user_credential:}
     │     ├── build_context_package()       # 构建上下文包（prompt、skills、memory、scoped context）
     │     ├── core.run()                    # 调用核心引擎执行
     │     │     └── AsyncIterator[RuntimeEvent]
     │     └── _consume_core_stream()        # 消费事件流
     │           ├── task_completed → artifact 验证、消息记录、事件发布
     │           ├── task_waiting    → WaitState 持久化
     │           └── task_failed     → 错误记录、异常发布
     │
     └── 返回 TaskRecord（状态 = PENDING / RUNNING）
```

### 4.6 RuntimeCore 核心引擎协议

`RuntimeCore` 是一个 Python `typing.Protocol`（文件：`core/protocol.py`），定义了执行引擎需要实现的接口。

```python
class RuntimeCore(Protocol):
    async def run(
        self,
        task_id: str,
        session_id: str,
        agent_id: str,
        input: Any,
        manifest: dict,
        workspace_manager: Any,
        trust_level: TrustLevel,
        metadata: dict,
        thread_binding_id: str | None = None,
    ) -> AsyncIterator[RuntimeEvent]:
        ...

    async def resume(
        self,
        task_id: str,
        session_id: str,
        agent_id: str,
        resume_envelope: ResumeEnvelope,
        manifest: dict,
        workspace_manager: Any,
        trust_level: TrustLevel,
        metadata: dict,
    ) -> AsyncIterator[RuntimeEvent]:
        ...
```

**两个实现**：

| 实现 | 适用场景 |
| --- | --- |
| `DeepAgentsRuntimeCore` | 生产环境。基于 LangGraph 的完整 Agent 执行引擎 |
| `FakeRuntimeCore` | 测试环境。模拟事件流，用于 API 合约测试 |

### 4.7 DeepAgentsRuntimeCore 详解

`DeepAgentsRuntimeCore`（文件：`core/deepagents_core.py`）是基于 LangGraph/DeepAgents 框架的生产执行引擎。

**构造参数（依赖注入点）**：

```python
class DeepAgentsRuntimeCore:
    def __init__(
        self,
        create_agent: CreateAgent,              # Agent 创建工厂（核心扩展点）
        checkpointer_factory: CheckpointerFactory,  # 检查点工厂
        registry: AgentRegistry,                # Agent 注册表
        policy: PolicyMiddleware,                # 策略中间件
        workspace_manager: WorkspaceManager,     # 工作区管理器
        workspace_resolver: WorkspaceResolver,   # 工作区解析器
        memory_store_adapter: Any | None,        # 内存存储适配器
        model_registry: ModelProviderRegistry,   # 模型提供者注册表
        dynamic_capability_providers: dict | None, # 动态能力提供者
    ):
```

**执行流程**：

```
core.run(manifest, input, ...)
  │
  ├── create_agent(manifest)             # 工厂方法创建 LangGraph Agent
  │     ├── 组装中间件管线
  │     ├── 创建 CompositeBackend（工作区/沙箱/内存/技能路径路由）
  │     ├── 选择后端（Subprocess / Daytona）
  │     └── 注册工具集
  │
  ├── agraph.ainvoke() / astream_events()  # LangGraph 执行
  │     └── 中间件管线拦截每次请求：
  │           ├── RuntimePolicyMiddleware  # G1 策略检查
  │           ├── ExecutionLimitMiddleware  # 执行次数限制
  │           ├── DelegationInputGuard      # 委托输入保护
  │           ├── OverwriteGuard            # 覆盖保护
  │           ├── ExternalActionApproval    # 外部操作审批
  │           ├── TodoProjection            # Todo 投影
  │           └── ModelContextGuard                 # 上下文保护
  │
  └── 标准化事件流 → AsyncIterator[RuntimeEvent]
```

#### 4.7.1 后端架构（Backend）

Runtime 使用 DeepAgents 的 `CompositeBackend` 实现虚拟文件系统，将不同路径映射到不同后端：

```
/workspace/     → LocalWorkspaceBackend / DaytonaWorkspaceBackend  （可读写）
/input/         → 输入文件后端 （只读）
/output/        → 输出产物后端
/resources/     → 资源文件后端 （只读）
/skills/        → 技能文件后端 （只读）
/memories/      → StoreBackend （内存存储）
```

**后端包装器（Wrapper）模式**：

```
实际后端
  ↑
ExecutePolicyWrapper      # 命令执行审计、输出脱敏、引用持久化
  ↑
CommandTransformSandboxWrapper  # 命令路径转换
  ↑
WorkspaceBackendMetadataWrapper # 工作区元数据
  ↑
PolicyBackendWrapper      # G3 策略（路径安全）
  ↑
QuotaBackendWrapper       # 配额限制
  ↑
PathPrefixBackend         # 路径前缀映射
  ↑
CompositeBackend          # 路由到实际后端
```

#### 4.7.2 沙箱后端选择

```python
def _sandbox_backend_for_manifest(manifest, trust_level, ...):
    if trust_level == UNTRUSTED:
        return None  # 不可信 Agent 无沙箱

    code_execution = manifest["capabilities"]["code"]
    if not code_execution.get("required"):
        return None  # 未声明代码执行需求

    # Runtime policy 决定具体后端
    if policy 选择 daytona:
        return DaytonaExecutor(...)
    else:
        return SubprocessExecutor(...)
```

#### 4.7.3 中间件管线

中间件按顺序执行，每个中间件可以拦截、修改或拒绝工具调用：

| 中间件 | 职责 |
| --- | --- |
| `RuntimePolicyMiddleware` | G1 策略检查：工具调用权限验证 |
| `DelegationInputGuardMiddleware` | 防止空壳委托（委托时必须传递完整上下文） |
| `OverwriteGuardMiddleware` | 防止意外覆盖已有工作 |
| `ExternalActionApprovalMiddleware` | 高风险操作审批流程 |
| `TodoProjectionMiddleware` | 长任务进度可视化投影 |
| `ModelContextGuardMiddleware` | 上下文预算保护 |
| `ExecutionLimitMiddleware` | 执行次数和超时限制 |

### 4.8 事件系统

#### 4.8.1 RuntimeEvent

`RuntimeEvent`（文件：`runtime/events.py`）是系统对外暴露的统一事件模型。

**事件类型**：

| 事件名 | 含义 |
| --- | --- |
| `task_started` | Task 已进入执行 |
| `task_waiting` | Task 暂停，等待用户输入/审批/外部结果 |
| `task_resumed` | 等待中的 Task 已恢复 |
| `task_completed` | Task 完成 |
| `task_failed` | Task 失败 |
| `task_cancelled` | Task 被取消 |
| `message_delta` | 流式文本增量（持久化时默认不保留原文） |
| `model_thinking` | 模型推理过程增量（持久化时默认不保留原文） |
| `tool_call_started` | 工具调用开始 |
| `tool_call_completed` | 工具调用成功 |
| `tool_call_failed` | 工具调用失败 |
| `policy_denied` | 策略拒绝 |
| `workspace_update` | 工作区文件状态变更 |
| `runtime_update` | Runtime 级别状态更新（Model Router 状态流转） |

**事件字段**：

```json
{
  "event": "message_delta",
  "task_id": "uuid",
  "agent_id": "demo-agent",
  "event_id": "evt_abc123",
  "sequence": 42,
  "correlation_id": "corr_001",
  "message_id": "msg_001",
  "session_id": "uuid",
  "workspace_id": "ws_001",
  "timestamp": "2026-05-26T10:00:00Z",
  "payload": { "delta": "Hello" }
}
```

#### 4.8.2 事件总线

`RuntimeEventBus`（文件：`runtime/event_bus.py`）实现**发布/订阅**模式，**sequence 由 Bus 统一分配**（非 Store），确保 live subscriber 看到连续序列号：

```
                                         ┌──────────────┐
publish(event) ──→ Bus 分配 sequence      │              │
                  │ 生成 event_id         │              │
                  │ 推送到 subscriber     │              │
                  └──────┬───────────────┘
                         │
                  ┌──────┴───────────────┐
                  │ 持久化分支            │
                  │                      │
                  │ message_delta /      │
                  │ model_thinking →     │
                  │   缓冲合并 (100条/    │
                  │   0.5s flush)        │
                  │                      │
                  │ 其他事件 → 直接持久化 │
                  └──────┬───────────────┘
                         │
                  EventStore.publish()
                         │
                  ┌──────┴───────┐
                  │ stream()      │
                  │               │
                  │ Replay→Live   │
                  │ 终端事件停止   │
                  └───────────────┘
```

**缓冲合并优化**（v1.1.1+）：高频 `message_delta` 和 `model_thinking` 事件默认不逐条持久化，而是合并为一条摘要事件（含 `delta_size`、`merged_count`、`merged_sequence_range`），显著减少存储写入量。`task_completed` / `task_failed` / `task_cancelled` 等生命周期事件立即持久化。

### 4.9 配置解析管线

Agent 的"请求→有效"能力解析是系统的关键设计：

```
AGENT.yaml 声明
  │
  ├── metadata.trust_level                           # Agent 声明的信任上限
  ├── capabilities.*                                 # Agent 请求的能力
  ├── budgets.*                                      # Agent 建议的预算
  └── normalization 至 _runtime 内部结构
        │
        ▼
resolve_effective_runtime_config(manifest, trust, policy)
  │
  ├── network:      block_all / allowlist / full      # 网络策略
  ├── filesystem:   quota / max_file_size / isolation # 文件系统限制
  ├── limits:       timeout / tool_calls / subagent   # 执行限制
  ├── workspace:    session_shared / task_isolated    # 工作区隔离
  ├── code_execution: backend / command_allowlist     # 代码执行
  ├── memory:       auto-write / ttl                  # 内存策略
  ├── preset_mcp:   playwright 配置                    # 预设 MCP
  └── orchestration: subagent_policy                  # 编排策略
        │
        ▼
EffectiveRuntimeConfig
  ├── effective_permissions       # 实际授予的权限
  ├── effective_limits            # 实际生效的限制
  ├── resolved_execution_profile  # 执行后端
  ├── capability_summary          # 能力授予摘要
  └── resolution_explanations[]   # 审计轨迹
        │
        ▼
冻结到 TaskRecord.agent_manifest_snapshot._runtime
```

每一个决议都记录在 `resolution_explanations` 中：

```json
{
  "domain": "network",
  "path": "capabilities.network.domains",
  "decision": "denied",
  "reason": "trust_level=untrusted prevents network access",
  "requested": ["*"],
  "effective": []
}
```

### 4.10 数据模型关系

```
Session (会话容器)
  ├── session_id: UUID
  ├── trust_level: platform | verified | untrusted
  ├── workspace_id
  ├── owner (user/principal)
  └── metadata
       │
       ▼
Task (一次执行)
  ├── task_id: UUID
  ├── session_id → Session
  ├── agent_id → Agent Manifest
  ├── status: pending / running / waiting_input / completed / failed / cancelled
  ├── agent_manifest_snapshot (冻结的完整 Manifest)
  ├── middleware_snapshot
  ├── effective_trust
  ├── workspace_id
  ├── owner
  └── deepagents_thread_id
       │
       ├── RuntimeEvent[] → EventStore     # 事件流
       ├── MessageRecord[] → MessageStore  # 会话消息
       └── Workspace → WorkspaceManager    # 工作区文件
```

---

## 第五章 API 参考

API 服务基于 FastAPI，默认端口 8877（开发模式）/ 8080（生产模式）。完整路由定义见 `src/agent_runtime/api/`。

### 5.1 基础约定

**Base URL**：

```bash
export RUNTIME_URL="http://localhost:8877"
```

**内容类型**：所有请求和响应均为 `application/json`。

**时间字段**：ISO 8601 字符串，Runtime 内部统一按 UTC 生成。

**统一错误格式**：

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

**错误类型与 HTTP 状态码**：

| error.type | HTTP | 说明 | 客户端处理建议 |
| --- | --- | --- | --- |
| `unauthenticated` | 401 | 缺少凭据或凭据无效 | 重新登录/刷新凭据 |
| `forbidden` | 403 | Scope 不足或非 owner 访问 | 检查 scope 和 owner |
| `policy_denied` | 403 | 策略拒绝 | 展示可读原因 |
| `validation_error` | 400/422 | 请求格式不合法 | 修正请求体 |
| `agent_not_found` | 404 | Agent ID 不存在 | 刷新 Agent 列表 |
| `session_busy` | 409 | 会话已有互斥执行中的 Task | 等待或取消当前 Task |
| `idempotency_conflict` | 409 | 幂等键冲突 | 查询已有 Task |
| `rate_limited` | 429 | 达到限流 | 按退避策略重试 |
| `runtime_not_ready` | 503 | Preflight 未通过 | 检查 /ready 和 /preflight |
| `timeout` | 500 | 执行超时 | 检查 timeout 配置 |
| `tool_error` | 500 | 工具调用异常 | 检查工具配置 |
| `model_error` | 500 | 模型 API 异常 | 检查模型配置 |
| `internal_error` | 500 | 内部未预期错误 | 记录 trace_id 排查 |

### 5.2 Session API

#### POST /sessions — 创建 Session

```bash
curl -X POST "$RUNTIME_URL/sessions" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Demo session",
    "trust_level": "verified",
    "agent_id": "demo-agent",
    "workspace_id": "my-workspace",
    "metadata": {"source": "web"}
  }'
```

**请求字段**：

| 字段 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `title` | string | 否 | null | 会话标题 |
| `trust_level` | enum | 否 | verified | 信任级别 |
| `workspace_id` | string | 否 | null | 复用已有工作区 |
| `agent_id` | string | 否 | null | 关联 Agent |
| `metadata` | object | 否 | {} | 业务元数据 |

**响应**：`SessionRecord`（包含 `session_id`、`status`、`workspace_id` 等）。

#### GET /sessions — 列出 Session

```bash
curl "$RUNTIME_URL/sessions?agent_id=demo-agent"
```

#### GET /sessions/{session_id} — 获取 Session

#### PATCH /sessions/{session_id} — 更新 Session

更新标题、状态、工作区等。

```bash
curl -X PATCH "$RUNTIME_URL/sessions/$SESSION_ID" \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated title"}'
```

#### DELETE /sessions/{session_id} — 删除 Session

```bash
curl -X DELETE "$RUNTIME_URL/sessions/$SESSION_ID"
curl -X DELETE "$RUNTIME_URL/sessions/$SESSION_ID?purge=true"  # 硬删除
```

#### POST /sessions/{session_id}/restore — 恢复 Session

恢复已软删除的会话。

#### GET /sessions/{session_id}/state — 获取 Session 状态

返回会话、关联任务列表和消息的完整状态快照。

#### GET /sessions/{session_id}/messages — 列出消息

```bash
curl "$RUNTIME_URL/sessions/$SESSION_ID/messages?limit=50"
```

支持游标分页：`before_message_id=<id>`。

### 5.3 Task API

#### POST /tasks — 启动 Task

```bash
curl -X POST "$RUNTIME_URL/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "<session_id>",
    "agent_id": "demo-agent",
    "input": "请生成周报摘要",
    "files": [
      {"filename": "data.json", "content_base64": "eyJmb28iOiAiYmFyIn0="}
    ],
    "workspace_id": "my-workspace",
    "dynamic_context": {
      "caller.project_name": "Q2 项目"
    },
    "idempotency_key": "req-001",
    "metadata": {"source": "web"}
  }'
```

**请求字段**：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | UUID/string | 是 | 所属会话 |
| `agent_id` | string | 是 | 执行 Agent |
| `input` | string/object | 是 | 任务输入（文本或结构化） |
| `files` | array | 否 | 上传文件列表 |
| `workspace_id` | string | 否 | 指定工作区 |
| `workspace_isolation` | enum | 否 | 覆盖隔离策略 |
| `timeout` | int | 否 | 覆盖执行超时（秒） |
| `dynamic_context` | object | 否 | 模板变量 |
| `system_prompt_append` | string | 否 | 追加系统指令 |
| `system_prompt_override` | string | 否 | 覆盖系统指令 |
| `idempotency_key` | string | 否 | 幂等键 |
| `metadata` | object | 否 | 业务元数据 |
| `persistence` | enum | 否 | 持久化策略 |
| `subject_user_id` | string | 否 | 代表用户执行 |

#### GET /tasks — 列出 Task

```bash
curl "$RUNTIME_URL/tasks?session_id=$SESSION_ID&status=completed&limit=20"
```

支持按 `session_id`、`status` 过滤和游标分页。

#### GET /tasks/{task_id} — 获取 Task

```bash
curl "$RUNTIME_URL/tasks/$TASK_ID"
```

返回 `TaskRecord`，包含完整的状态、有效快照和执行信息。

#### GET /tasks/{task_id}/diagnostics — 获取诊断信息

```bash
curl "$RUNTIME_URL/tasks/$TASK_ID/diagnostics"
```

返回全面的诊断信息，包括：
- `context.mode_resolution`、`context.memory_snapshot`
- `policy.denials[].reason_code`
- `tools.effective_tool_snapshot`
- `workspace.ownership`
- `artifacts.acceptance` / `artifacts.output_refs`
- `runtime.validation_issues`
- `suggested_actions`

#### POST /tasks/{task_id}/stream-token — 换取流式 Token

```bash
curl -X POST "$RUNTIME_URL/tasks/$TASK_ID/stream-token"
```

返回短期 `stream_token`，供浏览器 SSE 订阅使用。

#### GET /tasks/{task_id}/stream — 订阅 SSE

```bash
# 方式1：使用 stream-token
curl -N "$RUNTIME_URL/tasks/$TASK_ID/stream?stream_token=<token>"

# 方式2：使用 Authorization header
curl -N -H "Authorization: Bearer <token>" "$RUNTIME_URL/tasks/$TASK_ID/stream"

# 断线重连
curl -N -H "Last-Event-ID: 42" "$RUNTIME_URL/tasks/$TASK_ID/stream"
curl -N "$RUNTIME_URL/tasks/$TASK_ID/stream?after_sequence=42"
```

**SSE 格式**：

```text
id: 42
event: message_delta
data: {"event":"message_delta","task_id":"...","sequence":42,"payload":{"delta":"Hello"}}

id: 43
event: task_completed
data: {"event":"task_completed","task_id":"...","sequence":43,"payload":{...}}
```

流的终止条件：
- 收到 `task_completed`、`task_failed`、`task_cancelled`。
- 当前流观察到的 `task_waiting`。

#### POST /tasks/{task_id}/resume — 恢复等待的 Task

```bash
curl -X POST "$RUNTIME_URL/tasks/$TASK_ID/resume" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "同意继续执行",
    "idempotency_key": "resume-001"
  }'
```

#### POST /tasks/{task_id}/cancel — 取消 Task

#### GET /tasks/{task_id}/events — 读取持久化事件

```bash
curl "$RUNTIME_URL/tasks/$TASK_ID/events?after_sequence=0&limit=200"
```

### 5.4 Agent API

#### GET /agents — 列出 Agent

```bash
curl "$RUNTIME_URL/agents"
```

返回 Agent 摘要列表（id、name、version、trust_level、description）。需要 `agents:read` scope。

#### GET /agents/{agent_id} — 获取 Agent 详情

返回按 discovery policy 过滤后的 Agent manifest 视图。

#### GET /agents/{agent_id}/files/content — 读取 Agent 资源文件

```bash
curl "$RUNTIME_URL/agents/demo-agent/files/content?virtual_path=/README.md"
```

读取 Agent 声明 resource mount 下的文件。`virtual_path` 必须以 `/` 开头，支持 `download=true` 返回 `application/octet-stream`。

#### POST /agents — 上传 Agent 包（v1.1.2+）

```bash
# 上传 .zip 或 .tar.gz 包
curl -X POST "$RUNTIME_URL/agents" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@my-agent.zip"

# 覆盖已有 Agent
curl -X POST "$RUNTIME_URL/agents?overwrite=true" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@my-agent.tar.gz"
```

上传 Agent 压缩包（`.zip` 或 `.tar.gz`），解压到 `agents_dir`，校验 AGENT.yaml，触发 registry reload。需要 `admin:runtime` scope。压缩包内必须包含一个 `AGENT.yaml`（可位于任意子目录深度）。成功返回 `{"agent_id": "...", "message": "..."}`。

#### POST /agents/{agent_id}/delete — 删除 Agent（v1.1.2+）

```bash
curl -X POST "$RUNTIME_URL/agents/my-agent/delete" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

删除 `agents_dir` 下对应的 agent 目录，触发 registry reload。需要 `admin:runtime` scope。若被删 agent 被其他 agent 以子 agent 引用，reload 会检测到引用断裂并拒绝操作。成功返回 `{"agent_id": "...", "message": "..."}`。

#### POST /agents/reload — 手动重载 Registry（v1.1.2+）

```bash
curl -X POST "$RUNTIME_URL/agents/reload" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

手动触发全量 registry 扫描，等价于文件系统变更后的自动 reload。需要 `admin:runtime` scope。返回当前 agent 数量、列表和 load 诊断信息。

**文件系统自动监控**：Runtime 默认启用 `agents_dir` 的文件系统监控（可通过 `AGENT_RUNTIME_WATCH_AGENTS=false` 关闭），变更后 0.5 秒防抖自动 reload，无需手动调用 `/agents/reload`。

**对运行中任务的影响**：动态加载不影响已在运行的任务——`TaskRecord.agent_manifest_snapshot` 在任务创建时已冻结 manifest，新任务使用 reload 后的新 manifest。

### 5.5 Workspace API

#### GET /workspaces/{workspace_id}/files — 列出文件

```bash
curl "$RUNTIME_URL/workspaces/$WORKSPACE_ID/files?path=output"
```

#### GET /workspaces/{workspace_id}/files/content — 读取文件

```bash
# 文本文件
curl "$RUNTIME_URL/workspaces/$WORKSPACE_ID/files/content?path=output/report.md"

# 二进制文件下载
curl -L "$RUNTIME_URL/workspaces/$WORKSPACE_ID/files/content?path=output/deck.pptx&download=true" -o deck.pptx
```

#### PUT /workspaces/{workspace_id}/files/content — 写入文件

```bash
curl -X PUT "$RUNTIME_URL/workspaces/$WORKSPACE_ID/files/content?path=output/report.md" \
  -H "Content-Type: application/json" \
  -d '{"content": "# Hello World", "encoding": "utf-8"}'
```

#### DELETE /workspaces/{workspace_id}/files/content — 删除文件

### 5.6 A2A API

#### POST /a2a/invoke — 本地 A2A 调用

```bash
curl -X POST "$RUNTIME_URL/a2a/invoke" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "specialist-agent",
    "input": {"task": "generate_report", "data": {...}},
    "caller_task_id": "<parent_task_id>",
    "timeout": 300
  }'
```

响应：`A2AInvokeResponse`。

### 5.7 Callback API

#### POST /callbacks/{wait_id} — 外部回调投递

用于外部系统完成后将结果投递给等待中的 Task。

### 5.8 Runtime API

| 路径 | 说明 |
| --- | --- |
| `GET /runtime/health` | 健康检查 |
| `GET /runtime/ready` | 就绪检查（200 表示可执行任务） |
| `GET /runtime/deployment` | 部署配置快照 |
| `GET /runtime/preflight` | 前置检查（模型、DB、workspace、sandbox） |
| `GET /runtime/production-readiness` | 生产就绪检查（503 表示未就绪） |
| `GET /runtime/capability-health` | 能力健康状态 |
| `GET /runtime/diagnostics` | 全面诊断（migration、validation、safety） |
| `POST /runtime/maintenance/purge-soft-deleted-sessions` | 清理软删除会话 |
| `POST /runtime/maintenance/run-data-retention` | 执行数据保留策略 |

### 5.9 认证模式

| 模式 | 凭据 | 用途 |
| --- | --- | --- |
| `none` | 无需凭据 | 仅限本地开发 |
| `static_api_key` | `Authorization: Bearer <key>` 或 `X-API-Key: <key>` | 内部服务 |
| `jwt_jwks` | `Authorization: Bearer <jwt>` | 用户态 SaaS |
| `trusted_gateway` | 网关注入 principal 签名头 | 平台网关统一鉴权 |

### 5.10 Scope 权限参考

| Scope | 用途 |
| --- | --- |
| `sessions:create` | 创建 Session |
| `sessions:read` | 读取 Session |
| `sessions:update` | 更新 Session |
| `sessions:delete` | 删除 Session |
| `messages:read` | 读取消息 |
| `tasks:start` | 启动 Task |
| `tasks:start:any_user` | 代表其他用户启动 Task |
| `tasks:read` | 读取 Task |
| `tasks:stream` | 订阅 SSE |
| `tasks:resume` | 恢复 Task |
| `tasks:cancel` | 取消 Task |
| `events:read` | 读取事件 |
| `workspaces:read` | 读取工作区文件 |
| `workspaces:write` | 写入工作区文件 |
| `agents:read` | 读取 Agent 信息 |
| `callbacks:deliver` | 回调投递 |
| `admin:runtime` | 运维管理、Agent 动态管理（上传/删除/reload）、跨 owner 访问 |

---

## 第六章 配置参考

### 6.1 配置分层

AgentRuntime 有四层配置，按优先级从高到低：

```
环境变量 (.env)           ← 最高优先级，用于覆盖机密和差异化配置
    ↓ 覆盖
部署配置 YAML (configs/*.yaml)  ← 基础设施：路径、存储、日志、模型、策略
    ↓ 覆盖
代码默认值                  ← DeploymentConfig 模型默认值
```

| 层级 | 格式 | 负责角色 | 说明 |
| --- | --- | --- | --- |
| 环境变量 (`.env`) | dotenv | 部署/开发者 | API Key、Base URL、路径覆盖。仅设置与 YAML 不同的值 |
| DeploymentConfig | YAML | 部署/平台工程 | 基础设施：路径、存储、日志、模型、策略 |
| RuntimePolicyConfig | YAML | 安全运维 | Trust-Level 策略：network/code/filesystem 权限上限 |
| AGENT.yaml | YAML | Agent 开发者 | Agent 能力声明：model、tools、capabilities、skills |

**关键原则**：大部分配置已在 `configs/*.yaml` 中按 profile 预设，`.env` 中仅需覆盖 API Key 等机密信息和差异化配置。重复 YAML 默认值的环境变量属于冗余，不应出现在 `.env` 中。

### 6.2 环境变量参考

以下为 `.env.example` 中使用的核心环境变量。标注"YAML 兜底"的变量在 `configs/*.yaml` 中已有默认值，通常无需在 `.env` 中设置。

#### 6.2.1 必填（无 YAML 兜底）

| 变量 | 说明 |
| --- | --- |
| `OPENAI_COMPATIBLE_API_KEY` | openai_compatible provider 的 API Key |
| `OPENAI_COMPATIBLE_BASE_URL` | openai_compatible provider 的 Base URL（注释参考：`https://api.deepseek.com`、`https://dashscope.aliyuncs.com/compatible-mode/v1`） |

#### 6.2.2 可选覆盖（YAML 有默认值）

| 变量 | YAML 字段 | 说明 |
| --- | --- | --- |
| `AGENT_RUNTIME_CONFIG_PATH` | — | 指定部署配置 YAML 路径。未设置时自动发现：`./agent-runtime.yaml` → `./configs/dev.yaml` → `~/.config/agent-runtime/config.yaml` |
| `AGENT_RUNTIME_DEFAULT_MODEL` | `models.default_model` | 覆盖默认模型名 |
| `AGENT_RUNTIME_DEFAULT_MODEL_MAX_INPUT_TOKENS` | `models.max_input_tokens` | 覆盖最大输入 token 数 |
| `AGENT_RUNTIME_DEFAULT_MODEL_MAX_OUTPUT_TOKENS` | `models.max_output_tokens` | 覆盖最大输出 token 数 |

#### 6.2.3 基础路径（有 YAML + 代码双重兜底）

仅在需要覆盖默认路径时设置。以下变量在 `configs/*.yaml` 的 `paths` 段均有对应配置，且代码层有最终 fallback，绝大多数场景无需在 `.env` 中设置：

| 变量 | 说明 |
| --- | --- |
| `AGENT_RUNTIME_AGENTS_DIR` | Agent 配置目录 |
| `AGENT_RUNTIME_WORKSPACE_ROOT` | Workspace 根目录 |
| `AGENT_RUNTIME_SCHEMA_PATH` | JSON Schema 路径 |
| `AGENT_RUNTIME_MANIFEST_PATH` | 运行时 Manifest 路径 |
| `AGENT_RUNTIME_WATCH_AGENTS` | 是否启用 agents_dir 文件监控（默认 `true`），变更后自动 reload |

#### 6.2.4 Daytona 沙箱

| 变量 | 说明 |
| --- | --- |
| `AGENT_RUNTIME_DAYTONA_URL` | Daytona API 地址 |
| `DAYTONA_API_KEY` | Daytona API 密钥 |
| `AGENT_RUNTIME_DAYTONA_IMAGE` | 沙箱镜像（可选，默认 `agent-runtime-sandbox:base`） |

#### 6.2.5 持久化

| 变量 | 说明 |
| --- | --- |
| `AGENT_RUNTIME_DATABASE_URL` | PostgreSQL 连接串（仅 postgres 后端需要） |

#### 6.2.6 可观测性（可选，无 YAML 兜底）

| 变量 | 说明 |
| --- | --- |
| `LANGFUSE_PUBLIC_KEY` | Langfuse 公钥 |
| `LANGFUSE_SECRET_KEY` | Langfuse 密钥 |
| `LANGFUSE_HOST` | Langfuse 地址 |
| `MEM0_API_KEY` | Mem0 API 密钥 |

#### 6.2.7 日志（YAML 有默认值，通常无需覆盖）

日志级别、保留策略、格式等均在 `configs/*.yaml` 的 `logging` 段配置。调试时可临时通过环境变量开启完整日志：

| 变量 | 说明 |
| --- | --- |
| `AGENT_RUNTIME_LOG_LEVEL` | 覆盖日志级别（如 `DEBUG`） |
| `AGENT_RUNTIME_LOG_FULL_PROMPT` | 记录完整 Prompt（调试用） |
| `AGENT_RUNTIME_LOG_FULL_OUTPUT` | 记录完整模型输出（调试用） |
| `AGENT_RUNTIME_LOG_ALL_LLM_REQUESTS` | 记录全部 LLM 请求/响应（调试用） |

### 6.3 部署配置 YAML 参考

完整配置示例（`configs/dev.yaml`）：

```yaml
version: agent-runtime-config/v1

profile: local_dev

runtime:
  core: deepagents

paths:
  agents_dir: agents
  schema_path: schemas/agent.schema.json
  workspace_root: .runtime/workspaces
  log_dir: .runtime/logs

stores:
  backend: memory          # memory | postgres

workspace:
  backend: local            # local | daytona

logging:
  mode: auto
  level: DEBUG
  json: false
  full_prompt: true
  full_output: true
  all_llm_requests: true
  max_field_chars: 500
  retention_days: 30
  retention_audit_days: 90
  retention_error_days: 90

observability:
  backend: noop             # noop | otel | langfuse

models:
  default_provider: openai_compatible
  default_model: deepseek-v4-flash
  max_input_tokens: 250000
  max_output_tokens: 32000

model_router:
  enabled: true
  strategy: advisor_first
  executor:
    provider: openai_compatible
    model: deepseek-v4-flash
  advisor:
    provider: openai_compatible
    model: deepseek-v4-pro
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

policy:
  defaults:
    execution:
      default_backend: subprocess
      allowed_backends: [subprocess]
      subprocess_enabled_for_trust: [verified, platform]
      default_timeout_seconds: 300
    workspace:
      isolation: session_shared
      quota_mb: 1024
      max_file_size_mb: 64
```

### 6.4 Runtime Policy 配置

Runtime Policy 控制信任级别的能力上限（文件通过 `AGENT_RUNTIME_CONFIG_PATH` 指定）：

```yaml
version: agent-runtime-policy/v1
defaults:
  limits:
    timeout_seconds: 600
    max_tool_calls: 50
    max_subagent_calls: 10
  execution:
    default_backend: daytona
    allowed_backends: [daytona]
    default_timeout_seconds: 300
operator_policy:
  trust_levels:
    untrusted:
      network:
        mode: block_all
      code_execution:
        enabled: false
      filesystem:
        quota_mb: 128
        max_file_size_mb: 10
    verified:
      network:
        mode: allowlist
        allowed_domains: [api.company.com]
      code_execution:
        enabled: true
        backend: daytona
        allowed_backends: [daytona]
        require_command_allowlist: true
        max_timeout_seconds: 300
      filesystem:
        quota_mb: 1024
        max_file_size_mb: 64
    platform:
      network:
        mode: full
        allowed_domains: ['*']
      code_execution:
        enabled: true
        backend: subprocess
        allowed_backends: [subprocess, daytona]
        require_command_allowlist: false
        max_timeout_seconds: 3600
      filesystem:
        quota_mb: 10240
        max_file_size_mb: 512
```

### 6.5 Product Profile 映射

| Product profile | 说明 | 默认存储 | 默认认证 | 适用场景 |
| --- | --- | --- | --- | --- |
| `local_dev` | 本地开发 | memory | none | 个人开发调试 |
| `embedded_single_tenant` | 嵌入式单租户 | memory | none | 产品内嵌 |
| `embedded_multi_tenant` | 嵌入式多租户 | postgres | trusted_gateway | SaaS 产品内嵌 |
| `standalone_internal_service` | 独立内部服务 | postgres | static_api_key | 内部 HTTP 服务 |
| `regulated_enterprise` | 合规企业 | postgres | trusted_gateway | 合规要求场景 |

### 6.6 配置文件自动发现

当 `AGENT_RUNTIME_CONFIG_PATH` 环境变量未设置时，Runtime 按以下顺序查找配置文件：

1. `<AGENT_RUNTIME_ROOT>/agent-runtime.yaml`
2. `<AGENT_RUNTIME_ROOT>/configs/dev.yaml`
3. `~/.config/agent-runtime/config.yaml`（XDG 标准路径）

未找到任何配置文件时，日志中会输出 warning 并使用全部默认值启动。**生产环境建议显式设置 `AGENT_RUNTIME_CONFIG_PATH` 指向部署配置文件。**

---

## 第七章 扩展机制与插件开发

AgentRuntime 的核心扩展机制基于 Python `typing.Protocol`（结构化子类型），任何遵循协议接口的对象都可作为插件注入。以下逐一说明各扩展点。

### 7.1 核心引擎扩展 — RuntimeCore

`RuntimeCore` 协议定义了执行引擎接口，可以实现自定义引擎替换默认的 DeepAgents。

```python
from typing import AsyncIterator
from agent_runtime.core.protocol import RuntimeCore
from agent_runtime.runtime.events import RuntimeEvent

class MyCustomCore:
    """自定义执行引擎"""

    async def run(
        self,
        task_id: str,
        session_id: str,
        agent_id: str,
        input: str | dict,
        manifest: dict,
        workspace_manager,
        trust_level,
        metadata: dict,
        thread_binding_id: str | None = None,
    ) -> AsyncIterator[RuntimeEvent]:
        # 实现自定义执行逻辑
        # 通过 yield RuntimeEvent 推送事件
        yield RuntimeEvent(
            event="task_started",
            task_id=task_id,
            agent_id=agent_id,
            payload={},
        )
        # ... 执行逻辑 ...
        yield RuntimeEvent(
            event="task_completed",
            task_id=task_id,
            agent_id=agent_id,
            payload={"final_output": "done"},
        )

    async def resume(
        self,
        task_id: str,
        session_id: str,
        agent_id: str,
        resume_envelope,
        manifest: dict,
        workspace_manager,
        trust_level,
        metadata: dict,
    ) -> AsyncIterator[RuntimeEvent]:
        # 实现恢复逻辑
        ...
```

在 `RuntimeService.from_settings()` 中注入或在部署配置中指定 `runtime.core: my_custom`。

### 7.2 存储后端扩展

存储后端通过 `stores/protocol.py` 中的四个协议定义：

```python
# Session 存储
class SessionStore(Protocol):
    async def create(self, session: SessionRecord) -> SessionRecord: ...
    async def get(self, session_id: UUID | str) -> SessionRecord: ...

# Task 存储
class TaskStore(Protocol):
    async def create(self, task: TaskRecord) -> TaskRecord: ...
    async def set_status(self, task_id, status): ...

# Message 存储
class MessageStore(Protocol):
    async def create(self, message: MessageRecord) -> MessageRecord: ...

# Event 存储
class EventStore(Protocol):
    async def publish(self, event: RuntimeEvent) -> int: ...  # 返回 sequence
    async def stream(self, task_id, after_sequence) -> AsyncIterator[RuntimeEvent]: ...
```

实现其中一个或全部协议，即可替换默认存储。当前实现：

- `PostgresSessionStore` / `PostgresTaskStore` / `PostgresMessageStore` / `PostgresEventStore`（`stores/postgres_store.py`）
- 内存模式使用默认 dict 实现

### 7.3 检查点（Checkpointer）扩展

控制 LangGraph 检查点持久化：

```python
from agent_runtime.checkpoint.protocol import CheckpointerFactory

class MyCheckpointerFactory:
    def create(self):
        """返回检查点对象"""
        return my_checkpointer

    async def acreate(self):
        """异步工厂方法"""
        return await my_async_checkpointer
```

当前实现：`LangGraphCheckpointerFactory`（PostgresSaver）/ `NoOpCheckpointerFactory`。

### 7.4 沙箱后端扩展

实现 `CodeExecutor` 协议来添加新的代码执行后端：

```python
from agent_runtime.sandbox.protocol import CodeExecutor, ExecutionResult

class MySandboxExecutor:
    async def execute(
        self,
        command: str,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
        workspace_id: str | None = None,
    ) -> ExecutionResult:
        # 执行命令并返回结果
        return ExecutionResult(
            exit_code=0,
            stdout="output",
            stderr="",
            duration_ms=100,
            timed_out=False,
            output_refs=[],
        )
```

当前实现：`SubprocessExecutor`（本地子进程）/ `DaytonaExecutor`（远程沙箱）。

### 7.5 内存后端扩展

```python
from agent_runtime.memory.protocol import MemoryGovernanceBackend

class MyMemoryBackend:
    async def capabilities(self) -> dict:
        return {"version": 2, "modes": ["search", "write", "update", "delete"]}

    async def search(self, request) -> list:
        ...

    async def write(self, record) -> str:
        ...

    async def delete(self, memory_id: str) -> None:
        ...
```

当前实现：`Mem0Backend` / `RecordStoreBackend`（v2）/ `NoOpMemoryBackend`。

### 7.6 可观测性后端扩展

```python
from agent_runtime.observability.protocol import ObservabilityBackend

class MyObservabilityBackend:
    async def record_task_span(self, span: TaskSpanRecord) -> None:
        # 记录 Task 跨度
        ...

    async def record_event(self, name: str, attributes: dict) -> None:
        # 记录事件
        ...
```

当前实现：`LangfuseBackend` / `OTelBackend` / `NoOpBackend`。

### 7.7 认证提供者扩展

```python
from agent_runtime.security.protocols import AuthProvider
from agent_runtime.security.principal import Principal

class MyAuthProvider:
    async def resolve(
        self,
        headers: dict,
        query: dict,
        cookies: dict,
        source_ip: str | None = None,
    ) -> Principal | None:
        # 从请求中解析 Principal
        ...
```

当前实现：`StaticApiKeyAuthProvider` / `JwtJwksAuthProvider` / `TrustedGatewayAuthProvider`。

### 7.8 MCP 工具集成

MCP（Model Context Protocol）是接入外部工具服务的主要方式。

**Manifest 声明**：

```yaml
mcp_servers:
  my-service:
    description: "My external tool service"
    transport: http
    server_url: "https://service.example.com/mcp"
    auth:
      type: bearer
      credentials: "${env:MCP_API_KEY}"
```

**支持传输方式**：

| Transport | 说明 | 配置要点 |
| --- | --- | --- |
| `stdio` | 子进程通信 | 需确保命令在 PATH 中可用 |
| `http` / `sse` | HTTP 服务 | 需配置网络策略允许目标 host |
| `websocket` | WebSocket | 网络策略需允许 WebSocket 连接 |

**工具发现流程**：

```
Task 启动
  │
  ├── 连接所有 MCP Server
  ├── 发现可用工具及 Input Schema
  ├── 应用 allowed_tools 过滤
  ├── 检查跨 Server 工具名唯一性
  ├── 写入 checksum 和 auth fingerprint
  └── 合并到 Effective Tool Snapshot
```

**预设 Playwright MCP**：

```yaml
# 部署配置中的 preset MCP
policy:
  defaults:
    preset_mcp:
      playwright:
        enabled: true
        concurrency: 2
        timeout: 60000
        retention: success_only_or_3min
```

### 7.9 动态能力提供者（Dynamic Capability Provider）

用于在运行时动态注入工具，而非在 Manifest 中静态声明：

```python
class MyCapabilityProvider:
    async def load_tools(self, manifest: dict) -> list[BaseTool]:
        # 动态加载工具
        tools = []
        if "my-feature" in manifest.get("metadata", {}).get("capabilities", []):
            tools.append(my_custom_tool)
        return tools
```

通过 `AgentRegistry.set_dynamic_capability_provider()` 注册。

### 7.10 中间件扩展

在 DeepAgents 执行管线中添加自定义中间件：

```python
from langchain.agents.middleware import AgentMiddleware

class MyCustomMiddleware(AgentMiddleware):
    async def handle_tool_call(
        self, request: ToolCallRequest, next_callable
    ) -> ToolCallResponse:
        # 在工具调用前后添加逻辑
        self.log_before(request)
        response = await next_callable(request)
        self.log_after(response)
        return response
```

---

## 第八章 部署运维指南

### 8.1 环境要求

| 组件 | 最低要求 | 推荐 | 说明 |
| --- | --- | --- | --- |
| 操作系统 | Linux / macOS / Windows(WSL2) | Linux | 详见下方 Windows 说明 |
| Python | 3.11 | 3.12+ | 运行时要求 |
| 数据库 | — | PostgreSQL 16 | 生产必备 |
| 沙箱 | — | Daytona + Docker | 代码执行场景，Windows 需 Docker Desktop(WSL2) |
| 内存 | — | 64GB+ | 多 Task 并发 |

**Windows 部署说明**：生产环境建议使用 Linux 服务器或 Docker 容器。若必须在 Windows 上部署，请使用 WSL2 + Docker Desktop，避免使用 Windows 原生环境。沙箱（Daytona）、MCP 脚本预设等组件依赖 Linux 容器运行时，无法在 Windows 原生环境下运行。

### 8.2 启动方式

#### 方式1：开发模式（scripts/start.sh）

```bash
# 自动检测 dev/bundle 模式
# dev 模式：默认加载 configs/dev.yaml（memory 存储，本地工作区）
# bundle 模式：默认加载 configs/prod.yaml（需 runtime/manifest.json）
./scripts/start.sh

# 带 Daytona 沙箱
./scripts/start.sh --with-daytona

# 覆盖配置文件
AGENT_RUNTIME_CONFIG_PATH=configs/prod.yaml ./scripts/start.sh
```

#### 方式2：手动启动（CLI）

```bash
# 使用 CLI serve 命令
agent-runtime serve --config configs/dev.yaml

# 生产配置
agent-runtime serve --config configs/prod.yaml

# 或使用 ProductRuntimeConfig 格式
agent-runtime serve --config agent-runtime.yaml --product
```

#### 方式3：uvicorn 直接启动

```bash
# 安装完整依赖
pip install -e ".[deepagents,postgres]"

# 执行数据库迁移
python -m agent_runtime.db.migrations migrate \
  --database-url "$AGENT_RUNTIME_DATABASE_URL"

# 启动 uvicorn
uvicorn agent_runtime.api.app:create_app \
  --factory \
  --host 0.0.0.0 \
  --port 8080
```

#### 方式4：Embedded SDK 集成

```python
from agent_runtime import RuntimeService
from agent_runtime.runtime.models import CreateSessionRequest, StartTaskRequest

# 构造运行时
runtime = RuntimeService.for_product({
    "product_name": "MyApp",
    "profile": "embedded_single_tenant",
    "agents_dir": "agents",
})
await runtime.initialize()

# 创建会话并启动任务
session = await runtime.create_session(
    CreateSessionRequest(agent_id="demo-agent")
)
task = await runtime.start_task(StartTaskRequest(
    session_id=session.session_id,
    agent_id="demo-agent",
    input="Hello",
))
```

### 8.3 数据库迁移

AgentRuntime 使用自建的 SQL 迁移系统（16 个迁移文件）：

```bash
# 执行迁移
python -m agent_runtime.db.migrations migrate \
  --database-url "$AGENT_RUNTIME_DATABASE_URL"

# 查看迁移状态
python -m agent_runtime.db.migrations status \
  --database-url "$AGENT_RUNTIME_DATABASE_URL"
```

关键迁移表（按顺序）：

| 迁移 | 内容 |
| --- | --- |
| `0001_baseline` | 基础表结构 |
| `0002_session_last_task` | Session 最近任务投影 |
| `0003_runtime_event_log_sequence` | 事件序列号 |
| `0004_runtime_event_correlation` | 事件关联 |
| `0005_task_wait_projection` | Task 等待状态 |
| `0006_messages_and_task_links` | 消息与 Task 关联 |
| `0007_principal_ownership` | 主体所有权 |
| `0008_task_middleware_snapshot` | 中间件快照 |
| `0009_context_summaries` | 上下文摘要 |
| `0009_workspace_ownership` | 工作区所有权 |
| `0010_memory_records` | 内存记录 |
| `0011_memory_records_expires_idx` | 过期索引 |
| `0012_active_foreground_task_guard` | 前台任务保护 |
| `0013_task_lifecycle_persistence` | Task 生命周期持久化 |
| `0014_remove_task_mode` | 移除旧 mode 字段 |
| `0015_deepagents_thread_binding` | DeepAgents 线程绑定 |
| `0016_workspace_ownership_cleanup_at` | 工作区所有权清理时间 |

### 8.4 日志系统

AgentRuntime 提供结构化日志系统(`logging/`)，支持三种模式：

| 模式 | 行为 |
| --- | --- |
| `off` | 关闭日志 |
| `auto` / `standalone` | 接管日志处理器，每日轮转 |
| `embedded` | 保留现有处理器，额外配置 |

**日志文件**（standalone 模式）：

| 文件 | 内容 |
| --- | --- |
| `app.log` | 全量日志 |
| `error.log` | ERROR 级别及以上 |
| `audit.json` | 审计日志（JSON） |
| `llm_trace.json` | LLM 调用追踪（JSON） |
| `tool_trace.json` | 工具调用追踪（JSON） |
| `metrics.json` | 指标日志（JSON） |
| `agent_runtime.lifecycle.log` | 运行时生命周期 |

**日志字段控制**：

- `log_full_prompt: true` — 在 `llm_trace` 中记录完整 system/user prompt。
- `log_full_output: true` — 在 `llm_trace` 中记录完整模型输出。
- `log_all_llm_requests: true` — 记录每次 LLM 请求的摘要信息（受 `max_field_chars` 截断限制）。
- `max_field_chars` — 控制 LLM trace 中 content 字段的最大字符数，默认 500。

**日志上下文**：通过 `contextvars` 自动注入 `request_id`、`trace_id`、`session_id`、`task_id`、`agent_id`、`workspace_id` 等字段。

### 8.5 数据保留策略

```yaml
# 部署配置
retention:
  session_deleted_purge_days: 30   # 软删除 30 天后清理
  runtime_event_days: 90           # 事件保留 90 天
```

通过以下 API 手动触发清理：

```bash
# 清理软删除会话
POST /runtime/maintenance/purge-soft-deleted-sessions

# 执行全部数据保留策略
POST /runtime/maintenance/run-data-retention
```

### 8.6 生产就绪检查清单

```bash
# 前置检查
agent-runtime doctor --config agent-runtime.yaml --product --strict-production

# API 检查
curl "$RUNTIME_URL/runtime/preflight"      # 无 blocker
curl "$RUNTIME_URL/runtime/ready"          # 200 = 就绪
curl "$RUNTIME_URL/runtime/production-readiness"  # 200 = ready，503 = 未就绪
curl "$RUNTIME_URL/runtime/diagnostics"    # 全面诊断
curl "$RUNTIME_URL/runtime/capability-health" # 能力健康
```

生产上线 checklist：

- [ ] `agent-runtime validate` 通过
- [ ] `agent-runtime doctor --strict-production` 通过
- [ ] `GET /runtime/preflight` 无 blocker
- [ ] `GET /runtime/production-readiness` 返回 ready
- [ ] Postgres 迁移已完成并验证
- [ ] Auth/Scope/Tenant 配置正确
- [ ] Workspace Ownership 可回溯
- [ ] Daytona/Sandbox 配置完成
- [ ] 文件型 Agent 使用 artifact acceptance
- [ ] 可观测性已接入
- [ ] 日志保留策略已确认

---

## 第九章 安全模型

### 9.1 信任模型

AgentRuntime 使用三层信任模型：

```
Manifest 声明的 trust_level（上限）
     ↓
Session/调用方指定的 trust_level（按需降级）
     ↓
Runtime Policy 按 trust_level 控制的能力上限
```

**三信任级别**：

| 级别 | 信任 | 典型能力 |
| --- | --- | --- |
| `platform` | 平台内置 | workspace、code execution（subprocess）、full network、subagents |
| `verified` | 经审核 | workspace、code execution（daytona）、allowlist network、subagents |
| `untrusted` | 社区/未审核 | 最小能力，无 code execution、无 subagents、网络禁止 |

### 9.2 策略引擎（Policy Engine）

策略引擎（`policy/engine.py`）拦截所有工具调用，使用四道门控（Gates）：

```
Gate G1: 工具调用策略
  └── 验证工具是否允许当前信任级别使用

Gate G2: 命令执行策略
  ├── 检查信任级别是否允许执行
  ├── 命令模式匹配（allow/deny patterns）
  └── 动态安装检测（npm/pip install 拦截）

Gate G3: 工作区访问策略
  ├── 路径遍历保护
  ├── 配额限制（max_file_size、quota_mb）
  └── 文件类型限制

Gate G4: 内存访问策略
  └── Session 级别的内存隔离
```

### 9.3 Scope 权限体系

每个 API 端点要求特定的 Scope。调用方的 Principal 必须持有相应 Scope 才能访问：

```python
# 示例：创建 Task 需要 tasks:start scope
@router.post("")
async def start_task(
    request: StartTaskRequest,
    principal: Principal = Depends(require_scope(TASKS_START)),
    ...
):
```

**默认 Scope 捆绑**：

| Principal 类型 | 包含 Scope |
| --- | --- |
| USER | 所有标准 Scope（含 workspace 读写） |
| OPERATOR | 全部 Scope（含 admin:runtime） |
| SERVICE | 基础 Scope（不含 workspace 写入和删除） |

### 9.4 认证模式

| 模式 | 安全级别 | 生产可用 | 说明 |
| --- | --- | --- | --- |
| `none` | 无 | ❌ | 仅限本地开发 |
| `static_api_key` | 低 | ⚠️ | 内部服务间调用 |
| `jwt_jwks` | 高 | ✅ | 用户态 JWT 认证 |
| `trusted_gateway` | 高 | ✅ | 网关签名认证 |

### 9.5 所有权与多租户

- **Session/Task/Workspace** 记录创建者的 `owner_user_id` 和 `owner_principal_id`。
- 普通用户只能访问自己创建的资源。
- `admin:runtime` Scope 可以绕过所有者检查。
- 多租户场景需额外配置 tenant_id 隔离。

### 9.6 敏感信息保护

- 日志系统自动脱敏：匹配 `token`、`secret`、`password`、`api_key`、`credential`、`private_key` 等关键词的值会被自动替换。
- Manifest 引用使用 `${secret:KEY}` / `${env:VAR}` / `${user_credential:REF}`，不写入明文。
- RuntimeEvent 事件在持久化时自动脱敏：
  - `message_delta` 和 `model_thinking` 默认只保存元数据（大小等），不保存原文。
  - `task_completed` 的 `final_output` 保存摘要（类型、字符数、SHA-256）。
- MCP 认证绑定指纹使用脱敏后的摘要。

### 9.7 最佳实践

1. **最小权限原则**：Agent 只请求必须的能力，`capabilities` 中 `untrusted` 级 Agent 不应请求 code execution。
2. **信任降级**：外部来源的 Agent 应使用 `untrusted` 级别。
3. **命令白名单**：`verified` 级别若开启 code execution，必须配置严格的 command allowlist。
4. **沙箱隔离**：生产环境代码执行使用 Daytona 沙箱，不要使用 subprocess。
5. **网络限制**：非 `platform` 级别不应使用全通网络策略。

---

## 第十章 测试指南

### 10.1 测试架构

```
tests/
├── unit/             # 单元测试（~100 文件，覆盖各模块）
├── integration/      # 集成测试（~34 文件，覆盖 API 和核心流程）
├── e2e/              # 端到端测试（升级矩阵、验收）
├── security/         # 安全测试（策略拒绝、沙箱逃逸等）
├── live/             # 需要真实外部服务的测试
├── performance/      # 性能基线测试
└── fixtures/         # 测试夹具（Agent 配置、数据）
```

### 10.2 运行测试

```bash
# 运行全部测试
uv run pytest

# 运行特定模块
uv run pytest tests/unit/test_agent_loader.py
uv run pytest tests/unit/test_manifest_v11_contracts.py
uv run pytest tests/unit/test_examples_v11_manifests.py

# 运行集成测试
uv run pytest tests/integration/test_v11_contract_baseline.py

# 带覆盖率
uv run pytest --cov=agent_runtime
```

### 10.3 集成测试模式

集成测试通常使用 `RuntimeService` + FastAPI `TestClient`：

```python
import pytest
from fastapi.testclient import TestClient
from agent_runtime import RuntimeService
from agent_runtime.runtime.settings_env import RuntimeSettings
from agent_runtime.api.app import create_app

@pytest.fixture
def runtime():
    settings = RuntimeSettings(
        agents_dir="tests/fixtures/agents",
        core="fake",  # 使用假引擎
    )
    svc = RuntimeService.from_settings(settings)
    # ... 根据测试需要设置
    return svc

@pytest.fixture
def client(runtime):
    app = create_app(runtime)
    return TestClient(app)

@pytest.mark.asyncio
async def test_task_lifecycle(client, runtime):
    # 创建 Session
    session_resp = client.post("/sessions", json={
        "agent_id": "research-agent",
        "title": "test",
    })
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    # 启动 Task
    task_resp = client.post("/tasks", json={
        "session_id": session_id,
        "agent_id": "research-agent",
        "input": "test input",
    })
    assert task_resp.status_code == 200

    # 验证
    task_id = task_resp.json()["task_id"]
    task = await runtime.get_task(task_id)
    assert task.status in (...,)
```

### 10.4 测试夹具

- `tests/fixtures/agents/`：预置的 Agent 配置（research-agent、subagent-parent-agent 等）。
- `tests/fixtures/capability_contracts.py`：标准化的测试数据（RuntimeEvent、TaskRecord 等）。
- `conftest.py`：全局 Fixture（repo_root、wave0 基线事件等）。

### 10.5 Manifest 校验测试

```bash
# 校验所有示例 manifest
python scripts/validate_agent.py --all --strict

# 校验指定 manifest
python scripts/validate_agent.py agents/my-agent/AGENT.yaml

# 检查旧格式 manifest 残留
grep -R -n -E 'schema_version: anp-agent/v1($|[[:space:]])' src scripts tests examples
```

### 10.6 Live 测试

需要真实外部服务的测试在 `tests/live/` 目录：

```bash
# 需要配置 API keys 和外部服务
uv run pytest tests/live/
```

---

## 第十一章 故障排除

### 11.1 Runtime 未就绪

**现象**：API 返回 `runtime_not_ready` 或 `/ready` 失败。

**检查步骤**：

1. `GET /runtime/preflight` — 查看哪些 check 失败
2. `GET /runtime/ready` — 返回 200 或错误
3. `GET /runtime/diagnostics` — 查看 validation_issues
4. `GET /runtime/production-readiness` — 查看 production_safety_checks

**常见原因**：

- 模型 provider credential 未配置。
- Agent registry 加载失败（manifest 语法错误）。
- MCP server 连接失败。
- Daytona endpoint 不可用。
- 数据库迁移未执行。

### 11.2 Agent 无法加载

**现象**：`GET /agents` 看不到目标 Agent。

**检查**：

1. `AGENT.yaml` 是否在 `agents_dir` 下。
2. 手动运行 `python scripts/validate_agent.py <path>`。
3. 检查日志中的 `AgentLoadDiagnostic` 信息。
4. 确认 `schema_version` 为 `anp-agent/v1.1` 或 `v1.2`。
5. 检查 Agent JSON Schema 是否符合 `schemas/agent.schema.json`。

### 11.3 Task 启动失败

**现象**：`POST /tasks` 返回错误，或 Task 立即进入 `failed` 状态。

**检查**：

1. `GET /tasks/{task_id}/diagnostics` — 查看 error、policy、context 信息。
2. `GET /tasks/{task_id}/events?after_sequence=0` — 查看初始事件。
3. 检查 TaskRecord 中的 `error` 字段。

**常见原因**：

- Manifest 中 `${env:}` 或 `${secret:}` 引用缺失。
- Agent 声明的能力被 policy 拒绝导致初始化失败。
- 模型 API 调用失败（credential、quota、network）。
- 缺少 workspace（`capabilities.workspace.required=true` 但 workspace 不可用）。

### 11.4 事件缺失或 UI 不更新

**检查**：

1. `GET /tasks/{task_id}/events?after_sequence=0` — 确认有持久化事件。
2. SSE 是否使用正确的 stream-token 或 `tasks:stream` scope。
3. 客户端是否按 `(task_id, sequence)` 去重和排序。
4. 流是否因为 `task_waiting` 正常结束（需要 resume）。

### 11.5 工具不可见

**检查** Task 的 Effective Tool Snapshot：

1. Agent trust_level 是否允许该工具。
2. 检查 `code_execution.enabled` 是否为 true。
3. Sandbox backend 是否满足执行协议。
4. Workspace 是否可用。
5. MCP discovery 是否成功（MCP server 连接和工具 Schema 发现）。
6. A2A / Skill 是否被策略过滤。

### 11.6 Workspace 不同步

**现象**：Agent 声称写了文件，但 API 或 UI 看不到。

**检查**：

1. Task 的 `workspace_id` 是否正确。
2. `workspace.isolation` 是 `session_shared` 还是 `task_isolated`。
3. Daytona 工作区是否在 Task 完成前同步回 local workspace。
4. 读文件时 path 是否是 workspace-relative，不要用宿主机的绝对路径。
5. 二进制文件是否用 base64 + download 方式读写。

### 11.7 Artifact 缺失或验收失败

**检查**：

1. `acceptance.required_files[].path` 是否匹配真实输出路径。
2. 文件是否写在 `/output/` 下。
3. `type` 校验是否正确（any、pptx、docx、pdf 等）。
4. `min_size_bytes` 是否过高或文件为空。
5. Office/PDF 产物是否用正确的 sandbox profile 生成。

### 11.8 MCP 失败

| 错误 | 原因 | 处理 |
| --- | --- | --- |
| `permissions.network.mode is block_all` | 网络策略拦截 HTTP MCP | 改用 stdio 或调整网络策略 |
| `allowed_domains is empty` | allowlist 模式未配置 host | 填写目标 MCP 域名 |
| `duplicate MCP tool name` | 多个 Server 暴露同名工具 | 调整工具名或使用 allowed_tools |
| `frozen ... unavailable` | 历史快照工具无法执行 | 重新启动真实 MCP Server |

### 11.9 A2A 调用卡住

**检查**：

1. 被调 Agent 是否存在（`GET /agents`）。
2. 被调 Agent 是否 `exposes_a2a: true`。
3. 调用方是否有 `TASKS_START` 和 `AGENTS_READ` scope。
4. 外部 A2A 是否等待 `external_result` resume。
5. `tool_call_id` 是否正确回传给业务系统。

### 11.10 诊断 API 速查

```bash
# 快速诊断链路
curl "$RUNTIME_URL/runtime/preflight" | jq
curl "$RUNTIME_URL/runtime/diagnostics" | jq '.validation_issues'
curl "$RUNTIME_URL/runtime/capability-health" | jq

# Task 诊断
curl "$RUNTIME_URL/tasks/$TASK_ID/diagnostics" | jq '.policy.denials'
curl "$RUNTIME_URL/tasks/$TASK_ID/diagnostics" | jq '.tools.effective_tool_snapshot'

# 事件排查
curl "$RUNTIME_URL/tasks/$TASK_ID/events?after_sequence=0" | jq '.items[-5:]'
```

### 11.11 日志分析

**日志文件位置**：`$AGENT_RUNTIME_LOG_DIR/`（默认 `logs/`）

```bash
# 查看运行时错误
tail -f logs/error.log

# 查看审计 JSON
tail -f logs/audit.json | jq

# 查看 LLM 调用
tail -f logs/llm_trace.json | jq '.request.model'

# 查看工具调用审计
tail -f logs/tool_trace.json | jq '.tool_name'
```

---

## 附录

### A. 常用 Script 命令

```bash
scripts/start.sh              # 启动服务（自动检测模式）
scripts/restart.sh            # 重启服务
scripts/stop.sh               # 停止服务
scripts/validate_agent.py     # 校验 Agent manifest
scripts/manifest_lint.py      # Manifest 静态检查
scripts/manifest_migrate.py   # Manifest 格式迁移
scripts/preflight.sh          # 前置环境检查
scripts/deploy_daytona.sh     # Daytona 部署
scripts/build_export_smoke.sh # 导出包构建校验
```

### B. 配置 Profile 速查

| Profile | 存储 | 工作区隔离 | 认证 | 日志 |
| --- | --- | --- | --- | --- |
| `local_dev` | memory | session_shared | none | text, debug |
| `standalone_service` | memory | task_isolated | — | JSON |
| `生产推荐` | postgres | task_isolated | jwt/trusted_gateway | JSON, info |

### C. 相关文档索引

| 文档 | 内容 |
| --- | --- |
| [业务产品集成主线](product-integration-guide.md) | 产品接入完整指南 |
| [API 接入文档](...) | 全部 API 端点详情 |
| [SDK 使用文档](sdk.md) | SDK 和客户端使用 |
| [RuntimeEvent/SSE 契约](runtime-events-sse.md) | 事件格式和 SSE 协议 |
| [配置矩阵与迁移指南](configuration-migration-guide.md) | 配置迁移和兼容性 |
| [Manifest Schema 文档](manifest-schema.md) | Agent.yaml 完整 Schema |
| [MCP 工具开发](mcp-tools.md) | MCP 集成和排查 |
| [A2A 工具接入](a2a-tools.md) | Agent 间通信 |
| [Artifact Acceptance](artifact-acceptance.md) | 文件产物验收 |
| [Daytona 沙箱配置](daytona-profiles.md) | 沙箱 Profile |
| [生产上线 Checklist](production-readiness-checklist.md) | 上线检查项 |
| [故障排查手册](troubleshooting.md) | 常见问题排查 |

### D. 离线安装包

| 项目 | 说明 |
| --- | --- |
| 包路径 | `release/v1.1.2/agent-runtime-1.1.2-py312-pyc-only.tar.gz` |
| 编译环境 | Python 3.12.12 |
| 运行时依赖 | fastapi, httpx, jsonschema, pydantic>=2, pyyaml, uvicorn |
| 额外依赖（可选） | deepagents, postgres, daytona, observability, memory |
| 安装方式 | `tar -xzf <包> && cd <目录> && ./install.sh` |
| 验证 | `python -c "from agent_runtime import RuntimeService; print('ok')"` |






