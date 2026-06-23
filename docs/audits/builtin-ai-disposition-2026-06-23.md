# 内置智能能力处置审计（参考 #321）

## 背景

#321 已把 AgentRuntime 接入形态定为单一模型：AgentRuntime 是独立进程服务，zw-brain 只经 HTTP 驱动；embedded SDK 退役，`zw_brain/` 内不再存在 in-process provider 兜底。

本轮梳理目标是从产品上帝视角审视现有“智能检索”“AI 建议”“内置 Agent / 数据应用”等能力，给出保留、收敛、迁移、下线建议。

## 本轮实施结果

- 已把 `zw-platform-guide` 与 `legal-person-credit-profiler` 收敛到 #321 单一模式：`AGENT.yaml` 显式声明 `kind: api` 工具，工具经各自 `zw-brain-capabilities.openapi.yaml` 回调 `/api/skills/*`，不再依赖 embedded provider 注入。
- 已加 manifest 守卫：凡 `capabilities.json` 声明 `capability_tools`，`AGENT.yaml` 必须有同名 `kind:api` 工具，且 OpenAPI 中必须存在同名 `operationId`。
- 已把 Web 上泛称“智能检索”的入口收敛为场景名：P2“找数助手”、P3“申请助手”、B1.1“审计助手”、B1.2“接入助手”。
- 已补真实 UI E2E：AgentRuntime 开启时，数据应用页会从浏览器真实发送问题并等待 assistant 回复；本地验证使用独立 `agent-runtime serve` + REST + Playwright 完成。

## 现状分层

### 1. 能力面（`/api/skills/*`）

这些是平台能力，不应被统一塞进 AgentRuntime：

| 能力 | 当前定位 | 处置 |
| --- | --- | --- |
| `data.search` | P2 找数基础检索，确定性读能力 | 保留为一等检索能力 |
| `search.intent.parse` | P2 一句话意图解析，失败后规则降级 | 保留，但产品名收敛为“找数意图解析”，不要泛称通用“智能检索” |
| `application.draft.suggest` | P3 草拟建议：字段建议 + 风险摘要，只输出建议 | 保留为建议生成内核，不直接给用户“已预填”承诺 |
| `request.draft.ai_suggest` | 草稿表单内补全建议，会写 `ai_suggested` 待确认字段 | 保留，必须继续坚持只填空、不覆盖人工/派生、人工确认后才提交；客户界面不再裸露“AI 建议” |
| `catalog.entry.reverse_draft.suggest` | 反向编目三档预填，大部分确定性，LLM 仍是 stub | 保留但改名口径，不应宣传成完整 AI；直到真推理落地前叫“编目预填建议”更诚实 |
| `assistant.investigation_summary` | 审计面板脱敏后送推理摘要，失败规则降级 | 保留在审计场景，继续要求脱敏摘要、不可覆盖原始证据 |
| `recommendation.similar_catalog.suggest` | 申请前置相似目录推荐，规则/历史投影驱动 | 保留为推荐引擎能力，不归 AgentRuntime |
| `recommendation.rule.commit` | 推荐规则入库写能力 | 与“AI”解绑，它是引擎配置提交，不应出现在智能助手叙事里 |

### 2. AgentRuntime 面（`/api/agent-runtime/*`）

AgentRuntime 适合承载跨多个能力的多轮对话与数据应用，不适合替代普通表单按钮或检索接口。

当前 `agents/` 有 3 个内置 Agent：

| Agent | 当前入口 | 运行可用性 | 处置 |
| --- | --- | --- | --- |
| `zw-search-helper` 找数副驾 | `surface=copilot`，不进数据应用列表 | 已改为 `kind:api` 工具，可在 standalone AR 内回调 zw-brain | 保留，但应做成 P2 页内嵌副驾，替代“泛智能检索”膨胀 |
| `zw-platform-guide` 平台指南 | 悬浮平台指南问答 | 已改为 `kind:api` 工具，可在 standalone AR 内回调文档检索/读取能力 | 保留，并以 manifest 守卫防止回退到 sidecar-only |
| `legal-person-credit-profiler` 法人信用画像核验 | 数据应用画廊 | 已改为 `kind:api` 工具，可在 standalone AR 内回调目录检索/查询能力 | 保留，数据应用 E2E 必须持续验证真实对话往返 |

## 核心问题

### P0：#321 后曾有两个 Agent manifest 仍停在 embedded 时代

`zw-platform-guide` 和 `legal-person-credit-profiler` 的 `AGENT.yaml` 曾经都是 `tools: []`。`legal-person-credit-profiler` 还明确注释“由 ZwBrainCapabilityProvider 在 Embedded Runtime 启动时注入”。但 #321 已删除 in-process provider，`service.py` 只委派 HTTP，能力回调只认 `AGENT.yaml kind:api`。

这曾意味着：

- 前端能看到“平台指南”和“法人信用画像核验”的对话入口；
- 后端能通过 `capabilities.json` 做权限过滤；
- 但独立 AR 执行时拿不到这些工具，实际对话要么空转，要么只能凭模型猜。

本轮已修复：两个 Agent 均声明了显式 `kind:api` 工具，并新增 sidecar/tool/OpenAPI 一致性守卫。

### P1：“智能检索”命名过宽，和找数副驾职责重叠

