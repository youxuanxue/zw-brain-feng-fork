# AgentRuntime 接入形态二次决策（D68 全文）— 单一模型

> **状态：PROPOSAL（待产品研发负责人业务 sign-off）** · 2026-06-22 · 架构决策（GATE D28/D33.d）
> 重评对象：架构 §8.2 line 810「运行形态 = Phase 1 默认 Embedded SDK；Standalone HTTP 留 Wave 3+ 评估」。
> 本提案对应 decision-log **D68**；本轮只落「地基 + spike」，搬运行时的全量实施留作 spike-gated 下一轮。

---

## 0. 一句话结论（乔布斯裁决）

> **AgentRuntime 做成一个独立进程服务，被 zw-brain 调用（API/HTTP/CLI）；所有团队编写的 Agent（A 类副驾 + B 类用数方）统一在这个服务里跑，要用 zw-brain 的能力/数据时，作为带身份/凭据的普通客户端走 zw-brain 已发布的认证 API。一套模型，A/B 只差信任级与策略。**

这同时解决两件事：**低耦合**（AR 自带 py3.12.12 pyc + langchain/langgraph 依赖闭包不再压进 zw-brain 镜像；两产品独立迭代/发布）+ **故障隔离**（跑飞/OOM 的 agent 不再拖垮主 REST 进程）。而且它**统一**了 A/B 两类的接入形态，消灭了"两条道 + 进程内特例回调"的复杂度。

---

## 1. 为什么重开 §8.2

- **耦合（三轴，负责人最在意）**：嵌入把 AR 的 `.pyc`（Python 3.12.12 精确锁）+ langchain/langgraph/deepagents 依赖闭包灌进 zw-brain 自己的镜像；AR 升一次级 = zw-brain 一个 PR（依赖/版本耦合）；AR 与 REST 同进程共享内存/事件循环/连接池（故障域耦合）。
- **故障隔离不真**：场景副驾今天作为 ~30s LLM 任务跑在 :8800 REST 进程内的守护线程后台 asyncio 循环（`service.py:34-71`）——后台线程**不隔离故障**，跑飞/OOM 仍拖垮 API。真隔离要独立进程，而独立进程正是 AR 的原生形态（`agent-runtime serve`）。
- **规划**：未来一周 **A 类副驾 + B 类用数方一起突增**（`docs/scenario-agents/scenario-agents-design-v1.md`）。agent 量越大，主进程内 LLM 负载越大 → 把"跑 AI 那部分"挪出主后台**不算提前盖楼**，是这条规划必须的。
- **R4 归因更正**：§8.2 把 Embedded 默认挂在「与 R4 控制面纤薄一致」——但 R4 讲的是控制面**范围**最小化、**与进程拓扑无关**。这条归因张冠李戴，本决策一并更正。

---

## 2. 单一模型

> **AgentRuntime = 独立进程服务**（按信任级可分实例），暴露 run-task **API/HTTP（+CLI）**，**被 zw-brain 调用**（zw-brain → AR：起任务）。
> **所有团队编写的 Agent 统一在 AR 服务内运行**，用 zw-brain 能力/数据时**作为带身份/凭据的普通客户端走 zw-brain 已发布的认证 API（前门）**。

> **实施更新（2026-06-22）**：本提案早期写过 embedded fallback 占位；落地时已反转为 standalone-only。当前代码中 `zw_brain/` 零 AgentRuntime SDK import，REST 是否启用看 `ZW_BRAIN_AGENT_RUNTIME_ENABLED`，目标服务看 `ZW_BRAIN_AGENT_RUNTIME_URL`；`ZW_BRAIN_AGENT_RUNTIME_MODE=http` 只保留为 `start-local.sh` 本地兼容启动开关。

