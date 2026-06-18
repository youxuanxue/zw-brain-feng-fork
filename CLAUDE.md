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

> 本段为 **D-编号索引**。每条 = 日期 + scope + 一句裁决（+ 被全仓引用的子决策锚点如 `D46.g` 的速记，仅保锚点不展开）+ 全文指针；完整 Why/How **不在此展开**，权威副本见 `docs/approved/zw-brain-architecture.md`（设计基线，含 §十四 D21+）及 `docs/decisions/*`、`docs/acceptance/*`、`docs/reconstructs/*`。**新增/修订 D 条目须遵此格式——prose essay 不进索引**（CLAUDE.md 每会话整份入上下文，膨胀=持续烧 token；2026-06-03 据此把 D46–D49 essay 收口回锚点速记）。**此规则已硬化：preflight 段 68 `check_d_index_entry_size.py` 机械守卫每条 D-条目 ≤900 字符，超长即 FAIL**（不靠自觉）。

### 现行硬约束速查（per-session，均已 preflight 机械化）

- 所有模型服务调用（LLM/Embedding/ASR/Rerank/OCR）只走集团推理平台；连接变量只读 `ZW_BRAIN_INFERENCE_*`，禁 `INSPUR_INFERENCE_*` / `AUTH_TOKEN` / 裸 `BASE_URL`/`MODEL` 兜底（D6/D36，段 10/56）
- `zw_brain/` 内禁新增含 `skill` 的标识符——能力本体统一叫 capability；白名单 API surface 除外（D33，段 22 + check_no_skill_identifier）
- 写库 token（add/commit/merge/delete/裸 SQL DML）仅允许在 `zw_brain/adapters/legacy/`，其余皆禁（§9.5，段 25）
- UI 文本禁工程术语（R12，段 24）
- 已退役资产禁回潮：旧 R1-R8 角色矩阵（→7 角色码）、K12 可视化大屏（D23/D29/D15，段 20 + role/feature 守卫）；**alembic 已于 D58 回归**（反转 D23 删除决策，段 20 anti-alembic 正则已移除）
- `require_real_seed` 门槛禁用运行时累积表（capability_call/audit_event/anchor_outbox/audit_receipt）当 seed 门槛；floor 取稳定态~75%（D44，段 57）
- 业务数据禁 Mock，一律真实库回归（D11）
- 业务 sign-off（角色/流程/状态机类）走 D35 模板 + 段 53/54；效果验收走 D37 模板 + 段 55；落盘单源 = `.testing/signoff/<scope>.signoff.yaml` 账本（D46.b；PR 合并时 label `signoff:<scope>` + body 机读块自动落账 D46.d），status 由账本现算（不再 plan.yaml `[SIGNOFF-CLOSED]` 三处副本对账）
- GATE 元规则（D28/D33.d）：角色/流程/状态机决策须业务方 sign-off 才进 D-编号；每条 D 须审视与外部协议（AgentRuntime/MCP/A2A/ANP/推理 SDK）的命名冲突

### 早期双引擎与规则基建（2026-04）

- [04-15] 采用 Cursor Long-running Agent + Claude Code Headless 双引擎；规则单一事实源放独立仓库 dev-rules（sync.sh 分发）；流程加原型设计 + 两审批门禁
- [04-16] 软规则配套机械检查脚本，git pre-commit hook 自动触发，禁"靠自觉"
- [04-17] `~/.claude/CLAUDE.md` 收编进 dev-rules/global，sync.sh symlink + LaunchAgent 每小时 pull
- [04-28] 决策：dev-rules 方案 A——不接子模块、CI 不克隆，本机可选 symlink；通用 preflight 检查迁入 `scripts/`

### AI 原生研发工作原则（2026-06，非-D 方法论；全文见各自 memory 柜条目）

