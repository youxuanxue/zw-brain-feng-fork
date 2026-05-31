---
title: D46 — feature status 不存储、由 SPEC+MEASUREMENT+SIGN-OFF 现算
scope: feature-status-as-function
status: pending
date: 2026-05-30
deciders: 海若产品部产品研发负责人（架构决策门）
---

# D46 · status 不是事实，是函数（单一事实源 + 三角闭环飞轮 + 极致确定性）

## 背景 / 问题

同一个"feature 是否完成"的状态曾被**存了 3 份**：`.feature` 的 `# Status`、`.twin/plan.yaml`
的 `status:` / `[SIGNOFF-CLOSED]`、`docs/approved/zw-brain-architecture.md` 的 Wave 真相表。
PR #175 用对账守卫（段 58）机械同步副本，但那不是单一事实源——存的本就是个**派生值**，
且会撒谎（e6.F13 曾声称某测试模块"9 测试通过"，模块根本不存在）。

## 裁决

**status 永不存储，每次 preflight 由三个不可再分原料现算**（`scripts/feature_status_lib.py`）：

| 原料 | 单一写入者 | 位置 |
|---|---|---|
| SPEC（意图） | 人 | `.feature`（场景 + `# Owner/# Pytest/# Twin-F` 边 + 可选 `# Deferred:`） |
| MEASUREMENT（事实） | 机器（实跑 pytest，禁手写） | `.testing/status/measurement/<git_sha>.json` |
| SIGN-OFF（判断） | 人（append-only） | `.twin/**/plan.yaml` 含 `[SIGNOFF-CLOSED]` 的 item 的 `spec_ref` |

函数：`Done = 测量真绿 ∧ 业务签字`；`Ready = 已签未绿`；`InTest = 绿/在测但未签`；
`Draft = 纯意图`；`Backlog = # Deferred 排期外`。green() 只信 HEAD 祖先 SHA 的 committed
测量产物（fail-closed），**绝不读 plan.yaml 的 `status:`**（决策 a：那是 supervisor 执行态，
读它会重蹈 F13 谎报）。signed(f) = f ∈ 某 `[SIGNOFF-CLOSED]` item 的 spec_ref（零新字段、
复用段 38 已校验结构、零猜测）。

## 落地（本 PR）

- 新增 `feature_status_lib.py`（状态函数）/ `capture_feature_status.py`（测量捕获）/
  `gen_feature_status.py`（生成 `.testing/status/feature-status.md`，`--check` 字节守卫）。
- 删 `.feature` 全部 `# Status:`（46 个）；2 个 Backlog → `# Deferred:`。
- **删** `check_feature_status_drift.py`（段 58 对账守卫——无存储 status ⇒ 无可漂移，守卫自我消亡）
  与 `promote_signoff.py`（按 label 写 status 的机器——签字不再写 status，只作输入被读）。
- preflight：删段 58，加 **段 60**（测量产物校验）/ **段 61**（生成视图 --check）/
  **段 62**（禁手写 status 反向守卫）。
- `product_maturity_report.sh` 改读现算；arch.md §〇.1 降级为 Wave 路线图索引 + 指向生成视图；
  `.testing/README.md` / flywheel 模板行改指向生成器。Wave 滚动标签按决策不机械生成。

### D46.b — SIGN-OFF 独立账本（修签字寄生 twin 的破洞）

初版 `signed()` 借 `.twin` plan item 的 `spec_ref` 表达"签了哪些 feature"——这把**签字（人类判断）
耦合到 twin（执行计划）**，导致两个真问题：(1) twin 外、其他会话直接实现并合并 main 的功能**无处签字**；
(2) 借执行字段误判——`j1-supply-demand-meta-merge` 被误标已签（SIGNOFF 行落位巧合挂在它名下），
`b1-2-trust-level-upgrade` / `engine-ai-config-draft` 被漏签。

