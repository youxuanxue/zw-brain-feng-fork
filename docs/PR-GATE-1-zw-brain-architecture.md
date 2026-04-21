---
pr_type: prototype
pr_title: "prototype: 政务大脑（zw-brain）AI 原生重构 GATE-1（设计基线）"
branch: prototype/zw-brain-architecture
base: master
gate: GATE-1
status: awaiting_human_review_on_github
pr_url: https://github.com/feng222666888/zw-brain/pull/1
pr_number: 1
notes: PR 已通过 gh CLI 自动开（feng222666888 账号，scope=repo 权限），本文件作为 PR body 的 source of truth；后续如需更新 PR 描述，编辑本文 → `gh pr edit 1 --body-file docs/PR-GATE-1-zw-brain-architecture.md`
---

# PR-GATE-1：政务大脑（zw-brain）AI 原生重构 — 设计基线

> 本文是 GATE-1 审批的入口。审批方式：直接编辑 / 修正 `docs/approved/zw-brain-architecture.md`，merge = 审批通过。

---

## 一、本 PR 做什么 / 不做什么

| 维度 | 本 PR | 不在本 PR 范围 |
|---|---|---|
| 设计基线 | ✅ `zw-brain-research.md` → `docs/approved/zw-brain-architecture.md`，前置 YAML frontmatter（`approved_by: pending`） | — |
| 可运行原型代码 | ❌ 无（设计文档先行型 GATE-1，与 `digital-clone-research.md` 同结构） | 留 Phase 0（GATE-1 通过后第 1 周）落地 |
| 强约束脚本 | 🟡 **部分已就绪**：本 commit 通过 preflight 8 段检查并 PASS（段 1/2/3/8 全过；4/5/6/7 因下游脚本未建而 skip）。`scripts/preflight.sh` + `.git/hooks/pre-commit` 此前已装，本 PR 起草时由 hook 实跑 → PASS 后 commit 才落地 | 段 4/5/7a/7b/10/11/12 的专项检查脚本留 Phase 0 |
| `.testing/` / `adapters/` / `mcps/` 目录骨架 | ❌ 无 | 留 Phase 0 |
| 数字漂移防御层（stat 块包裹） | ❌ 无（裸写） | 留 GATE-1 PR 落脚本时统一补，详见 §十四 OPC 升级触发的决策 |

**为什么先做设计基线、原型代码留 Phase 0**：参照 `digital-clone-research.md` 的 GATE-1（同样是设计文档型），先用「设计先经过审批 → 再落骨架」避免「按未审计共识写出 1 周代码后被推翻」。`product-dev.mdc` Stage 2 「最小可运行原型」的硬要求由 Phase 0 的「`zw-brain/` 工程骨架（**Postgres + 推理平台调用层**固定；**Web 框架 + 编排引擎 ⏳ Phase 0 PoC 后决策**，详见设计基线 §十四 第 9 轮决策）」承接，详见 §十 Phase 0 任务表。

---

## 二、文件变更清单

```
A  docs/approved/zw-brain-architecture.md       # 1526 行设计基线（含 14 行 frontmatter；已审批 status: approved，approved_by: xuejiao02）
A  docs/PR-GATE-1-zw-brain-architecture.md      # 本 PR 描述
A  .gitignore                                    # 治 IDE/OS 噪音 + 排除外部参考文档与历史素材
D  zw-brain-research.md                          # 已 mv 到 docs/approved/
```

**通过 `.gitignore` 排除**（user 决策，详见 §八）：
- `.DS_Store` / `**/.DS_Store`（IDE/OS 噪音）
- `old/integrated-bigdata-platform/`（旧平台界面截图含合规敏感内容，不入库）
- `digital-clone-research.md`（跨产品研究档，不公开）
- `old/`（历史素材，不进版本控制）

**仍 untracked、不在本 PR 范围**：
- `scripts/extract_meeting_screenshots.sh`（属于素材采集工具链，留独立 PR 处理）

**追加 chore commit（method A，commit `a631cc6`，发生在 PR 起草后期）**：

为让 `.gitignore` 真正生效，对以下 3 个「`.gitignore` 列出但仍被 tracked」的文件做 `git rm --cached`（**只解 tracking，不重写历史**，磁盘文件保留，过往 commit 仍可 `git show` 查到）：

