# 政务产品研发工作区

## 项目概述

浪潮云（Inspur Cloud）政务方向 IT 产品研发工作区。隶属人工智能工厂/海若产品部，负责政务行业的 AI 产品研发与交付。

## 角色上下文

我是产品研发负责人，带领团队推进公司重点项目 zw-brain。核心目标是确定性自动化运营和运维：通过 Cursor + AI 数字分身杠杆团队产能，把可机械化的交付与运维环节脚本化、门禁化。

- 所在公司：浪潮云信息技术股份公司
- 部门：人工智能工厂 / 海若产品部
- 工作模式：团队协同研发 — 通过 Cursor + Claude Code 双引擎驱动长时运行交付
- 产品设计：遵循乔布斯理念（聚焦、简洁、端到端、精品意识）
- 研发运维：遵循确定性自动化运营和运维原则（杠杆最大化、流程极简、自动化优先）

## 关联项目（同级目录）


| 项目         | 路径                                           | 技术栈                                        | 说明            |
| ---------- | -------------------------------------------- | ------------------------------------------ | ------------- |
| 行业大脑       | `../industry-brain/`                         | Next.js + FastAPI + LangGraph + PostgreSQL | 石化行业大脑产品，三层架构 |
| PetroMind  | `../jingbohainan/jing_ying_xian/PetroMind/`  | FastAPI + React + PostgreSQL               | 石化利润经营智能体     |
| PetroIntel | `../jingbohainan/jing_ying_xian/PetroIntel/` | Python + SQLite + REST/MCP                 | 外部情报采集平台      |
| 数智世界智能体    | `../open-world/`                             | Vue 3 + Vite + Three.js + Phaser           | 数智世界前端 SPA    |
| 推理平台       | `../pcowork/推理平台/`                           | 文档                                         | 企业级模型推理平台能力介绍 |


## 架构约束（Agent 必须遵守）

- 分层依赖：entry → command → domain → shared，禁止反向引用
- API 契约变更后必须同步更新文档（参照 .cursor/rules/agent-contract-enforcement.mdc）
- 所有配置通过环境变量注入，禁止硬编码密钥或连接串
- 数据库操作通过 ORM，禁止裸 SQL 拼接
- 敏感数据（密钥、证书、内部 IP）禁止提交到版本控制

## 研发流程（必须按阶段通过）

```
需求分析 → 原型设计 → [人工审批] → 功能实现 → 测试验证 → [人工审批] → 合并上线
```

详见 .cursor/rules/product-dev.mdc

## 规则体系

规则与通用门禁脚本来自独立的 **dev-rules** 规范仓库；本机习惯放在 `~/Codes/dev-rules`（可用 `DEV_RULES_HOME` 覆盖）。zw-brain **不**跟踪 dev-rules 为子模块、也不在 CI 中检出该仓库。

- **本机可选**：`bash scripts/link-dev-rules.sh` 创建 **`dev-rules/` → 本机 mirror 的 symlink**（`dev-rules/` 已 `.gitignore`），便于 `sync.sh --local`、`cloud-agent-bootstrap` 等与 mirror 一致。
- **仓内自带**：`scripts/preflight_common.sh`、`scripts/check_approved_docs.py`、`scripts/sync-stats.sh` + `scripts/.stats.json`，保证 **preflight 与 CI 不依赖** 单独的 dev-rules 目录。
- `.cursor/rules/*.mdc` 是 sync 产物，**禁止直接编辑**；更新规则内容仍在 **dev-rules 规范仓库** 的 `rules/` 中编辑，再同步到本仓库的 `.cursor/rules/`（若配置了 symlink，可用 `dev-rules/sync.sh --check` 做漂移检查）。

## 强约束门禁（机械检查，已生效）

提交时 git pre-commit hook 自动运行 `scripts/preflight.sh`，违反硬约束的 commit 会被拦截。当前激活的检查段：

- 分支命名（`master`/`main`/`prototype/`/`feature/`/`fix/`/`chore/`/`docs/`）
- 未配置 dev-rules 子模块时段 2 skip；若存在 `dev-rules/sync.sh`，段 3 检查 `.cursor/rules/` 与 `dev-rules/rules` 是否一致
- 其余段（contract / story / approved / stat / …）按 `scripts/preflight_common.sh` 与项目段执行

