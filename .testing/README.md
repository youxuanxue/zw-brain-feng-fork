---
doc_id: testing-readme
status: navigation
authors:
  - 薛娇（产品研发负责人）
  - Claude Code (claude-opus-4-7) — 测试设计协作
driven_by: docs/approved/zw-brain-architecture.md
fact_source:
  - old/共享平台V5.0.2-冒烟.xlsx
  - docs/approved/zw-brain-roles.md
  - docs/approved/zw-brain-data-model.md
---

# zw-brain Feature Spec 总入口

> **权威性**：`docs/approved/zw-brain-architecture.md` §10 五个 Wave 决定了 spec 节奏。
> 本目录是 zw-brain 各阶段 **Feature Spec 规约**的**唯一权威设计文档**（命名为 `.testing/` 是历史遗留 — 实质是 **business spec 库**，不是可运行测试代码）。
> **形态**：Gherkin/BDD（Feature / Background / Scenario / Given-When-Then）。
> **维度**：Wave 主轴 + cross-cutting 横切附录。
>
> **在飞轮中的位置**：本目录是飞轮齿轮组的 **Spec 层**（What + R13 签字）。Plan 层在 `.twin/*`，Verification 层在 `tests/*` + `zw-brain-web/tests/e2e/*` + preflight。三者通过三角字段（`# Owner` / `# Pytest` / `# Twin-F` + `spec_ref`）机械连接，由 preflight 段 37 守住。完整飞轮设计：[`docs/approved/zw-brain-flywheel.md`](../docs/approved/zw-brain-flywheel.md)。

## 目录结构

```
.testing/
  README.md                            # 本文（导航 + 写法规范 + 索引）
  cleanup-plan.md                      # tests/*.py 全量重写一次性档案（merge 后 30 天可删）
  waves/
    wave-0-golden-path/                # Wave 0：机械守卫 + J1 黄金链路
    wave-1-j1-j2-closed-loop/          # Wave 1：J1 闭环深化 + J2 最小闭环
    wave-2-engines-b1-zones/           # Wave 2：三引擎 + B1 + P7
    wave-3-protocol-tenant-national/   # Wave 3：协议硬化 + 多租户 + 国家通道
    wave-4-legacy-retirement/          # Wave 4：legacy 退役判据
  cross-cutting/
    role-matrix.md                     # 7 角色 × 4 旅程/支撑面 任务覆盖
    consumer-faces-matrix.md           # WebUI / API / CLI / MCP / A2A × Capability
    state-machines.md                  # 6+2 / 3 / 5 / 5 / 双轨 状态机
    negative-and-guardrails.feature    # AI 一票否决 + 系统级护栏（cross-wave 回归）
    legacy-128-mapping.md              # 旧 xlsx 128 用例 → 新 wave 映射
    role-task-skill-trace.md           # 角色 → 旅程任务 → Skill 追溯
  user-stories/                        # dev-rules verify_quality.py 入口（不动）
    index.md
    verify_quality.py
```

## Wave 索引

| Wave | 范围 | features 数 | 主要旅程 / 支撑面 | 完成判据简版 |
|---|---|---|---|---|
| **Wave 0** | 机械守卫 + 首条黄金链路 | 11 | J1（端到端） + 5 infra | 客户能用真实数据跑通"检索 → 申请 → 审批 → 凭据 → 调用"一次 |
| **Wave 1** | J1 闭环深化 + J2 最小闭环 + 首个外部 Agent | 12 | J1 异议 5 维度 / 供需对接 / J2 4 步 | J2 部门可独立完成"编制 → 挂接 → 审核 → 发布"；J1 异议任一维度可独立闭环 |
| **Wave 2** | 三引擎 + B1 合规 + 共享专区 + 一表通 | 10 | 三引擎 + B1.1/B1.2 + P7 | 项目级流程 / 表单 / 推荐通过配置完成，不改代码；B1 合规底线最小可用 |
| **Wave 3** | MCP/A2A 硬化 + 多租户 + 国家通道 | 7 | MCP/A2A + 国家直达 + 国家扩展要素 | 5 消费面对同一 Capability 的投影一致；国家通道独立子旅程可用 |
| **Wave 4** | legacy 退役判据 | 1 (+ docs/customer-readiness/) | 写入口（机械测）+ 4 类 SLI（看板）| legacy 已无唯一写入口；客户主旅程稳定运行 90 天（SLI 由 `docs/customer-readiness/wave4-cutoff-criteria.md` 承接，飞轮反模式 #8 拆分）|
| **cross-cutting** | 横切回归 + 角色/消费面/状态机/负向矩阵 | 6 文档 | All | 每 Wave PR 必扫；旧 xlsx 131 数据行 → 128 distinct 用例全量映射 |

