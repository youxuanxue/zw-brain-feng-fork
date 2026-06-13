---
doc_id: design-zw-brain-flywheel
status: approved
gate: approved
approved_by: 薛娇（产品研发负责人）
revision_date: 2026-05-26
authors:
  - 薛娇（产品研发负责人）
  - Claude Code (claude-opus-4-7) — 设计协作
related_docs:
  - docs/approved/zw-brain-architecture.md
  - docs/approved/zw-brain-roles.md
  - docs/approved/zw-brain-data-model.md
  - .testing/README.md
  - .testing/signoff/README.md
related_prs: []
related_commits: []
phase_after_approval: Phase 0 后期 — 飞轮势能完成、齿轮组连接、首客户上线启动
---

# zw-brain 业务提升飞轮

> **权威性**：本文是 zw-brain 业务持续增长的**唯一权威飞轮设计基线**。架构基线（`zw-brain-architecture.md`）回答"造什么样的产品"，本文回答"怎么让产品持续把 N 个客户上线"。
>
> **核心论点**：把"每个客户都从头做一遍"的 N × O(N) 苦活，沉淀为"积累一次、N 客户复用"的 O(1) 飞轮。
>
> **修订规则**：后续修订在本文原位演进；与架构基线 D-编号 / R-编号互引，不复制内容。

## 〇、文档身份

| 维度 | 内容 |
|---|---|
| **本文回答** | zw-brain 怎么从"做一个政务大脑"升级为"做能让 N 个政务大脑上线的飞轮" |
| **不回答** | 产品形态（基线 §五）/ 数据模型（data-model）/ 角色（roles）|
| **读者顺序** | 产品 / 架构 / PM 先读本文 §一-§三；工程读 §四-§六；运维读 §七-§十 |
| **机械连接** | 三角字段规范（附录 B）由 preflight 段 38 守；飞轮速度指标由 `scripts/flywheel_velocity_report.sh` 出 |

## 一、飞轮叙事（核心论点）

> **zw-brain 的本质**：不是做产品，是做产品的产品。

| | 错误叙事（陷阱） | 正确叙事（飞轮） |
|---|---|---|
| 业务目标 | "做一个好用的政务大脑" | "做能持续上线 N 个政务大脑的能力" |
| 客户视角 | 每个客户都要工程介入 | 第 N 客户由配置 + CLI 上线 |
| 工程视角 | 多个客户 = 多个分支 | 多个客户 = 同一仓库 + 不同配置 |
| 成熟度判据 | "代码完成多少行 / 测试覆盖率" | **第 N+1 客户上线成本 < 第 N 客户** |

**健康飞轮的硬判据**：

```
∀i ≥ 1,  T(客户 N(i+1) 上线 worker·week)  <  T(客户 N(i) 上线 worker·week)
```

哪一次变大，说明有齿轮咬不动了 — 立即拆解原因，不允许"再赶一赶就好"的话术。

## 二、飞轮的三层结构

