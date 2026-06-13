---
title: 测试充分度收敛 — 诚实账（D46 后续）
scope: test-sufficiency-convergence
kind: 工程诚实账记录（非 GATE 决策；D46 现算 status 飞轮的收敛实践）
status: informational  # 工程交付侧收敛记录，无独立业务签字；D46 架构门见 feature-status-as-function-architecture.md
date: 2026-05-30
authors: 工程交付（D46 现算飞轮收敛）
related_docs:
  - docs/decisions/feature-status-as-function-architecture.md   # D46 本体
  - CLAUDE.md D46 决策索引
---

# 测试充分度收敛 — 诚实账（D46 后续，PR chore/converge-undertested-unsigned）

## 背景

承 D46（status 现算）：从现算分布找出「已实现但测试不充分 / 未业务签字」逐个收敛。
用 test-sufficiency workflow（27 路并行核验每个「绿但未签」feature 的链接测试是否**真覆盖
其 .feature scenario**），再以**代码二次核验**校正——因为 workflow 有系统性偏差。

## 核心发现 1：「绿」≠「测试充分」

大量 feature 的链接测试只覆盖正向 scenario，漏负向/一票否决。例：contract-projection 的
12 个测试全是 happy-path（干净时投影一致），从不测「drift 时守卫真能拦下」。

## 核心发现 2：也不能反向迷信 workflow 的「不足」判定

workflow 每个 agent 只被喂单个链接 `.py`，**系统性漏看 `# Pytest` 字段还声明的 preflight 段
覆盖 + 多文件覆盖 + 共享测试矩阵**，导致大面积误判：

| feature | workflow 判 | 代码二次核验真相 |
|---|---|---|
| negative-and-guardrails | inadequate 1/14 | **误判**：`# Pytest` 声明 = preflight 段10(推理收口)/24(R12术语)/25(adapter写禁区) + test_capability_boundary，三段守卫均存在且每 commit 跑绿 |
| j1-credential-revoke | inadequate 0/7 | **链接漏挂（已修）**：revoke 行为测试 `test_j1_credential_issue_revoke_on_application_revoke` 真实存在于 `test_wave0_j1_credential_call.py`，但 feature `# Pytest` 只挂了 `test_wave1_j1_credential.py`（仅 issue/query/sample，0 revoke 断言）→ workflow 看链接文件判 0/7 合理。本轮把 `# Pytest` 补上 `test_wave0_j1_credential_call.py`，链接如实反映覆盖 |
| j1-objection-{catalog,authz,use,content,resource} | 0/6~2/6 | **误判**：5 维共享 test_wave1_objection_5dim_state(13 测试,0 skip)+lifecycle(6)同一状态机矩阵；workflow 按单维 scenario 名逐字匹配漏判。content/resource 仅真实数据状态集为空（数据缺口非代码债）|

## 本轮实补（代码二次核验确认 = 已实现 + 缺一票否决测试 + 高杠杆，1 个）

| feature | 补了什么 | 验证 |
|---|---|---|
| infra-contract-projection | `test_check_projection_drift_catches_tampered_projection`：内存里把一份已生成投影内容篡改一字节 → 断言 `check_projection_drift()` 报 `projection drift` → 干净态回零 + 多余 MCP 描述符报 `unexpected` | 13 passed。**5 消费面单一事实源守卫终于被证明「该报错时报错」** |

**核验中发现的守卫真实边界（记 debt）**：尝试用「新增 registry manifest」造 drift 时，`check_projection_drift` 返回空——它按设计只比对「已知投影文件内容是否被改」(`current != expected`)与「多余 MCP 描述符」，**不检测「registry 多一个能力但从未投影」**（新文件不在 `expected_files` 的 key 内）。这不是测试写错，是该守卫的设计盲区：段 28 capability-registration（DISPATCH+handler+_CATEGORIZATION 三处一致）实际兜住了「新增能力」一致性，与本守卫互补。盲区记此备查，暂不扩守卫（无证据表明该路径漏过真问题）。

## 经核验避免的误补（workflow/初判建议补，但代码证明不该补，2 个）

| 候选 | 不补理由（代码证据）|
|---|---|
| multi-tenant-policy 跨租户写拒绝 | **代码未实现**：cross_tenant_write / session.tenant / policy.py tenant_id 全部 0 命中。第二租户 + 跨租户写禁是 wave3 未立项功能；补测试 = 测未实现功能 = 假绿。归 deferred |
| objection content/resource 维度 | 数据缺口（sd-default 无这两维异议数据），非代码/测试债；补也无真数据可断言 |

## 本轮链接修正（feature # Pytest 漏挂真实覆盖文件，1 个）

| feature | 修正 |
|---|---|
| j1-credential-revoke | `# Pytest` 补 `tests/test_wave0_j1_credential_call.py`（含 `test_j1_credential_issue_revoke_on_application_revoke` revoke 行为断言）→ 链接如实反映覆盖（段 38 绿） |

## deferred（本期故意不做，记 debt 不补 — 与 workflow/二次核验一致）

- infra-audit-bus：audit_event 12 富字段 + 7 角色码 CHECK（现最小表，富字段落 capability_call）→ W0-07/Wave1
- infra-iam-session：actor_org_role_binding 投影 + valid_to 软删除（D-2 红线冻结）+ token 过期 refresh（未实现）
- j1-api-call-monitoring / j1-credential-issue：配额 500/QPS/到期 401 阈值引擎 → W0-07/W0-08
- infra-inference-gateway：circuit-breaker + fallback → W0-07/Wave1
- mcp-hardening / observability-cost-quota：wave3 协议硬化 not-started（/metrics 端点未实现），未到立项期

## 待业务方签字（测试充分、只差签字 — 工程不替签）