- zw-brain 的 `/api/agent-runtime/*` facade 变成对 AR HTTP API 的**薄代理**；WebUI 不变。
- **agent 编写范式统一为 declared api-tools**（`tools:[kind:api]` 指向 zw-brain 已发布认证 API）；A 类一并改此范式，最终删进程内 `ZwBrainCapabilityProvider` 特例。
- **两种访问模式（= A/B 唯一差别，策略维度非两套架构）**：
  - **A 类（平台内副驾 · on-behalf-of）**：zw-brain 调 AR 带 acting user（`subject_user_id`+凭据）→ AR 内 agent 回调 `/api/skills/{id}` 携该 user 凭据 → zw-brain 现有 per-user 鉴权照常（绑定派生角色 + trusted-session），**role 服务端解析、agent 不可伪造**。
  - **B 类（用数方 · 凭据）**：agent 持已签发凭据（application.resource.submit→approval→credential.issue→credential.query）经数据消费面取数 —— 本就是标准带凭据 API 客户端，out-of-process 天然契合。
- **近路 vs T1 按编写方分（不是 A/B 域）**：**内部团队编写&部署**的 agent（A 类、B 类都在 `agents/`）= 近路，下周一起突增；**真正外部第三方提供 AGENT.yaml**（ANP/Cursor/三方 IDE）= **T1**（Registry/validate/doctor + 沙箱/Daytona if code-exec）。团队写的 B 类（net_new=none、API 取数、无 code-exec）**不需要 Daytona**。法人画像试点 = 团队写的 B 类 → 走近路，不触发 T1。
- **不保留进程内回退**：embedded（in-process SDK）已退役；`ZW_BRAIN_AGENT_RUNTIME_MODE=embedded` 不再是可用 fallback。

---

## 3. 为什么不是 A 嵌入 / 不是 B「现在全量切」

- **不留嵌入（A）**：三轴耦合 + 故障不隔离 + agent 突增放大问题；后台线程是半隔离假象。
- **不"现在全量切运行时"（B-now）**：身份怎么过进程边界（on-behalf-of）依赖一个需向 AR 团队确认的未知数（见 §5）。在未确认前全量改 ~20+ agent + 重写 adapter，风险是中途返工。故**先地基+spike**，钉死范式再让突增按新范式落。

---

## 4. 接缝（低耦合的载重件，已存在）

- **接缝已在代码里**：所有 `from agent_runtime`（SDK）import 只在 2 文件（`zw_brain/shared/agent_runtime/service.py` + `capability_provider.py`）；上层只调 ~6 函数 facade（`run_agent_task[_sync]` / `resume_agent_task` / `get_agent_runtime` / `register_brain_provider` / ...）。
- 故从 embedded 切到独立服务 = **换 adapter 实现体**（`service.py` 函数体打 AR REST、删后台循环/drain），facade 签名不变、manifests + command 层不动。
- **本轮把接缝硬化为不变量**：新增 preflight 段 77 `check_agent_runtime_import_confinement.py` 断言 SDK import 只在那 2 文件，越界即 FAIL（防接缝悄悄烂掉、退回嵌入）。

---

## 5. Linchpin spike（本轮验证，覆盖两类）

**R1**：agent 在独立 AR 进程里回调 zw-brain 已发布 API 取能力/数据时，**身份怎么带过去**使 per-user/凭据鉴权成立（不塌缩成单一 all-roles 身份）。

地面事实：
- AR api/mcp tool auth 文档上是**每 tool/server 静态凭据**（handbook §7.8）；是否把每任务 acting 身份带进出站 tool 调用 = **待向 AR 团队确认**。
- `/api/skills/{id}` 走正常 REST **per-user** 鉴权（`server.py:534/575`）；zw-brain MCP server 反而 stdio-only + dev-bypass all-roles + prod 拒启（`entry/mcp/server.py:177/459/395`）→ **优先 api-tools→`/api/skills`，不优先升级 MCP**。

spike 产出 `docs/agent-runtime/copilot-out-of-process-spike.md`：R1 结论 + 两类身份传递设计 + **下周突增 agent 的 AGENT.yaml 编写范式模板** + 下一轮 effort 重估。