- [06-13] **可机械化边界**：确定性自动化只在可机械化（计数/解析/查表/状态派生）内最大化；不可化约的语义判断（doc 漂移类——approved 说"不实施"其实已实施、签字指针对错）留 GATE 评审节奏，硬造守卫=天天误报负债（dev-rules §77 过度机械化反模式）。提守卫前先指名"哪一步可机械化、由什么脚本承载"，指不出就不建、降评审清单项。承此：squash + 集成工作流 = AI 原生并行 agent 开发的正典落地（可机械化的并行汇聚自动化、main 历史压成一语义一行可读账本）。
- [06-13] **测量假象**：聚合数字（死引用数/覆盖率/计数）在精确测量前常是测量假象，禁据此决策或建守卫——审计报"47 个 doc 死引用"精确正则 + 诚实标注识别后真漂移=0（`.feature` 正则截断、`--out` 生成目标路径、已诚实标注"不存在"的 prose 被误计）；"40/57 D-编号未被 approved 引用"实为流程/元决策本就不属 approved。看到"N 个问题/N% 覆盖"先问 N 怎么数出来的、正则会不会截断或误匹配。

### GATE-1 设计基线（2026-04-18，D1–D22）

- D1：产品形态 = 精简 WebUI（≤10 场景页）+ 嵌入式 NL 加速器 + 核心 Agent + 可注册能力，不复刻旧菜单形态、不做裸对话框
- D2：5 消费面（WebUI/REST/CLI/MCP/A2A）共享同一套契约，单脚本生成
- D3：能力扩展唯一路径 = 能力注册，禁在 Agent/编排层内嵌业务逻辑
- D4：审计总线强制同步落库（写失败熔断）；区块链锚定走可插拔 adapter 异步
- D5：区块链轻量 adapter，先骨架后详设
- D6：模型调用收口集团推理平台，禁直连第三方 LLM（段 10）
- D7：Agent-Native 数据模型 + Adapter 层，旧数据单向同步进入，不复造旧 schema
- D8：UI 仅保留 §7.3 ≤10 场景页
- D9：共享专区从砍掉清单移出，升级 K11 必保留
- D10：5 低价值功能默认不重构，重激活前走 product-dev 流程（后由 D31 部分兑现）
- D11：所有能力以旧平台真实业务数据（脱敏）回归，禁 Mock
- D12：与数据治理/区块链/国家平台/推理平台保持外部依赖，不复造
- D13：外部 Agent/能力接入是合法扩展路径（A2A + 注册），协议待业务侧同步
- D14：推理平台 SDK 形态待同步，Phase 0 先 mock `shared/inference/client.py`；**[已兑现] client.py 默认 platform 模式真连集团网关（HTTP→`ZW_BRAIN_INFERENCE_GATEWAY_URL`，mock 仅 `ZW_BRAIN_INFERENCE_MODE=mock` 开发档），见 infra-inference-gateway(Done) / D36 env 收口**
- D15：原"不做大屏"反转为 K12 必保留；**[05-20] 二次反转：K12 大屏本期退役**（删 dashboard 全套 + 段 11）
- D16：数据模型章加 URN 小白解释，新文档首次出现 URN 须回链 §4.4.2
- D17：散文档数值漂移用 stat 块包裹，注册 `scripts/.stats.json`，sync-stats --check 校验
- D18：fixture 覆盖 + doc-xref 守卫治"上游补实体/下游缺位"与"幽灵编号/行号硬编码"
- D19：技术选型（Web 框架/编排引擎）从设计基线剔除，延后 Phase 0 PoC；GATE-1 只 freeze 哲学/架构/数据模型/契约
- D20：数字漂移 stat 命名修订，只 wrap prose 中真有硬数字的 stat，反对"为 stat 而 stat"
- D21：设计文档须配可运行原型 + 机械反向防御（段 13）；**[04-28] 退役可点击 SPA 原型**，界面验证以正式 WebUI 为准
- D22：仓外 SoT 文件 + 锚点须可解析，架构文档附录 D 为自包含软→硬映射（段 14）；禁 `|| true` 静默吞错作主路径
- [04-18] 后续：history rewrite 清除 3 个 .gitignore 文件（30→26 commits，备份在 ~/Backups）
- [05-18] 退役 `prototype/` 目录，`.experiences/` 成角色级体验权威源
- [05-22] GATE-2 后追加 fixture 覆盖 / doc-xref 守卫

### GATE-1.1 产品定义重置（2026-05-19，D23–D29）

