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
- 已退役资产禁回潮：旧 R1-R8 角色矩阵（→7 角色码）、K12 可视化大屏、alembic（D23/D29/D15，段 20 + role/feature 守卫）
- `require_real_seed` 门槛禁用运行时累积表（capability_call/audit_event/anchor_outbox/audit_receipt）当 seed 门槛；floor 取稳定态~75%（D44，段 57）
- 业务数据禁 Mock，一律真实库回归（D11）
- 业务 sign-off（角色/流程/状态机类）走 D35 模板 + 段 53/54；效果验收走 D37 模板 + 段 55；落盘单源 = `.testing/signoff/<scope>.signoff.yaml` 账本（D46.b；PR 合并时 label `signoff:<scope>` + body 机读块自动落账 D46.d），status 由账本现算（不再 plan.yaml `[SIGNOFF-CLOSED]` 三处副本对账）
- GATE 元规则（D28/D33.d）：角色/流程/状态机决策须业务方 sign-off 才进 D-编号；每条 D 须审视与外部协议（AgentRuntime/MCP/A2A/ANP/推理 SDK）的命名冲突

### 早期双引擎与规则基建（2026-04）

- [04-15] 采用 Cursor Long-running Agent + Claude Code Headless 双引擎；规则单一事实源放独立仓库 dev-rules（sync.sh 分发）；流程加原型设计 + 两审批门禁
- [04-16] 软规则配套机械检查脚本，git pre-commit hook 自动触发，禁"靠自觉"
- [04-17] `~/.claude/CLAUDE.md` 收编进 dev-rules/global，sync.sh symlink + LaunchAgent 每小时 pull
- [04-28] 决策：dev-rules 方案 A——不接子模块、CI 不克隆，本机可选 symlink；通用 preflight 检查迁入 `scripts/`

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