经二次核验测试真充分、可直接走 D37/D35 业务签字流程 → 签后自动算 Done：
j1-supply-demand-meta-merge · j1-objection-{catalog,authz,use} · j1-credential-revoke
（其余 thin 项含少量未实现/deferred，不在可签清单）。

## 裁决

26 个「不足」经代码二次核验 = **1 个真高杠杆缺口已补**（contract drift 注入）+ **3 个误补已避免**
（credential-revoke 已充分 / multi-tenant 未实现 / objection 数据缺口）+ **约 8 类 deferred**
（配额/D-2/audit 富字段/wave3）+ 其余被 workflow 误判实已充分。
**最高杠杆收敛 = 给只验 happy-path 的单一事实源守卫补「该报错时报错」的负向**——这一个补丁
比盲目补 19 个测试更值。两轮均以代码为准（D46 ground-truth 纪律）；**不为补而补**。

---

## 第二轮（D46.f）：e2e 测量轴 + 全 38 non-Done 逐个核实 + webui 收敛

第二轮用 dynamic workflow 把 38 个 non-Done feature（27 InTest + 3 Ready + 8 Draft）全量
fan-out 核实，**再以代码 grep + 读测试文件二次校准**（workflow 仍有过度悲观偏差，14/38 agent
未出结构化结论，需手工补）。

### 发现 3：测量轴只认 pytest 是架构盲区（已修）

状态函数 `green()` 经 `PYTEST_PATH_RE` 只认 `tests/**.py` 与 `zw-brain-web/tests` 前缀；3 个
已签 webui feature 的 `# Pytest` 指向仓根 `tests/e2e/*.spec.ts`（Playwright），两分支都不匹配
→ refs=0 → green 永 False → **即便业务已签字也永远卡 Ready，到不了 Done**。
修复：`test_refs()` 泛化认 `.spec.ts`；`green()` test-runner 无关（读测量产物聚合 result）；
`capture_feature_status.py --with-e2e` 实跑 Playwright 回填同一产物（退出码即事实，禁手写）。

### 发现 4：workflow「14 needs-impl」多为过度悲观，代码二次核验纠正

workflow 按 .feature **全量场景**（含显式延后到 W0-07 浏览器 / W0-08 配额 / Wave1+ 的场景）判
needs-impl。代码核验真相：多数 InTest 的**本期核心**（状态机 / 审计传输 / 检索 / 审批数据层 /
j2 三层流水线 26 测试 / topic-package 12 integration）**确实已建且测绿**，被误判的业务深度场景
是 by-design 延后。逐个核验结论：

| feature | workflow 判 | 二次核验真相 | 处置 |
|---|---|---|---|
| a2a-hardening | InTest | **挂名不测**：`# Pytest` 挂 test_wave3，该文件 0 个 a2a 用例 | → `# Deferred`（Wave3 未实装）落 Backlog |
| j1-approval-conditional | needs-impl(0/7) | **误判**：test_wave0_j1_approval_conditional.py 8 真测试（决策记录/两步流/R11 方向/状态机）覆盖本期数据层；运行时分派 by-design 延 Wave1 | 留 InTest |
| j2-{department-review,online-catalog-compile,platform-publish} | （agent 失败）| test_wave1_j2_pipeline.py 26 测试 0 skip，全链路+返工+驳回+审计双事件+角色门控 | 留 InTest，**待业务签字** |
| p7-shared-zones | （agent 失败）| 12 integration（topic-package discovery+curation），后端已 e3.F9 签 | 留 InTest，p7 页面**待签** |
| infra-audit-bus/iam-session/inference-gateway · j1-objection-* · j1-credential-* | needs-impl | 本期核心已建已测；跨能力链路/多组织/脱敏/级联/非属主403/自动撤销 = by-design 延后（见上方 deferred 清单）| 留 InTest |

**唯一状态变更 = a2a-hardening → Backlog**（真过度声称）。其余 26 InTest 对本期核心诚实。

### webui×3 e2e 收敛（干净 seed 库实跑）

干净重建 seed 库（customer_acceptance_up.sh）+ 全新 vite build，实跑 3 webui spec：

| feature | spec | 干净库结果 | 现算 |
|---|---|---|---|
| webui-action-role-binding | permission_invisibility | ✓3 ✘0 | **Done** |
| webui-routing-cleanup | twin_browser_pages | ✓14 ✘0（污染库曾假 fail #/integration-admin，干净库通过）| **Done** |
| webui-pages-real-data | customer_acceptance_checklist | ✓12 ✘3 | **Ready**（不冒绿）|

webui-pages-real-data 的 3 失败（P2「案例」分类快捷检索链接 / P4 凭据三语样例 / P7 订阅按钮）
经核验 = **seed 数据内容脆性**（dump 重建 seed 缺这 3 个场景断言的特定数据；e5 委验证据在其 seed 上
记 15 passed），**非 webui 功能回归**（页面正常渲染，仅数据驱动元素缺）。truth-first：不冒绿，留
Ready + 记 debt（见 docs/preflight-debt.md）。22 个 pytest 模块在干净库全绿（无本地 seed 脆性）。

### 第二轮裁决

现算 9→**11 Done**（webui×2）/ 1 Ready / 26 InTest / 8 Draft / **3 Backlog**（+a2a）。
测量轴盲区已结构性消除（green test-runner 无关）；a2a 过度声称已校准；其余 InTest 经代码核验对
本期核心诚实，业务深度延后已在上方 deferred 清单登记。**待业务签字集合**（测试充分、只差签字）：
j2×3 · p7-shared-zones · j1-supply-demand-meta-merge · j1-objection-{catalog,authz,use} ·
j1-credential-revoke——签后现算自动翻 Done（工程不替签，D46 人类门）。
