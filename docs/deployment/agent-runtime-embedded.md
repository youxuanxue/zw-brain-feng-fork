# zw-brain Embedded AgentRuntime 启用指南

> 架构依据：`docs/approved/zw-brain-architecture.md` §8（Phase 1 默认 Embedded SDK）、R15。  
> 协议细节：`docs/agent-runtime/product-integration-guide.md`、`docs/agent-runtime/agent-runtime-api-cn.md`。

## 1. 定位

| 组件 | 职责 |
|------|------|
| **zw-brain** | 业务平台：Capability、IAM、审计、领域状态机 |
| **AgentRuntime（Embedded）** | 进程内执行 `AGENT.yaml` 声明的 Agent：Session/Task/工具循环 |
| **桥接** | `ZwBrainCapabilityProvider` 将 Agent 工具调用映射为 `BrainService.invoke_skill` |

不启动 Standalone HTTP；不与 `agent-runtime/.env.local`（旧环境路径）混用路径类环境变量。

**懒加载**：未设置 `ZW_BRAIN_AGENT_RUNTIME_ENABLED=1` 时，REST 进程可正常启动；`agent-runtime` Python 包仅在首次执行任务或 `get_agent_runtime()` 时加载。未安装可选依赖时，仅 AgentRuntime 相关 API 在启用后会返回 503/运行时错误。

## 2. 安装

在 zw-brain 仓库根目录安装 **vendor 离线包**（Python 3.12），再安装 zw-brain：

```bash
cd /path/to/zw-brain/vendor/agent-runtime/release/v0.1
sha256sum -c agent-runtime-0.1.0-py312-pyc-only.tar.gz.sha256  # 完整性校验必须通过
tar -xzf agent-runtime-0.1.0-py312-pyc-only.tar.gz
cd agent-runtime-0.1.0-py312-pyc-only
uv pip install -r requirements.txt -r ../../../requirements-deepagents.txt
./install.sh
cd /path/to/zw-brain
pip install -e ".[dev]"
```

`schemas/agent.schema.json` 已随仓库提供，无需外部 agent-runtime 仓库。详见 [`vendor/agent-runtime/README.md`](../../vendor/agent-runtime/README.md)。

## 3. 环境变量

### 3.1 启用 Embedded

| 变量 | 说明 |
|------|------|
| `ZW_BRAIN_AGENT_RUNTIME_ENABLED=1` | 打开 Embedded SDK 与 REST 任务接口 |
| `ZW_BRAIN_AGENT_RUNTIME_PROFILE` | `local_dev`（测试/fake core）或 `embedded_single_tenant`（生产） |
| `ZW_BRAIN_AGENT_RUNTIME_CONFIG` | 可选，默认 `zw-brain/agent-runtime.yaml` |
| `ZW_BRAIN_AGENTS_DIR` | 可选，默认仓库 `agents/`；Docker 镜像为 `/app/agents` |
| `ZW_BRAIN_AGENT_RUNTIME_SCHEMA` | 可选，覆盖 `agent-runtime.yaml` 中 `schema_path`；Docker 为 `/app/schemas/agent.schema.json` |

### 3.2 模型（集团推理平台，D6）

| 变量 | 说明 |
|------|------|
| `INSPUR_INFERENCE_BASE_URL` | 集团推理网关 OpenAI 兼容地址 |
| `INSPUR_INFERENCE_MODEL` | 模型名 |
| `INSPUR_INFERENCE_API_KEY` | 集团推理网关 API Key（或 `AUTH_TOKEN`）；Embedded 启动时**写入进程** `OPENAI_COMPATIBLE_API_KEY`（AgentRuntime 模型层只读 `os.environ`） |
| `ZW_BRAIN_INFERENCE_API_KEY_OPTIONAL` | 设为 `1` 时，未配置 Key 则使用占位值 `unused`（适用于网关不校验 Bearer 的环境） |
| `ZW_BRAIN_INFERENCE_API_KEY_PLACEHOLDER` | 可选，覆盖上述占位字符串（默认 `unused`） |

测试/无网关时可设 `ZW_BRAIN_TEST_MODE=1` + `ZW_BRAIN_AGENT_RUNTIME_PROFILE=local_dev`（使用 fake core，不发起真实 LLM 调用）。

### 3.3 勿从旧 `.env.local` 继承的路径项

