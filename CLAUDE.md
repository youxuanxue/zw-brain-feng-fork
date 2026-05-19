# 政务产品研发工作区

## 项目概述

浪潮云（Inspur Cloud）政务方向 IT 产品研发工作区。隶属人工智能工厂/海若产品部，负责政务行业的 AI 产品研发与交付。

## 角色上下文

我是产品研发负责人，以 OPC（One-Person Company）模式运作：一个人 + AI 数字分身 = 精干团队的产出。

- 所在公司：浪潮云信息技术股份公司
- 部门：人工智能工厂 / 海若产品部
- 工作模式：OPC — 通过 Cursor + Claude Code 双引擎驱动长时运行的自主研发
- 产品设计：遵循乔布斯理念（聚焦、简洁、端到端、精品意识）
- 研发运维：遵循 OPC 哲学（杠杆最大化、流程极简、自动化优先）

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

完整软→硬约束映射：见 `docs/approved/zw-brain-architecture-v4-gpt55.md` **附录 C**（当前实现与通用 preflight 映射以 v4 基线为准；项目特有硬约束继续由 `scripts/preflight.sh` 追加）。

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

- [2026-04-15] 决策：采用 Cursor Long-running Agent + Claude Code Headless 双引擎架构
- [2026-04-15] 决策：规则单一事实来源放在独立仓库 ~/Codes/dev-rules/（不随公司项目删除），通过 sync.sh 分发
- [2026-04-15] 决策：研发流程增加原型设计阶段和两个审批门禁（原型审批 + 合并审批）
- [2026-04-15] 决策：消费端通过 sync 分发 `.cursor/rules/`；zw-brain 自 [2026-04-28] 起不接 dev-rules 子模块，本机 symlink + CI 浅克隆（见上文「规则体系」）
- [2026-04-16] 决策：强约束实现层落地——每条软规则配套机械检查脚本（映射见设计基线附录 D），git pre-commit hook 自动触发，禁止"靠自觉"
- [2026-04-17] 决策：`~/.claude/CLAUDE.md` 收编进 `dev-rules/global/CLAUDE.md`，由 `sync.sh` 维护 symlink，由 LaunchAgent 每小时 `git pull` 自动同步——消除最后一个手维护的孤儿配置文件

### [2026-04-18] GATE-1 通过：政务大脑 AI 原生重构设计基线

