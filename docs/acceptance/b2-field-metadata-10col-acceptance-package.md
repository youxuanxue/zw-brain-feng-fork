---
doc_id: b2-field-metadata-10col-acceptance-package
status: awaiting-signoff
gate: pending
scope: b2-field-metadata-10col
evidence: .testing/acceptance/b2-field-metadata-10col/evidence.json
sign_off_required:
  - 产品研发负责人
vehicle_pr: 257
driven_by:
  - .testing/waves/wave-1-j1-j2-closed-loop/features/j2-resource-mount.feature
  - old/问题反馈/字段级元数据10列-本期立项草案.md
---

# b2-field-metadata-10col 效果验收材料包 — 库表/文件资源「字段级元数据 10 列」录入→快照→详情逐列回显

> 债 `b2-field-metadata-10col` 提前本期（0611 核查 §四 6.5#5.2「提前立项」裁决 + 负责人确认
> 「提前本期」，立项草案 `old/问题反馈/字段级元数据10列-本期立项草案.md`）。方案 A：注册采集的
> 字段级元数据逐列写 `ResourceSchemaSnapshotRecord`（与存量旧平台导入快照同源同形），详情
> `metadata.schema.query` 读路径零改动——同时修复「UI 新注册资源字段数据模型恒为空」数据通路断点。

## 验收范围（强制节，缺则段 55 FAIL）

- 库表资源注册向导「字段数据模型」逐列录入（10 列：字段名/释义/关联目录信息项/字段类型/长度精度/
  主键/可空/更新主键/更新时间/数据标准·数据字典）→ 提交复核 → 部门管理员挂接审核 → 业务运营员
  资源发布 → 找数据资源详情「字段数据模型」逐列回显与注册输入一致（10 列全比，不抽样）；
- 文件资源同走（字段登记可选，登记后同样回显）；
- 存量不回归：legacy 导入快照资源的字段数据模型基线列照常渲染；注册覆盖写绝不触碰 legacy 行；
- 写读键单源对齐（后端 `FIELD_METADATA_SNAPSHOT_KEYS` = 前端写端 payload 键 ⊆ 前端读端消费键）+
  债现算关账（predicate stale-fixed）。
- **不在本次验收范围**：字段快照与真实库的自动比对/探活（属发布激活校验另有口径）；「数据标准/
  数据字典」与数据治理标准库的联动（本期为录入列＋详情回显，草案 §2.3）。

## 验收点 + 证据（每条必须挂 evidence 标签）

| 验收点 | evidence（机读证据） | 结果 | 业务方判定 |
|---|---|---|---|
| 真 UI 全链：逐列填 10 列→审核→发布→详情逐列回显一致 + 文件同走 + 存量基线照常渲染 | `WebUI 活跑验收（b2_field_metadata_10col 全链 + 存量不回归）`（e2e passed） | pass | ☐ 通过 / ☐ 打回 |
| 写入/读出/幂等覆盖/legacy 不触碰/键对齐/债关账（pytest 全量） | `后端 / 契约测试套`（pytest exit 0） | pass | ☐ 通过 / ☐ 打回 |
| 5 消费面投影一致（payload 新键不破契约） | `5 消费面投影一致`（contract） | pass | ☐ 通过 / ☐ 打回 |

## 业务方眼见为实（人验，机器测不了的）

- P5 资源挂接向导（库表）：字段表逐行填 字段名/释义/类型/长度/主键/可空，行内「更多」展开填
  关联目录信息项/更新主键/更新时间/数据标准/数据字典；提交复核；
- 审核发布后打开该资源详情「字段数据模型」：扩展 3 列（关联目录信息项/更新标识/数据标准·数据字典）
  随真数据出列，逐列与录入一致；
- 任选存量导入的库表资源详情：字段数据模型仍为基线列展示（无空荡扩展列）。

## 数字纪律（段 55 复用 D35 规则）

- 测试与列覆盖等事实计数由 evidence.json / 测量产物承载，prose 不裸写易漂移数字。

## Provenance 注记

- evidence.json 采于 #257 基线 sha；其后两处后续修复（#257 复审 info：mount manifest
  input_schema 补登 `field_columns`、b2 包本注记）不改运行行为，由下一轮全量重采
  （capture --with-e2e）覆盖核验。

## 落盘（验收通过后 — D46.b/d，账本是唯一权威源）

- [ ] **A**：vehicle PR 加 label `signoff:b2-field-metadata-10col` + PR body `<!-- signoff ... -->` 机读块（kind: 效果验收 / covers: j2-resource-mount.feature / decision_only: false）。
- [ ] **B**：债账本已按先例收口（debt yaml 移除 + debt-status 重生成 + preflight-debt.md 结语），无新增 D-编号决策（无角色/流程/状态机口径变更）。
- [ ] **C**：本文 frontmatter `status: approved`。