```
                  ┌─────────────────────────────┐
                  │   势能层：业务真值源          │
                  │   ─────────────────────     │
                  │   ① 架构基线 R1-R15         │
                  │   ② 决策 D1-D30+            │
       回灌 ←─────│   ③ 业务方 review 21 条      │← 反哺
       (累积)     │   ④ sd-default SQL 17 dump  │
                  │   ⑤ ★ 旧 xlsx 128 用例      │
                  └──────────────┬──────────────┘
                                 │
                                 ↓ 一次积累，长期消费
                                 │
            ┌════════════════════┼════════════════════┐
            ║   齿轮组：三角闭环                       ║
            ║                                          ║
            ║   status = f( SPEC, MEASUREMENT, SIGN-OFF ) 现算（不存储，D46）║
            ║                                          ║
            ║   ┌─ SPEC ─────────────┐                 ║
            ║   │ .testing/*.feature │ # Owner/# Pytest║
            ║   │ What + R13          │                 ║
            ║   └─────────┬──────────┘                 ║
            ║             │ # Pytest                    ║
            ║   ┌─ MEASUREMENT ──────┐                  ║
            ║   │ tests/* + e2e 实跑 │ → .testing/      ║
            ║   │ CI 绿 + Playwright │   status/        ║
            ║   └─────────┬──────────┘   measurement/   ║
            ║             │                             ║
            ║   ┌─ SIGN-OFF ─────────┐                  ║
            ║   │ .testing/signoff/  │ 账本 covers（D46.b║
            ║   │ 单一权威源、来源无关│ append-only 人判）║
            ║   └────────────────────┘                  ║
            ╚════════════════╤═════════════════════════╝
                             │ SPEC↔test 双边硬化（段38）+ status 现算守卫（段60/61/62/63）
                             ↓
                  ┌──────────────────────────────┐
                  │   动能层：客户上线             │
                  │   ─────────────────────      │
                  │   • M0 CLI 灌库              │
                  │   • 真实 dump 跑等价回归       │
                  │   • R14 三引擎吃项目级差异     │
                  │   • 90 天 SLI 监控           │
                  │   • 反馈 → 回灌真值源 ↑      │
                  └──────────────┬───────────────┘
                                 │
                                 ↓
                  ┌──────────────────────────────┐
                  │   飞轮回转 + 加速              │
                  │   下一个客户上线更快           │
                  └──────────────────────────────┘
```

**三层各自的角色**：

| 层 | 角色 | 时间属性 | 不可替代性 |
|---|---|---|---|
| **势能层**（真值源）| 飞轮的"输入" | 一次积累 + 持续回灌 | 每类真值源都有唯一视角，不可合并 |
| **齿轮组**（三角闭环）| 飞轮的"传动" | 每个 commit / PR 都在转 | 任意一个齿轮断链飞轮停转 |
| **动能层**（客户上线）| 飞轮的"输出" | 每客户一次完整循环 | 不上线 = 飞轮在原地空转 |

## 三、势能层：7 类业务真值源

### 3.1 真值源清单

| # | 真值源 | 物理位置 | 视角 | 是否签字属性 |
|---|---|---|---|---|
| 1 | 架构基线 R1-R15 | `docs/approved/zw-brain-architecture.md` §十一 | 工程架构 | ✓（GATE-1 / 1.1）|
| 2 | 决策 D1-D32+ | `CLAUDE.md` 决策记录 | 历史决定 | ✓（D 编号即签字）|
| 3 | 业务方 review 21 条反馈 + PR #129 50 条逐条签字 | `old/20260519/` + D27 摘要 + `docs/legacy-not-reproduce-signoff.md` | 客户真实痛点 | ✓（业务方亲签）|
| 4 | sd-default SQL 17 dump | `old/10示例数据/` (438MB) | 真实数据形态 | ✗（事实，无需签字）|
| 5 | **★ 旧 xlsx 128 用例** | `old/共享平台V5.0.2-冒烟.xlsx` | **业务方亲手验过的路径** | ✓（业务方亲签）|
| 6 | **旧平台模块 reconstruction plans** | `docs/reconstructs/dsp-*-reconstruction-plan-v1.md`（10 份）| 旧代码 → zw-brain 落地路径 | ✓（plan v1 sign-off + D32 触发 active）|
| 7 | **旧平台真实 API 调用数据** | `old/old_codes_analyse/*-apis.md` + `old/使用日志分析情况/` | 客户真实使用画像（Pareto 决策依据）| ✗（事实）|

### 3.2 第 5 类的特殊地位（旧 xlsx 128 用例）

xlsx 是**唯一一份"业务方亲手写、旧平台已生产验证、用业务语言"的用例集**：