## Gherkin 写法规范

每个 `.feature` 文件 **必须** 满足：

### 1. 文件头注释（Trace 元数据 + 三角字段）

```gherkin
# Wave: 0 | 1 | 2 | 3 | 4
# Journey: J1 | J2 | B1.1 | B1.2 | Cross
# Pages: P1 | P2 | P3 | P4 | P5 | P7 | B1.1 | B1.2 | None
# Consumer-faces: WebUI | API | CLI | MCP | A2A
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER | ROLE_BUSIAUDIT | ROLE_SECURITY_ADMIN | ROLE_SECURITY_AUDIT | ROLE_SYSTEM
# Trace: R[1-15] / D-XX / 业务反馈 #N / 旧 xlsx 行 [N..M]
# Priority: P0 (黄金链路必跑) | P1 (Wave 完成判据) | P2 (回归/边界)
# Status: Draft | Ready | InTest | Done
# Owner: e1 | e2 | e3 | e4 | e5 | e6                       ← 三角字段：哪个 worker owns
# Pytest: tests/test_waveN_xxx.py 或 pending               ← 三角字段：哪个 pytest 实现
# Twin-F: eN.FX 或 cross 或 pending                         ← 三角字段：哪个 F-item 承接
```

**三角字段说明**：

- `Owner` 指向 `.twin/eN-*/` 中存在的 worker；与 `.twin/eN/plan.yaml` `spec_ref` 双向绑定
- `Pytest` 指向 `tests/` 或 `zw-brain-web/tests/e2e/` 中实际存在的文件；写 `pending` 表示等实施 PR 接力
- `Twin-F` 3 种合法值：
  - `eN.FX` — 明确的 F-item 承接
  - `cross` — 横切类（cross-cutting / 跨多 F-item / 系统级护栏），不归属单一 F
  - `pending` — 等 PR 接力 OR 该 feature 所在 Wave 整体 deferred
- preflight 段 37（PR2 落地）会三向校验上述字段；任意失配 commit 拦下

`Trace` 行**必须**引用至少一个权威源：

- **R-编号**：架构基线 §11（R1–R15）
- **D-编号**：CLAUDE.md §决策记录（D1–D29+）
- **业务反馈 #N**：基线 §5.6 / D27 列出的 21 条
- **旧 xlsx 行 N**：`old/共享平台V5.0.2-冒烟.xlsx` **数据行号 1-based**（数据行 N = xlsx 行 N+1；header 在 xlsx 行 1）。注意：`cross-cutting/legacy-128-mapping.md` 表内行号是人工维护，已知在 row 17 / 19 / 53 / 54 等处与 xlsx 数据行有局部漂移；交叉对照请以**用例名字面值**为锚点而非行号数字（详见 mapping 文顶部"行号体系警告"）。

### 2. Feature 段（业务语义，不写工程术语）

```gherkin
Feature: J1 资源发现（P2 资源发现页）
  As a 部门操作员 (ROLE_ORGAN_OPERATER)
  I want 通过自然语言或目录树找到可申请的数据资源
  So that 不需要理解工程术语就能完成业务申请
```

`Feature` 名 + `As a / I want / So that` **必须用业务语义**（R12）。禁止使用 `package` / `projection` / `capability` / `policy_decision` 等工程术语；如需在 Then 断言中提到（如审计断言），用代码引号包裹清晰标注是后端字段。

### 3. Background 段（前置条件）

```gherkin
Background:
  Given 单租户 sd-default 已初始化
  And 7 角色码已 CHECK 约束生效
  And 集团推理平台 gateway mock 已就绪
  And 数据资源种子：T101 / T102（不同 owner_org / 不同 shared_type）
```

### 4. Scenario 段（必含三类）

每个 .feature **必须**至少包含：

- **正向 (Happy path)** ≥ 1 个 — 典型业务路径
- **负向 (Negative)** ≥ 1 个 — 权限 / 跨租户 / 字段缺失 / 错误状态机迁移
- **回归 (Regression)** ≥ 1 个 — 一票否决项 / 工程术语黑名单 / 已修复 bug 防漂移

### 5. 可观测断言

`Then` / `And` 步骤**必须**包含可观测的断言：

- UI 断言：DOM 元素 / 中文文案 / 状态徽标
- API 断言：HTTP status / 响应 schema / 业务字段
- 审计断言：`capability_call` 记录 / `audit_class` 等级 / 事件序列
- 状态机断言：实体 status 转移路径

禁止"模糊断言"如"工作正常 / 显示正确 / 无报错"。

### 6. 业务方 sign-off 标记