裁决：**SIGN-OFF 唯一权威源 = `.testing/signoff/<scope>.signoff.yaml` 账本**（append-only、机读、
来源无关、独立于 twin）。`signed(f) = f ∈ 某账本 covers`。`decision_only:true` 账本 covers 空、
只记决策史不抬 feature 状态。守卫 **段 63** `check_signoff_ledger.py`（schema + covers 路径存在 + 禁空签）。
**段 54** 从"对账 plan.yaml `[SIGNOFF-CLOSED]` + CLAUDE.md D-编号 + doc 三处副本"**收敛为**"approved
材料包 scope 在账本有落盘"单源（同段 58 自我消亡的同构收益——又删一个对账守卫）。

迁移：7 个历史 approved scope → 8 个账本文件（e3.F9 共用一个）；忠实修正上述误标/漏签。
`.twin` 历史 `[SIGNOFF-CLOSED]` 行**保留作执行归档不删**（twin 是 append 执行账本，删它高风险），
但不再是任何守卫的事实源。CLAUDE.md D-编号**保留**作决策史（D1–D46），不再当签字三角一角。

### D46.c — SPEC 是进飞轮的唯一入口

功能要有可追踪状态，**必须有对应 `.feature`**（SPEC 是入口）。独立会话直接合并 main 的功能：
先补 `.feature`（自动显 InTest）→ 往账本追加签字 → 算出 Done。纯 infra/脚本/文档不补 feature、
不进状态视图。**立明文规则（`.testing/README.md` + 本决策），不加机械守卫**——"什么算一个功能"
无法可靠机械界定，强行检测会变 `||true` 伪绿（全局宪法 §5：反复出现才硬化，现未反复）。

## 后果（诚实口径，用户已确认"绿∧签字=Done"）

逐 feature 真相落地后：**14 Done / 16 InTest / 14 Draft / 2 Backlog**。其中 16 个 InTest =
"测试绿、代码完成，但从未业务签字"——揭开了旧手敲 "Done" 把"工程完成"当"业务验收"的真相。
这是 SSOT 的诚实暴露，不是退步。

## 试金石

段 58（对账守卫）被删除即证明 SSOT 成立：用守卫同步两份副本是设计未收敛的味道；收敛后副本与
守卫一起消失，只留"生成 --check"+"禁手写"反向守卫。

### D46.e — `.twin/` 整体退役

`.twin/`（xuejiao persona supervisor 的执行计划 + 状态）经 D46/D46.b 已**不承载任何真相**：
status 现算（不读 plan.yaml `status:`）、签字住 `.testing/signoff/`。故 `.twin/` 退化为纯执行工具，
本轮直接退役（用户决策：不留历史兼容、不归档）。

- 退役前补齐唯一遗留缺口（D46.c 存量违例）：e5 三个用户面 feature（8 主页面真实数据 / 写操作
  角色绑定 / 子路由去占位）此前只活在 twin plan、无 `.feature`，删 twin 会使其从飞轮消失 →
  补 `webui-pages-real-data` / `webui-action-role-binding` / `webui-routing-cleanup`（owner=e5，
  纳入 `.testing/signoff/e5` 账本，现算 Ready）；并修正迁移期误挂的 j1-credential-issue。
- `git rm -r .twin/`（74 文件）。段 38 三角收敛为 `.feature # Owner/# Pytest ←→ tests` **双边**
  （删 Twin-F 解析 + plan spec_ref 反查）；46 个 `.feature` 删 `# Twin-F` header。
- 删段 26 `check_twin_workspaces`（纯校验 .twin）。`feature_status_lib` 不再 import TWIN_DIR。
- `/twin` 命令（全局 `~/.claude/CLAUDE.md` 定义）随之失去本仓工作区；如不再用 supervisor 续跑可忽略。

验证试金石同 D46：又一个「为 .twin 而存在的守卫（段 26）」被删除即证明 .twin 已无真相职责。

## 残留 debt

- CI 自动刷新测量产物（push-to-main 跑 capture 并持久化）未接，本期靠 PR 提交基线 + 合并前
  本地 `capture_feature_status.py` 手跑（同 capture_acceptance_evidence 模型）；段 60 对陈旧
  仅 WARN。记 `docs/preflight-debt.md`。