| 解 tracking 文件 | 大小 | 入仓来源 |
|---|---|---|
| `old/05-浪潮云共享平台白皮书V1.3 20260204.docx` | docx | init commit `eb306cb` |
| `old/系统简介-一体化政务大数据平台.xlsx` | xlsx | init commit `eb306cb` |
| `digital-clone-research.md` | 74 KB | 5 个 commit，最新到 master `2ea4f60` |

→ PR diff 因此多出 `-1249` 行（来自 `digital-clone-research.md` 文本 + 两个二进制 docx/xlsx 的 binary deletion 标记），**与设计基线无关**，是补 .gitignore 一致性的运维 chore。

**Method B（`git filter-repo` 重写历史 + force push）刻意延后**：会改写所有 commit SHA，本 PR 必须 close 重开。等 GATE-1 merge 后若有合规硬要求再一次性彻底清。

---

## 三、设计基线核心摘要（10 行能看完，详见正文）

1. **三哲学交汇**：Jobs（聚焦/简洁/端到端）+ OPC（杠杆/极简/自动化）+ 政务三硬约束（合规可证迹 / 国家通道 / **模型推理统一走集团推理平台**）→ §〇
2. **要重构掉什么**：旧平台 20+ 子系统、入口埋深、合规事后取证、自然语言能力欠缺 → §一
3. **形态变化**：精简 WebUI（≤10 个核心场景页）+ 嵌入式 NL 加速器 + 4 入口（API/CLI/MCP/A2A）+ Agent 编排 + N 个可注册 Skill；可视化大屏（K12）独立部署 → §二 / §三 / §七 / §7.7
4. **架构 5 层**：L1 入口 / L2 编排 / L3 核心 Agents / L4 Skills / L5 基础数据 + 外部系统（含集团推理平台、外部区块链、国家平台）→ §四.1
5. **数据模型 Agent-Native first**：稳定 URN（含小白解释）+ 显式状态机 + 可序列化意图 + 一等审计字段（树状级联）+ PII 标签；旧平台数据通过 `adapters/` 单向同步 → §四.4
6. **强硬约束**：审计同步阻塞落库 / 区块链 adapter 异步锚定 / **禁止直连任何第三方 LLM API** → §四.5 / §十三
7. **能力扩展唯一路径**：Skill 注册（含外部技能平台）；4 入口共享同一套 Skill 契约，单脚本生成 → §五 / §六
8. **真实数据验证**：8 类 fixture（catalogs/resources/requests/exchange-tasks/audit-logs/zones/cases/apps）+ 5 个 mock 容器（Postgres/数据治理/区块链/推理平台/国家平台）→ §九.3
9. **路线图**：Phase 0 第 1 周搭基线 / Phase 1 第 2-4 周核心 5 Skill / Phase 2 第 5-8 周编排 + Skill 注册 / Phase 3 第 9-16 周国家直达 + 大屏 + 灰度 → §十
10. **成本**：重构期 ¥0.6-1.1M（vs 旧模式 ¥6-12M），生产推理走集团内部结算不计新增成本 → §十一

---

## 四、关键决策清单（GATE-1 审批通过后写入 `CLAUDE.md` 决策记录段）

详见 `docs/approved/zw-brain-architecture.md` §十四，**19 条决策**摘要（第 19 条 = GATE-1 review 触发的新增）：

