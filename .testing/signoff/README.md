# 签字账本 README — .testing/signoff/

> SIGN-OFF 原料的**唯一权威源**（D46）。状态函数 `signed(f)` 只读这里。

## 是什么

业务方对 feature 的**验收签字事件账本**。每签一次 = 新增一个 `<scope>.signoff.yaml` 文件，
**append-only**：只新增、不修改旧文件，git 历史即签字史。

签字是「人对系统做了什么」的事件，独立于：
- `.feature`（SPEC = 意图，"要什么"）—— 签字不写进 feature 头（那会重蹈被删的 `# Status`）
- 执行过程（supervisor / 任意会话 / 纯人工验收）—— 签字**来源无关**：无论功能怎么实现，统一往这里追加
- `docs/approved/*`（设计意图）—— 受治理文档不承载高频签字事件

## 怎么签（两种录入方式，账本格式相同）

### 方式 A：PR 合并自动落账（推荐，D46.d）

「GitHub 是录入口，账本是真相」——在 PR 上签字，合并时自动落成账本文件：

1. PR 加 label `signoff:<scope>`（如 `signoff:e3.F9`）
2. PR 正文（body）含一段机读块：
   ```
   <!-- signoff
   scope: e3.F9
   kind: 效果验收            # 决策签字 | 效果验收 | 双签
   covers:                   # decision_only:true 则留空
     - .testing/waves/wave-2-engines-b1-zones/features/topic-package-discovery.feature
   -->
   ```
3. 合并 → `.github/workflows/signoff-ledger.yml` 调 `scripts/signoff_from_pr.py`，
   取 **approvers**（GitHub 权威"谁批的"）+ **merged_at**（"何时合的"）+ **PR#**（evidence），
   生成 `.testing/signoff/<scope>.signoff.yaml` 提交回 main。

此后 `signed()` 只读仓库账本（离线可验、进 git 历史）；GitHub 仅在合并那刻用一次。
逻辑全在 `signoff_from_pr.py`（可单测，见 `tests/test_signoff_from_pr.py`），workflow 只编排。

### 方式 B：手写账本文件（无 CI 时的退路）

直接在 `.testing/signoff/` 新增 `<scope>.signoff.yaml`（schema 见下），段 63 守卫校验。

## schema

```yaml
scope: e3.F9                    # 签字范围标识（与 acceptance/business-review-package 的 scope 对应）
signed_by: 海若产品部业务方      # 签字人
date: 2026-05-30               # 签字日期
kind: 效果验收                  # 决策签字 | 效果验收 | 双签
evidence: PR #170 / .testing/acceptance/e3.F9/evidence.json   # 证据指针（PR / evidence.json / git_sha）
covers:                        # 本次签字覆盖的 feature 路径列表；signed(f)=f∈某账本 covers
  - .testing/waves/wave-2-engines-b1-zones/features/topic-package-discovery.feature
decision_only: false           # true = 纯决策签字（无对应 feature，covers 留空，不影响 feature 状态）
```

- `covers` = feature 路径直列（feature 级，零歧义）。跨 feature 签就列多个。
- 纯决策签字（如能力面设计、IA 反转）`decision_only: true` + `covers: []`：记决策史，不抬任何 feature 状态。

## 规则（D46）

- **功能进 main 必须有对应 `.feature` 才进状态飞轮**（SPEC 是入口）。独立会话做完合并 main 的功能：
  先补 `.feature`（自动显 InTest）→ 往本目录追加签字 → 算出 Done。纯 infra/脚本/文档不补 feature、不进状态视图。
- 守卫：preflight 段 63 校验本目录每文件 schema 合法 + covers 的 feature 路径存在 + evidence 非空（禁手写空签）；段 54 校验 approved 验收文档 ↔ 账本一致（账本单一权威源）。
