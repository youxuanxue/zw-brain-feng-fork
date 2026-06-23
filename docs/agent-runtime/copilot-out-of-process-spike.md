# Spike：Agent 搬出主进程的身份传递（R1）— 结论报告

> 关联：`docs/decisions/agentruntime-formfactor-proposal.md`（D68 单一模型）。
> 目的：在动手搬运行时前，验证「agent 在独立 AR 进程里运行、回调 zw-brain 已发布 API 取能力/数据时，**每次调用怎么带上当前用户/凭据身份**」是否可行——决定下周突增 agent 的 AGENT.yaml 编写范式。
> 方法：读 AR `agent-runtime-api-cn.md` + `AgentRuntime系统集成开发手册.md` + 对 vendored pyc 包做标识符/字符串探针。

## 0. 一句话结论

> **R1 可行，且是 AgentRuntime 原生能力——无需 AR 改造、无死路。** AR 有一套可插拔的 **per-user 凭据解析**：manifest 里 tool/mcp 的 `auth.credentials` 写 `${user_credential:zw-brain}`，AR 在 task 启动时按 **`(user_id, ref)`** 解析成「该用户的凭据」注入出站调用——`user_id` 即 task 的 `subject_user_id`（on-behalf-of 的那个用户）。zw-brain 侧 `/api/skills`、数据消费面照常按 per-user/凭据鉴权，**role 服务端解析、agent 不可伪造**。

## 1. R1 证据链

### 1.1 入站 on-behalf-of（zw-brain → AR）— 已支持
- `StartTaskRequest.subject_user_id`（代表哪个用户执行；不同于 principal 时需 scope `tasks:start:any_user`）（api §4.1 / §2.2）。
- 鉴权模式含 `trusted_gateway`（网关注入 principal + 签名 + 时间戳头），适配 zw-brain 作为可信网关（api §2.2）。
- `TaskRecord` 记录 `owner_user_id / owner_principal_id / actor_principal_id / subject_user_id`（api §4.1）。

### 1.2 出站工具凭据（AR 内 agent → zw-brain）— per-user 原生可插拔
- manifest 引用语法：`${secret:KEY}` / `${env:VAR}` / `${user_credential:REF}`，由 `resolve_manifest_refs(..., execution_phase="initial_run"|"resume")` 在执行期解析（handbook §4.9/§9 line 941、2565）。
- pyc 包探针（`agent_runtime/security/`）确认完整实现：
  - 协议 `UserCredentialProvider.resolve_user_credential(user_id, ref)`；正则 `^\$\{user_credential:([^}]+)\}$`。
  - `StoreBackedUserCredentialProvider` — *“Lookup `(user_id, ref)` in store when context provides **user_id**; else env-only fallback.”* ← **per-user 路径**。
  - `EnvironmentUserCredentialProvider` — *“Load credential payloads from `AGENT_RUNTIME_USER_CREDENTIAL_<NAME>` JSON.”* ← 进程级（非 per-user）。
  - `InMemoryUserCredentialStore`（.get/.put）— *“Process-local store for tests and single-instance dev.”*
  - 缺失时报 *“User credential not available for ref …”*（fail-closed，不静默放行）。
- 即：tool/mcp `auth.credentials: "${user_credential:zw-brain}"` → AR 按当前 task 的 `subject_user_id` 解析出该用户凭据注入回调。**per-user 身份原生到达出站工具调用，不是单一静态 all-roles bearer。**

> 反例排除：zw-brain 自己的 MCP server 今天 stdio-only + dev-bypass all-roles + prod 拒启（`entry/mcp/server.py:177/459/395`）——故**优先把能力/数据暴露为 `kind:api` 工具→已 per-user 的 `/api/skills` 与数据消费面**，不优先改造 MCP。

## 2. 推荐设计（两类，统一 `${user_credential:REF}`）

**Provider 选型**：用 **StoreBackedUserCredentialProvider**（per-user）。AR 独立进程启动时配置该 provider；store 由 zw-brain 在 **task 启动前/时**按 `subject_user_id` 写入「该用户对 zw-brain 的短时凭据/令牌」（或实现自定义 provider 在解析时回调 zw-brain 现铸 per-task 令牌）。`InMemoryUserCredentialStore` 适合本地/单实例 dev；生产用持久/共享 store 或自定义 provider。

- **A 类（平台内副驾 · on-behalf-of）**
  - AGENT.yaml：能力写 `kind:api` 工具指向 `/api/skills/{id}`（或 http MCP），`auth: {type: bearer, credentials: "${user_credential:zw-brain}"}`。
  - 流：zw-brain 起 task 带 `subject_user_id=<登录用户>` → AR 解析 `${user_credential:zw-brain}`=该用户令牌 → 回调 `/api/skills` 携该令牌 → zw-brain 现有 per-user 鉴权（binding 派生角色 + trusted-session）照常。
  - A① 只读 4 能力（search.intent.parse/data.search/catalog.browse/catalog.entry.query），无 canonical 写、无 code-exec → 最低风险首验。

- **B 类（用数方 · 凭据）**
  - AGENT.yaml：数据消费面写 `kind:api`/`kind:a2a` 工具，`credentials: "${user_credential:<resource-ref>}"`。
  - `${user_credential:REF}` 解析为该用数方已签发凭据（application.resource.submit→approval→credential.issue→credential.query）。本就是标准带凭据 API 客户端，out-of-process 天然契合。

## 3. 下周突增 agent 的 AGENT.yaml 编写范式模板（避免范式债）