| # | 决策 | 类型 |
|---|---|---|
| 1 | WebUI（≤10 页）+ NL 加速器 + 4 入口，**不复刻旧菜单 / 不做裸对话框** | 形态决策 |
| 2 | 4 入口共享同一套 Skill 契约（单脚本生成） | 架构决策 |
| 3 | 能力扩展唯一路径 = Skill 注册 | 架构决策 |
| 4 | 审计同步落库（写入失败必熔断），区块链 adapter **异步**锚定 | 强硬约束 |
| 5 | 区块链对接采用轻量 adapter 模式 | 实施策略 |
| 6 | **所有模型调用必须走集团推理平台 SDK，禁止直连任何第三方 LLM API** | 强硬约束 |
| 7 | 数据模型 Agent-Native first + Adapter 层单向同步 | 架构决策 |
| 8 | UI 仅保留 §7.3 的 ≤10 个核心场景页 | 形态决策 |
| 9 | （修订）「共享专区」从砍掉清单移回 K11 必保留 | 范围决策 |
| 10 | 5 个低价值功能默认不重构（数据资源库 / 绩效考核 / 应用案例独立子系统 / 通用服务+链接资源 / 指标平台） | 范围决策 |
| 11 | 全部 Skill 用旧平台真实业务数据（脱敏）回归验证 | 验证策略 |
| 12 | 与数据治理中心 / 外部区块链 / 国家平台 / 集团推理平台保持「外部依赖」关系 | 边界决策 |
| 13 | 外部 Agent / Skill 接入是合法路径（A2A 服务端 + Skill 注册），具体协议⏳待业务侧同步 | 边界决策 |
| 14 | 推理平台 SDK 具体协议⏳待业务侧同步，Phase 0 用 mock client 占位 | 边界决策 |
| 15 | （修订）「政务大脑可视化大屏」从「不做清单」反转为 K12 必保留（独立部署单元） | 范围决策 |
| 16 | URN 小白解释入文档 §4.4.2，后续凡新文档首次出现 URN 必回链 | 文档约定 |
| 17 | 数字漂移防御层缺失记入 GATE-1 PR 验收清单（OPC 升级触发自第 3 轮自检） | 元层决策 |
| 18 | （修正第 3 轮论断）`sync-stats.sh` 已支持父仓库扫描，统一 `dev-rules/.stats.json`，`zwbrain.` 命名空间 | 元层决策 |
| **19** | **（第 9 轮 / GATE-1 review 触发）技术选型「Web 框架 + 编排引擎」从设计基线剔除，⏳ 留 Phase 0 PoC 后决策**（5 维度：推理平台 SDK 兼容 / 审计 hook 注入 / AI Coding 改对率 / 政务部署兼容 / 集团技术栈一致）；同时识别新反模式「随手提到 = 隐式决策」 | **元层决策** |

外加 §十四 末尾**第 7 / 第 8 / 第 9 轮自检 + GATE-1 review 的元层观察**三条决策（`check_fixture_coverage.py` GATE-2 后追加 + `check-doc-xrefs.sh` 治本提议 + 「提到 ≠ 决策」反模式登记），共 21 条记录。

---

## 五、自检透明度：8 轮自检 + GATE-1 review 触发的第 9 轮发现与修复

| 轮次 | 发现严重度 | 性质 | 是否已修 |
|---|---|---|---|
| 1 | 文本错 / 数字算错 / 引用悬空 | 4 处 | ✅ |
| 2 | §八 统计再次算错 / 附录 B 行错位 | 2 处 | ✅ |
| 3 | **数字漂移防御层缺失**（OPC 升级触发） | 1 类系统性 | ⏳ 留 GATE-1 PR 落脚本时一次性补 |
| 4 | 自我修正第 3 轮关于 sync-stats.sh 的误判 | 1 元层 | ✅ |
| 5 | 7 个实体未定义（契约缺口） | 1 类系统性 | ✅ |
| 6 | 4 个 adapter 未补（数据迁移缺口） | 1 类系统性 | ✅ |
| 7 | 3 类 fixture + 1 mock 容器漏列（验证基础设施缺口） | 1 类系统性 | ✅ |
| 8 | 4 处衍生漂移（任务表 / 清单 / 幽灵编号 / 硬编码行号）+ 1 处隐患登记 | 5 处 | ✅ + 元层提议 |
| **9（GATE-1 review 触发）** | **「FastAPI + LangGraph」未到决策时点就被默认拍板**（3 处）；新反模式：**「随手提到 = 隐式决策」** | **1 类元层系统性** | ✅ 全部改为「⏳ Phase 0 PoC 后决策」+ §十四 新增第 19 条决策记录反模式 |

第 5–9 轮一致暴露的反模式：
- 上游修了下游没跟（`§4.4` 改了，`§九 / §十` 没跟）
- 跨段引用幽灵编号（不存在的 Step / 不存在的小节）
- 行号硬编码（`line N` 引用必漂移）

