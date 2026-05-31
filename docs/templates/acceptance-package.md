---
doc_id: <scope>-acceptance-package
status: awaiting-signoff   # awaiting-signoff → approved（业务方验收通过后）
gate: pending              # pending → signed
scope: <eN，整 epic；或 eN.FX 单 feature>
evidence: .testing/acceptance/<scope>/evidence.json   # 由 capture_acceptance_evidence.py 生成,禁手写
sign_off_required:
  - 海若产品部业务方
vehicle_pr: <PR 号>
driven_by:
  - <被验收 .feature 列表 / 真值源文档>
---

# <Scope> 效果验收材料包 — <交付物一句话>

> **本模板由 D37 确立**：效果验收（"做完的东西真能跑"）的签字材料走本骨架,通过
> preflight **段 55**（`check_acceptance_package.py`）守卫。与 D35 的**决策**签字
> （F9 那种"该不该做"）区分：决策签字查"数据真不真",验收签字查"**功能真跑过没**"。
>
> **铁律**：验收点的"结果"不许裸写"已验证 / 通过"。每条必须挂一个 `evidence` 标签,
> 指向 `.testing/acceptance/<scope>/evidence.json` 里某条 check；该产物由 `capture_acceptance_evidence.py`
> **现场跑出来**（contract / pytest / e2e），段 55 校验它 result=pass 且来自当前历史。

## 验收范围（强制节，缺则段 55 FAIL）

- <这次验收覆盖哪些 feature / 页面 / 消费面>
- <明确不在本次验收范围的（避免"验收了就等于全都行"的误读）>

## 验收点 + 证据（每条必须挂 evidence 标签）

> evidence 标签 = `.testing/acceptance/<scope>/evidence.json` 里某条 check 的 name；段 55 据此回链校验。

| 验收点 | evidence（机读证据） | 结果 | 业务方判定 |
|---|---|---|---|
| <如：5 消费面投影一致> | `5 消费面投影一致`（contract） | pass | ☐ 通过 / ☐ 打回 |
| <如：后端契约测试全绿> | `后端 / 契约测试套`（pytest exit 0） | pass | ☐ 通过 / ☐ 打回 |
| <如：WebUI 关键路径活跑> | `WebUI 活跑验收（…）`（e2e N passed） | pass | ☐ 通过 / ☐ 打回 |

## 业务方眼见为实（人验，机器测不了的）

> 机器证据(上表)是底线;真正的"效果"业务方要亲眼看。列出请业务方在浏览器/真机
> 走查的关键页面与路径,作为人验补充（这一栏机器不卡,但留痕）。

- <如：P2 发现页用 sd-default 真数据检索出结果>
- <如：P5 反向编目向导能生成建议>

## 数字纪律（段 55 复用 D35 规则）

- 禁过程/估算数字（N 分钟 / N-M 天 / worker·day）；测试数量这类**事实计数**写进
  evidence.json（由脚本采集），prose 不裸写易漂移的数字。

## 落盘（验收通过后 — D46.b/d，账本是唯一权威源）

- [ ] **A**：vehicle PR 加 label `signoff:<scope>` + PR body 写 `<!-- signoff ... -->` 机读块（`scope` / `kind: 效果验收` / `covers`（被验收 .feature 相对路径列表）/ `decision_only: false`）。合并时 `signoff-ledger.yml` 调 `signoff_from_pr.py` 自动落 `.testing/signoff/<scope>.signoff.yaml` 账本（`signed_by`=approvers，`date`=merged_at，`evidence`=PR#）。status 由账本现算（无 `# Status` 翻转、无 `Verified` 态）。
- [ ] **B**：CLAUDE.md 追加 `D<编号>` 决策条。
- [ ] **C**：本文 frontmatter `status: approved`。

> A 由 **段 54**（`check_signoff_landed.py`：approved scope ↔ 账本）+ **段 63**（账本 schema/covers/evidence）校验；本文证据真实性 + 结构由 **段 55** 校验。