若曾在 shell 中 `source` 过 `agent-runtime/.env.local`（旧环境 `/data/xuanzhaofeng/...`），以下变量会被 Embedded **自动忽略**，避免指向错误目录：

- `AGENT_RUNTIME_AGENTS_DIR`
- `AGENT_RUNTIME_SCHEMA_PATH`
- `AGENT_RUNTIME_WORKSPACE_ROOT`
- `AGENT_RUNTIME_CONFIG_PATH`
- `AGENT_RUNTIME_DATABASE_URL`

Standalone 跑 AgentRuntime 服务时请为本环境单独配置；zw-brain Embedded 以 `zw-brain/agent-runtime.yaml` 与 `zw-brain/agents/` 为准。

## 4. 内置 Agent

| 目录 | Agent ID | 绑定 Capability |
|------|----------|-----------------|
| `agents/zw_search_helper/` | `zw-search-helper` | `search.intent.parse`、`data.search` |
| `agents/zw_platform_guide/` | `zw-platform-guide` | `platform.docs.search`、`platform.docs.read`（`exposes_chat: true`，Web 全局「平台指南」浮窗） |

侧车清单：`agents/zw_search_helper/capabilities.json`（Registry 四字段在 T1 外部 Agent 接入时再写入 manifest）。

## 5. 校验与诊断

```bash
# 在 zw-brain 仓库根目录执行
export INSPUR_INFERENCE_BASE_URL=http://<集团网关>/v1
export INSPUR_INFERENCE_MODEL=<模型名>
export INSPUR_INFERENCE_API_KEY=<网关密钥>

python scripts/agentruntime_validate.py agents/zw_search_helper/AGENT.yaml
python scripts/agentruntime_doctor.py agents/zw_search_helper/ --target dev
# 生产门禁加严：
python scripts/agentruntime_doctor.py agents/zw_search_helper/ --target production
```

## 6. REST API（需 IAM 会话 + `ZW_BRAIN_AGENT_RUNTIME_ENABLED=1`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 含 `agent_runtime.enabled` 与 agents 列表摘要 |
| GET | `/api/agent-runtime/status` | 仅 Runtime 状态（无需登录） |
| GET | `/api/agent-runtime/agents` | 已注册内置 Agent 列表 |
| POST | `/api/agent-runtime/tasks` | 启动一次 Agent 任务（同步等待终态） |

### 6.1 启动任务示例

```bash
export ZW_BRAIN_AGENT_RUNTIME_ENABLED=1
# 先完成 IAF 登录取得 session cookie 后：

curl -s -X POST "http://127.0.0.1:8800/api/agent-runtime/tasks" \
  -H "Content-Type: application/json" \
  -H "Cookie: zw_brain_session=<session>" \
  -d '{
    "agent_id": "zw-search-helper",
    "input": "帮我解析搜索意图：停车场数据",
    "request_id": "req-demo-001"
  }'
```

响应字段：`session_id`、`task_id`、`status`、`final_output`。

调用方角色须对 Agent 绑定的 Skill 具备执行权限（与直接调 `/api/skills/search.intent.parse` 一致）。

## 7. Python SDK（进程内）

```python
import os
os.environ["ZW_BRAIN_AGENT_RUNTIME_ENABLED"] = "1"

from zw_brain.shared.agent_runtime import get_agent_runtime, run_agent_task_sync
import asyncio

# 异步
async def main():
    runtime = await get_agent_runtime()
    manifests = runtime._registry.list_manifests()
    print([m.agent_id for m in manifests])

asyncio.run(main())

# 同步任务
result = run_agent_task_sync(
    agent_id="zw-search-helper",
    user_input="解析：户籍信息检索",
    metadata={"request_id": "req-1"},
)
```

## 8. Docker 镜像

自 `zw-brain` 1.0.0 起，标准镜像在构建阶段从 `vendor/` 离线包安装 agent-runtime，并打包 `agents/` 与 `schemas/`。构建与运行变量见 [`docker-image-deployment.md`](docker-image-deployment.md) §1、§5。

## 9. 与架构路线图的关系

| 阶段 | 内容 | 状态 |
|------|------|------|
| Wave 0/1 | Embedded SDK + 内置 `zw-search-helper` + validate/doctor | 已落地 |
| T1 触发 | Registry 四字段、`external-register` manifest | 待业务需求 |
| Wave 3+ | Standalone HTTP 形态评估 | 未启动 |