- **客户期望底线**：旧能做的新必须能做，或明示不复刻（业务方签字接受）
- **回归基线**：防 ship 后客户回头骂"重构把我用的弄没了"
- **退役判据硬指标**（处置完整度 = 116/131 = 89%）：✅ 等价回归 73 + ❌ 接受不复刻 16 + ⏸ 占位延后 / 按 plan 落地 23 + ⚠ 外部依赖 4 = 116 已处置；unmapped 15 是 mapping doc 未登记 gap（待真值源回灌补足，不计入退役公式）。分布由 `tests/fixtures/legacy_smoke.yaml` 实时维护，看板由 `scripts/check_legacy_retirement_ready.py` 输出（D31 业务方 PR #129 触发 24 条 ❌ → ⏸；D32 升级两份 reconstruction plan 为 active：A 类 → `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md`；D 类 → `docs/reconstructs/dsp-sharezone-topic-package-reconstruction-plan-v1.md`）
- **机械化路径**：xlsx → `tests/fixtures/legacy_smoke.yaml` → `tests/test_legacy_smoke_equivalence.py` parametrize → mapped 条目等价回归（当前 73；分布由 yaml 实时维护）

详见 `.testing/cross-cutting/legacy-128-mapping.md` + 本文附录 A.5。

### 3.3 真值源的"势能"属性

势能 = **一次积累，长期消费**。判定一个文件是不是真值源的硬标准：

| 判定问题 | 是真值源 | 不是真值源 |
|---|---|---|
| 删了能再生成吗？ | ✗ 不能（历史 / 业务方记忆 / 真实数据）| ✓ 可由代码 / 配置生成 |
| 谁有权改？ | 业务方 / 架构 GATE | 任意工程师 |
| 改了会触发回灌吗？ | ✓ 触发 spec/test 更新 | ✗ 改了只影响自己 |

`.testing/*.feature` / `tests/*.py` **都不是真值源** — 它们是真值源的衍生物。

## 四、齿轮组：status 现算三角（SPEC + MEASUREMENT + SIGN-OFF）

### 4.1 三轴定位

> status 不存储，由三个不可再分原料现算（D46）：`STATUS(f) = f(SPEC, MEASUREMENT, SIGN-OFF)`，由 `scripts/gen_feature_status.py` 算出权威视图 `.testing/status/feature-status.md`。

| 原料 | 文件 | 真实身份 | 谁写 |
|---|---|---|---|
| **SPEC** | `.testing/*.feature` | 业务 Spec 规约（GWT + `# Owner`/`# Pytest`）| 业务方（R13）|
| **MEASUREMENT** | `.testing/status/measurement/<sha>.json` | 机器实跑 pytest/e2e 的 pass/fail（带 git_sha，禁手写）| `capture_feature_status.py` |
| **SIGN-OFF** | `.testing/signoff/<scope>.signoff.yaml` | 账本 `covers`（**单一权威源、来源无关、append-only**，D46.b）| 业务方（人判）|

**关键认知**：`.testing/` 的命名误导 — 它不是测试库，是 **feature spec 库**。重命名是大手术（多文件硬编码引用），心智模型先正过来。

### 4.2 SPEC↔test 双边连接字段

详见**附录 B 字段规范**。摘要（`.feature` header 自带 SPEC↔test 双边，无 plan 端）：

```yaml
# .feature header（SPEC 端）
# Owner: e1                                          # 哪个 worker owns（归属标签）
# Pytest: tests/test_wave1_objection_5dim_state.py   # 哪个测试实现（.py 或 tests/e2e/*.spec.ts）
# Deferred: <理由>                                    # 可选：排期外 → Backlog
```

```python
# tests/test_waveN_xxx.py（test 端）
# Wave: 1
# Feature-ref:                             # 反向引用 spec
#   .testing/waves/wave-1/.../j1-objection-5dim.feature
```

### 4.3 机械守卫

| 守卫 | 实现 | 段号 |
|---|---|---|
| feature `# Owner` ∈ e1–e6 + `# Pytest` 指向的文件存在（或 pending）| `scripts/check_trace_triangle.py`（SPEC↔test 双边）| preflight 段 38 |
| status 现算不存储：`feature-status.md` 与 SPEC+MEASUREMENT+SIGN-OFF 字节一致；禁手写 status；MEASUREMENT 产物合法；账本合法 | `gen_feature_status.py --check` / `check_no_hand_typed_status` / `check_feature_measurement` / `check_signoff_ledger` | 段 60/61/62/63 |
| xlsx 行号 normalize | `scripts/check_legacy_smoke_row_numbers.py` | preflight 段 39 |

