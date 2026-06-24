# Wave 1 场景智能体试点 · 落地与端到端验收记录

> 关联设计：`scenario-agents-design-v1.md`（§4 A① / §5.1 B 试点）。
> 本记录是**乔布斯军团并发方案**（侦察波→建造波→验收波）执行后的验收证据，可被 review 复核。
>
> **D68 更新（2026-06-23）**：本页是 Wave 1 当时的历史验收记录，文中的 embedded / SDK lifecycle / `ZW_BRAIN_INFERENCE_*`
> 口径已由 #321/#322 取代。当前权威形态：AgentRuntime 只作为独立服务运行，zw-brain REST 仅经 HTTP
> 驱动它；内置 Agent 的可执行工具必须在 `AGENT.yaml` 声明为 `kind:api` 并引用本地 OpenAPI spec；
> 模型网关变量只在 AR 服务侧读取 `OPENAI_COMPATIBLE_*` / `AGENT_RUNTIME_DEFAULT_MODEL`。当前验收证据见
> `docs/audits/builtin-ai-disposition-2026-06-23.md` 与 `.testing/status/measurement/*`。

## 1. 本期建造（聚焦：1 条 A 链 + 1 条 B 试点）

| 智能体 | 形态 | 改动 | 工具（全只读） |
| --- | --- | --- | --- |
| **A① `a-zw-search-helper`**（就地升级，ID 按 A 类前缀规范化） | embedded builtin, `trust_level=platform`, `exposes_chat=false` | 改 2 文件：`AGENT.yaml`(指令升级为 意图→检索→可行性评分→TOP-N→术语对齐) + `capabilities.json`(加 `catalog.browse`/`catalog.entry.query`，并把 `data.search` 对齐真实契约 `{query,page}`) | `search.intent.parse` · `data.search` · `catalog.browse` · `catalog.entry.query` |
| **B 试点 `b-legal-person-credit-profiler`**（新增，**embedded → 不触发 T1**） | embedded builtin, `trust_level=platform`, `exposes_chat=false` | 新建 2 文件 `AGENT.yaml` + `capabilities.json` | `data.search` · `catalog.entry.query` · `metadata.catalog_item.query` |

**为何 B 试点不触发 T1**：T1 的触发锚点是"真实**外部**第三方 agent 经 A2A/公网 API 接入并经 §8.4 注册流水线"，不是"消费了什么数据"。B 试点做成 zw-brain 自己 owner、随仓发布、经 Embedded Runtime 的 sidecar 注入既有 live 只读能力的 builtin agent，与现存 2 个 agent 同构，完全不经外部注册流水线 → 不触发 T1。external 凭据链（`application.resource.submit→approval.review_decide→credential.issue→credential.query`）是 **T1 触发后的演进路径**，本期不实装。

## 2. 验收分档与结果（全绿）

| 档 | 验收内容 | 命令 | 结果 |
| --- | --- | --- | --- |
| tier-1 结构 | manifest 校验 / doctor / bundles 守卫 | `agentruntime_validate.py` · `agentruntime_doctor.py --target dev` · `check_agentruntime_bundles.py` | ✅ validate OK×2 / doctor 全 [OK] / `3 bundle(s) valid` |
| tier-1 §8.5 | 确定性只读安全闸（逐 skill 核 side_effects/hcr/live/禁区前缀） | 内置脚本 | ✅ 7 处 skill 全 read-only / 无人工确认 / live / 无禁区前缀 |
| tier-2 回归 | embedded + wave0 + capability_boundary + j1 + REST | `pytest`（主仓 `.venv` 3.13，PG 已在跑，mock 推理） | ✅ 0 失败（skip 仅 SDK wheel + 待解冻特性，与本改动无关） |
| **tier-3a 端到端·工具执行** | **能力调用 e2e**：经真实 `ZwBrainCapabilityProvider.call_tool → BrainService.invoke_skill` 链路实际调用两 agent 全部工具 | `pytest tests/test_scenario_agents_pilot_e2e.py` | ✅ **8/8 通过** |
| **tier-3b 端到端·运行时生命周期** | **真实 AgentRuntime SDK Task e2e**：两 agent 经 `run_agent_task`（create_session→start_task→drain）跑到 `completed` 终态，manifest 快照携带升级后工具集 | `pytest tests/test_scenario_agents_runtime_e2e.py`（需 `.venv-rt` 装 vendor SDK；**CI / 主仓 `.venv` 无 SDK → `importorskip` 整体 skip**） | ✅ **2/2 通过（本地 `.venv-rt`；CI=skip，非 CI 门；承载链 CI 覆盖见 tier-3a）** |
| **tier-4 端到端·LLM 自主编排（live）** | **真实 LLM（Volcengine Ark / GLM-4-7）** 经 `embedded_single_tenant` profile 自主决定并串联工具，跑到 `completed`、合成真实答案 | 一次性 live 演示（非 CI，真实推理凭据，见 §3.5） | ✅ **两 agent completed**（A① 出 TOP-N 推荐+术语对齐+追问；B 试点诚实拒绝幻觉） |
| 收尾门禁 | 契约漂移 / 全段 preflight | `export_agent_contract.py --check` · `scripts/preflight.sh` | ✅ contract in-sync（无新能力）/ **preflight PASS（common+project 全段）** |

