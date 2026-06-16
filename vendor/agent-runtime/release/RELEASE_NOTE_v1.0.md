# AgentRuntime v1.0 正式发布

> 发布日期：2026-06-01 | 协议版本：anp-agent/v1.2 | Python ≥ 3.11

---

## 一、项目概述

AgentRuntime 是面向**声明式 Agent** 的通用执行引擎（harness）。开发者通过 `AGENT.yaml` 声明 Agent 的模型、指令、工具、权限、工作区和交付物，Runtime 负责加载 Manifest、管理 Session/Task 生命周期、执行模型-工具循环、管理工作区文件，并通过 SSE 事件流对外暴露可审计的完整执行过程。

**一句话定位：** 把 Agent 从代码中解耦出来，变成可声明、可组合、可审计、可部署的执行单元。

## 二、核心能力

### 2.1 声明式 Agent Manifest（anp-agent/v1.2）

```yaml
schema_version: anp-agent/v1.2
kind: Agent
metadata:
  id: my-agent
  name: My Agent
  trust_level: verified
model:
  provider: dashscope
  model: qwen3-max
  temperature: 0.25
instructions: |
  你是一个面向企业任务的 Agent...
capabilities:
  workspace: { required: true }
  code: { required: true, languages: [python, bash] }
  artifacts: { required: true }
```

- **一个 YAML 文件定义完整 Agent**：模型配置、系统指令、工具清单、权限边界、工作区、代码执行策略、MCP 服务器、A2A 委托、Office Skills、验收标准。
- 内置 **JSON Schema 校验**（`schemas/agent.schema.json`），编辑器可提供自动补全和即时检查。
- 提供 `manifest_lint.py` 和 `manifest_migrate.py` 工具，支持 manifest 质量检查和版本迁移。

### 2.2 完整的执行生命周期

| 阶段 | 说明 |
|---|---|
| **Session 创建** | 用户会话容器，绑定 workspace 和消息历史 |
| **Task 启动** | 冻结 Manifest 快照、中间件快照、有效工具快照和上下文 |
| **流式执行** | 模型与工具循环，通过 SSE/RuntimeEvent 实时推送每一步 |
| **等待与恢复** | 支持 Human-in-the-Loop，等待用户输入后继续执行 |
| **交付验收** | Artifact 注册与校验，阻止文件缺失时误报完成 |

**Task 状态机：** `PENDING → RUNNING → WAITING_INPUT → RUNNING → COMPLETED / FAILED / CANCELLED`

### 2.3 工具系统

- **默认工具目录：** `ls`、`read_file`、`glob`、`grep`、`write_file`、`edit_file`、`execute`、`task`、`delegate_agent`、`write_todos`、`ask_user`、`propose_plan`、`artifact_list/validate/register`、`document.convert`、`approval_request`
- **MCP（Model Context Protocol）：** 支持 stdio 和 HTTP MCP 服务器，工具自动发现与参数扁平化
- **A2A（Agent-to-Agent）：** 通过 `delegate_agent` 将子任务委托给 Runtime 注册的其他 Agent
- **Skills（可复用能力包）：** Agent 可挂载 PDF、DOCX、XLSX、PPTX、browser-use 等 Skill，按需激活

### 2.4 Office 办公文档能力

预置 5 个内联 Office Skills，**Agent 直接调用完成交付**，无需委派给独立子 Agent：

| Skill | 能力 |
|---|---|
| **PDF** | 创建、转换、表单填写、文本提取、OCR、合并、拆分、校验 |
| **DOCX** | Word 文档创建、编辑、批注、模板、格式化 |
| **XLSX** | Excel 创建、编辑、数据清洗、公式、图表、透视表 |
| **PPTX** | PowerPoint 创建、编辑、幻灯片排版、缩略图导出 |
| **browser-use** | 浏览器自动化：网页导航、表单填写、截图、数据提取、Web 测试 |

### 2.5 安全模型（三级信任 + 四道策略门）

| 信任级别 | 代码执行 | 网络 | 子 Agent | 适用场景 |
|---|---|---|---|---|
| **platform** | 原生 subprocess | 全通 | 允许 | 平台内置 Agent |
| **verified** | Daytona 沙箱 | 白名单 | 允许 | 企业定制 Agent |
| **untrusted** | 禁止 | 禁止 | 禁止 | 社区/第三方 Agent |

**四道策略门：** G1 工具策略 → G2 命令执行策略 → G3 工作区访问策略 → G4 记忆访问策略

### 2.6 Daytona 沙箱执行

- 6 种沙箱预设（`base`、`coder`、`office-lite`、`office-standard`、`office-full`、`browser`、`no-exec`）
- 支持运行中动态安装依赖
- 网络和命令白名单控制
- Daytona ↔ Runtime 工作区双向同步

### 2.7 存储后端