**断三角 = commit 拦下**。这条不做，前面所有动作都是"靠自觉"。

## 五、动能层：客户上线

### 5.1 客户上线的"完整一圈"

每个客户上线是飞轮转完整一圈的标志。完整一圈包含 5 步：

```
1. M0 CLI 灌库         scripts/import_legacy_dumps + verify
   ─────────          客户机房 dump → sd-default 等价 schema
2. 等价回归            pytest tests/test_legacy_smoke_equivalence.py
   ─────────          mapped xlsx 用例（当前 73）在客户 dump 上跑通
3. 项目级差异配置       三引擎（审批流 / 表单 / 推荐）
   ─────────          配置 + AI 草稿，不改代码
4. 验收脚本            scripts/customer_demo_j1.py / customer_demo_j2.py
   ─────────          客户业务方在场看演示，签字
5. 90 天 SLI 监控      集团运维监控接入
   ─────────          每日 ≥10 申请 / 每周 ≥3 发布 / B1 无 P0 阻断
```

5 步全绿 = 客户上线成功 + 飞轮转完一圈。

### 5.2 上线后的强制 ritual：回灌真值源

**这是飞轮自加速的核心**。每次客户上线后必须做：

| 客户上线发现 | 回灌目标 | 谁负责 |
|---|---|---|
| 新 bug | `tests/test_legacy_smoke_equivalence.py` 加用例 | 上线 worker |
| xlsx 之外的真实路径 | `legacy_smoke.yaml` 扩展 + .feature 新增 | 产品 + worker |
| 接受了某 ❌ 不复刻 | 给该条加客户证据 | 业务方 PR comment |
| 推迟某 ⏸ | 移到下批次评估 | 产品 |
| 三引擎配置示例 | 沉淀为模板 / 公共配置 | e3 owner |

**回灌不做 = 飞轮转一圈停一圈，第二客户与第一客户同等成本**。

## 六、3 个加速器

飞轮速度差异的真正来源。3 个加速器不齐全 → 飞轮第 N 圈与第 1 圈同速。

### 加速器 1：业务真值源回灌机制（§5.2）

每客户上线后强制回灌 → 真值源越用越丰满 → 下一客户上线时教训已经在 spec/test 里。

### 加速器 2：R14 三引擎

| 客户 | 审批流 | 表单 | 推荐规则 | 工程介入 |
|---|---|---|---|---|
| sd-default | 默认 3 层 | 默认字段集 | 默认推荐 | 全栈搭建 |
| 鞍山 N1 | 4 级（编→二级→一级→发）| +2 字段 | 5 条规则 | **0（配置）**|
| 四川 N2 | 默认 | +7 字段 | 默认 | **0（配置）**|
| 荆州 N3 | 默认 | 默认 | 自定义 5 条 | **0（配置）**|

**Wave 2 三引擎不 land 完，飞轮第二圈与第一圈速度相同**。这是 8 月底前必兑现的核心加速器。

### 加速器 3：sd-default ↔ 客户机房复用

M0 CLI（`import_legacy_dumps / verify` + e6 AC2/AC4）让 sd-default 跑通的全部测试**直接**在客户机房复用：

```
sd-default (山东) dump → pytest 绿 → Playwright 绿
       │
       ↓ 同一套 M0 CLI 灌库
       │
鞍山 / 四川 / 荆州机房 dump → 同一套 pytest 绿 → 同一套 Playwright 绿 → ship
```

**反 per-tenant fork（R8）+ M0 mapper 唯一源**是这条加速器的硬底线。任何"客户机房专用 fixture / 专用 mapper"出现立即拆。

## 七、单一健康度指标

> Jobs 式的"single number that matters"。

### 7.1 飞轮速度（Flywheel Velocity）

```
Flywheel Velocity = 1 / (单客户上线 worker·week)
```

| 客户 | 预估 / 实测 | worker·week | 速度 | 倍速 |
|---|---|---|---|---|
| N0 sd-default (baseline) | 实测 | 6 worker × 16 周 = 96 | 1/96 | 1× |
| N1 首客户（6-8 月）| 预估 | 6 worker × 4 周 = 24 | 1/24 | 4× |
| N2 二客户（9-11 月）| 目标 | 3 worker × 2 周 = 6 | 1/6 | 16× |
| N3+ 后续（12 月+）| 目标 | 2 worker × 1 周 = 2 | 1/2 | 48× |