在 **dev-rules 规范仓库** 内修改共享规则工件时，仍应运行其自带的 `./verify-rules.sh`（该检查不随 zw-brain 分发）。

完整软→硬约束映射：见 `docs/approved/zw-brain-architecture.md` **附录 C**（当前实现与通用 preflight 映射以 v4 基线为准；项目特有硬约束继续由 `scripts/preflight.sh` 追加）。

## 当前迭代目标

- 搭建数字分身基础设施（Phase 0: 配置文件 + 命令 + 工作流）
- 验证单任务长时运行能力（Phase 1）

## 任务处理原则

1. 收到任务后，先输出执行计划，等待人工审批后再执行
2. 新功能必须先做原型设计，审批通过后再做生产级实现
3. 遇到需要业务决策的问题，记录问题并等待，不要猜测
4. 产出以 PR 形式提交，不直接推送到主分支
5. 长时运行任务中，每完成一个里程碑提交一次，避免一次性大 PR

## 决策记录

> **D-编号索引（D1–D65+）全量权威副本已移出每会话热路径 → `docs/decisions/decision-log.md`**（D65，2026-06-19；根因＝CLAUDE.md 每会话整份入上下文、~1.8 万字符 D-索引只增不减＝持续烧 token，§6 净零）。本段只保留下方「现行硬约束速查」(per-session 必备)；完整 D-索引、批次沿革、全文指针都在 decision-log.md。随此移出退役了 preflight 段 68/72 两道 D-索引字符守卫（其立论随索引离开热路径蒸发）。
>
> **新增 D 条目**写进 `docs/decisions/decision-log.md`（不写回本文件），遵其格式契约（日期 + scope + 一句裁决 + 被全仓引用的子决策锚点速记 + 全文指针；prose essay 不进索引）；**GATE 元规则**见下方速查末条（D28/D33.d）。

### 现行硬约束速查（per-session，均已 preflight 机械化）

- 所有模型服务调用（LLM/Embedding/ASR/Rerank/OCR）只由独立 AgentRuntime 服务经集团推理平台承载；zw-brain 进程内禁推理 SDK/env，连接变量只在 AR 服务侧读取 `OPENAI_COMPATIBLE_BASE_URL` / `OPENAI_COMPATIBLE_API_KEY` / `AGENT_RUNTIME_DEFAULT_MODEL`，禁 `INSPUR_INFERENCE_*` / `AUTH_TOKEN` / 裸 `BASE_URL`/`MODEL` 兜底（D6/D36/D68，段 10/56/78）
- `zw_brain/` 内禁新增含 `skill` 的标识符——能力本体统一叫 capability；白名单 API surface 除外（D33，段 22 + check_no_skill_identifier）
- 写库 token（add/commit/merge/delete/裸 SQL DML）仅允许在 `zw_brain/adapters/legacy/`，其余皆禁（§9.5，段 25）
- UI 文本禁工程术语（R12，段 24）
- 已退役资产禁回潮：旧 R1-R8 角色矩阵（→7 角色码）、K12 可视化大屏（D23/D29/D15，段 20 + role/feature 守卫）；**alembic 已于 D58 回归**（反转 D23 删除决策，段 20 anti-alembic 正则已移除）
- `require_real_seed` 门槛禁用运行时累积表（capability_call/audit_event/anchor_outbox/audit_receipt）当 seed 门槛；floor 取稳定态~75%（D44，段 57）
- 业务数据禁 Mock，一律真实库回归（D11）
- 业务 sign-off（角色/流程/状态机类）走 D35 模板 + 段 53/54；效果验收走 D37 模板 + 段 55；落盘单源 = `.testing/signoff/<scope>.signoff.yaml` 账本（D46.b；PR 合并时 label `signoff:<scope>` + body 机读块自动落账 D46.d），status 由账本现算（不再 plan.yaml `[SIGNOFF-CLOSED]` 三处副本对账）
- GATE 元规则（D28/D33.d）：角色/流程/状态机决策须业务方 sign-off 才进 D-编号；每条 D 须审视与外部协议（AgentRuntime/MCP/A2A/ANP/推理 SDK）的命名冲突