| 后端 | 适用场景 |
|---|---|
| **Memory（内置）** | 本地开发、独立部署、快速验证 |
| **Postgres** | 生产环境，含 LangGraph checkpoint-postgres |

### 2.8 可观测性

- **结构化日志：** 按类别（tool、llm、audit、metrics、app、error、lifecycle）输出 JSON 日志，含 `request_id`/`task_id` 全链路追踪
- **OpenTelemetry** 和 **Langfuse** 后端支持
- **日志查询 API：** 支持按时间范围、类别、关键词过滤

### 2.9 模型路由

- **Executor + Advisor 双模型策略：** Executor（`deepseek-v4-flash`）处理快速工具调用，Advisor（`deepseek-v4-pro`）负责复杂推理
- **自动卡顿检测与回退：** Advisor 无响应时自动降级

## 三、对外接口

### 3.1 HTTP API（FastAPI + OpenAPI）

| 路由组 | 核心端点 |
|---|---|
| **Sessions** | `POST/GET/PATCH/DELETE /sessions` |
| **Tasks** | `POST /tasks`，`POST /tasks/{id}/cancel|resume|stream-token`，`GET /tasks/{id}/stream|events` |
| **Agents** | `GET /agents`，`GET /agents/{id}`，`GET /agents/{id}/files/content` |
| **A2A** | `POST /a2a/invoke` |
| **Workspaces** | `GET/POST/DELETE /workspaces/{id}/files`，`POST /workspaces/{id}/upload` |
| **Runtime** | `GET /runtime/health|ready|preflight|diagnostics` |
| **Logs** | `GET /logs/search` |

### 3.2 Python SDK

```python
from agent_runtime import RuntimeService, RuntimeSettings

service = RuntimeService(RuntimeSettings(...))
session = await service.create_session(...)
task = await service.start_task(session_id=session.id, agent_id="main-agent", ...)
async for event in service.stream_task_events(task.id):
    print(event)
```

### 3.3 CLI

```bash
agent-runtime init       # 初始化项目
agent-runtime validate   # 校验 Agent manifest
agent-runtime serve      # 启动服务
agent-runtime doctor     # 环境诊断
```

## 四、部署方式

| 模式 | 配置文件 | 说明 |
|---|---|---|
| **独立部署** | `configs/standalone.yaml` | Memory 存储 + 本地工作区，零外部依赖 |
| **开发模式** | `configs/dev.yaml` | Postgres + Daytona + DeepAgents + 完整功能集 |
| **生产模式** | `configs/prod.yaml` | 全功能 + 数据保留策略 + 运维端点 |

一键启动：

```bash
./scripts/start.sh
```

- 自动检测运行环境，匹配配置 profile
- 内置健康检查和就绪探测（`/runtime/health`、`/runtime/ready`）
- 支持离线包部署（`release/v1.0/*.tar.gz`）

## 五、内置 Chat UI

访问 Runtime 根路径 `/` 或 `/chat` 即可使用内置 Web 聊天界面，支持：
- Session/Task 创建与管理
- SSE 流式消息展示
- 文件上传和下载
- 等待态恢复

## 六、质量保障

- **单元测试：** ~180 个用例
- **集成测试：** ~43 个用例
- **安全测试：** 权限边界、策略门、注入防护
- **验收矩阵：** 基于 `anp-agent/v1.1` 和 `v1.2` schema 的 contract 测试
- **CI/CD：** GitHub Actions 自动化构建、测试和 live runtime 验证

## 七、技术栈

| 层级 | 技术选型 |
|---|---|
| HTTP 框架 | FastAPI + Uvicorn |
| 数据校验 | Pydantic v2 + jsonschema |
| AI 引擎 | LangGraph + DeepAgents ≥ 0.6.6 |
| 沙箱 | Daytona SDK |
| 存储 | PostgreSQL + SQLAlchemy / In-Memory |
| 可观测性 | OpenTelemetry + Langfuse + 结构化 JSON 日志 |
| 测试 | pytest + pytest-asyncio |
| 构建 | setuptools + uv |

## 八、从 0 到 1 的里程碑

AgentRuntime v1.0 在不到两周的开发周期内完成了：

- **v0.1**（5月下旬）：核心执行引擎上线，支持 Manifest 加载、Session/Task 生命周期、SSE 流式事件、本地 workspace
- **v0.2**：上下文优化，上下文压缩（summary + recent window），预置 main-agent
- **v0.3**：HITL 等待恢复，启动脚本和配置体系重构，A2A 委托、Daytona 沙箱集成、Office Skills 挂载
- **v1.0**：DeepAgents 0.6.6 升级，browser-use 集成，token 计数优化，Session-Task 遗留问题修复，制品打包，正式发布

---

**项目仓库：** `https://git.cloud.inspur.com/llms/agent-runtime`
**技术文档：** `release/AgentRuntime系统集成开发手册.md`
**API 文档：** `release/agent-runtime-api-cn.md`