**单数字看板**：`scripts/flywheel_velocity_report.sh` 每周一刷。

### 7.2 产品成熟度（每周报表）

辅助指标，对每 Wave 维度分子分母：

```
Wave 0  J1 主路径:     11 设计 ✓ / N InTest / M Ready / K Done
Wave 1  J1 深化+J2:    13 设计 ✓ / ...
Wave 2  三引擎+B1:     10 设计 ✓ / ...
Wave 3  [delayed]      本期不做
Wave 4  [post-ship]    客户上线后

Ship gate (Wave 0+1+2 全 Done): K / 34
```

实现：`scripts/product_maturity_report.sh`。

### 7.3 不健康信号

| 信号 | 含义 | 拆解动作 |
|---|---|---|
| T(N+1) ≥ T(N) | 某齿轮没咬动 | 查 §九反模式清单逐一对照 |
| worker·week 不降 | 飞轮原地空转 | spec/test 没复用，每次重写 |
| 真值源不增 | 客户反馈没回灌 | §5.2 ritual 没执行 |
| 30 Draft 持续不动 | R13 通道无流量 | 业务方 review 节奏未固化 |

## 八、启动节奏

### 第 0 圈 — 势能完成期（当前 → 2026-06 初）

**目标**：势能积累完成 + 三角硬化连接。