---

## 6. 本轮交付（地基 + spike，零行为变更）

1. §8.2 line 810 改写为单一模型 + 更正 R4 归因（本提案 §1/§2）。
2. preflight 段 77 接缝导入守卫 + 真命中测试（`tests/test_check_agent_runtime_import_confinement.py`）。
3. decision-log **D68** 条目。
4. 历史 `ZW_BRAIN_AGENT_RUNTIME_MODE` 占位管线已被后续实施收敛：运行时只保留 `ZW_BRAIN_AGENT_RUNTIME_ENABLED` / `ZW_BRAIN_AGENT_RUNTIME_URL`；`ZW_BRAIN_AGENT_RUNTIME_MODE=http` 仅作为 `start-local.sh` 本地兼容启动开关。
5. 本提案文档（即本文件）。
6. spike 报告（§5）。

**历史说明**：本 proposal 阶段原计划不碰运行时代码；2026-06-22 后续实施已完成 standalone-only cutover，删除 in-process SDK 回退。

---

## 7. 下一轮（spike-gated）

AgentRuntimeClient HTTP adapter（重写 `service.py` 函数体打 AR REST、删后台循环/drain）+ 两类身份传递（A on-behalf-of→`/api/skills`、B 凭据→数据消费面）+ A 类 AGENT.yaml 改 declared api-tools（最终删 `ZwBrainCapabilityProvider`）+ 本地/docker/CI co-located `agent-runtime serve`（保持确定性 CI）+ A① 试点验通 → 下周突增 A/B 按新范式直接落 standalone + AR vendored v1.1.2.2→1.1.3 对齐。外部第三方 onboarding（沙箱实例 + Registry/validate/doctor）仍 T1。

---

## 8. 风险与翻盘条件

| 风险 | 缓解 / 翻盘 |
|---|---|
| **接缝烂回嵌入** | 段 77 守卫硬化（载重前置，非可选）。 |
| **身份过进程边界（on-behalf-of）AR 不支持** | spike 先验；优先 `/api/skills`（已 per-user）。若 AR 无法带 per-task 身份，回退评估 MCP-http per-user 升级或 AR 侧改造，记债。**read-only A 类**先行最低风险。 |
| **D4 同步 fail-closed 审计过网络跳** | A 类只读不写 canonical，审计写不在其关键路径；写类仍走 zw-brain 内部、不外部化（§8.5）。 |
| **突增 agent 按旧范式写出** | spike 先定编写范式模板，突增按新范式落，避免范式债（本轮先做的核心理由）。 |

---

## 9. 命名冲突筛查（GATE D33.d）

- **`trust_level` 双命名空间**：包级 F4（`baseline/...`）vs AGENT.yaml Registry 级（`platform/verified/untrusted`）—— T1 须 rename 一方（`runtime.py:18-19` 已标注）。
- **`skill`/`capability`（D33）**：AR 协议词 `skill_id`/`skills:` 留 JSON/协议字符串（在 `agents/`，非 `zw_brain/` Python 标识符）；未来 HTTP adapter 禁在 `zw_brain/` 暴露 `skill` 命名符号（段 50 守卫）。
- **`anp-agent` spec_version**：钉死 v1.2，T1 validate/doctor 机械强制。
- 推理 SDK：zw-brain 主进程不持有；独立 AgentRuntime 服务侧读 `OPENAI_COMPATIBLE_*` / `AGENT_RUNTIME_DEFAULT_MODEL`。

---

## 10. 签字闸

- 本提案 = §8.2 已记录产品决策的变更（GATE D28/D33.d），须**产品研发负责人业务 sign-off** 才权威；走 D35/D46 signoff 账本（`.testing/signoff/agentruntime-formfactor.signoff.yaml`，decision_only）。
- 合并到 main 永远人工（main 分支保护 require-CI-green）。