```yaml
schema_version: anp-agent/v1.2
kind: Agent
metadata:
  id: <agent-id>
  trust_level: platform        # A 类；B 类外部=untrusted→verified
  exposes_chat: false          # 逐 agent 显式
model:
  provider: openai_compatible
  model: ${env:AGENT_RUNTIME_DEFAULT_MODEL}   # AR 服务侧经 OPENAI_COMPATIBLE_* 网关（硬约束 段10/78）
tools:
  - kind: api
    name: data_search
    description: 按关键词检索共享数据资源目录（只读）。
    # 指向 zw-brain 已发布认证 API（已 per-user 鉴权）
    endpoint: ${env:ZW_BRAIN_API_BASE}/api/skills/data.search
    auth:
      type: bearer
      credentials: "${user_credential:zw-brain}"   # AR 按 subject_user_id 解析为该用户令牌
  # ... 其余只读能力同形态；写类能力不外部化（§8.5）
```
> 要点：①能力/数据只经 zw-brain 已发布认证 API（前门），不用进程内 provider；②身份永远 `${user_credential:...}` per-user，禁静态 all-roles；③`skill` 词仅作协议/JSON 字符串留在 `agents/`，禁进 `zw_brain/` Python 标识符（段50）；④A/B 只差 trust_level + 调哪些面 + 凭据来源。

## 4. 残留确认项（窄，建 build 前一次性敲定，非阻塞机制可行性）

1. **store 写入协议**：用 StoreBackedUserCredentialProvider + zw-brain 在 task 启动写 store，还是自定义 `UserCredentialProvider` 在解析期回调 zw-brain 现铸 per-task 令牌？（二选一，均属配置/小代码，建议后者更无状态。）— 与 AR 团队（wangzhihua）确认自定义 provider 在 standalone serve 下的装配方式。
2. **令牌形态**：zw-brain 侧 `/api/skills` 接受的 per-user 令牌 = 复用现有 trusted-gateway/binding 令牌，还是新铸短时 on-behalf-of 令牌（推荐，最小权限 + 过期）。
3. **AR 版本**：vendored v1.1.2.2 是否已带上述 provider（探针对象是 1.1.3）；build 时对齐 1.1.3。

## 5. 对下一轮的影响

机制可行性=**确认**，故下一轮可直接进 build：AgentRuntimeClient HTTP adapter + StoreBacked/custom UserCredentialProvider 装配 + A① AGENT.yaml 改 `kind:api`+`${user_credential:}` + co-located `agent-runtime serve` + A① 端到端验通（含 §4 两确认项落定）。原「先地基+spike」的 spike 部分到此收口，结论支持单一模型，无需回退评估 MCP-http per-user 升级。

---

## 6. 实测结果（本地联调 · 2026-06-22）

下一轮 build 的 **DRIVE 链路已端到端实测打通**（独立进程 AR 被 zw-brain 经 HTTP 驱动）：

- **独立 AR 起栈**：把 vendored 升到 1.1.3（`agent-runtime serve --config agent-runtime.dev.yaml --product --host 127.0.0.1 --port 8001`，`embedded_library` memory store / 无 DB / `runtime_core=deepagents` / 真网关），`/runtime/ready` ok。
- **DRIVE adapter（`http_client.py`，纯 HTTP 零 SDK 依赖）**：`run_agent_task_sync` / `start_agent_task_background` / `poll_agent_task` / `resume` 经 AR 原生 REST（`POST /sessions`→`POST /tasks`→poll `GET /tasks/{id}`→`/resume`）实测 completed + 真实 LLM 产出。
- **全链路经 zw-brain 真 REST**：`POST /api/agent-runtime/tasks {zw-platform-guide}`（REST :8801, `ZW_BRAIN_AGENT_RUNTIME_MODE=http`）→ http_client → 独立 AR :8001 → deepagents+真网关 → `running`→`completed` → 真实中文产出。两进程、HTTP 通信。
- **进程隔离实证（本轮头号收益）**：`kill -9` 独立 AR 后，REST `/health` 仍 200；新任务**优雅降级**为 500「AgentRuntime unreachable」（非崩溃），REST 不被拖垮。对比 embedded 后台线程（service.py:34-71）跑飞会拖垮 REST。
- **复现**：`ZW_BRAIN_AGENT_RUNTIME_MODE=http ZW_BRAIN_PYTHON_BIN=<py312> bash scripts/start-local.sh`（co-located 起 AR+REST，健康门）。

**仍待 build（A① 取真数据，本轮未做）**：A① 副驾的能力回调（data.search 等取 catalog 真数据）需 §2/§3 的能力-over-wire 落地。实测发现 `zw_brain/entry/rest/openapi.json` 是**薄 stub**（GET-only、无 operationId/requestBody/servers），故 `kind:api` 路线须**手写一份聚焦功能 OpenAPI**（每能力 1 path，POST + capabilities.json 的 input_schema + servers=zw-brain REST）后接 `${user_credential:}` per-user；或回退 MCP（66 个 per-capability tool spec 现成，但 stdio 子进程耦合 + repo schema mcp_servers 偏 preset-only 的版本漂移）。zw-brain `/api/skills` 在无 cookie + dev-bypass 下对**只读**能力自动解析角色（不需注入），是 A① 落地的便利前提。`search.intent.parse` 标了 `side_effects:true`（写路径角色逻辑），其余 3 只读能力 clean。
- **平台指南副驾**不依赖能力回调（文档问答），故全链路已完整可用；**A① 找数副驾**待能力-over-wire 接通后即同链路可用。
