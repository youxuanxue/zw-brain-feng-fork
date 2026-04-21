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

本项目规则通过 git submodule `dev-rules/`（→ `github.com/youxuanxue/dev-rules`）统一管理。

- `.cursor/rules/*.mdc` 是 sync 产物，**禁止直接编辑**
- 唯一编辑入口：`dev-rules/rules/*.mdc`
- 修改流程：编辑 `dev-rules/rules/` → `dev-rules/sync.sh --local` → 提交 submodule + `.cursor/rules/`

## 强约束门禁（机械检查，已生效）

提交时 git pre-commit hook 自动运行 `scripts/preflight.sh`，违反硬约束的 commit 会被拦截。当前激活的检查段：

- 分支命名（`master`/`main`/`prototype/`/`feature/`/`fix/`/`chore/`/`docs/`）
- dev-rules submodule SHA 在远端可达（防"父先于子"提交）
- `.cursor/rules/` 与 submodule 不漂移（`dev-rules/sync.sh --check`）
- 其余段（contract / story / approved）在缺少对应基础设施时自动 skip

修改 dev-rules 子模块前必须额外运行 `./dev-rules/verify-rules.sh`（<!-- stat:verify-rules-checks -->8<!-- /stat --> 段：frontmatter / README 双向引用 / 哲学映射覆盖 / 幽灵路径检测 / global 关键文件存在性 等）。

完整软→硬约束映射：见 `docs/approved/zw-brain-architecture.md` **附录 D**（zw-brain 自包含权威；其通用层与 `digital-clone-research.md §六.½` 同源，项目特有层在此基础上追加）。

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
- [2026-04-15] 决策：所有项目通过 git submodule 引入 dev-rules，在项目内编辑提交，sync --local 分发到 .cursor/rules/
- [2026-04-16] 决策：强约束实现层落地——每条软规则配套机械检查脚本（详见 digital-clone-research.md §六.½），git pre-commit hook 自动触发，禁止"靠自觉"
- [2026-04-17] 决策：`~/.claude/CLAUDE.md` 收编进 `dev-rules/global/CLAUDE.md`，由 `sync.sh` 维护 symlink，由 LaunchAgent 每小时 `git pull` 自动同步——消除最后一个手维护的孤儿配置文件

### [2026-04-18] GATE-1 通过：政务大脑 AI 原生重构设计基线

PR [#1](https://github.com/feng222666888/zw-brain/pull/1) merged at 2026-04-18 08:15:41Z by `feng222666888`；设计基线落盘 `docs/approved/zw-brain-architecture.md`（`status: approved`, `approved_by: xuejiao02`）。完整决策详见基线 §十四，以下为 D-编号摘要（D1–D20 为 GATE-1 通过时落定，D21/D22 为 GATE-1 后 retrofit）：

- [2026-04-18] D1：政务大脑产品形态 = 精简 WebUI（≤10 核心场景页）+ 嵌入式 NL 加速器 + N 个核心 Agent + M 个可注册 Skill，**不复刻旧平台菜单导航形态，也不做"裸对话框"入口**
- [2026-04-18] D2：4 入口（WebUI / REST / MCP / A2A）**共享同一套 Skill 契约**，由单一脚本生成，禁止 4 处手维护
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
- [2026-04-18] D22（自检中触发）：**外部引用悬空 retrofit — 仓外 SoT 文件 + 锚点必须可解析 + 引用本地化**。`digital-clone-research.md` 在 history rewrite 之后被悄悄从 working tree 删除，15 处引用悬空、`hard-constraint-rows` stat 因 `|| true` 静默吞错假绿。补：① 从备份恢复物理文件到 workspace 同级；② `scripts/check_external_refs.py` 接入 preflight 段 14（验证文件 + 锚点）；③ 架构文档新增 **附录 D**（zw-brain 自包含的软→硬约束完整映射 = 16 通用 + 8 项目特有），关键 SoT 引用切换到附录 D，外部文件降级为「上游 + 深度延伸」。元规则：`|| true` 类静默吞错只能作为已通过 `[ -f ... ]` 守卫之后的 fallback，禁止用作主路径。详见基线 §十四 D22