**OPC 升级提议（已写入 §十四，留 GATE-1 落脚本时实施）**：在 `dev-rules/sync-stats.sh` 同侧追加 `dev-rules/check-doc-xrefs.sh`，扫描 `*.md/*.mdc` 中 `§…` 章节引用与 `line N` 行号引用，前者比对章节标题、后者直接 fail。**这是治本（治反模式），不是治症（治个案）**。

---

## 六、人工审批 Checklist（按 `product-dev.mdc` Stage 2 GATE-1）

请审批者逐项确认，merge = 全部通过：

- [ ] **数据模型是否合理**（§四.4 Agent-Native first + Adapter 层 + URN 小白解释 + 7 类新增实体 + 树状审计级联）
- [ ] **API 设计是否符合现有规范**（§五 4 入口契约 + §六 Skill 三件套 + 附录 C 协议待回填登记表）
- [ ] **技术选型「固定部分」是否恰当**（Postgres + 集团推理平台 SDK + 外部区块链 adapter）
- [ ] **是否同意「Web 框架 + 编排引擎延后到 Phase 0 PoC 决策」**（设计基线 §十四 第 9 轮决策；PoC 必须对比 5 个维度：推理平台 SDK 兼容性 / 审计 hook 注入 / AI Coding 改对率 / 政务部署兼容 / 集团技术栈一致；审批时只需确认「延后是否合理 + 5 维度是否完备」，不需拍板具体框架）
- [ ] **原型是否可演示核心流程**（⚠️ 设计文档先行，原型在 Phase 0 落地——是否接受这种「分两步走」）
- [ ] **是否需要调整设计方向**

**若需要调整**：直接编辑 `docs/approved/zw-brain-architecture.md` 对应小节，merge 即采纳。

**若否决**：请在 PR 评论中标注「否决：原因…」，分支会被废弃，回到需求分析阶段。

---

## 七、GATE-1 通过后立即执行（Phase 0 第 1 周）

按 `docs/approved/zw-brain-architecture.md` 附录 A 执行 13 项接入（前 2 项**已在本 commit 验证就绪**）：

```
- [x] cp dev-rules/templates/preflight.sh scripts/preflight.sh   ← 此前已装；本 commit hook 触发 PASS 验证
- [x] bash dev-rules/templates/install-hooks.sh                  ← 此前已装；本 commit hook 触发 PASS 验证
- [ ] 创建 scripts/export_agent_contract.py（生成 4 入口契约；preflight 段 4 当前 skip）
- [ ] 创建 scripts/check_fixture_pii.py（preflight 段 9）
- [ ] 创建 scripts/check_no_direct_llm.py（preflight 段 10）
- [ ] 创建 scripts/check_audit_must_block.py（preflight 段 7a）
- [ ] 创建 scripts/check_blockchain_async.py（preflight 段 7b）
- [ ] 创建 scripts/check_dashboard_readonly.py（preflight 段 11）
- [ ] GATE-2 后创建 scripts/check_fixture_coverage.py（preflight 段 12）
- [ ] 创建 .testing/user-stories/verify_quality.py（preflight 段 5 当前 skip）
- [ ] 创建 dev-rules/schemas/skill.schema.json
- [ ] 创建独立子项目 zw-brain-dashboard/（K12 大屏骨架）
- [ ] 数字漂移防御层：注册 4 个 zwbrain.* stat 到 dev-rules/.stats.json + 包裹本文档对应位置（注：本 commit preflight 段 8 PASS 是因为本文档**当前没有任何 stat 块** —— 没有需要 check 的目标，naturally PASS；并不代表已完成此项治理，详见 §十四 OPC 升级触发的决策）
- [ ] 在 CLAUDE.md「决策记录」段追加 §十四 全部决策
```

**额外（本 PR 自检暴露、需 GATE-1 落脚本时回头校对）**：
- 附录 A 中 `zwbrain.preflight-sections` 的 compute 命令正则需放宽为 `[0-9]+[a-z]?` 以匹配 `7a` `7b` 段
- `.gitignore` 加入 `.DS_Store` / `**/.DS_Store`

---

## 八、外部依赖文档（user 决策：不入库，由 `.gitignore` 排除）

设计基线引用的 2 个 workspace 内文档**不进 zw-brain 仓库**：

