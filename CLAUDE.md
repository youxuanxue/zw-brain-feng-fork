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

- [2026-04-15] 决策：采用 Cursor Long-running Agent + Claude Code Headless 双引擎架构
- [2026-04-15] 决策：规则单一事实来源放在独立仓库 ~/Codes/dev-rules/（不随公司项目删除），通过 sync.sh 分发
- [2026-04-15] 决策：研发流程增加原型设计阶段和两个审批门禁（原型审批 + 合并审批）
- [2026-04-15] 决策：消费端通过 sync 分发 `.cursor/rules/`；zw-brain 自 [2026-04-28] 起不接 dev-rules 子模块，本机 symlink + CI 浅克隆（见上文「规则体系」）
- [2026-04-16] 决策：强约束实现层落地——每条软规则配套机械检查脚本（映射见设计基线附录 D），git pre-commit hook 自动触发，禁止"靠自觉"
- [2026-04-17] 决策：`~/.claude/CLAUDE.md` 收编进 `dev-rules/global/CLAUDE.md`，由 `sync.sh` 维护 symlink，由 LaunchAgent 每小时 `git pull` 自动同步——消除最后一个手维护的孤儿配置文件

### [2026-04-18] GATE-1 通过：政务大脑 AI 原生重构设计基线

PR [#1](https://github.com/feng222666888/zw-brain/pull/1) merged at 2026-04-18 08:15:41Z by `feng222666888`；当前实现基线以 `docs/approved/zw-brain-architecture.md` 为准。完整决策详见 v4 基线相关章节，以下为 D-编号摘要（D1–D20 为 GATE-1 通过时落定，D21/D22 为 GATE-1 后 retrofit）：

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
  - **[2026-05-20] D15 二次反转**：K12 大屏**本期退役**。理由：（1）非 J1 黄金链路必要条件；（2）独立部署 + 独立技术栈分散团队维护精力；（3）真实客户大屏诉求未明确，提前内建违反 R7；（4）旧平台"演示场景"占比高于"运营使用"。代码层 `zw-brain-dashboard/` + `zw_brain/entry/dashboard_bff.py` + `scripts/check_dashboard_readonly.py` + preflight 段 11 + 4 个相关 tests 全部删除。复活路径：作为外部能力包独立产品或 Wave 3+ 立项。
- [2026-04-18] D16：在 §4.4.2 数据模型章节加入 **URN 小白解释**；后续凡新文档首次出现 URN 必须回链 §4.4.2，不得自行简化为「ID」「主键」
- [2026-04-18] D17（确定性自动化升级触发，第三轮自检）：**散文档数值漂移必须用 stat 块包裹**（详见基线附录 A「数字漂移防御层」），注册到 `scripts/.stats.json`，preflight 的 `sync-stats.sh --check` section 自动校验，禁止裸写"X 段 / X 类 / X 条"
- [2026-04-18] D18（确定性自动化升级触发，第七+八轮自检）：**「上游补实体 → 下游 fixture 缺位」「跨节引用幽灵编号」「行号硬编码"反复触发 → 治本：(a) GATE-2 后追加 `scripts/check_fixture_coverage.py` 校验 `adapters/*_adapter.py` ↔ `fixtures/<entity>/`；(b) `dev-rules/check-doc-xrefs.sh` 扫描 `§X.Y` 与 `line N` 引用形式
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

2026-05-19 海若产品部业务方（旧平台产研负责人）线上视频 review zw-brain 当前角色旅程（`.experiences/R1-R8`），提出 18 条业务问题 + 3 条 UX 问题（原始材料：`old/20260519/`）。综合 Jobs 视角诊断：GATE-1 设计基线犯了三个根本性错误（角色矩阵化拍平、流程图当设计常量、AI 包装旧菜单 ≠ AI 原生）。本批 D23-D29 决策驱动一次性重写，**不留兼容**。

主评审材料：`docs/approved/zw-brain-architecture.md`；新角色规范：`docs/approved/zw-brain-roles.md`；新 IA：`docs/approved/zw-brain-architecture.md`；基线附录 D：`docs/approved/zw-brain-architecture.md`。

- [2026-05-19] D23：**R1-R8 角色矩阵退役**。采用旧平台 7 角色码（`ROLE_SYSTEM` / `ROLE_BUSIAUDIT` / `ROLE_ORGAN_MANAGER` / `ROLE_ORGAN_OPERATER` / `ROLE_SECURITY_ADMIN` / `ROLE_SECURITY_AUDIT`） + 标签位 `tag_lead_dept`。事实源：`old/20260519/平台系统角色菜单梳理v5.xlsx`。alembic 0009 一次性迁移存量数据，`policy.py` 启动检查兜底 + role_code CHECK 约束 + 前端字符串清零。
  - **[2026-05-20] D23 二次升级（alembic 整体删除）**：alembic 整体删除（全新项目不背历史兼容；新功能 drop & recreate 替代）。原 0009 数据迁移本质性错误——zw-brain 是全新项目，无 r1-r8 存量数据需要迁移；`policy.assert_no_legacy_role_codes` + `scripts/check_no_legacy_role_codes.py` 启动检查 + 仓库 grep 双兜底仍存。
- [2026-05-19] D24：**信息架构收敛 3 旅程**。基线 §5.1 旧 J1-J4 + S1-S2 收敛为 J1 找数→用数 / J2 挂数→维数 / J3 看全局→处异常。§5.2 P1-P8 页面不变，重新归属。
  - **[2026-05-20] D24 二次反转**：J3 退为**后台支撑面 B1**，3 旅程 → 2 旅程（J1+J2）+ B1。原 P6/P8 改 B1.1/B1.2；K12 退役（详见 D15 二次反转）。**pending R13 业务方下次 review 二次 sign-off**；ia-v2.md 维持 3 旅程描述作为 GATE-1.1 sign-off 历史快照。
- [2026-05-19] D25：**审批流可配置化承诺**。业务方反馈 #4 项目级流程定制（鞍山"编制→二级部门审→一级部门审→发布"），下期立项流程引擎，本期不做。
- [2026-05-19] D26：**表单 schema 化承诺**。业务方反馈 #17 项目级表单定制（四川/荆州），下期立项表单引擎，本期不做。
- [2026-05-19] D27：**21 条反馈处置摘要**。完整处置见评审主文档 §三。本期落地：#1 #2 #3 #5 #7 #8 #9 #10 #11 #12 #14 #15 #16 + U-1 U-2 U-3；延后：#4 #6 #13 #17 #18。
- [2026-05-19] D28：**GATE-x 元规则升级**。角色定义 / 业务流程 / 状态机三类决策，业务方 sign-off 才能进 D-编号。本批 D23-D29 待评审主文档 §九 sign-off。建议同步进 `dev-rules/global/CLAUDE.md` §2。
- [2026-05-19] D29：**R 编号空间区分**。`D-编号` GATE 后决策；基线 §11 `R1-R9` 架构约束保留（且本附录追加 R10/R11/R12）；用户角色 `R[1-8]` 完全退役，仓库 grep 残留为 0。

### [2026-05-24] D30 retrofit：产品完成度 review 触发的漂移一次性清理

2026-05-24 乔布斯视角逐条对照架构基线 §1-附录 C 与代码事实（200 manifest / 5 消费面 / 14 preflight 段 / 18 测试套件），发现 6 项漂移并一次性清理。摘要：

- [2026-05-24] D30：**R15 AgentRuntime 触发式落地（撤回 Wave 1 sign-off）**。原 §10.2 "Wave 1 必达 ≥1 内置 Agent 用 AGENT.yaml 通过 validate+doctor"（产品负责人 sign-off 2026-05-22）落地范围**撤回**——原 sign-off 由产品负责人单独发出，未经业务方 GATE，按 R13 元规则不构成业务流程类决策的硬承诺，本次按确定性自动化运营和运维「只为真实需求建复杂度」改为触发式（§8.6 T1/T2/T3）。代码层无任何 AgentRuntime runtime 提前建造；协议规范 docs/agent-runtime/* 保留；Registry schema 字段（`runtime_spec_version` / `agent_yaml_ref` / `trust_level` / `workspace_required`）+ validate/doctor 工具链在 T1（首个真实外部 Agent 接入需求）触发当日落地。debt entry 见 [docs/preflight-debt.md](docs/preflight-debt.md)「2026-05-24 — AgentRuntime runtime 触发式延后」。
  - **R12 工程术语不进 UI 机械化**：新增 preflight 段 24 `scripts/check_ui_term_blacklist.py`。判定模型剥离 ${...} / HTML 属性值 / skill_id slug 后查残留 UI 文本，对真违规精确捕获、不误伤 contract slug。
  - **§9.5 adapter 写禁区机械化**：新增 preflight 段 25 `scripts/check_adapter_write_ban.py`。`zw_brain/adapters/legacy/` 之外任何写 token（session.add/commit/merge/delete / 裸 SQL INSERT/UPDATE/DELETE）拦下；legacy 一次性迁移区显式放行。
  - **R14 / §10.3 三引擎契约字段就位**：200 manifest 全量增加 `config_change_class: live` 默认值；`validate_manifest` 强制取值 ∈ {live, preview, draft}。Wave 2 三引擎落地时由配置 capability 显式改 preview/draft，无需再改 schema。
  - **死引用清理**：`standard.asset.sync`（deferred:wave-4）的 4 处主仓代码引用（brain.py dispatch union + policy.py 权限映射 + compliance_ops.py docstring + scripts/regenerate_bsp_capability_manifest.py FUNC 映射）全删；manifest 与 forbidden-zone 测试夹具保留（验证 §1.3 标准服务禁区回潮防护）；`tests/test_contract_projection.py::test_registered_skill_permissions_are_assigned_to_roles` 改为只校验 live skill；debt 条目「2026-05-22 standard.asset.sync」移除。
  - **附录 C 4 条 pending trigger 化**：外部能力包元数据 / Capability 确认边界 / 反 per-tenant fork / 控制面手维护投影 4 项从「待接入」改为「trigger 化 pending」，每条配明确 trigger，禁止长期沉淀。
  - **副作用确认**：5 消费面投影 `export_agent_contract.py --check` 零漂移；默认测试套 81 passed / 12 skipped；新增 2 段守卫脚本（段 24 R12 + 段 25 §9.5）对负向测试用例精确拦下；preflight 16 段全 PASS（14 旧 + 2 新）。


### [2026-05-27] D31 retrofit：业务方 PR #129 sign-off 触发 50 条不复刻清单部分复活

2026-05-27 海若产品部业务方在 [PR #129](https://github.com/feng222666888/zw-brain/pull/129) 对 `docs/legacy-not-reproduce-signoff.md` 50 条 ❌ 不复刻清单逐条签字判定。**8 类中 6 类接受不复刻 + 2 类复活**：

| 类别 | 业务方判定 | 影响 |
|---|---|---|
| A 融合 / 通用 / 代理服务（21 条） | ☑ 部分复活 20/21（106 案例提出页不复活） | 大改 — 重新设计服务能力面 |
| B 数字化运营 / 大屏（4 条） | ☑ 接受 | 无 |
| C 数据质量 / 元数据采集（2 条） | ☑ 接受 | 无 |
| D 主题库 / 专题库 / 数购车（4 条） | ☑ 复活 | 大改 — 重启主题库设计 |
| E 栏目管理（4 条） | ☑ 接受 | 无 |
| F 知识中心独立模块（1 条） | ☑ 接受 | 无 |
| G 多 SPA 拼接（1 条） | ☑ 接受 | 无 |
| H 应用中心 / 服务流程残项（13 条） | ☑ 接受 | 无 |

业务方对 A 类附注："**不需要 BSP / 不需要旧门户 / 可以考虑整合代理、融合、通用服务**" — 即**重新设计为服务能力面**而非复刻旧实现。

- [2026-05-27] D31：**业务方触发 24 条 ❌ → 复活（A 类 20 + D 类 4）— D10 retrofit 兑现**。D10（2026-04-18）原文承诺"5 个低价值功能（数据资源库 / 绩效考核 / 应用案例独立子系统 / 通用服务+链接资源 / 指标平台）默认不重构，**重激活前必走 product-dev.mdc 流程**"。本次业务方 PR #129 sign-off 正是该承诺中"重激活前流程"的兑现 — A 类 = D10 "通用服务+链接资源"重激活；D 类 = D10 "数据资源库"重激活（主题库 / 专题库 / 数购车；人口库 / 法人库继续不做）；H 类 = D10 "应用案例独立子系统" 保持不复活（业务方明示 106 案例提出页除外）；指标平台 / 绩效考核 在原 50 条 ❌ 范围内继续不复活。按飞轮 §五.2 / §九 反模式 #4 「不回灌客户反馈到真值源」立即启动 P0 真值源回灌：架构基线 §1.3 / 附录 A §3.1 / §5.6 同步修订 + mapping doc 24 条状态 ❌ → ⏸（deferred / 待 Wave 2.x+ 立项）+ `tests/fixtures/legacy_smoke.yaml` 刷新 + `docs/customer-readiness/wave4-cutoff-criteria.md` 判据 D 数字 sync。本批次仅做**真值源对齐**，不做执行立项；A/D 类的「服务能力面」与「主题库重启」设计另需业务方/产品 30 分钟 review 后走 R13 + GATE 流程产生新 D-编号（暂未发出）。
- [2026-05-27] D31.a：**A 类 106 案例提出页保持不复活**。业务方在 §二 A 注释明确"案例提出页不复活"，单独保留 ❌；mapping doc 行 106 / yaml entry 不变。
- [2026-05-27] D31.b：**复活范围归属待定**：(a) 进 Wave 2.x（与三引擎同期，作为"项目级服务能力面配置"）；(b) 进 Wave 3+（与协议硬化同期）；(c) 走外部能力包路径（B1.2 接入扩展中心承接）。三选一由下次业务方/产品 review 决定，不在本 P0 范围。
- [2026-05-27] D31.c：**飞轮反模式 #1 防御强化**：复活的"服务能力面"必须走 R8 反 per-tenant fork + R14 三引擎，禁止为复活功能在 zw-brain 内部复造旧 BSP / 旧门户结构。preflight 段 22 (capability-boundary) + 段 25 (adapter-write-ban) 继续守住。

### [2026-05-27] D32 retrofit：A/D 类复活归属决策 — 既存 reconstruction plan 接管

D31 子项 D31.b 原文："复活范围归属待定：(a) 进 Wave 2.x / (b) 进 Wave 3+ / (c) 外部能力包"。本次 V3 上帝视角穿透发现：**docs/reconstructs/ 内已有两份 reconstruction plan 完整覆盖 A/D 类**，D31 P0 真值源回灌时漏引用。D32 是 D31.b 的兑现 + V3 真值源补回灌。

- [2026-05-27] D32：**A 类 20 条复活 → 按 `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md`（399 行）落地**。该 plan 已写完旅程归属（J1 申请审批 / J2 发布审核 / B1.1 调用统计与网关健康 / Wave 3 编排外部化）+ §3.5 12 个 Capability slug（`resource.api.{register,change,submit_review,review,publish,withdraw,revoke,test,policy.update}` + `ops.gateway.{heartbeat.ingest,log.anchor}` + `ops.service.{report.query,invocation.query}`）+ §二.1 旧 5 模块映射（mgmt → J1+J2+B1.1；gateway → 运行时 adapter；work → anchor_outbox；orchestrator → 注册 Capability 包；hystrix-dashboard → 不迁入）+ §二.3 Pareto P0-P3 优先级。**业务方"整合后重新设计"已在此 plan 兑现**：不复刻旧 BSP / 旧门户子系统形态，承重语义散落到 J1/J2/B1.1 + 注册 Capability + 外部 adapter。Wave 归属：Wave 0 网关心跳 + 调用统计投影 / Wave 1 API 资源化 / Wave 2 R14 三引擎承接服务发布审批 / Wave 3 orchestrator 外部化。
- [2026-05-27] D32.a：**D 类 4 条复活 → 按 `docs/reconstructs/dsp-sharezone-topic-package-reconstruction-plan-v1.md` 落地**。该 plan 已写完旅程归属（J1 主题导航发现 + J2 运营方组织专题包）+ TopicPackage 6 张表 + §四 12 个 Capability slug（`topic.package.*` 系列）+ 首批 sd-default 山东高频跨部门政务标杆 + basesubject 81 表硬保护不复造（与 D7 forbidden-zone / §5.6 #13 一致）+ 一表通 Wave 2 候选可选 adapter 定位。Wave 归属：Wave 2 P7 共享专区，与三引擎同期。
- [2026-05-27] D32.b：**两份 plan 状态从"待业务方触发"升级为"D31/D32 已触发，active"**。plan 文件头加 D31/D32 触发注明；mapping doc 24 条 disposition 注明对应 plan 路径；signoff doc 加"批准后归属"段。
- [2026-05-27] D32.c：**D31.b 三选一关闭**：不是 (a)(b)(c) 任一，是 (d) **既存 reconstruction plan 接管，散落到 Wave 0/1/2/3 + 外部能力包**。A 类的 dsp-service-orchestrator 走 (c) 外部能力包，其余 19 条按 plan §3.5 拆到 J1/J2/B1.1；D 类按 P7 落地（与 plan 既定 Wave 2 一致）。
- [2026-05-27] D32.d：**V3 暴露 D31 P0 真值源回灌漏洞**：D31 P0 覆盖 7 文件（CLAUDE.md / 架构基线 §1.3/§3.1/§5.6 / 飞轮 / mapping doc / yaml / Wave 4 README），漏引用 `docs/reconstructs/` 内 2 份核心 plan。D32 补回灌 + meta finding：写 `scripts/check_approved_doc_drift.py` 扫"D-编号引用是否涵盖所有相关 reconstructs/*.md"，未来 D-编号决策必须 explicit 引用既存 plan。

### [2026-05-28] D33 retrofit：skill→capability 命名收敛 + AgentRuntime T1 触发前夜准备

**触发背景**：业务方启动首个外部 Agent 接入（T1 触发预告），按 D30 (2026-05-24) "AgentRuntime runtime 触发式延后"承诺，Registry 4 字段须在 T1 触发当日 land；同时跨边界审视发现 zw-brain 内部 "skill" 与 AgentRuntime `AGENT.yaml` `skills:` 段**同名异义**——zw-brain 内 skill ≡ capability（能力本体，230 manifest 中 `skill_id` 与 `slug` 值始终相等的冗余字段）；AgentRuntime `skills:` ≠ capability（外部 Agent 声明对 zw-brain capability 的消费引用）。命名歧义会随接入 Agent 数量线性扩散。Jobs 式裁决：「一个概念一个名字。外部协议不能改（D6 集团推理平台 + ANP 协议），那就让内部让路」。

- [2026-05-28] D33：**zw-brain 内部 "skill" 词整体退役 → 统一 "capability"**。
  - 目录 rename：`zw_brain/skill_registration/` → `zw_brain/capability_registry/`
  - manifest 顶层 `skill_id` 字段删除（与 `slug` 值始终相等的冗余）；保留 `slug` 作为唯一标识
  - Python 类名 / 函数名 / 模块 import 全部 rename（138 处标识符跨 39 文件 + 25 处 import）
  - preflight 段 22 内部命名已是 `capability-boundary`，仅同步引用路径
  - **范围裁决（关键）**：保留 `BrainService.invoke_skill()` 方法名 + envelope 返回字段 `skill_id` + `output_schema.properties.skill_id`——这些是 5 消费面投影（webui/api/cli/mcp/a2a）API surface，改它需同步前端/MCP/CLI 客户端，远超 D33 命名收敛初衷。envelope 字段名 `skill_id` 在新代码注释中明确为「等同于 capability slug；下一迭代统一」
  - **Why**：第一个外部 Agent 接入后，每个 Agent 作者开 AGENT.yaml 写 `skills:` 再翻 zw-brain 文档看 skill 会本能误判语义；命名收敛在 T1 触发**前**做边际成本最低（盘点：230 manifest + 138 标识符 + 25 import + 30 test 文件 + 11 preflight + 文档 1286 行）
  - **How to apply**：未来在 `zw_brain/` 代码下新增标识符时，禁止使用 `skill` 词（白名单外）；D33.c 新增 preflight 段机械守卫
- [2026-05-28] D33.a（**撤回，延后下一 PR**）：**`trust_level` 同名冲突解决 — 包级改名 `package.review_status`**。
  - 原计划：zw-brain `PACKAGE_TRUST_LEVELS = (baseline/reviewed/restricted/revoked)` → `PACKAGE_REVIEW_STATUSES`，字段名 `package.trust_level` → `package.review_status`
  - **撤回原因（执行中发现）**：`trust_level` 不仅是 manifest 字段名，还是完整 capability `package.trust_level.update` 的 slug + permission (`package.trust_level.update.execute`) + input/output_schema 字段 (`trust_level` / `previous_trust_level` / `new_trust_level`)。完整 rename 是 5 消费面（webui/api/cli/mcp/a2a）API breaking change，超出本 PR 的命名收敛初衷；半 rename（只改 Python 常量保留 manifest 字段）反而留下命名不一致
  - **现状继续守住**：runtime.py:17-22 反污染注释 + manifest_checks.py:15 ALLOWED_TRUST_LEVELS 隔离 namespace + 新人代码 review 时人工核对
  - **下一 PR 议题**：D33.a-followup — 完整 rename（capability slug + permission + schema + Python 常量同期 ship）+ 同期更新 5 消费面投影
  - AgentRuntime `metadata.trust_level (platform/verified/untrusted)` **不动**（外部协议字段）
- [2026-05-28] D33.b：**D30 触发式 4 字段中 runtime_spec_version validate + 工具链接入 preflight 持续守卫（最小可行；其余 3 字段延后）**。
  - 执行中盘点发现 4 字段中 `runtime_spec_version` 已在 `manifest_checks.py:43-49` 实装（从 AGENT.yaml schema_version / sidecar.runtime_spec_version / metadata.runtime_spec_version 多源提取并 validate）；其余 3 字段（`agent_yaml_ref` / `connection_trust_level` / `workspace_required`）是给 **未来 external-register 类型 Registry entry** 用的 schema 预留，**本 PR 不实装**（按"不为假需求盖楼"原则不强行填空值，T1 触发当日按届时实际需要扩展）
  - **本 PR 真实落地**：scripts/agentruntime_validate.py / agentruntime_doctor.py 已 246+52+54 行就位，新增 preflight 段 51 `scripts/check_agentruntime_bundles.py` 持续扫 `agents/*/AGENT.yaml`，T0 起即守住 schema 漂移
  - **下一 PR 议题**：T1 真触发（首个 source_type=external-register 接入）时，按需补 3 字段 schema + 230 manifest 默认值不需要填（external entry 是新 manifest，不是改老）
  - **Why**：D30 承诺「T1 触发当日落地」核心是 validate/doctor 工具链可跑——已通过 preflight 段 51 接入持续守卫，T1 来临时只需补外部 Agent bundle 即可，不需要再开 PR 做基础设施
  - **How to apply**：T1 触发当日，在 `agents/` 下新建外部 Agent 目录 + AGENT.yaml + capabilities.json，preflight 段 51 自动校验；如需 Registry 端字段 `agent_yaml_ref` 等，按届时实际需要 schema 扩展
- [2026-05-28] D33.c：**防回潮机械守卫 — preflight 段新增**。
  - 新增 `scripts/check_no_skill_identifier_in_zw_brain.py`：扫 `zw_brain/` 下 Python 文件，禁止新增包含 `skill` 字符串的 `class`/`def` 定义
  - 白名单（明确的 API surface contract）：`BrainService.invoke_skill` 方法、envelope 字段 `skill_id` 字符串字面量、引用 AgentRuntime AGENT.yaml `skills:` 字段的字符串字面量、`output_schema.properties.skill_id` 引用
  - **Why**：D17 / D18 / D22 已多次确立「软规则配套机械检查」原则；命名规则不机械化必回潮
  - **How to apply**：新代码若必须用 `skill` 词，须在 white_list 显式注册 + 注释说明 contract surface 理由
- [2026-05-28] D33.d：**元规则承诺 — GATE 决策必同步审视外部协议词汇边界（脚本延后）**。
  - 凡新增 / 修订 D-编号决策，须 explicit 审视与外部协议（AgentRuntime / MCP / A2A / 集团推理平台 SDK / ANP）的命名冲突
  - 长期目标：写 `scripts/check_external_protocol_term_drift.py` 扫 zw-brain 代码标识符与 `docs/agent-runtime/*` 协议字段的同名异义
  - 本 PR 仅落决策承诺；脚本随首次实操（下次 GATE 决策时手工审视，回炉成脚本）
  - **Why**：D33 是事后补救，根因是 GATE-1 没在「契约形态」决策时审视外部协议；元规则升级避免再现

### [2026-05-29] D34：F9 P7 共享专区 / TopicPackage 启动 sign-off（业务方全采纳建议）

业务方（海若产品部）对 `docs/wave2-acceptance/F9-business-review-package.md` 4 项业务决策点 sign-off，**全采纳建议**。载体 = PR #162 label `business-signoff: e3.F9`（`promote_signoff.py` 已将 topic-package-discovery/curation 两 feature Draft→Ready）；plan.yaml F9 `[SIGNOFF-CLOSED 2026-05-29]` 落盘。本次 review 用「上帝视角 Jobs」据**真实数据**（`old/10示例数据` dump + `seed_snapshot.json`）逐条验证，产出四条实质裁决（满足 D28/D32.b 元规则：状态机 / 可见性属 sign-off 范围）：

- [2026-05-29] D34.a：**共享专区 = 运营方策展容器 ≠ 主题分类**。旧定义据 `old/12-datastructure/dsp_catalog.xml` `share_zone*` 系列表（专区=运营方挑选目录的命名容器 + 组织授权 + 上线审核 + 统计）；真实 dump 中 `share_zone*` **实例=0**（仅 schema 无数据）→ 首批 sd-default 专区由运营方**新建策展**，无真实专区可镜像。专区只**引用**目录（`topic_package_item → catalog_entry`）不持有；目录自带的「主题/分类」（`data_catalog_category`）归 **catalog 线**的 `catalog_entry.subject_tags`，**不进 F9 专区**。纠正本会话前期把「主题包」误当「按 subject 聚类全部目录」的概念漂移。
- [2026-05-29] D34.b：**`topic.package.policy.update` 默认双签**。可见性策略写权限默认收紧为「`ROLE_BUSIAUDIT` + 大数据局领导双签」，业务方主动放开才独立——政务安全产品敏感写权限默认从严。
- [2026-05-29] D34.c：**seed 上游依赖 sequencing**。专区只引用不造目录 → Z1 医疗救助（目录已全在 `seed_snapshot.json`）**P0 先行**；Z2 医保码 / Z3 异地就医引用的目录真实 dump 有、**未进 seed**，须 **catalog 线先补种**后做（采纳路径 a）。F9 delivery worker 启动顺序受此约束。
- [2026-05-29] D34.d：**残疾人两项补贴排除**。真实 dump 未命中 → 守 D11（禁 Mock 业务数据）默认排除，有真实数据源再加。
- **外部协议词汇审视（D33.d 元规则）**：`topic.package.*` / `policy.update` 均为 zw-brain capability 内部 slug，与 AgentRuntime `skills:` / MCP / A2A / ANP 协议字段无同名异义。
- **下一步（不在本决策范围）**：F9 delivery（6 表 + capability + fixture + e2e）另起 worktree 执行；catalog 线补种 Z2/Z3 目录是其前置。

### [2026-05-29] D35：sign-off 模式升级 — 模板 + 两段机械守卫（确定性自动化）

D34 这次 review 的所有问题（概念漂移 / 选择依据未验真 / 假数字 / 硬前置埋没 / 权限默认反向）**全靠人仔细读抓出来，无一被机器拦**——违背宪法 §5「靠自觉反复出现必须硬化」。**dogfood 当场再证**：即便经 Jobs 视角逐条审 + 业务方 sign-off，段 53 仍机械捕获到「特困人员救助供养信息」被误标 dump 命中（"特困"仅见于医疗救助申请材料文本，无独立目录）→ 已更正为排除（D11）。故把三类质量保障沉淀为 zw-brain 可复用机制：

- [2026-05-29] D35.a：**sign-off 材料包统一模板** `docs/templates/business-signoff-package.md`。强制节：① 启动硬前置（sequencing，列上游依赖，无则显式"无"）；② 每个「业务方判定」表配「建议」列 + 一句理由（预填**安全方向**默认）；③ 触及 legacy 概念必带「概念边界」澄清 + 旧 schema 引用。真实性标签词表：`seed 真实` / `dump 命中` / `dump 未命中` / `evidence 关联`。禁过程/估算数字（N 分钟 / N-M 天 / worker·day / 未 stat-wrap 的 N 态）。
- [2026-05-29] D35.b：**段 53 `check_signoff_package.py`（检测层）**。Layer 1 数据真实性：标 seed/dump 命中的行必须真的在 `seed_snapshot.json` / `old/10示例数据` dump 命中，否则 FAIL（dump 缺位显式 skip，不 `|| true` 静默吞错，遵 D22）；Layer 2 完整性：禁过程数字 + 强制「启动硬前置」节 + 判定表必配「建议」列；Layer 3 概念边界 WARN。
- [2026-05-29] D35.c：**段 54 `check_signoff_landed.py`（落盘层）**。材料包 frontmatter `status: approved` 时，校验 `.twin/**/plan.yaml` 有匹配 `[SIGNOFF-CLOSED ... <scope>]` evidence + CLAUDE.md 有提及 `<scope>` 的 D-编号；缺则 FAIL。**关闭 F9 §5.3 自陈的「C/D 落盘靠人记忆」债**（不再 debt 化）。
- [2026-05-29] D35.d：**元规则升级（接 D28/D32.b）**：今后业务方 sign-off 材料必须走 D35.a 模板并通过段 53/54。F9 材料包补 frontmatter 成为首个模板对齐样本（dogfood）。
- **外部协议词汇审视（D33.d）**：本决策新增标识符 `check_signoff_package` / `check_signoff_landed` / `business-signoff:<scope>` label 均为 zw-brain preflight/CI 内部，与 AgentRuntime / MCP / A2A / ANP 协议无同名异义。
- **范围**：zw-brain 内（证明有效后再议上提 dev-rules global，惠及 industry-brain / PetroMind 等）。

### [2026-05-29] D36 retrofit：推理网关 env 契约收敛 `INSPUR_INFERENCE_*` → `ZW_BRAIN_INFERENCE_*` + 兜底清零

> **编号说明**：本节随 PR #163 落地，原拟编号 D34；合并 main 时发现 D34（F9 共享专区）/ D35（sign-off 模式）已被 PR #162 占用，故顺延为 **D36**。PR #163 早期 commit message 与测试 `request_id`（`REQ-D36-*`）可能仍现 "D34" 字样——以本编号 D36 为准。

**触发背景**：审视 `zw_brain/shared/inference/client.py` 取值链时发现推理平台连接变量散落两套前缀（公司级 `INSPUR_INFERENCE_*` + 项目级 `ZW_BRAIN_INFERENCE_*`）且层层裸名兜底（`AUTH_TOKEN` / `BASE_URL` / `MODEL`），与项目自有 env namespace（`ZW_BRAIN_*`，如 `ZW_BRAIN_INFERENCE_MODE` / `ZW_BRAIN_DEV_IAM_BYPASS`）不一致；裸名兜底还会在多工作区 shell 污染下静默取错密钥/网关。Jobs 式裁决：「一个东西一个名字，前缀随项目 namespace 收敛，不接受任何隐式兜底」。

- [2026-05-29] D36：**推理网关连接变量统一为 `ZW_BRAIN_INFERENCE_*`，删除一切其他前缀/裸名兜底**。
  - 连接三变量定型：`ZW_BRAIN_INFERENCE_GATEWAY_URL`（网关地址）/ `ZW_BRAIN_INFERENCE_API_KEY`（解析后的字面密钥）/ `ZW_BRAIN_INFERENCE_MODEL`（模型名）
  - **删除的兜底**：`client.py` / `config.py` 桥接 / `manifest_checks.py` doctor 内的 `INSPUR_INFERENCE_*`、`os.getenv("AUTH_TOKEN")`、裸 `os.getenv("BASE_URL")`、裸 `os.getenv("MODEL")` 全部删除；连接变量只认唯一 `ZW_BRAIN_INFERENCE_*` 键，取不到即按既有 `InferenceError` / doctor FAIL 路径显式报错
  - **保留**：`DEFAULT_INFERENCE_MODEL`（代码缺省模型常量，非竞争前缀的 env 兜底）；`OPENAI_COMPATIBLE_*` / `OPENAI_*`（AgentRuntime 适配器原生下游变量，是桥接目标与显式配置逃生口，非 zw-brain 前缀兜底）；`ZW_BRAIN_INFERENCE_API_KEY_OPTIONAL` / `_PLACEHOLDER`（占位 feature）
  - **同步面**：`agent-runtime.yaml` + 2 个内置 `agents/*/AGENT.yaml`（`${env:ZW_BRAIN_INFERENCE_MODEL}`）+ `scripts/start-local.sh` + 部署文档（docker / embedded）+ 5 个测试文件 + `.twin/` spike 残留
  - **Why**：与 D6「模型调用收口集团推理平台」属同一契约面；项目 env namespace 单一化降低运维与多工作区误配风险；裸名兜底违反 D17/D18/D22「不靠自觉、软规则配套机械守卫」精神（兜底=隐式取值=回潮温床）
  - **How to apply**：未来在 `zw_brain/` 内新增模型服务取值，禁止读取 `INSPUR_INFERENCE_*` / `AUTH_TOKEN` / 裸 `BASE_URL`/`MODEL`；只读 `ZW_BRAIN_INFERENCE_*`
- [2026-05-29] D36.a：**密钥引用间接层保留 — `_API_KEY_REF`（指针）与 `_API_KEY`（字面值）严格区分，禁止合并**。
  - `ZW_BRAIN_INFERENCE_API_KEY_REF` = 部署期配置的**密钥引用指针**（`arn:secrets:...` / `vault:...`），与 `ZW_BRAIN_IAF_CLIENT_SECRET_REF` / `ZW_BRAIN_BLOCKCHAIN_KEY_REF` 同套约定；仅存于 3 份部署文档，**密钥材料不进入镜像/版本控制**
  - `ZW_BRAIN_INFERENCE_API_KEY` = 部署层解析 `_REF` 后注入进程的**字面密钥**，运行时代码（`client.py` / 桥接 / doctor）实际读取
  - 解析流向：`_API_KEY_REF=arn:...` →（部署层/密钥库解析）→ 字面 `ZW_BRAIN_INFERENCE_API_KEY` → 代码读取
  - **现状边界**：仓内仅有文档契约，`_REF` 无代码 reader、解析属外部部署层（与改动前一致，也与 IAF/blockchain `_REF` 同样未在仓内解析）。若未来需仓内轻量 ref 解析器，另立 PR
  - **Why**：合并两者会把"指针"赋给"字面密钥"变量（`arn:...` 整串当 Bearer token 发出→鉴权失败 + 合规告警），破坏既有密钥不落明文的安全姿态
  - **How to apply**：禁止把 `_API_KEY_REF` 与 `_API_KEY` 视为同义；新增任何外部凭证 env 一律遵循 `*_REF`（指针）/ 字面值（运行时）二元命名
- [2026-05-29] D36.b：**回潮机械守卫由负向测试承担**。`tests/test_agentruntime_config.py::test_embedded_runtime_env_does_not_bridge_legacy_auth_token_or_base_url` 断言 `AUTH_TOKEN` / `BASE_URL` 不再被桥接，锁死 D36 兜底清零；未来若有人重新引入兜底即测试红。`tests/integration/test_inference_client.py` env 清理同步只清 `ZW_BRAIN_INFERENCE_*`。
- [2026-05-29] D36.c（上帝视角 re-review 触发）：**两项边界显式化**。
  - **客户端层负向守卫补齐**：D36.b 的兜底守卫原仅覆盖 `config.py` 桥接层；新增 `tests/integration/test_inference_client.py::test_client_ignores_legacy_{base_url,api_key}_env_prefixes`，在 `InferenceClient` 本体也机械锁死「连接变量只认 `ZW_BRAIN_INFERENCE_*`」——设 `INSPUR_INFERENCE_*` / `AUTH_TOKEN` / 裸 `BASE_URL` 后平台模式仍报 `base_url/auth token is required`，证明旧前缀不被读取。**Why**：D36 头号承诺是 client.py 不兜底，但守卫此前只在 bridge 层，client 层规则形同 prose（D17/D18/D22）。
  - **`INSPUR_*` 代码标识符保留是 deliberate，非漏改**：`manifest_checks.py` 的 `INSPUR_GATEWAY_MARKERS` / `_url_is_inspur_gateway` / sample `provider: inspur-inference-gateway` 保留 `inspur` 命名——它们识别的是**物理集团网关 host**（如 `inference.inspur.com`，见 `docs/deployment/sd-default-onboarding.md`），不是 env 变量名；marker `"inspur"` 对真实网关 host 探测是**承重**的，改名会破坏 D6 网关识别。**How to apply**：禁止以「命名一致性」为由把这些 `inspur` 标识符改成 `zw_brain`；env 变量前缀（配置句柄）与网关 host 身份（物理系统）是两个维度，D36 只收敛前者。
- [2026-05-29] D36.d（xj-review R-002 触发）：**wave2 验收测试 shadow DB 隔离修复（WAL/SHM 旁路清理）**。`tests/integration/test_wave2_three_engines_acceptance.py::_shadow_db` 原只 `unlink()` `.db`，遗留 WAL 模式 `-wal`/`-shm` 旁路 → 新建 `.db` 重挂不匹配旧 WAL → `sqlite3.DatabaseError: database disk image is malformed`（间歇）。修复：setup 先 `reset_engine_cache()` 再删 `.db`+`-wal`+`-shm` 三件套，teardown 同样清理。**性能基准 flaky**（`test_wave0_j1_request_list_perf` 负载敏感超 1000ms 预算）属另一类，记 `docs/preflight-debt.md`，不在本 PR 修。
- [2026-05-29] D36.e（已 close 的 PR #160 触发，salvage 单独成 PR）：**`INSPUR_INFERENCE_*` 回潮机械守卫落地**。D36 / D36.c 此前只有 client 层 pytest 负向测试，无仓库级防线；已 close 的 PR #160 差点把已退役 `INSPUR_INFERENCE_*` env 前缀钉进 twin 证据源 + 运维债务文档（preflight 全绿却放过 = prose 规则被绕过的活案例）。新增 `scripts/check_no_legacy_inference_env.py` + preflight 段 56：扫全仓 tracked 文件禁该字面量；allowlist 仅 3 文件（本 CLAUDE.md D36 决策记录 + `tests/integration/test_inference_client.py` 负向守卫 + 守卫自身）。承重网关 host 标识 `INSPUR_GATEWAY_MARKERS` / `inspur-inference-gateway` 不含该子串、天然不匹配（D36.c：env 前缀 vs 网关 host 身份两个维度）。PR #160 本体（F2 blocked→completed 翻转）已被 #167 取代、作 stale close，仅此守卫 salvage。**Why**：D17/D18/D22「软规则必须配套机械检查」——#160 实证 prose 不机械化必回潮。

### [2026-05-29] D37：效果验收签字守卫 — 锚在可机读证据产物（确定性自动化）

> **编号说明**：本节原拟 D36；合并 main 时 PR #163 的「推理 env 契约收敛」已占 D36，故顺延为 **D37**（e5 验收顺延 D38）。早期 commit message / 文件内 `(D36)` 字样以本编号 D37 为准。

D35 覆盖**决策**签字（"该不该做",查数据真不真）；本批补**效果验收**签字（"做完的真能跑没"，查功能真跑过没）。触发：扫 zw-brain 发现 e5（WebUI/5 消费面，17 feature completed）与 e6 交付已久但 **0 验收签字**；走 e5 一遍暴露验收侧"靠人、无护栏"（结构无模板 / 证据声称无机核 / 状态滞后手搬 / 标签语法无整 epic scope）。

- [2026-05-29] D37.a：**验收证据锚在产物,禁 prose 裸断言**。`scripts/capture_acceptance_evidence.py` **现场跑** contract(`export_agent_contract --check`)+pytest(exit 码)+e2e(解析 Playwright 日志),写 **tracked** 产物 `.testing/acceptance/<scope>/evidence.json`(`.data/` 是 gitignore 派生区,不放,否则 CI 查不到)。记 git_sha + captured_at。
- [2026-05-29] D37.b：**段 55 `check_acceptance_package.py`**。Layer1 证据真实性:frontmatter.evidence 指向的产物必须存在 + 每条 check result=pass + git_sha 是 HEAD 祖先(否则 WARN 异线/陈旧);验收点表每条引用的 evidence 标签必须在产物 checks 里找得到(声称必有背书)。Layer2 结构:强制「验收范围」节 + 每验收点挂 evidence 标签(禁裸"已验证") + 禁过程数字。
- [2026-05-29] D37.c：**补两处糙点**。`promote_signoff.py` 支持整 epic scope `eN`(翻该 epic 全部 `eN.F*` .feature);`check_signoff_landed.py`(段 54)同时认 `*acceptance-package*.md`,与决策包共用落盘三角。
- [2026-05-29] D37.d：**dogfood e5（机制验证）**。`docs/acceptance/e5-acceptance-package.md` + `.testing/acceptance/e5/evidence.json`:contract 零漂移 / pytest exit 0 / e2e 15 passed-1 skipped 三项 **现场实测 pass**。段 55 正向 OK、负向(改 fail / 删 evidence 标签)精确拦下。
- **dogfood 暴露真实约束(已记 e5 包 + 待办)**:(1) **证据 provenance** —— worktree 无 venv,本次在共享主仓(sibling commit)采集,evidence git_sha 非本分支祖先 → 段 55 如实 WARN「异线」;正常流程在 PR commit 上采集即无 WARN;待办:让 worktree 可跑验证 / CI 在 PR commit 重采。(2) **采集隔离** —— e2e 活跑把共享 dev DB 撑到 200MB+,拖慢随后 pytest + 与他人 pytest 抢 sqlite 锁;验收采集应用独立/临时 DB。
- **元规则升级(接 D28/D35.d)**：效果验收签字材料走 D37 模板 + 段 55；与决策签字(D35)区分但共用段 54 落盘三角。
- **外部协议词汇审视(D33.d)**：新增标识符 `capture_acceptance_evidence` / `check_acceptance_package` / scope `eN` 均 zw-brain preflight/CI 内部,与外部协议无同名异义。

### [2026-05-29] D38：e5 WebUI / 5 消费面投影 — 效果验收通过（D37 守卫首个真验收）

D37 建的验收守卫的首个真实使用。e5（WebUI 8 页面 + 5 消费面 + NL 加速器，plan 17 feature completed、0 验收签字）走 D37 流程完成效果验收，**业务方 2026-05-29 全过**。

- [2026-05-29] D38：**e5 效果验收通过**。机器证据(`.testing/acceptance/e5/evidence.json`)：投影零漂移 / pytest exit 0 / e2e `customer_acceptance_checklist` 15 passed-1 skipped 三项现场实测 pass。业务方 A/B/C 清单(客户买方视角 6 项 + 7 角色日常活 + 4 跨切非谈判项)全过(详见 `docs/acceptance/e5-acceptance-package.md`)。载体 = PR #164 label `business-signoff: e5`(`promote_signoff` 翻 e5 全部 `e5.F*` .feature InTest→Ready)；plan.yaml F3 `[SIGNOFF-CLOSED 2026-05-29] covers e5`。本文 status→approved。
- [2026-05-29] D38.a：**证据 provenance 受限,记 debt 不阻塞**。验收证据在共享主仓(sibling commit `3383562`)采集 → 段 55 如实 WARN「git_sha 非本分支祖先」。**已验证 worktree 内重采得到正确 sha 但 pytest 因 bare-worktree 无 venv 而 fail** —— 即"绿 pytest"与"正确 sha"在当前 env 拓扑下二选一。真正修法：**CI 在 PR commit 上 emit evidence.json**（消除人工采集的 env 依赖）。登记 `docs/preflight-debt.md`「2026-05-29 — 验收证据 CI 化采集」，trigger=下个验收签字 / CI evidence job 立项。WARN 非阻塞,approved 记录保留该 provenance 注记。

### [2026-05-29] D39：IA 二次反转业务方二次 sign-off — 信息架构定型为 2 旅程 + B1 后台

闭合 **D24 明文「pending R13 业务方下次 review 二次 sign-off」**。GATE-1.1（2026-05-19）业务方签的是 3 旅程；产品侧二次反转为 2 旅程 + B1 后台（J3 退役、K12 大屏退役），WebUI 已按此建成并经 e5 验收（D38），但反转本身未经业务方二次签。本次走 D35 决策签字模板补签，**业务方 2026-05-29 全部同意**。

- [2026-05-29] D39：**信息架构定型 = 2 旅程（J1 找数→用数 / J2 挂数→维数）+ B1 后台支撑面**。业务方 sign-off 3 决策点全接受：① J3「看全局→处异常」退为 B1 后台（仅大数据局管理员/审计员，能力不减只是重新归类）；② K12 可视化大屏本期退役（复活走外部能力包 / Wave 3+）；③ ≤8 主入口 2旅程+B1 形态定型。载体 = PR #165 label `business-signoff: ia-2journey-b1`；plan.yaml e5 F3 `[SIGNOFF-CLOSED 2026-05-29] covers ia-2journey-b1`（锚 e5，WebUI 体现该 IA）。材料 `docs/decisions/ia-2journey-b1-business-review-package.md`。
- [2026-05-29] D39.a：**D24「pending 二次 sign-off」债闭合**。GATE-1.1 的 3 旅程历史快照保留为档案；当前 IA 真值源 = 架构基线 §1.2/§7.3（已是 2+B1）。
- **外部协议词汇审视（D33.d）**：scope `ia-2journey-b1` 为 zw-brain 内部 signoff 标识，与外部协议无同名异义。

### [2026-05-29] D40：A 类「数据服务能力面」设计业务方 sign-off — 20 条复活落地形态定型

闭合 **D31/D32 遗留的 A 类「服务能力面」设计 review**（D 类主题库/专题包已 F9 落地；A 类 20 条复活的设计此前"暂未发出"）。据 `dsp-dataservice-reconstruction-plan-v1.md`，**业务方 2026-05-29 全部同意**。

- [2026-05-29] D40：**A 类 20 条复活 = 数据服务能力面，按 dsp-dataservice plan 落地**。业务方 sign-off 5 决策点全接受：① 重设计为服务能力面、不复刻旧 BSP/门户/服务后台；② API 服务资源化（进 J1 主旅程 P2/P3/P4，不切独立后台）；③ 网关心跳/调用统计 = B1.1 只读投影 + 对接集团运维（不重造业务报表/熔断大屏）；④ orchestrator 走外部能力包、hystrix 不迁入；⑤ 106 案例提出页保持不复活（D31.a 确认）。Wave 节奏全认可（Wave 0 网关心跳 / Wave 1 API 资源化 / Wave 2 服务发布审批复用 R14 / Wave 3 编排外部化）。载体 = PR #165 label `business-signoff: aclass-dataservice`；plan.yaml e6 F1 `[SIGNOFF-CLOSED 2026-05-29] covers aclass-dataservice`。材料 `docs/decisions/aclass-dataservice-capability-business-review-package.md`。
- [2026-05-29] D40.a：**dsp-dataservice plan 升级为"业务方设计 sign-off 完成"**。A 类此后按 plan + Wave 节奏执行，禁止绕过 plan 直接立项（D32 元规则）。
- **外部协议词汇审视（D33.d）**：`resource.api.*` / `ops.gateway.*` / `ops.service.*` capability slug 均 zw-brain 内部，与 AgentRuntime / MCP / A2A / ANP 协议无同名异义。

### [2026-05-29] D41：B1 borderline 报表 capability 定性 — 5 条确认留 live（关 2026-05-23 债）

闭合 `preflight-debt.md`「2026-05-23 — 5 个 borderline B1 业务报表 capability 仍 live，待业务方 sign-off」，其触发条件 (a) = "业务方下次 IA review 对 5 条逐一 sign-off"，本次 IA review（D39）即该时机。**业务方 2026-05-29 全部同意留 live**。

- [2026-05-29] D41：**5 条 B1 capability 定性 = 业务运营报表，留 `status: live`**（非运维监控、不转 external）：`service.rating.submit` / `ops.catalog.statistics.query` / `ops.exchange.statistics.query` / `ops.service.invocation.query` / `ops.service.report.query`。判据：均基于 zw-brain 自有业务事实（申请/调用/评价），非网关/主机运行指标；运维监控（CPU/存活/熔断）才归集团（基线 §3.4）。与 D40 A 类「业务报表内建 + 运维指标外接」边界一致。载体 = PR #165 label `business-signoff: b1-borderline-reports`；plan.yaml e6 F1 `[SIGNOFF-CLOSED 2026-05-29] covers b1-borderline-reports`。`preflight-debt.md` 2026-05-23 债条删除。材料 `docs/decisions/b1-borderline-reports-business-review-package.md`。
- **外部协议词汇审视（D33.d）**：scope `b1-borderline-reports` 为 zw-brain 内部 signoff 标识，与外部协议无同名异义。

### [2026-05-30] D42：F9 P7 共享专区 / 专题包 — 效果验收通过（D37 守卫 + 本地部署逐条走查）

闭合 F9（D34.c 启动准入 → 收尾 PR 真端到端 → 本地验收）。e3.F9（TopicPackage 6 表 + 10 capability + sd-default 3 标杆 + P7 前端真接）走 D37 效果验收 + 业务方本地部署逐条走查，**2026-05-30 全部通过**。载体 = PR #170。

- [2026-05-30] D42：**e3.F9 效果验收通过**。机器证据（`.testing/acceptance/e3.F9/evidence.json`）：投影零漂移 / pytest exit 0 / P7 e2e 4 passed 三项现场实测 pass（git_sha 对齐 HEAD，段 55 无 WARN）。业务方本地部署逐条走查全过：① P7 列表真拉 3 标杆；② 订阅诚实回显（isSubscribed，按钮态「订阅/已订阅」）；③ 目录诚实展示；④ 召回候选 422 修复。plan.yaml e3 F9 `[SIGNOFF-CLOSED 2026-05-30] covers e3.F9` + status→completed。材料 `docs/acceptance/e3-f9-topicpackage-acceptance-package.md`。
- [2026-05-30] D42.a：**订阅降级为诚实信号（概念 A），概念 B 待立项**。P7「订阅专题」是旧平台弱概念 A（专区收藏，旧平台真实使用=0）的实现，本期只做 isSubscribed 诚实回显、无下游业务。真业务价值的「部门级数据供给契约」（概念 B：`dc_subscribe` / 持续供给 + 国家平台回执，属 J1 找数 + 交换线）记 `preflight-debt.md` 待立项，**不在 F9**。守 D11 不为伪需求建复杂度。
- [2026-05-30] D42.b：**F9 引用目录主表不可达 → 诚实展示 + 下个 PR 打通**。F9 三标杆引用的 5 个目录在 `catalog_entry` 主表 0 条可检索、无详情页（只在召回字典 + 专题包 ref_id）。本期 P7 目录项改诚实文本「待 J1 目录主表录入后开放」、P2 召回候选卡片去坏按钮（修既有 422），不假装有去处。根因记 `preflight-debt.md`，下个 PR 专项打通「目录主表录入 + 目录详情页」（属 J1 找数能力）。
- **外部协议词汇审视（D33.d）**：scope `e3.F9` / `isSubscribed` / `recall_dictionary` 均 zw-brain 内部标识，与 AgentRuntime / MCP / A2A / ANP 协议无同名异义。

### [2026-05-30] D43：J1 目录→资源钻取链路 — D42.b 兑现 + 效果验收通过

闭合 **D42.b**（F9 验收时记的"下个 PR 打通目录主表录入 + 目录详情页"）。本地验收发现「资源发现没区分目录/资源、点目录看不到目录下资源」缺口，本 PR（#171）补全 J1 找数的目录→资源钻取链路 + 真实数据充分展现，业务方 2026-05-30 本地全集真实库逐页走查通过。

- [2026-05-30] D43：**目录→资源钻取链路落地 + 效果验收通过**。新增 `catalog.resource.list` 能力（列目录下 resource_asset；目录挂0资源→诚实空列表、不存在→404）+ `ResourceApiRepository.list_assets_by_catalog` + `P2CatalogDetail` 目录详情页（`#/discovery/catalog/:code`）+ `P2CatalogBrowse` 接 `catalog.browse` 真 API 真钻取（修软搜索假钻取）。机器证据（`.testing/acceptance/j1-catalog-drilldown/evidence.json`）：投影零漂移 / pytest exit 0（干净全量真实库）/ e2e 3 passed，git_sha 对齐 HEAD。载体 = PR #171 label `business-signoff: j1-catalog-drilldown`；plan.yaml e1 F4 `[SIGNOFF-CLOSED 2026-05-30] covers j1-catalog-drilldown`。材料 `docs/acceptance/j1-catalog-drilldown-acceptance-package.md`。
- [2026-05-30] D43.a：**目录浏览页信息增强（本地验收反馈）**。`_browse_catalog_entries` 批量算 resource_count（list_assets 一次 + 按 catalog_code 分组，避免 N+1）+ enrich ownerName（summary.org_name 真实机构名）+ description。前端列：目录名/资源数/责任方机构名/说明/操作（去状态列，都是 active 无意义）。解决"97/154 active 目录无资源、逐个点进去才知道"的体验缺口。
- [2026-05-30] D43.b：**F9 5 医保目录录入 catalog_entry 主表（兑现 D42.b）**。seed `provider.catalogs` 追加 5 个 `basic-elem:*` 医保目录 + database_store sync 补 `catalog_code` 映射断点。它们挂0资源（basic-element 本就无资源，数据真相）→ 详情页诚实空列表。F9 目录从"召回字典软提示"升级为"主表可检索 + 可点进目录详情"。
- [2026-05-30] D43.c：**全局数据缺位 + 真数据脆测试 → 另起 PR**。本 PR 验收时系统性审计发现：(1) 多个 snapshot 字段（资源发现/申请/审批/专题包列表）仍 seed 精选 demo 而非真实库全量（`docs/decisions/global-data-gap-audit.md`）；(2) 真数据 baseline 脆测试一批（`require_real_seed` 用运行时累积量当门槛 + 阈值>稳定态）。两者均 **与 #171 钻取无关、预存问题**，记录后另起专项 PR，不混入本 PR。
- **外部协议词汇审视（D33.d）**：scope `j1-catalog-drilldown` / slug `catalog.resource.list` 均 zw-brain 内部标识，与 AgentRuntime / MCP / A2A / ANP 协议无同名异义。

### [2026-05-30] D44：真数据 baseline 脆测试批量修 — 兑现 D43.c(2)

闭合 **D43.c(2)**（"真数据 baseline 脆测试一批 → 另起专项 PR"）。脆测试两类病灶逐条对照稳定态真值（clean 全量真实库，sd-default：catalog_entry=1222 / application_record=263 / approval_case=267 / approval_step=889 / approval_decision=888 / delivery_task=67 / capability_call=运行时遥测）一次性修正。**纯工程决策，非 D28/D35 业务 sign-off 范畴**（不触角色/流程/状态机）。本 PR 不混入 D43.c(1) 的全局数据缺位修复（另起 PR）。

- [2026-05-30] D44：**两类脆测试修正**。
  - **A 类（必修，设计错误）— `tests/test_wave0_j1_credential_call.py`**：① `require_real_seed({"capability_call": 744})` 把**运行时累积遥测量**当 seed 门槛——`capability_call` 由 pipeline 每次 invoke 经 `record_capability_call` 落库、**不来自 legacy import**（fresh import=0、本机 clean=个位数），744 是某次本机累积后的量 → CI 无 DB skip、本地 clean 也 skip、**整 module 永久不跑**。修：门槛改 gate 真正依赖的 legacy-seeded 前置表（`delivery_task≥50` + `approval_case≥200`），capability_call 改由新增 `_runtime_capability_calls` session fixture **自产真实运行时遥测**（genuine `invoke_skill("catalog.browse", {role})` × 2 角色 × 3 次 = 6 行 succeeded，真"跑过真实调用流"，非 mock；capability_call 是运行时遥测非业务实体，D11 不冲突）。② `delivery_task >= 68` baseline 比稳定态 67 多 1（off-by-one）→ module 一旦真跑必挂；修为稳健 floor 50。③ 重写 `>= 744` 硬断言为 `>= SELF_PRODUCED_CALLS`。**结果：整 module 从永久 skip → 11 passed（10 个 W0-07/W0-08 范围 skip 保留）**。
  - **B 类（精确阈值改稳健）**：阈值贴稳定态（仅 ~5 行余量或全等）→ 真实库行数自然漂移即误挂。改稳健 floor（约稳定态 70-82%，仍能区分全量真实库 vs 空/部分库）：`test_wave0_j1_discover_draft.py` catalog_entry 1222→1000（gate+baseline）、application_record 258→200（baseline）；`test_wave0_j1_approval.py` approval_case 262→200（gate+baseline）、approval_step 884→600、approval_decision 883→600。
  - **Why**：宪法 §5「靠自觉反复出现必须硬化」+ D17/D18/D22「门槛/阈值不机械对齐真值即回潮」。运行时量当 seed 门槛 = 隐式取值反模式；精确阈值 = 把"够不够真实数据"的 floor 误当"精确计数"断言。CI 本就无 `.data/zw_brain.db`（`require_real_seed` 在 `SEED_DB.exists()` 即 skip），故阈值只在本地全量真实库咬合——修正纯增本地稳健性、不改 CI 行为。
  - **How to apply**：未来写 `require_real_seed` / baseline 断言，floor 取稳定态约 75%、禁贴稳定态；**禁把运行时累积量（capability_call / audit_event 等遥测）当 seed 门槛**，需要运行时数据的测试由 fixture 自产（genuine invoke）。
- [2026-05-30] D44.a：**A 类设计错误机械硬化（宪法 §5）**。运行时累积量当 seed 门槛导致整 module 静默 skip 数周、无任何机械守卫抓到 → 新增 `scripts/check_require_real_seed_sanity.py` + preflight **段 57**：AST 扫 `tests/` 所有 `require_real_seed(...)`，禁 gate 运行时累积表（DENYLIST：`capability_call` / `audit_event` / `anchor_outbox` / `audit_receipt`）。正向 OK、负向（dict + tuple 两形式）精确 FAIL。B 类（阈值贴稳定态）需稳定计数 oracle、难机械化，留 prose（本节 How to apply）。**Why**：D17/D18/D22「软规则配套机械检查」——A 类不机械化必回潮。**How to apply**：需要运行时数据的测试由 fixture 自产（genuine invoke 经真实 pipeline 落库，参见 `_runtime_capability_calls`）；确有合法 gate 场景才按 `(file, table)` 加 ALLOWLIST 并在 PR 说明。
- **外部协议词汇审视（D33.d）**：新增标识符 `_runtime_capability_calls` / `SELF_PRODUCED_CALLS` / `check_require_real_seed_sanity` 均 zw-brain 测试/preflight 内部，与 AgentRuntime / MCP / A2A / ANP 协议无同名异义。

### [2026-05-30] D45：全局数据缺位修复 — J1 列表字段全量真实库投影（关 D43.c(1)）

闭合 **D43.c(1)**（"全局数据缺位 → 另起 PR"，地图 `docs/decisions/global-data-gap-audit.md`）。`system.snapshot` =
seed 静态精选 + 既有 3 enrich（provider/zones/disputes），**J1 核心列表字段没 enrich** → 页面只显示 5-12 条 demo。
本次 God's-eye 穿透代码事实，把审计的 5 项**收敛为 3 项 alive**（其余 #171/F9 后已是死消费者）。

- [2026-05-30] D45：**3 个 alive 列表字段 enrich 全量真实库（DB 有行替换 / 空库保留 seed）**。新增 `zw_brain/domain/discovery_snapshot_projection.py`：`enrich_requests_snapshot` / `enrich_approvals_snapshot` / `enrich_discovery_resources_snapshot`，接线 `system_ops.py` snapshot handler（既有 3 enrich 之后）+ `data.search` 空 query 改查 DB 资源（复用 `project_resource_cards`）。**轻量 serializer**（只产页面列表真读字段，snake→camel，applicant 走 mask_default 脱敏）——禁用 `application_service.record_to_request` 重序列化器（per-record resource/delivery/legacy 查找，数百条炸 D-9 perf 预算；详情页仍用它）。本地全量真实库实测：requests=97 / approvals=267 / discovery.resources=186。
  - **requests = 申请类，排除需求类**：`application_record.payload_json.kind` ∈ {`require`,`original_require`}（166 条需求、无 resource_name、属 J2 供需线）排除；申请类（`apply`/`None`，97 条）进 P3「在途申请」。**纠正审计"263"naive 计数**（含 166 需求）。
  - **discovery.resources = resource_asset（资源中心，架构 §5.2.1）**：P2Discovery 是 J1 找数主入口、渲染「可复用资源」ResourceCard；P2CatalogBrowse（#171）已独占目录浏览→钻取路径。两页各司一职——不让 P2Discovery 复造目录浏览。诚实展示真实库各 lifecycle 态（revoked→已下线 等），不在发现层过滤。
  - **merge = replace-when-DB-nonempty-else-keep-seed**：CI 无 `.data/zw_brain.db`，但 `DatabaseStore.initialize()` 给 fresh DB 注入 5/5/12 参考行 → enrich 替换为同源 5/5/12，**CI 快照不变、既有测试照绿**（实测全量 CI-mirror 套件仅 known-flaky perf 失败）。
  - **死字段不做（Jobs 聚焦 / D11 不为伪需求建复杂度）**：`topic_packages`（P7 已走 live `topic.package.query`，F9）/ `provider.catalogs`（仅 P5 fallback，已被 DB `field_decisions` 取代）/ `discovery.catalogTree`·`recallDictionary`（零消费者）—— enrich 它们=为无人建复杂度。
- [2026-05-30] D45.a：**follow-up（不在本 PR）**：`data.search` **typed** query 返回 `catalog_entry`（目录）而非 resource——与 P2Discovery 资源中心语义的**预存**不一致（非本 PR 引入）；属搜索语义重构，trigger=业务确认 P2Discovery 搜索应搜资源。记 `docs/preflight-debt.md`。
- [2026-05-30] D45.b：**发现页默认只展示「可用」资源（产品裁决，反转 D45「不在发现层过滤」）**。本地验收暴露：全量 186 真实资源里 113 是草稿/审核中/已暂停/已下线/已过期（非「可复用」语义），默认全展示噪声大。产品负责人裁决：发现页默认只展示 `active`（可复用）+ `approved_pending_publish`（待发布）= 75 条；其余态详情/目录线仍可达、但不进默认「找可复用数据」视图。落 `project_resource_cards` 的 `_DISCOVERABLE_STATUSES` 过滤（同源覆盖 snapshot enrich + data.search 空 query）。**注**：属展示层产品裁决，非 D28 角色/流程/状态机类，不需业务 GATE。
- [2026-05-30] D45.c：**资源卡片信息密度优化（Jobs，本地验收触发）**。全量真实库暴露旧卡片过空（单列满宽 + `desc` 82% 是空/「无」/标题复读噪声）。优化：① `.card-grid` 改响应式多列（`minmax(300px,1fr)`，1440px≈4 列）；② `ResourceCard` 增物化形态徽标（`resource_kind`→库表/文件/接口/服务/文件夹/链接）+「更新 {date}」+ **共享类型色级 chip**；③ 后端 `_asset_to_resource_card` 清洗 desc 噪声（空/「无」/== 标题 → 不渲染）。卡片信息密度从「名+空 desc+按钮」升为「类型徽标+名+状态+**共享类型**+责任方+更新日」，4× 列密度。
  - **共享类型决策信号（access_policy_json.share_type → 中文色级 chip）**：找数页买方第一问是「能不能拿、要不要审批」→ 无条件共享(绿)/有条件共享(琥珀)/不予共享(红)。**映射权威 = 源表 `dc_resource_base_info` DDL 注释「1：无条件 2：有条件 3：不予」+ 真实数据双重确认**（人口信息=2=有条件 / 学校名单=1=无条件；本地实测 无条件49+有条件26=75）。⚠️ **纠错陷阱**：`approval_flow_baseline.py` 的 `SHARED_TYPE` 常量是反的（1=有条件），那是审批流另一码空间——禁止用于资源卡（用了会把有条件标成无条件=合规风险）。
  - **更新周期延后（不在本批）**：`qos_policy_json.update_cycle`（码 1-7）源表注释「见附录4更新周期」——**代码库无权威 code→中文映射，附录4 未在仓**。守 D11 不猜测，暂不展示；记 `docs/preflight-debt.md`，待业务给附录4 标准后加。
- **读路径守卫（段 32）**：三 repo 列表方法（`list_records`/`list_cases`/`list_assets`）均已带 full-scan-ok 豁免注释（<2k 演示规模），无新违规。
- **外部协议词汇审视（D33.d）**：新增标识符 `enrich_{requests,approvals,discovery_resources}_snapshot` / `project_resource_cards` 均 zw-brain 内部，与 AgentRuntime / MCP / A2A / ANP 协议无同名异义。
- [2026-05-30] D45.d：**效果验收通过（D37）**。scope `j1-data-gap` 走 D37 验收：机器证据 `.testing/acceptance/j1-data-gap/evidence.json`（投影零漂移 / pytest exit 0，干净全量真实库 / e2e `j1_data_gap` 3 passed）+ 业务方本地全集真实库逐页走查全部通过（在途申请/待我审批全量 + 发现页 75 可用 + 共享类型色 chip）。载体 = PR #173 label `business-signoff: j1-data-gap`；plan.yaml e1 F4 `[SIGNOFF-CLOSED 2026-05-30] covers j1-data-gap`。材料 `docs/acceptance/j1-data-gap-acceptance-package.md`。