**两层端到端合起来覆盖了整条承载栈**（agent → AgentRuntime → Task → tool → BrainService → handler → 真实数据），唯一未覆盖的是 LLM 自主决定调哪个工具（见 §4）：

- **tier-3a 工具执行层**（`tests/test_scenario_agents_pilot_e2e.py`）：A① 注入恰好 4 个只读工具；经 provider 真实调用 `data.search` 只命中 active（draft 被过滤，D53① 口径）；`catalog.browse`/`catalog.entry.query` 返回真实结构化目录条目；`search.intent.parse` 规则回落返回结构化意图（无需 LLM）；全程 `api_resources` 快照不变（只读）。B 试点注入恰好 3 个只读工具；**授权 manager 角色**经 provider 真实消费已编目法人画像目录全链路通；快照不变（只读）。
- **tier-3b 运行时生命周期层**（`tests/test_scenario_agents_runtime_e2e.py`）：两 agent 经**真实 AgentRuntime SDK**（vendor pyc-only 包，`runtime_core=fake` / local_dev profile）的完整 Task 生命周期跑到 `completed` 终态、产出非空，且 runtime 加载的是升级后的 manifest（A① 4 工具 / B 3 工具）。SDK 缺席环境（CI / 主仓 `.venv`）按既有 `importorskip` 语义整体 skip。

> **vendor SDK 本机安装**（复现）：解压 `vendor/agent-runtime/release/v1.1.3/*.tar.gz` →
> `uv pip install --find-links wheelhouse -r requirements.txt`（uv venv 无 pip，不能直接 `./install.sh`）
> → 把 `python/agent_runtime` + `dist-info` 拷进 site-packages → `from agent_runtime import RuntimeService` 验通。

## 3. e2e 抓到并正确处置的一个真问题（validate/doctor 看不到的）

`metadata.catalog_item.query` 对默认 `ROLE_ORGAN_OPERATER` 抛 `AccessDenied`。查 `zw_brain/domain/policy.py:242`：该能力授予 `{ROLE_ORGAN_MANAGER, ROLE_BUSIAUDIT, ROLE_SECURITY_AUDIT}`，注释"元数据查询（开放给运营/审计）"。

**结论：这是正确的最小权限治理**——字段级敏感映射（失信/纳税信用等级等）不对基础操作员开放。B 试点是用数方**研判**场景，其用户本就是 manager 级。Provider 的 `ROLE_ORGAN_OPERATER` 只是 fallback，运行时走真实 `caller_role`。已在 `test_bpilot_field_mapping_denied_for_basic_operator` 把"operator 被拒"钉死，作为 §8.5 最小权限边界的防回归断言。

## 3.5 tier-4 live LLM 演示 + 抓到并修复的真实生产 bug

用主仓 `.env` 的真实推理凭据（网关 = **公网 Volcengine Ark** `https://ark.cn-beijing.volces.com/api/v3`，模型 `glm-4-7-251222`），以 `embedded_single_tenant` profile（真实 LLM 核，非 fake）对两 agent 跑真实 Task。D68 后该模型出口已收敛到独立 AgentRuntime 服务侧，zw-brain REST 不再持有推理 SDK/env：