| 引用文件 | 在设计基线中的位置 | 不入库的原因 |
|---|---|---|
| `old/integrated-bigdata-platform/`（README 21 章 + 47 张界面截图 + 转写时间戳） | §一 / §八 / §15 / 附录 B | 含客户内部界面截图，**合规敏感**，公开仓库不合适 |
| `digital-clone-research.md` | §〇 / §六.½ / §九 / §十一 同源引用 | 跨产品研究档，归个人 / 内部知识管理，**不公开** |

**对 PR 评审的影响**：
- 设计基线本体引用路径写的是 `old/integrated-bigdata-platform/...` 与 `digital-clone-research.md`，**这些路径在 user workspace 内有效，但 clone zw-brain 仓库到任意机器后不可见**。
- 评审者如果在 user 的 workspace 内（路径有效）→ 可点击/打开外部参考；如果只 clone zw-brain 仓库 → 引用是「外部依赖说明」，README 摘要 + §八 映射表已把核心事实内嵌到设计基线，足以独立评审。
- 设计基线 frontmatter 的 `related_docs:` 字段**保留**这两个引用，作为「需在 user workspace 内才能展开」的元数据声明，不视为引用悬空。

**反转记录**：上一轮决策 5「同意紧随开 PR-2 入库 `old/integrated-bigdata-platform/`」**已被 user 修正为「确认不入库 + 加 .gitignore」**（详见 §九 决策 5 状态）。该反转不需要改动 §十四（设计基线决策段），因为它属于「本仓库的发布边界」而非「政务大脑产品的设计决策」。

---

## 九、决策已落定（5/5）

| # | 议题 | User 决策 | 落地动作 |
|---|---|---|---|
| 1 | 远端选择 | `git@github.com:feng222666888/zw-brain.git` | ✅ 已 push 成功（仓库已创建并为空） |
| 2 | dev-rules 残留清理 | user 手动清理 | ✅ 已确认 |
| 3 | 审批 | `approved_by: xuejiao02` / `approved_at: 2026-04-18` / `status: approved` | ✅ 已落 frontmatter |
| 4 | 接受「设计文档先行型 GATE-1」 | 接受 | ✅ Phase 0 骨架在 GATE-1 merge 后立即启动 |
| 5 | 外部依赖文档处理 | **修正**：从「同意紧随 PR-2 入库」反转为「不入库 + 加 .gitignore」 | ✅ `.gitignore` 已写入；详见 §八 |

**SSH 鉴权落地方案**：本机持有两套 SSH key（`~/.ssh/id_ed25519` → `youxuanxue`，`~/.ssh/id_ed25519_feng222` → `feng222666888`），通过 **per-repo** `git config core.sshCommand "ssh -i ~/.ssh/id_ed25519_feng222 -o IdentitiesOnly=yes"` 把本仓库的 git over ssh 钉到 feng 账号 key，**不污染全局 ssh config**。验证：`ssh -i ~/.ssh/id_ed25519_feng222 -T git@github.com` → `Hi feng222666888!`。

**Push 实况（已完成）**：
- ✅ `git push -u origin master` → `[new branch] master -> master`
- ✅ `git push -u origin prototype/zw-brain-architecture` → `[new branch] prototype/zw-brain-architecture -> prototype/zw-brain-architecture`
- ⏳ `gh pr create`：`gh auth status` 显示登录账号为 `youxuanxue`（token scope 含 `repo`），跨账号开 PR 取决于 `youxuanxue` 是否为 `feng222666888/zw-brain` 的 collaborator；不可用时回落到 GitHub Web UI 手动开 PR（直接复制本文档作 body）

**注意**：`prototype/zw-brain-architecture` 分支比 `master` 多 3 个 commit：
1. `7fc575a` prototype: 政务大脑 GATE-1（设计基线 mv + frontmatter + 本 PR 描述）
2. `6eece83` chore: sync dev-rules submodule and preflight label after workspace move（user 在 GATE-1 起草过程中插入的子模块同步，不属于 GATE-1 设计变更，但因在 prototype 分支上 commit 而被一并带入 PR；review 时可单独检视）
3. `d59effe` chore: GATE-1 approved + scope publication boundary via .gitignore（user 审批落 frontmatter + `.gitignore` 排除外部参考文档）