PR [#1](https://github.com/feng222666888/zw-brain/pull/1) merged at 2026-04-18 08:15:41Z by `feng222666888`；当前实现基线以 `docs/approved/zw-brain-architecture-v4-gpt55.md` 为准。完整决策详见 v4 基线相关章节，以下为 D-编号摘要（D1–D20 为 GATE-1 通过时落定，D21/D22 为 GATE-1 后 retrofit）：

- [2026-04-18] D1：政务大脑产品形态 = 精简 WebUI（≤10 核心场景页）+ 嵌入式 NL 加速器 + N 个核心 Agent + M 个可注册 Skill，**不复刻旧平台菜单导航形态，也不做"裸对话框"入口**
- [2026-04-18] D2：5 消费面（WebUI / REST / CLI / MCP / A2A）**共享同一套 Skill 契约**，由单一脚本生成，禁止 5 处手维护
- [2026-04-18] D3：能力扩展**唯一路径是 Skill 注册**，禁止在 Agent / 编排层内嵌业务逻辑
- [2026-04-18] D4：审计总线**强制同步落库**（写入失败必须熔断），区块链锚定通过**可插拔 adapter 异步执行**（外链 down 不阻塞业务，但需告警 + 重试）
- [2026-04-18] D5：区块链对接采用轻量 adapter 模式，先实现接口骨架，外部链协议明确后再详设
- [2026-04-18] D6：**所有模型服务调用（LLM / Embedding / ASR / Rerank / OCR 等）必须走集团推理平台统一 SDK / API；禁止任何模块直连 OpenAI / Anthropic / 百川 / 智谱 / 通义等第三方 LLM API**；preflight 段 10 强制检查
- [2026-04-18] D7：数据模型采用「Agent-Native 优先 + Adapter 层」——先按 Agent 可消费形态设计新模型，旧平台数据通过 `adapters/` 单向同步进入，**不在大脑内复造旧 schema**
- [2026-04-18] D8：UI 仅保留 §7.3 列出的 ≤10 个核心场景页，其他低频功能不进 WebUI 主导航
- [2026-04-18] D9（修订）：原计划砍掉的「共享专区」**从砍掉清单移出**，升级为 K11 必保留功能；旧平台「几乎不用」是形态问题（入口埋深 + 无订阅）而非需求问题
- [2026-04-18] D10：5 个低价值功能（数据资源库 / 绩效考核 / 应用案例独立子系统 / 通用服务+链接资源 / 指标平台）默认不重构，重激活前必走 product-dev.mdc 流程
- [2026-04-18] D11：所有 Skill 必须以**旧平台真实业务数据（脱敏）回归验证**，禁止 Mock 业务数据
- [2026-04-18] D12：与数据治理中心 / 外部区块链 / 国家平台 / 集团推理平台保持「外部依赖」关系，**不在大脑内复造**
- [2026-04-18] D13：**外部 Agent / Skill 接入政务大脑是合法且必备的扩展路径**（A2A 服务端 + Skill 注册），具体协议⏳ 待业务侧同步；Phase 0 先以占位 schema 跑通编排闭环
- [2026-04-18] D14：**所有模型推理调用走集团推理平台的硬约束不变**；推理平台 SDK 具体形态⏳ 待业务侧同步；Phase 0 先以 mock 实现 `zw_brain/shared/inference/client.py`，文档到位后只换内部实现
- [2026-04-18] D15（修订）：原 N1「不做政务大脑自己的可视化大屏」**反转**为 K12「必保留」；架构上**保持相对独立**——独立部署单元 `zw-brain-dashboard/`、只读消费 dashboard.* Skill、禁止内嵌写操作（preflight 段 11 强制）、故障与主大脑隔离
- [2026-04-18] D16：在 §4.4.2 数据模型章节加入 **URN 小白解释**；后续凡新文档首次出现 URN 必须回链 §4.4.2，不得自行简化为「ID」「主键」
- [2026-04-18] D17（OPC 升级触发，第三轮自检）：**散文档数值漂移必须用 stat 块包裹**（详见基线附录 A「数字漂移防御层」），注册到 `dev-rules/.stats.json`，preflight 段 8 自动校验，禁止裸写"X 段 / X 类 / X 条"
- [2026-04-18] D18（OPC 升级触发，第七+八轮自检）：**「上游补实体 → 下游 fixture 缺位」「跨节引用幽灵编号」「行号硬编码"反复触发 → 治本：(a) GATE-2 后追加 `scripts/check_fixture_coverage.py` 校验 `adapters/*_adapter.py` ↔ `fixtures/<entity>/`；(b) `dev-rules/check-doc-xrefs.sh` 扫描 `§X.Y` 与 `line N` 引用形式
- [2026-04-18] D19（GATE-1 review 触发）：**技术选型从设计基线剔除** —— L1 Web 框架 + L2 编排引擎 ⏳ 延后到 Phase 0 PoC 决策（5 个对比维度：推理平台 SDK 兼容 / 审计 hook 注入难度 / AI Coding 改对率 / 政务部署兼容 / 集团技术栈一致性）；GATE-1 应 freeze 的是「哲学 / 架构层 / 数据模型 / 契约形态」，**反对「随手提到 = 隐式决策」反模式**
- [2026-04-18] D20（M-I (b) 落地，第六轮自检）：**数字漂移防御层 stat 命名修订 + wrap 范围** —— 落地附录 A 时发现原 `mapping-rows-old/new` 误判 §八 表用 K/N 行标识，修订为 `zwbrain.kept-functions`（§3.1 K 表）+ `zwbrain.not-doing`（§3.4 N 表）；5 个 zw-brain stat 中只有 `zwbrain.webui-pages-cap` 在 prose 中存在硬数字声明，已包裹（§7.3 共 3 处），其余 4 个 compute 就位但 prose 无对应数字、**不强行 wrap**（反对「为 stat 而 stat」反模式）

GATE-1 通过后立即收尾动作：

- [2026-04-18] 决策（GATE-1 后清理）：history rewrite 完成 —— 用 `git filter-repo --invert-paths` 从 master 全量历史清除 `digital-clone-research.md` + `old/05-*.docx` + `old/系统简介-*.xlsx` 共 3 个 .gitignore 排除文件（30→26 commits，备份在 `~/Backups/zw-brain-pre-rewrite-2026-04-18.git`，PR #1 merge commit `6e6f844` 重写为 `2268366`，PR 页面 commit 链接已失效但 PR 内容 / review / merge 时间戳保留）
- [2026-04-18] 决策：进入 Phase 0 ——「机械守卫脚手架」分支 `feature/phase-0-foundation`，按基线附录 A 13 项接入清单逐项落地（5 个 `check_*.py` + `export_agent_contract.py` + `skill.schema.json` + `verify_quality.py` + 数字漂移 stat 块 + `zw-brain-dashboard/` 骨架）
- [2026-04-18] D21（PR #1 后审视触发）：**GATE-1 retrofit — 设计文档必须配套可运行原型 + 机械化反向防御**。PR #1 误将"工程骨架"当作`product-dev.mdc` 阶段 2 的「最小可运行原型」交付。补：① `prototype/`（11 页可点击 SPA + 3 storyboards + README 12 条验证 checklist）；② `scripts/check_gate1_prototype.py` 接入 preflight 段 13 强制每份 `status: approved` 文档配套原型，缺则 commit 拦下。详见基线 §十四 D21
- [2026-04-18] D22（自检中触发）：**外部引用悬空 retrofit — 仓外 SoT 文件 + 锚点必须可解析 + 引用本地化**。history rewrite 之后仓外个人研究笔记从 working tree 消失，多处引用悬空、`hard-constraint-rows` stat 曾依赖该文件且因 `|| true` 静默吞错假绿。补：① 可选：从备份恢复物理文件到 workspace 同级；② `scripts/check_external_refs.py` 接入 preflight 段 14；③ 架构文档 **附录 D** 为 zw-brain 自包含软→硬映射（16 通用 + 8 项目特有），**B 路径**：仓内文档改为引用附录 D / 本文章节，`hard-constraint-rows` 改为从附录 D.1 计数。元规则：`|| true` 类静默吞错禁止用作主路径。详见基线 §十四 D22
- [2026-04-28] 决策：**退役 GATE-1 可点击 SPA 原型** —— 删除 `prototype/ui/`、`prototype/scripts/` 等可点击实现，移除 `scripts/check_gate1_prototype.py` 与 preflight 段 13；界面验证以正式 WebUI（`zw-brain-web/`）为准。**保留** `prototype/capability-sheets/` 与 `prototype/storyboards/` 作为持续演进的产品能力叙事与边界说明。D21 历史决策保留为档案；当前门禁不再要求可点击原型存在。
- [2026-04-28] 决策：**dev-rules 方案 A** —— zw-brain 不接子模块、CI 不克隆规范仓库；本机可选 symlink；通用 preflight 段依赖的 approved / stat 检查迁入 `scripts/`。
- [2026-05-18] 决策：**单一事实来源收敛 —— 退役 `prototype/` 目录**。`.experiences/` 已成为角色级稳态体验文档的权威源（M0 + R1-R8，~137KB），`prototype/storyboards/` 与 `prototype/capability-sheets/` 与之同主题但叙事冗余。Jobs 式取舍：从 `prototype/capability-sheets/README.md` 抽取"能力归属判定规则"（平台内建 vs 外部 ANP）+ 从 `prototype/storyboards/08-negative-flows-and-guardrails.md` 抽取 6 条系统级护栏，吸收为 `.experiences/README.md` 两节；其余（9 个 storyboards 含已退役 SPA 路由、6 份 CP 同模板冗余、prototype/README.md 客户交付内容已在 `docs/deployment/` 覆盖）直接删除。架构基线 §附录 C 同步更新——`prototype/*` 不再作为保留产物。

### [2026-05-19] GATE-1.1 retrofit：业务 review 触发的产品定义重置

2026-05-19 业务方（红军，旧平台产研负责人）线上视频 review zw-brain 当前角色旅程（`.experiences/R1-R8`），提出 18 条业务问题 + 3 条 UX 问题（原始材料：`old/20260519/`）。综合 Jobs 视角诊断：GATE-1 设计基线犯了三个根本性错误（角色矩阵化拍平、流程图当设计常量、AI 包装旧菜单 ≠ AI 原生）。本批 D23-D29 决策驱动一次性重写，**不留兼容**。

主评审材料：`docs/approved/zw-brain-gate1.1-retrofit-2026-05-19.md`；新角色规范：`docs/approved/zw-brain-roles-v2.md`；新 IA：`docs/approved/zw-brain-information-architecture-v2.md`；基线附录 D：`docs/approved/zw-brain-architecture-v4-gpt55.md`。

- [2026-05-19] D23：**R1-R8 角色矩阵退役**。采用旧平台 7 角色码（`ROLE_SYSTEM` / `ROLE_BUSIAUDIT` / `ROLE_ORGAN_MANAGER` / `ROLE_ORGAN_OPERATER` / `ROLE_SECURITY_ADMIN` / `ROLE_SECURITY_AUDIT`） + 标签位 `tag_lead_dept`。事实源：`old/20260519/平台系统角色菜单梳理v5.xlsx`。alembic 0009 一次性迁移存量数据，`policy.py` 启动检查兜底 + role_code CHECK 约束 + 前端字符串清零。
- [2026-05-19] D24：**信息架构收敛 3 旅程**。基线 §5.1 旧 J1-J4 + S1-S2 收敛为 J1 找数→用数 / J2 挂数→维数 / J3 看全局→处异常。§5.2 P1-P8 页面不变，重新归属。
- [2026-05-19] D25：**审批流可配置化承诺**。业务方反馈 #4 项目级流程定制（鞍山"编制→二级部门审→一级部门审→发布"），下期立项流程引擎，本期不做。
- [2026-05-19] D26：**表单 schema 化承诺**。业务方反馈 #17 项目级表单定制（四川/荆州），下期立项表单引擎，本期不做。
- [2026-05-19] D27：**21 条反馈处置摘要**。完整处置见评审主文档 §三。本期落地：#1 #2 #3 #5 #7 #8 #9 #10 #11 #12 #14 #15 #16 + U-1 U-2 U-3；延后：#4 #6 #13 #17 #18。
- [2026-05-19] D28：**GATE-x 元规则升级**。角色定义 / 业务流程 / 状态机三类决策，业务方 sign-off 才能进 D-编号。本批 D23-D29 待评审主文档 §九 sign-off。建议同步进 `dev-rules/global/CLAUDE.md` §2。
- [2026-05-19] D29：**R 编号空间区分**。`D-编号` GATE 后决策；基线 §11 `R1-R9` 架构约束保留（且本附录追加 R10/R11/R12）；用户角色 `R[1-8]` 完全退役，仓库 grep 残留为 0。