- **A① `a-zw-search-helper`** → `completed`。真实 GLM-4 **自主编排** `search_intent_parse → data_search ×3 → catalog_browse ×2 → catalog_entry_query ×3`，合成出**真实 TOP-N 推荐**（列出"企业年报信息""山东省企业登记基本信息"含目录编码）+ **术语对齐提示**（"企业纳税"暂无对应条目，建议替代）+ **追问建议**——正是 §4 设计承诺的页内嵌副驾体验。
- **B 试点 `b-legal-person-credit-profiler`** → `completed`。LLM 调 13 个工具（失信/经营异常/纳税信用/黑名单/参保/注册资本/行政处罚…），检索未命中相关条目时**诚实拒绝幻觉**："我只能引用检索/查询工具真实返回的字段，不编造未编目的标签或评分"——§8.5 + honesty 文化的活体现，agent **不造假信用分**。

**抓到并修复的真实 bug（fake/mock/直接 call_tool 都漏掉，唯 live LLM 暴露）**：
`zw_brain/command/handlers/j1/data_search.py:79` 用 `int(payload.get("page", 1))` —— 默认只在键**缺失**时回落；而 LLM 工具编排惯常给可选字段填**显式 null**（`page: null`，键存在值为 None），导致 `int(None)` 崩 `DynamicToolExecutionError`。修为 `int(payload.get("page") or 1)`，对齐全仓既有惯例（`request.py`/`recommendation_suggest.py`/`direct_access.py`/`audit.py` 同款 `or` 写法；data_search 是唯一漏网）。回归测试 `test_a1_data_search_tolerates_llm_null_page` 钉死。**这是"对真实客户的端到端验收"相对"工程师 happy-path 测试"的核心价值**——LLM 的 null 填充是真实生产输入，happy-path 测不到。

> live 演示是**一次性**的（真实推理凭据 + 计费 + 外部 API，不进 CI、不作提交件）；其证据即上述工具序列与产出。`run_agent_task` 阻塞超时本为 25s（HTTP 客户端口径），认真多调工具的 Task 超 25s 属正常——生产对长任务走 `start_agent_task_background()`+`poll_agent_task()` 非阻塞路径，演示中放宽到 150s 以观察合成完整答案。

## 4. 残留事项（本期不阻塞验收，记录待后续）
- **445MB 真实数据模板**：`scripts/build_realistic_pg_template` 在仓库中不存在（被引用未提交），真实模板 opt-in、CI 同 skip。本期用 BrainService 内存快照注入真实形状 fixture 覆盖；`catalog.browse/entry.query` 实测返回了仓内 bundled 目录数据。
- **Playwright 真 UI e2e**：可跑（需 `npm run build` 前端 + `start-local.sh` 起后端）。但 P2 资源发现页当前**直连 `/api/skills/data.search`、不经 agent_id 调用本 agent**，故 P2 UI e2e 证明的是平台 P2 页、非 A① agent 本身。把"TOP-N 推荐 + 术语对齐"端到端搬进 P2 页内嵌副驾 UI（web→`/api/agent-runtime start_task`）是**另一条交付**，不在本试点建造面内。

## 5. 改动面（git status，仅以下，无 old/dev-rules 污染）

```
 M agents/a_zw_search_helper/AGENT.yaml
 M agents/a_zw_search_helper/capabilities.json
 M zw_brain/command/handlers/j1/data_search.py   # live 演示抓到的 null-page 崩，修为 or-idiom
?? agents/b_legal_person_credit_profiler/{AGENT.yaml,capabilities.json}
?? docs/scenario-agents/{scenario-agents-design-v0.md,scenario-agents-design-v1.md,wave1-pilot-acceptance.md}
?? tests/test_scenario_agents_pilot_e2e.py          # tier-3a 工具执行 e2e
?? tests/test_scenario_agents_runtime_e2e.py        # tier-3b 运行时生命周期 e2e
```
（vendor SDK 解压目录与 `.venv-rt` 均 gitignored，不进改动面。）

分支 `feature/scenario-agents`（已从 `design/*` 改名以过 preflight 白名单）。**尚未 commit**（按纪律等显式授权）。