**完成度判据**：
- [x] 7 类真值源齐全（D32 补回灌 reconstruction plans + 真实 API 调用数据）
- [x] 飞轮文档 land（#123）
- [x] 三角字段加上（#123）
- [x] preflight 段 38/39 守住（#125）
- [x] xlsx → `legacy_smoke.yaml`（#125）
- [x] 原 50 条 ❌ 不复刻清单业务方签字（PR [#129](https://github.com/feng222666888/zw-brain/pull/129) → `docs/legacy-not-reproduce-signoff.md` `status: approved`；D31/D32 后：26 接受 + 24 复活按 reconstruction plan 落地：A→dsp-dataservice / D→sharezone-topic）
- [ ] 业务方 review 节奏固化（每月一次）

### 第 1 圈 — 首客户上线（2026-06 → 2026-08）

**目标**：齿轮真转一次，跑出 baseline。

| 节点 | 里程碑 | 出口标准 |
|---|---|---|
| 6 月初 | Wave 0 Done | 11 个 feature 全 Done（测试真绿 ∧ 业务方签字）|
| 6 月底 | Wave 1 Done | 13 个 feature 全 Done（J2 + 异议 + 供需）|
| 7 月 | Wave 2 Done | 三引擎 + B1 在鞍山/四川/荆州配置示例跑通 |
| 8 月 | 首客户机房 | M0 灌库 + dry-run + 上线 + 90 天 SLI 启动 |

**第一圈耗时长是正常的** — 这一圈在搭飞轮本体。

### 第 2 圈 — 加速验证（2026-09 → 2026-11）

**目标**：证明飞轮在加速。

- 第 2 客户接入仅用三引擎配置
- worker 介入 ≤ 3 人
- 真值源累计客户反馈 ≥ 20 条进 `legacy_smoke.yaml` 扩展
- **出口标准**：T(N2) ≤ T(N1) / 3

### 第 N 圈 — 飞轮自转（2027+）

**目标**：飞轮可被运营接管。

- 客户上线 = M0 灌库 + 三引擎配置 + 验收脚本
- 工程介入仅在新能力包 / 新协议（A2A / 国家通道）
- B1.2 后台治理面承接长尾差异（原「接入扩展中心」容器已随 **D52(2026-06-05)** 解体为后台四独立模块：查审计/外部系统/流程表单/身份治理，见 `docs/decisions/integration-admin-governance-axis-refactor.md`）

## 九、反模式清单（一旦出现立即拆）

| # | 反模式 | 后果 | 拆解 |
|---|---|---|---|
| 1 | 客户机房专用 fixture / 专用 mapper | 飞轮第二圈与第一圈同速 | 反 per-tenant fork（R8）+ M0 mapper 唯一源 |
| 2 | 业务方 review 不签字 / 不批量签字 | InTest 永远翻不到 Done | 签字通道走通（PR 加 `signoff:<scope>` label + body 机读块 → 合并自动落 `.testing/signoff/` 账本，D46.d；月度 review 固化）|
| 3 | spec 改了 test 没跟（或反之）| 三角断裂，spec/test 各自漂移 | preflight 段 38 三向 trace 守 |
| 4 | 不回灌客户反馈到真值源 | 飞轮停转 | 上线 ritual 把"回灌"作为硬步骤（§5.2）|
| 5 | 三引擎走捷径硬编码客户差异 | R14 不兑现，飞轮加速器失效 | preflight 段 25 写禁区 + Wave 2 AC5 验收 |
| 6 | xlsx 128 条只引用不验证 | 客户上线发现"旧的能新的不能" | mapped 条目等价回归 pytest 必跑（当前 73；分布由 yaml 实时维护）|
| 7 | 把"全部 feature 全 Done"当 ship 判据 | 永远 ship 不出去（Wave 4 结构上不可能）| ship 判据 = Wave 0+1+2 Done + 首客户机房 dry-run |
| 8 | 用 GWT 写 SLI 监控判据（Wave 4 老错配）| 永远到不了 Done | 90 天 SLI 移到 `docs/customer-readiness/` + 监控 cron |

## 十、回灌 ritual（上线后强制步骤）

每客户上线后 30 天内**必做**：

```bash
# 1. 收集客户上线发现
$ git log --since="客户上线日期" --grep="customer-N"

# 2. 回灌到真值源
- 新 bug      → tests/fixtures/legacy_smoke.yaml 加用例
- 新路径      → .testing/waves/.../{wave}/new-feature.feature
- 接受不复刻   → docs/legacy-not-reproduce-signoff.md 加证据
- 三引擎配置   → docs/customer-templates/{customer}/ 沉淀

# 3. 飞轮速度盘点
$ scripts/flywheel_velocity_report.sh
# 写入 docs/customer-readiness/velocity-history.md

# 4. 反模式自检
- 对照 §九 8 条反模式逐一确认本次无新增

# 5. 业务方 sign-off ritual
# 5. 业务方 sign-off ritual（D46 起）
# 往 .testing/signoff/<scope>.signoff.yaml 追加签字账本（covers 列被签 feature）；
# status 由 scripts/gen_feature_status.py 现算（绿∧签字=Done），不再手改/按 label 升级。
```

**ritual 不做完不算客户上线**。这是飞轮自加速的最关键步骤。

---

## 附录 A — 与架构基线的接口

| 基线节 | 飞轮接口 | 关系 |
|---|---|---|
| §一 我们造什么 | 产品定义 → 飞轮的"动能"输出 | 飞轮把基线 §1.5 成功标准实现 |
| §五 产品形态 | 8 页面 + Wave 0-4 | 飞轮齿轮组 Spec 层归集 |
| §六 统一能力契约 | 5 消费面投影 | 飞轮加速器 3（一处契约 N 处复用）|
| §八 外部能力集成 | AgentRuntime + 三引擎 | 飞轮加速器 2 + 长尾承接 |
| §十 实施路线图 | Wave 0-4 节奏 | 飞轮启动节奏（§八）的执行视图 |
| §十一 R 主张 | R8 反 fork + R13 sign-off + R14 三引擎 | 飞轮的硬约束载体 |
| §附录 C 软→硬映射 | preflight 段 38/39 | 飞轮三角守卫的实现 |
| **D-编号决策** | 真值源 #2 | 飞轮势能来源 |

### A.5 xlsx 128 用例的飞轮路径（明示）

```
old/共享平台V5.0.2-冒烟.xlsx
       ↓ scripts/extract_legacy_smoke_xlsx.py
tests/fixtures/legacy_smoke.yaml
       ↓ pytest parametrize
tests/test_legacy_smoke_equivalence.py
       ↓ 每客户机房 dump 上跑
mapped 等价回归绿（当前 73 条）
       +
docs/legacy-not-reproduce-signoff.md
       ↓ 业务方签字（PR #129）
not_reproduce 签字接受（当前 16 条；24 条 D31 复活转 ⏸）
       +
deferred 占位 / 按 plan 落地（当前 23 条）+ external 外部依赖（4 条）有处置
       =
Wave 4 退役判据闭合
       ↓
legacy 写入口可关闭
```

## 附录 B — 三角字段规范

### B.1 `.feature` header 字段（SPEC↔test 双边：`# Owner` / `# Pytest`）

```gherkin
# Wave: 0 | 1 | 2 | 3 | 4 | Cross
# Journey: J1 | J2 | B1.1 | B1.2 | Cross
# Pages: P1-P5 | P7 | B1.1 | B1.2 | None
# Consumer-faces: WebUI | API | CLI | MCP | A2A
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER | ROLE_BUSIAUDIT | ROLE_SECURITY_ADMIN | ROLE_SECURITY_AUDIT | ROLE_SYSTEM
# Trace: R-N / D-N / 业务反馈 #N / 旧 xlsx 行 N
# Priority: P0 | P1 | P2
# Owner: e1 | e2 | e3 | e4 | e5 | e6      ← SPEC↔test 连接：worker 归属标签
# Pytest: tests/test_waveN_xxx.py         ← SPEC↔test 连接（如无对应实现写 "pending"；e2e 用 tests/e2e/*.spec.ts）
# Deferred: <理由/ref>                     ← 可选：排期外意图 → Backlog
```

> `# Status` 不写进 header —— 状态由 `gen_feature_status.py` 现算（D46 / 段 62 禁手写）。

### B.2 `tests/test_waveN_*.py` 文件头（1 个新增）

```python
# Wave: 1
# Feature-ref:                            # ← 新增（反向引用 spec）
#   .testing/waves/wave-1/.../j1-objection-content.feature
#   .testing/waves/wave-1/.../j1-objection-use.feature
"""..."""
```

### B.3 Owner 映射表（worker × 责任域）

| Worker | 负责 .feature 范围 |
|---|---|
| e1 | wave-0/j1-* (除审批二段) + wave-1/j1-objection-* + wave-1/j1-supply-demand-* + wave-1/j1-credential-revoke |
| e2 | wave-1/j2-* + wave-1/j2-platform-publish |
| e3 | wave-2/engine-* + wave-2/p7-* + wave-2/adapter-* |
| e4 | wave-2/b1-* + wave-1/ext-agent-pilot + wave-0/infra-agentruntime-embedded + wave-0/infra-audit-bus |
| e5 | wave-0/infra-contract-projection（前端侧）+ wave-3/mcp-* / a2a-* |
| e6 | wave-0/infra-inference-gateway + wave-0/infra-iam-session + wave-3/* (除 mcp/a2a) + wave-4/* + cross-cutting |

## 附录 C — 飞轮维护原则

1. **真值源不可删**：7 类真值源任一删除等于飞轮势能丢失。
2. **三角连接不可断**：preflight 段 38 是硬约束。
3. **回灌 ritual 不可省**：客户上线 30 天内必做（§十）。
4. **加速器 3 个都不可缺**：缺 1 个飞轮第 N 圈与第 1 圈同速。
5. **反模式 8 条立即拆**：见 §九，发现一条拆一条。
6. **本文修订**：飞轮设计层修订原位演进；与架构基线 R-编号 / D-编号互引，不复制内容。
7. **本文不替代基线**：架构基线是"造什么"，本文是"怎么持续上线"，正交关系。

---

## 文档维护说明

- 本文是 zw-brain 业务持续增长的**唯一权威飞轮设计基线**
- 后续修订在本文原位演进；新增飞轮 F-编号写入 §一-§六对应位置
- 重大飞轮变化（如新增势能类 / 新增加速器）需新建 status 提案并走 GATE 流程
- 与架构基线 / 角色基线 / 数据模型基线**正交**，不重复
