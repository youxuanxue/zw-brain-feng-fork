---
doc_id: <feature-slug>-business-review-package
status: awaiting-signoff   # awaiting-signoff → approved（业务方 sign-off 后人工改；PR 合并时 label signoff:<scope> 自动落 .testing/signoff/ 账本，D46.d）
gate: pending              # pending → signed
sign_off_required:
  - 海若产品部业务方
vehicle_pr: <PR 号，如 #162>
scope: <eN.FX，如 e3.F9 — 与 PR label signoff:<scope> 一致>
driven_by:
  - <真值源文档 / plan / 旧 schema>
---

# <Feature> 业务方 review 材料包 — <一句话主题>

> **本模板由 D35 确立**：业务方 sign-off 材料必须走本骨架，并通过 preflight
> 段 53（`check_signoff_package.py`）+ 段 54（`check_signoff_landed.py`）两段守卫。
> 删除或弱化任一**强制节**会被段 53 拦下。
>
> **三层质量保障**（D35）：
> - 预防：本模板让"证据 + 建议 + 边界 + 硬前置"成为默认结构。
> - 检测：段 53 校验数据真实性标签、禁过程数字、强制节、建议列。
> - 落盘：段 54 校验 approved 材料包的 `scope` 在 `.testing/signoff/<scope>.signoff.yaml` 账本有对应记录（D46.b 单一权威源）。

## 0. 背景速览（开会前先读）

- <D-编号触发链路：为什么现在做这次 sign-off>
- <本次签字范围：业务可感知的 N 项；技术细节由开发侧承担>

## 启动硬前置（sequencing — 强制节，缺则段 53 FAIL）

> 任何**上游依赖**未满足都列在这里。未满足 = sign-off 不可一键、worker 启动会立刻 blocked。
> 如无上游依赖，显式写"无"。

- <例：Z2/Z3 引用的目录真实 dump 有、未进 seed → catalog 线须先补种；二选一路径定在 §1 sign-off>

## 概念边界澄清（触及 legacy 概念时为强制节）

> 凡材料触及旧平台概念（共享专区 / 专题包 / 主题库 / …），必须有本表 + 引用旧 schema/SoT，
> 防止概念漂移（段 53 Layer 3 告警）。如不触及 legacy 概念，可删本节。

| | 本次范围内的概念 | 易混淆的相邻概念（不在本节） |
|---|---|---|
| 本质 | <…> | <…> |
| 旧表 / SoT | `old/12-datastructure/<file>.xml` `<table>` | `<other table>` |
| zw-brain 落点 | <…> | <…> |

## 1. <第一个决策点>（每个判定表必须有「建议」列 — 强制，缺则段 53 FAIL）

> **真实性标签词表**（段 53 Layer 1 据此校验，禁止裸断言"真实"）：
> - `seed 真实` → 必须在 `zw_brain/domain/seed_snapshot.json` 命中，否则 FAIL
> - `dump 命中` → 必须在 `old/10示例数据/dump-*.sql` 命中（dump 缺位时显式 skip，不静默吞错）
> - `dump 未命中` → 必须伴随「排除」建议或显式数据源（守 D11 禁 Mock）
> - `evidence 关联` → 复用证据，不做 catalog 真实性强校验

| 候选项 | 数据真实性 | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|---|
| <目录/资源名> | seed 真实 / dump 命中 / dump 未命中 / evidence 关联 | **<必含/含/排除/关联>** — <一句理由> | ☐ 必含 / ☐ 排除 |

## 2…N. <其余决策点>

> 同上：每个「业务方判定」表配「建议」列 + 一句理由；预填**安全方向**默认
> （敏感写权限默认从严，由业务方主动放开，而非默认放开再问要不要收）。

## 数字纪律（段 53 Layer 2）

- **禁**过程 / 估算数字：会议时长（"N 分钟"）、worker·day（"N-M 天"）、未 stat-wrap 的"N 态"。
  它们会漂移、逼读者心算，且不改变任何决策。
- 真需计数 → 走 `.stats.json` + `<!-- stat:NAME -->值<!-- /stat -->`（D17），由 `sync-stats.sh --check` 校验。

## 落盘（sign-off 后 — D46.b/d，账本是唯一权威源）

业务方对全部决策点 sign-off 后，签字事实落进 `.testing/signoff/<scope>.signoff.yaml` 账本（append-only、来源无关）；status 由账本现算、不写第二份（无 `# Status` 翻转、无 `Verified` 态）：

- [ ] **A**：vehicle PR 加 label `signoff:<scope>`（如 `signoff:e3.F9`）+ PR body 写 `<!-- signoff ... -->` 机读块（YAML：`scope` / `kind`（`决策签字` / `效果验收` / `双签`）/ `covers`（被签 `.feature` 相对路径列表）/ `decision_only`）。合并时 `signoff-ledger.yml` 调 `signoff_from_pr.py` 自动生成账本（`signed_by`=PR approvers，`date`=merged_at，`evidence`=PR#）提交回 main。
- [ ] **B**：本文 frontmatter `status: approved`。
- [ ] **C**：CLAUDE.md 追加 `D<编号>` 决策条（记**实质裁决**，非空泛"通过"）。

> 一致性由 **段 54 + 段 63** 校验：本文 `status: approved` 时，`scope` 必须在 `.testing/signoff/<scope>.signoff.yaml` 账本有对应记录（covers 的 .feature 存在、evidence 非空）；缺则 FAIL。**不再**对账 plan.yaml `[SIGNOFF-CLOSED]` 三处副本（D46 起 .twin/plan.yaml 退役，账本即真相）。

## sign-off PR body 机读块 + 评论模板（业务方填空 / 全采纳建议一键贴）

PR body（合并时被 `signoff_from_pr.py` 消费）：

```
<!-- signoff
scope: <scope，与 label signoff:<scope> 一致>
kind: 决策签字          # 决策签字 / 效果验收 / 双签
decision_only: false   # 决策签字且不绑具体 feature 时 true（covers 留空）
covers:
  - .testing/waves/<wave>/features/<feature>.feature
-->
```

PR 评论（人读）：

```
[<scope> launch sign-off | by <角色> | <日期>] 全采纳建议
<逐节决策结果，分歧处圈改>
```