涉及 R13 元规则（角色 / 业务流程 / 状态机）的 Scenario，文件头 `Status:` 必须为 `Draft` 直到业务方（红军，海若产品部业务方）确认；sign-off 后改为 `Ready`，对应决策落 D-编号。

## 测试金字塔与本目录关系

```
                  端到端 / 客户验收
                       △
                      / \
                     /   \      ← .testing/waves/wave-{0..4}/  全部 .feature 在此
                    /-----\
                   /       \
                  /  集成   \
                 /-----------\
                /             \  ← Wave 实施 PR 在 tests/test_wave{0..4}_*.py 用 pytest 实现 .feature
               /  单元 / 机械  \
              /-----------------\
             /                   \
            /  保留的 4 个机械测试  \  ← tests/test_role_codes_alignment.py 等（永远在 tests/）
           /-----------------------\
```

**本目录 ≠ 单元测试**。单元测试在 `tests/`，由 Wave 实施 PR 引入；本目录是**用例设计**（业务可读、跨 5 消费面）。

## 用例形态与执行路径

| 用例类别 | 在哪 | 执行方式 | 由谁跑 |
|---|---|---|---|
| **机械对齐**（角色码 / 契约 / 打包 / domain policy） | `tests/test_*.py` | `pytest tests/ -q` | CI + 本机 preflight |
| **Wave 用例**（J1/J2/B1 端到端 + infra） | `.testing/waves/wave-N/features/*.feature` | 设计期：人工 review；实施期：pytest-bdd 或手写 GWT 风格落到 `tests/test_waveN_*.py` | Wave 实施 PR |
| **横切回归**（一票否决 / 角色矩阵 / 消费面矩阵 / 状态机 / 旧 128 映射） | `.testing/cross-cutting/*.{feature,md}` | 每个 Wave PR 必扫 review；机械化部分由 preflight 段承接 | 每个 PR + 业务方 review |

## 引用规范

| 在 .feature 引用 | 标准写法 |
|---|---|
| 架构基线章节 | `参见基线 §3.3` |
| R-编号 | `R10`（不写完整描述） |
| D-编号 | `D23` |
| 业务反馈 | `业务反馈 #4`（编号见 D27） |
| 旧 xlsx | `旧 xlsx 行 12` 或 `旧 xlsx 行 [12..16]` |
| 角色码 | `ROLE_ORGAN_OPERATER`（大写下划线） |
| 角色中文名（UI 文案断言用） | `"部门操作员"`（双引号） |
| 页面编号 | `P2 资源发现页` / `B1.1 合规与运营` |

## 文档维护

- **新增用例**：在对应 Wave 目录新增 `.feature`；同步更新本 README 的 Wave 索引计数
- **退役用例**：直接删除；git 历史保留即可（与基线 §决策"不留 superseded/archived"对齐）
- **修订基线后**：受影响的 `.feature` 必须更新 Trace 行；如需新增 R-编号写入基线 §11，必须先 sign-off

## 入口清单

- 本目录架构问题 → 基线 `docs/approved/zw-brain-architecture.md`
- **飞轮设计 / 三角连接** → `docs/approved/zw-brain-flywheel.md`
- 测试质量门禁脚本 → `user-stories/verify_quality.py`（dev-rules 提供，不动）
- pytest 实现入口 → `tests/`（19 个 wave PR 已 land + Wave 2/3 接力）
- Playwright e2e → `zw-brain-web/tests/e2e/`（12 spec / 62 passed）
- Worker plan → `.twin/eN/plan.yaml`（spec_ref 反向引用本目录）
- 不复刻清单（待签字）→ `docs/legacy-not-reproduce-signoff.md`
- Wave 4 SLI 看板 → `docs/customer-readiness/wave4-cutoff-criteria.md`
- 一次性档案 → `cleanup-plan.md`（merge 后 30 天可删）

## Owner 责任映射

| Worker | 负责 .feature 范围 |
|---|---|
| `e1` | wave-0/j1-* (除审批二段) + wave-1/j1-objection-* + wave-1/j1-supply-demand-* + wave-1/j1-credential-revoke |
| `e2` | wave-1/j2-* |
| `e3` | wave-2/engine-* + wave-2/p7-* + wave-2/adapter-* |
| `e4` | wave-2/b1-* + wave-1/ext-agent-pilot + wave-0/infra-agentruntime-embedded + wave-0/infra-audit-bus + wave-3/agentruntime-* |
| `e5` | wave-0/infra-contract-projection + wave-3/mcp-* + wave-3/a2a-* |
| `e6` | wave-0/infra-inference-gateway + wave-0/infra-iam-session + wave-3/multi-tenant + wave-3/national-* + wave-3/observability-* + wave-4/* + cross-cutting |

详见飞轮文档附录 B.4。