- D23：旧 R1-R8 角色矩阵退役 → 采用旧平台 7 角色码 + 标签位 `tag_lead_dept`；**[05-20] 二次升级：alembic 整体删除**（全新项目不背历史兼容，drop&recreate）+ policy 启动检查 + grep 双兜底
- D24：信息架构收敛 3 旅程（J1 找数→用数 / J2 挂数→维数 / J3 看全局→处异常）；**[05-20] 二次反转：J3 退为后台 B1，3→2 旅程 + B1，pending 业务方二次 sign-off**（后由 D39 闭合）
- D25：审批流可配置化承诺，下期立项流程引擎，本期不做
- D26：表单 schema 化承诺，下期立项表单引擎，本期不做
- D27：21 条业务反馈处置摘要，本期落地 16 条、延后 5 条
- D28：GATE 元规则升级——角色/流程/状态机决策须业务方 sign-off 才进 D-编号
- D29：R 编号空间区分——D-编号属 GATE 决策；§11 架构约束 R1-R15 保留；用户角色 R1-R8 完全退役（grep=0）

### Retrofit 批次（2026-05-24 起）

- D30 [05-24]：AgentRuntime 触发式落地（撤回 Wave 1 sign-off）+ R12 UI 术语段 24 + §9.5 adapter 写禁区段 25 + R14 三引擎契约字段 + 死引用清理 + 附录 C 4 条 trigger 化
- D31 [05-27]：业务方 PR #129 sign-off，24 条不复刻清单复活（A 类 20 + D 类 4），D10 retrofit 兑现；106 案例提出页保持不复活（D31.a）；复活须走 R8 反 fork + R14 三引擎（D31.c）
- D32 [05-27]：A/D 类复活归属 = 既存 reconstruction plan 接管（dsp-dataservice + dsp-sharezone-topic-package），散落 Wave 0/1/2/3 + 外部能力包；补 `check_approved_doc_drift.py`（D32.d）
- D33 [05-28]：zw-brain 内部 "skill" 整体退役 → 统一 "capability"（目录/类/manifest rename）；保留 `invoke_skill()` + envelope `skill_id` 作 API surface；`trust_level` 完整 rename 撤回延后（D33.a）；防回潮段 + check_no_skill_identifier（D33.c）；GATE 须审视外部协议词汇边界（D33.d）
- D34 [05-29] **e3.F9**：F9 P7 共享专区/TopicPackage 启动 sign-off（业务方全采纳）；专区=运营方策展容器≠主题分类（D34.a）；`topic.package.policy.update` 默认双签（D34.b）；seed 上游 sequencing，Z1 先行、Z2/Z3 待 catalog 补种（D34.c）；残疾人两项补贴排除（D34.d）
- D35 [05-29]：sign-off 模式升级——统一模板 `docs/templates/business-signoff-package.md` + 段 53 检测层 + 段 54 落盘层
- D36 [05-29]：推理网关 env 契约收敛 `INSPUR_INFERENCE_*` → `ZW_BRAIN_INFERENCE_*` + 删一切兜底；`_API_KEY_REF`(指针)/`_API_KEY`(字面)严格区分（D36.a）；负向测试守卫（D36.b/c）；`INSPUR` 网关 host 标识保留是 deliberate（D36.c）；段 56 仓库级回潮守卫（D36.e）
- D37 [05-29]：效果验收签字守卫——证据锚在 `.testing/acceptance/<scope>/evidence.json` 产物 + 段 55；与决策签字共用段 54 落盘（D46.b 后收敛为 `.testing/signoff/` 账本单源）
- D38 [05-29] **e5**：e5 WebUI / 5 消费面投影效果验收通过（D37 守卫首验）；证据 provenance 受限记 debt（D38.a）
- D39 [05-29] **ia-2journey-b1**：信息架构定型 = 2 旅程（J1/J2）+ B1 后台；J3 退役、K12 退役；闭合 D24 pending 二次 sign-off
- D40 [05-29] **aclass-dataservice**：A 类 20 条复活 = 数据服务能力面，按 dsp-dataservice plan 落地（不复刻旧 BSP/门户）；106 案例页保持不复活
- D41 [05-29] **b1-borderline-reports**：5 条 borderline B1 报表 capability 定性 = 业务运营报表，留 live（非运维监控）；关 2026-05-23 债
- D42 [05-30] **e3.F9**：F9 P7 共享专区/专题包效果验收通过；订阅降级为诚实信号 isSubscribed（概念 B 待立项，D42.a）；F9 引用目录主表不可达→诚实展示 + 下个 PR 打通（D42.b）
- D43 [05-30] **j1-catalog-drilldown**：J1 目录→资源钻取链路（`catalog.resource.list` + 目录详情页），兑现 D42.b；目录浏览页信息增强（D43.a）；5 医保目录录入主表（D43.b）；全局数据缺位 + 脆测试另起 PR（D43.c）
- D44 [05-30]：真数据 baseline 脆测试批量修，兑现 D43.c(2)；段 57 禁运行时累积量当 seed 门槛（D44.a）
- D45 [05-30] **j1-data-gap**：J1 列表字段（requests/approvals/discovery.resources）enrich 全量真实库，兑现 D43.c(1)；发现页默认只展示可用资源（D45.b）；资源卡片信息密度 + 共享类型色 chip（D45.c）；效果验收通过（D45.d）
- D46 [05-30] **feature-status-as-function**（架构门，产品研发负责人 sign-off）：feature status 不存储，由 SPEC(.feature)+MEASUREMENT+SIGN-OFF 现算（feature_status_lib.py；段60 测量新鲜 /61 生成--check /62 禁手写）；Done=绿∧签字，计数实时现算见 .testing/status/feature-status.md。子决策：D46.a plan.yaml status 留 supervisor 执行态、不入函数；D46.b SIGN-OFF 独立账本 .testing/signoff/ 单源（段63 守卫 + 段54 收敛）；D46.c SPEC 是进飞轮唯一入口、无 .feature 不进状态；D46.d PR 合并自动落账（label `signoff:<scope>` + body 机读块 → signoff_from_pr.py）；D46.e .twin/ 整体退役（段38 收敛 SPEC↔test 双边）；D46.f 测量轴 test-runner 无关化（green() 纳入 e2e、capture --with-e2e 实跑 Playwright）；D46.g 测量信任锚 git_sha→内容指纹 feature_fingerprint=sha256(.feature+引用测试文件)（段60「绿但指纹陈旧→FAIL」、squash 免疫）。全文 docs/decisions/feature-status-as-function-architecture.md（+ test-sufficiency-convergence.md）。
- D47 [06-02] **c1-demo-removal-credential-honesty**（C-1 余下，产品研发负责人 sign-off）：删演示单（seed_snapshot.json 清空捏造演示记录、一切围绕真实导入；读路径单源 #191；段36 零 allow-list）+ 凭据诚实化（真实授权表无 per-grant 凭据 → legacy granted 停捏造 AK-DEMO、改 credential=None/not_issued，段66；新建在产单 approve 平台自签保留）。子决策：D47.a J1 凭据取网关 SECRET 口径 + apply_id↔service↔app 绑定供数=上游缺供、记债不在本期；D47.b 历史导入单在线动作混合门控承接 `j1-legacy-record-actionability` 债；D47.c 效果验收通过（证据 .testing/acceptance/c1-demo-removal-credential-honesty/evidence.json）。全文 docs/acceptance/c1-demo-removal-credential-honesty-acceptance-package.md。
- D48 [06-03] **data-model-referential-integrity**（架构门，产品研发负责人 sign-off）：硬约束「zw-brain 永不留孤儿行——删父级联或拒绝、由系统机制强制」。17 边 FK+ON DELETE CASCADE（A12+B5 复合）+ C 类 9 边无 FK、由 preflight 段67 check_orphan_rows 枚举登记边孤儿守卫兜底。[06-03 amendment] 守卫覆盖=常量登记边集合（*_EDGES 单源、非 schema 全反射），“全边”措辞收敛“登记边”——补 catalog_item/delivery_subscription.resource_code 两条原裸奔软引用边（干净 seed 0 孤儿实证）；objection_case.related_application_id 无 live deref、刻意不纳入（纳入即虚构约束）。缺陷4 悬挂 ref=只读派生就绪信号（topic.package 详情路径、用户侧不可见 by design）；缺陷2(D47.a)/3 + 上游真因(subscribe_job/码列多态 D47.b) 另立项。全文 docs/decisions/data-model-referential-integrity-design.md。
- D49 [06-03] **wave-residuals-approval-depth**（流程/状态机变更，产品研发负责人 sign-off；#200 已签但漏记 D-编号，本条补登 D28 索引、不新增决策不新签）：committed 自定义 live approval schema 真驱动 J1——approval_flow_walker 走查 schema(nodes+branches+rules)→有序 ApprovalStep，request.py 优先 find_live_for_scope(项目级) 否则回落 baseline（baseline 零改动、golden 钉死）；本期 deliberately 串行（always→串行多级 / on_decision→happy-path / expression→fail-closed 走 always，不做条件求值器、属镀金延后）。签字=.testing/signoff/wave-residuals-approval-depth.signoff.yaml（薛娇 2026-06-03，属 D28 状态机变更）；全文 engine-approval-flow.feature(Done) Landing-Note + .testing/acceptance/wave-residuals-approval-depth/evidence.json。
- D50 [06-04] **national-platform-access**（架构+流程/状态机门，产品研发负责人 sign-off 2026-06-04 双签）：反转 §10.4「国家通道本期不实施」，立项启用 national-direct + national-ext-elements 两子旅程，锚定真实协议（数据直达 v0.55：地方端调国家端 查询/上报/消息同步；HMAC-SHA256 签名报文 + 小写 JSON）+ 真实库 dc_*/data_ext_elem_catalog_compile_task。两道正交门：清单门 国家出站收口 escalate(j1)/compile(j2) handler 经 gate+client（compile 转 live + 新建 application.escalate_national builtin live；10×adapter.national.* 保持 deferred、不改禁区保段22；standalone external-bridge 注册=future 避 external_capability 误配，C8 回退 C4）+ 运行门 resolve_national_channel_state 三态（env 注入凭据、flag 默认 off、未配置即诚实 pending 非 404）。凭据 not_issued 不捏造（承 D47）；扩展要素编制态独立 data_catalog 主线；协议桩≠业务 mock（承 D11，外部基建 §3.4）。默认 off → 未签未配租户「本期不实施」仍成立。签字 .testing/signoff/national-platform-access.signoff.yaml（双签 covers 两 feature → Done；负责人 2026-06-04 真 UI 走查）；全文 docs/decisions/national-platform-access-D50.md。
- D51 [06-04] **iam-identity-claim**（流程/状态机变更，负责人 2026-06-04 sign-off，属 D28）：修复"存量用户首登产生两套用户数据"——登录/重导入统一走 `claim_legacy_actor_by_iaf`：sub 优先；辅助字段(account/phone/email)唯一命中 status∈{iam_account_missing,unmatched} 存量行即就地 rekey 到真 sub（同 PK、保 legacy profile、同事务搬 binding+object_mapping），消除双行；多命中 fail-closed（ActorMatchError→403 actor_identity_ambiguous）；不认领 disabled 行（不继承角色）；登录只在认领时一次性搬 binding、绝不新写/禁用（守 wave-0 D-2 deferral）；死代码 `bind_actor_to_iaf_claims` 收口为薄壳委托。存量脏数据 `scripts/repair_actor_identity_duplicates.py`（dry-run→apply→幂等）清 + runbook `docs/deployment/m0-site-migration.md`。签字 .testing/signoff/iam-identity-claim.signoff.yaml（decision_only；infra-iam-session.feature 仍 Done）；测试 test_iam_identity_claim.py + test_repair_actor_identity_duplicates.py。
- D52 [06-05] **integration-admin-governance-axis**（IA + 角色可见性确认，D28 GATE；产品研发负责人 2026-06-05 sign-off；含 #214 来源叙事 A 的补登 ratify + #216 三轮重做）：「接入扩展中心」容器解体 → 后台四模块各自独立左导航（查审计/外部系统/流程表单/身份治理；全角色页面数压线 ≤10，守 D1/D8）。子决策：D52.a 一词一概念——「外部系统」=治理对象（导航/页头/表头/详情同词），「外部接入」只作来源叙事形容词；D52.b 身份治理独立导航（撤回第一轮"融入第三 tab"）；D52.c 外部系统页瘦身=只留可操作（砍能力总览/契约逐条清单/账目行/空版本列/永久灰回滚；操作 v-if 仅渲染当前可执行项；exposure-matrix 查询退役）；D52.d 去工程黑话（三引擎→流程表单、Wave2/生 slug/跨省样例清除，R12 段24 兜底）；D52.e Q3 价值切面分类方向认可但缓行（无 owner 分类法会腐烂，待"平台能力地图"owner+场景立项）。签字 .testing/signoff/integration-admin-governance-axis.signoff.yaml（decision_only）；全文 docs/decisions/integration-admin-governance-axis-refactor.md §六/§七。
- D53 [06-06] **feedback-0605-gate**（可见性/资源类型/角色/流程/IA 多点裁决，D28 GATE；产品研发负责人 2026-06-06 sign-off，decision_only）：0605 走查 6 项方向口径全采纳——①找数据只展示已发布 active（反转 D45.b，待发布退出发现+未发布不可申请）②资源类型只支持库表/文件/API（剔文件夹/链接，folder→file、退役 url 分型，补登 §11）③API服务化重写为代理服务注册向导（用户输原始接口地址接 resource.api.register，纳入 dsp-dataservice plan）④供数 IA 取方案 a 页内重排（编目/挂接/发布升首屏、供需对接/异议降次，不动 D39 守 ≤10；方案 b 拒；负责人加注：酌情呈现供数侧目录/资源管理）⑤业务运营员待办改发布类（待发布目录/资源+待受理申请/异议+待汇总需求，去错配审核类）⑥交付回执角色收窄到部门管理员。实现由修复任务清单承接（old/问题反馈/问题反馈-0605/修复任务目标清单.md），落地后各带 D37 验收。签字 .testing/signoff/feedback-0605-gate.signoff.yaml；全文 docs/decisions/feedback-0605-gate-signoff-business-review-package.md。
- D54 [06-08] **feedback-0605-acceptance-gate**（角色/权限口径 + 一词一概念，D28 GATE；产品研发负责人 2026-06-08 sign-off，decision_only）：0605 验收回合两道 GATE——GATE-1 代理服务注册角色口径纠正：注册（resource.api.register/submit_review）= 部门操作员+部门管理员（业务运营员退出注册）、审核发布（review/publish/withdraw）= 部门管理员，纠正 policy.py:112 把注册权错配业务运营员/漏部门操作员的口径错（旧平台角色菜单 v5：服务注册=部门操作员/管理员、融合服务受理=业务运营员）；GATE-2 命名：采纳「反向编目审核」与正向编目「目录审核」并存区分、守一词一概念（拒撞名）。承 D53（补其下注册/审核角色必签项）+ D52.a。实现由 T6/T7/T8、G1 承接（修复任务目标清单-验收回合.md §三/§四），落地后各带 D37 验收。签字 .testing/signoff/feedback-0605-acceptance-gate.signoff.yaml；全文 docs/decisions/feedback-0605-acceptance-gate-D54.md。
- D55 [06-09] **permission-realignment-0609**（角色/权限/状态机多点裁决，D28 GATE；产品研发负责人 2026-06-09 两轮 sign-off，decision_only）：业务方权限专项梳理（重构平台权限梳理-0609.docx，6 角色×越界/缺失/细化 21 条 + 上帝视角角色身份补漏）逐项裁——①退本期：专题包整面下线（消解 ⊥D34 创建下放争议）+ 安全管理员角色退役（数据安全中心未立项，记债待恢复）；②反转 D53/F1：领数据回归部门操作员+部门管理员（v5 资源订阅口径）；③业务运营员保留受理(初级审核)、退申请人身份（docx「处理别人申请≠提申请」，与决策A兼容）；④受理/审核两级(改 D49 关联)：无条件=业务运营员受理即终、有条件=受理→部门管理员审核（与现状角色/顺序对调）；⑤流程表单配置归平台运维员(反转 D49 配置角色：管理员项目级→运维员平台级；recommendation.similar_catalog.suggest 消费侧不迁)；⑥A 档照 v5 校正(业务运营员退供数维护/外部系统/身份治理、管理员+运维员退审计日志保服务调用监控、安全审计员退找数据/领数据、操作员补反向编目)；⑦安全审计员收敛纯只读(docx「无任何写操作权限」，清异议/合规/工单/谱系/熔断写权、工单巡检归运维员)。承 D54/D52/D34/j1-credential-revoke 决策A。签字 .testing/signoff/permission-realignment-0609.signoff.yaml；全文 docs/decisions/permission-realignment-0609-D55.md。
- D56 [06-11] **action-d-write-path-single-source**（架构门，产品研发负责人 sign-off）：申请/审批/交付三聚合唯一事实源收口 DB，内存快照 requests/approvals/delivery_tasks 三键退役——CardSession per-dispatch 卡片会话（identity map+指纹脏检，PersistMiddleware flush 直落三表；运行时/导入判别=payload 无 kind）（D56.a）；REQ-* 序列退役→新铸 uuid4().hex 与导入单同形（D56.b）；凭据 secret 永不落库——DB 只存签发事实、按 (request_id,seed) 读时确定性重导出，承 D47（D56.c）；投影写者不毁条件引擎审步（修 SPEC Scenario 4 潜伏违约）（D56.d）；退役回写过渡件/镜像循环/演示链拼接，存量 snapshot_json 加载剥离（D56.e）。流程/状态机语义零变更（D55/D49/方案B 原样）。债 j1-runtime-write-path-dual-track 收账。全文 docs/decisions/action-d-write-path-single-source-D56.md。
- D57 [06-12] **feedback-0611-gate**（角色/流程/状态机/IA 多点裁决，D28 GATE；产品研发负责人 sign-off，decision_only）：0611 核查 9 项逐裁——①业务运营员「待受理异议」不删、补受理面（接通 objection.case.accept，拒 6.9#3 删待办）；②操作员工作台维持申请进度、拒协作待办（0609 docx 明文），seed 虚构「办理建议」清理(R8)；③管理员领数据驳回 6.10#8、维持 D55②；④管理员申请人身份照 v5 保留，前端 pageAccess 补回 MANAGER 发起入口（收口前后端劈叉）；⑤目录发布权回收仅 BUSIAUDIT（R-001 保留无签字且「仅自家目录」未实现，严格 v5）；⑥管理员+安全审计员退全局服务调用监控（自家资源调用留 P4Credential 凭据门内）；⑦业务运营员保留查审计、驳回 6.10#13（D57.a：docx 0609 措辞 > v5 0519 行，新近业务输入优先）；⑧反向编目审核改两级管线（管理员部门审→运营员平台审，替换仅 BUSIAUDIT 一级，拒下放操作员；同级展示升供数首屏主卡）——唯一改已签口径项，状态机变更；⑨挂接审核角色错位按 v5 关闭（现状正确），管理员收件箱盲批补详情+驳回(R10)。签字 .testing/signoff/feedback-0611-gate.signoff.yaml；全文 docs/decisions/feedback-0611-gate-D57.md。
- D58 [06-14] **alembic-migration-reintroduction**（架构+数据安全门，反转 D23 二次升级；产品研发负责人 sign-off 待签）：alembic forward-migration 回归取代冷启动 `drop_all+create_all`——`ensure_runtime_schema()` 四态分支（空库→upgrade head 建全 75 表 / 已纳管→upgrade head 续迁 / 存量库[有数据·无版本表·schema 一致]→stamp baseline 零 DDL 保数据后 upgrade head / 真漂移→raise SchemaDriftError 拒启），**绝不再 DROP**。reset_and_upgrade() 闸在 ZW_BRAIN_ALLOW_SCHEMA_RESET=1 后（M5 fail-closed 仿 DevBypassInProductionError；迁移批 --reset-db 唯一合法显式重置入口）。alembic>=1.13 入运行时依赖、工件 force-include 到 zw_brain/_migrations/（开发态/wheel/迁移批三态可定位）；段 20 anti-alembic 正则移除、/alembic/ 加扫描豁免（K12 大屏退役守卫不动）。签字 .testing/signoff/alembic-migration-reintroduction.signoff.yaml（decision_only）；全文 docs/decisions/alembic-migration-reintroduction-D58.md。
- D59 [06-15] **b11-dispute-fold**（IA 重定位，D28 GATE；产品研发负责人 2026-06-15 sign-off，decision_only）：删 B1.1 异议详情(B11DisputeDetail) 零入口孤儿页（全站无 link/push/href 指向、仅 router import+route+route-table 三处引用），唯一独占动作「升级督办」(objection.case.escalate，事件式不改 status) 归位 P5ObjectionDetail 异议处理方面（角色门 ROLE_ORGAN_MANAGER/BUSIAUDIT 与原 B11/policy.py escalate 门一致）；close 已 P3ObjectionDetail 双消费不动；后端 handler/policy/状态机/能力零改动。签字理由=纯 IA/可见性重定位，**非撞 D57**——经重审证伪原 keynote 三条理由（grep 督办/escalate 于 D57 全文=0、escalate handler 自写「不改 status」、督办与处理角色完全重合无职责分离）。签字 .testing/signoff/b11-dispute-fold.signoff.yaml（decision_only）；全文 docs/decisions/b11-dispute-fold-D59.md。
- D60 [06-15] **narrative-positioning-downgrade**（对外叙事定位，D28 GATE；产品研发负责人 2026-06-15 sign-off，decision_only）：对外产品身份"数据共享网关"（管道工口吻、仅 architecture.md×2+AGENT.yaml 内部命中、零 webui/用户面）→ 改"数据共享平台"，并在架构基线 §1.1 顶部补客户面体验承诺一句话「要数据，不用再跑窗口、不用再问我是哪个角色、拿到就能调用」（平台=内部品类口径，用户感知=体验承诺）；飞轮 §7.1 倍速 4×/16×/48× 除 N0 baseline 实测外全为预估/目标，0 客户期降为内部规划锚点 + 加「样本量=0、未验证」警示、禁作对外卖点/产品心跳。AGENT.yaml 搜索助手口径同步对齐功能面。纯文档、对运行产品零行为影响。签字 .testing/signoff/narrative-positioning-downgrade.signoff.yaml（decision_only）；全文 docs/decisions/narrative-positioning-downgrade-D60.md。
- D61 [06-16] **dept-data-isolation**（角色/可见性变更，D28 GATE；产品研发负责人 2026-06-16 四问裁决+计划审批，decision_only）：根因＝所有读路径只按 tenant_id+角色 redaction 过滤、从不按调用者部门过滤行（记录皆带 owner_org_id/applicant_org、会话已带 org_code、system_ops 装快照没读），致不同部门用户看到资源/目录/申请全同。四裁决——①发现面/找数据永久全局（承 D60/D53① 不动）；②部门管理员见本机构+下级、本期落本机构（parent_org_code 实测全空，解析器+list_org_children 子树递归就绪、待 pub_organ_tree.PARENT_CODE 导入零改动展开，记债 dept-isolation-subordinate-org）；③我的申请按个人（mine=payload.applicant==登录人）；④全局角色（业务运营员/运维员/审计员）保持全量、仅部门管理员/操作员收口、平台级待办不收。实现复用 D57⑥ ops_service scope 范式＝ReferenceService.visible_org_codes 三态(None全局/集本机构+下级/空集 fail-closed)+org_in_scope 名码归一，供数/申请(applicant∨provider)/审批R11/异议/工作台五面收口；删死代码 can_dept_manager_see_request；enrich 层 fail-closed 不回落 seed（xj-review R-001）。只动读可见性、写授权不动。签字 .testing/signoff/dept-data-isolation.signoff.yaml；全文 docs/decisions/dept-data-isolation-design.md；真·双账号浏览器 e2e 实证。PR #294。
- D62 [06-18] **iam-role-governance-self-build**（架构+角色/状态机门，D28 GATE；产品研发负责人 plan-mode 批准 2026-06-18，decision_only）：反转「产品角色从通用共享 IAM token 派生」——IAM 只认证、zw-brain 自拥授权事实源 actor_org_role_binding（bearer/MCP/CLI 与浏览器两门都读 binding，token 角色永不进授权，段73 check_no_token_role_authz 守卫；依据旧 BSP 实证 IAF token 无业务角色/BSP 自拥 pub_user_role 4187 边）。媲美 BSP 运营面：身份治理 3-tab（用户与角色 分派/撤销/停用 + 谁能访问什么只读矩阵 + 旧权限映射审核）+ 5 新能力 governance.actor.{list,role.assign,role.revoke,status.set}/access_matrix（全 ROLE_SYSTEM 门控+审计）。子决策：A0 修订 D51——disabled 登录 fail-closed（不复活/不新插重复行）；A1 登录不写 token 角色、binding 镜像 role_codes_json；A4 backfill_actor_bindings；D1 binding→actor C 类孤儿守卫（段67；external_actor_id rekey+SQLite 不上硬 FK，承 D48 §2.5）。say-no：角色目录 CRUD/树/APP域/菜单引擎/区划直授。签字 .testing/signoff/iam-role-governance.signoff.yaml；全文 docs/decisions/iam-role-governance-self-build-D62.md。
