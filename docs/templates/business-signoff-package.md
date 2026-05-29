---
doc_id: <feature-slug>-business-review-package
status: awaiting-signoff   # awaiting-signoff → approved（由 promote_signoff.py + label 翻转）
gate: pending              # pending → signed
sign_off_required:
  - 海若产品部业务方
vehicle_pr: <PR 号，如 #162>
scope: <eN.FX，如 e3.F9 — 与 business-signoff 标签 scope 一致>
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
> - 落盘：段 54 校验 sign-off 后 plan.yaml evidence + CLAUDE.md D-编号 + label 一致。

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

## 落盘（sign-off 后，段 54 机械验证）

业务方对全部决策点 sign-off 后：

- [ ] **A**：plan.yaml 对应 feature `actual_evidence` 追加
      `[SIGNOFF-CLOSED <日期>] covers <scope> | by <角色> | vehicle PR <#> 评论 business-signoff: <scope> | <关键决策摘要> → <下一步>`
- [ ] **B**：PR 加 label `business-signoff: <scope>`（`promote_signoff.py` 翻 .feature Status + 本文 status→approved）
- [ ] **C**：CLAUDE.md 追加 `D<编号>` 决策条（记**实质裁决**，非空泛"通过"）
- [ ] **D**：（如需）另起 worktree 启动 delivery worker

> A/B/C 一致性由 **段 54** 自动校验：本文 `status: approved` 时，plan.yaml 必须有
> 匹配 `[SIGNOFF-CLOSED]` evidence + CLAUDE.md 必须有对应 D-编号；缺则 FAIL（关掉"靠人记忆"）。

## sign-off PR 评论模板（业务方填空 / 全采纳建议一键贴）

```
[<scope> launch sign-off | by <角色> | <日期>] 全采纳建议
<逐节决策结果，分歧处圈改>
```