`NLAcceleratorPanel` 原先在 P2/P3/B1.1/B1.2 都叫“智能检索”，但它本质是结构化动作解析器：

- P2：`search.intent.parse` 后自动填搜索；
- P3：申请/审批动作摘要；
- B1.1/B1.2：审计/接入治理快捷动作。

这会把用户预期拉到“全局 AI 搜索/问答”，同时又和 `zw-search-helper` “找数副驾”重叠。乔布斯式处置是收口：一个用户意图只保留一个主入口。本轮已把入口改为场景名，不再把所有页面统称“智能检索”。

### P1：“数据应用”首个应用不能只做壳

`DataApps.vue` 会展示法人信用画像，并打开 `AgentChatPanel`。此前 e2e 只断言卡片和输入框存在，不验证一次真实 agent 对话。若 manifest 工具未声明，客户看到的是可打开但不可依赖的演示壳。

数据应用是高信任入口，必须宁缺毋滥。没有可解释数据链路，就不要上画廊。

本轮已补浏览器 E2E：AgentRuntime 开启时，从真实 UI 发起法人信用画像对话，并断言 assistant 不返回空回复或任务失败。

### P2：配置口径曾有 mode 幻觉

`.env.example` 与 `start-local.sh` 早期把 `ZW_BRAIN_AGENT_RUNTIME_MODE=http` 写得像运行时形态选择；但 `config.py` 真实运行时只读：

- `ZW_BRAIN_AGENT_RUNTIME_ENABLED`
- `ZW_BRAIN_AGENT_RUNTIME_URL`
- `ZW_BRAIN_AGENTS_DIR`

这会让运维误判“mode 控制启用”。本轮已统一：`ZW_BRAIN_AGENT_RUNTIME_MODE=http` 只作为 `start-local.sh` 本地兼容启动开关；REST 是否启用看 `ZW_BRAIN_AGENT_RUNTIME_ENABLED`，HTTP 目标看 `ZW_BRAIN_AGENT_RUNTIME_URL`。

## 最优处置建议

### 立即做

1. 已修 `zw-platform-guide` 与 `legal-person-credit-profiler`：
   - 为各自补 `*.openapi.yaml`；
   - 在 `AGENT.yaml tools` 声明 `kind:api`；
   - 删除 embedded provider 注释；
   - 加一个 manifest 守卫：凡 builtin Agent 的 `capabilities.json` 有 `capability_tools`，`AGENT.yaml` 必须有对应 `kind:api` 工具或显式标注 `tools_runtime=none`。

2. 法人信用画像已修好并保留在数据应用画廊；若未来任一内置 Agent 不能通过 manifest 守卫，应在修复前隐藏或标为不可用。

3. 已改测试：
   - e2e 不只点开输入框，至少发一个快捷问题并断言不返回“无工具/任务失败/空回复”；
   - 增加 `agents/*/AGENT.yaml` 与 `capabilities.json` 一致性单测。

### 下一步做

1. 已完成产品口径收敛：
   - P2 入口叫“找数助手”或“找数意图解析”；
   - P3 按钮叫“补全建议”；
   - 反向编目叫“编目预填建议”；
   - 审计叫“调查摘要”；
   - 不再把所有东西都叫“智能检索”。

2. P2 做入口合并：
   - 基础搜索框保留；
   - `search.intent.parse` 作为轻量解析增强；
   - `zw-search-helper` 作为“需要推荐/术语对齐/多轮追问”时的副驾；
   - 不新增第二个平行的“找数聊天入口”。

3. 清理运行时配置文档：
   - `ZW_BRAIN_AGENT_RUNTIME_MODE` 只作为 `start-local.sh` 本地兼容启动开关；
   - 文档明确 REST 是否启用看 `ZW_BRAIN_AGENT_RUNTIME_ENABLED`，HTTP 目标看 `ZW_BRAIN_AGENT_RUNTIME_URL`。

### 暂不做

1. 不把 `application.draft.suggest`、`request.draft.ai_suggest` 全部迁进 AgentRuntime。它们是表单内确定性工作流的一部分，保留在 `/api/skills` 更稳。

2. 不新增“全局 AI 助手”。当前信息架构已经有平台指南、找数副驾、数据应用、页面 NL 加速器。再加一个全局助手只会增加选择成本。

3. 不把 `recommendation.rule.commit` 包进“AI 建议”叙事。它是高风险写操作配置提交，应保持严肃的引擎管理语义。

## 推荐优先级

1. 已完成：修复两个 standalone AR 下工具链断裂的 Agent。
2. 已完成：加 manifest/tool 一致性守卫，防止后续新增 Agent 再走 embedded 旧范式。
3. 已完成：收敛“智能检索”命名，按场景命名。
4. 已完成：补真实对话 e2e，覆盖数据应用首个应用。
5. 已完成：清理 `ZW_BRAIN_AGENT_RUNTIME_MODE` 文档口径，明确它不是生产运行形态选择。

## 结论

最优路径不是“更多 AI 入口”，而是少数可靠入口：

- 找数据：搜索框 + 找数助手；
- 填申请：补全建议，但必须待确认；
- 编目录：预填建议，但来源分级；
- 查问题：平台指南；
- 做专题研判：数据应用。

每个入口都必须有真实数据依据、权限边界和失败降级。做不到的入口先隐藏，不用 UI 壳透支信任。
