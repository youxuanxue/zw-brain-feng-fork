---
doc_id: e3.F9-acceptance-package
status: approved
gate: signed
scope: e3.F9
evidence: .testing/acceptance/e3.F9/evidence.json
signed_off_by: 海若产品部业务方
signed_off_at: 2026-05-30
sign_off_required:
  - 海若产品部业务方
vehicle_pr: "#170"
driven_by:
  - .twin/e3-wave2-engines/plan.yaml F9
  - .testing/waves/wave-2-engines-b1-zones/features/topic-package-discovery.feature
  - .testing/waves/wave-2-engines-b1-zones/features/topic-package-curation.feature
  - docs/reconstructs/dsp-sharezone-topic-package-reconstruction-plan-v1.md
---

# e3.F9 效果验收材料包 — P7 共享专区 / 专题包 TopicPackage 真端到端

> **D37 效果验收**（"做完的东西真能跑"），与 F9 **启动准入**签字（D34，PR #162，查"该不该做"）区分。
> 本包查"功能真跑过没"：每个验收点挂 `.testing/acceptance/e3.F9/evidence.json` 里某条 check，
> 由 `capture_acceptance_evidence.py` 现场跑出（contract / pytest / e2e），段 55 校验 result=pass。

## 验收范围（强制节）

**覆盖**：
- F9 后端：TopicPackage 6 表 + 10 capability（create/configure/submit/review/publish/policy.update/
  subscribe/evidence.attach/query/metric.query）+ 完整发布状态机（draft→configuring→configured→submitted→published /
  rejected→offline_pending→offline）+ 三维可见性（org/role/region + surface/intent）。
- 数据底座：sd-default 山东 3 标杆专题包（医疗救助 / 医保码 / 异地就医），引用 #168 已补种的真
  `catalog_entry`（守 D11；专题包容器为运营策展产物，守 D34.a）。
- 前端真端到端：P7 列表页 / 详情页真接 `topic.package.query` / `topic.package.subscribe`（不再 snapshot+stub）。

**不在本次验收范围**：
- 编制侧 8 个 capability（create/configure/submit/review/publish/policy.update/evidence.attach/metric.query）
  的 WebUI 表单（维持 capability/CLI/MCP/A2A 可达、不进 P7 发现页，保留 webui-render 债务台账登记）。
- 审批流可配置化（D25）、表单 schema 化（D26）——下期引擎，不在 F9。

## 验收点 + 证据（每条挂 evidence 标签）

| 验收点 | evidence（机读证据） | 结果 | 业务方判定 |
|---|---|---|---|
| 5 消费面投影与 Registry 一致（含 topic.package.* 真接后零漂移） | `5 消费面投影一致`（contract） | pass | ☐ 通过 / ☐ 打回 |
| F9 后端真链路全绿：10 capability + 完整状态机流转 + publish 前置校验 + 三维可见性 + D11 ref 反向断言 + 既有套不回归 | `后端 / 契约测试套`（pytest exit 0） | pass | ☐ 通过 / ☐ 打回 |
| P7 真端到端活跑：列表真拉 3 标杆 / 订阅真写 / 详情真渲染（含目录与可见性） | `WebUI 活跑验收（webui_smoke P7（真端到端））`（e2e 全 passed） | pass | ☐ 通过 / ☐ 打回 |

## 业务方眼见为实（人验，机器测不了的）

> 机器证据是底线；"效果"请业务方在浏览器亲眼走查（全新 seed 库 / 真实部署态，本地撑肥库需重建后才注入标杆）。

- P7「共享专题包」列表：用 `ROLE_ORGAN_OPERATER` 进 `#/zones-pack`，应看到「医疗救助信息专题包 / 医保码信息专题包 / 异地就医专题包」3 张卡片。
- 点「订阅专题」：应弹「已订阅专题」提示（真写 topic.package.subscribe，非占位）。
- 进详情 `#/zones-pack/zone/tp-yidi-jiuyi`：应看到 3 个真目录（统筹区 / 定点医疗机构 / 经办机构）+ 可见性策略。

## 数字纪律

测试与投影计数为事实计数，住 `evidence.json`（脚本采集），prose 不裸写易漂移数字。

## 落盘（验收通过后 — 2026-05-30 业务方本地验收全部通过，A/C/D 已落，B label 待合并前加）

- [x] **A**：plan.yaml F9 `actual_evidence` 追加 `[SIGNOFF-CLOSED 2026-05-30] covers e3.F9 | 效果验收 | evidence=.testing/acceptance/e3.F9/evidence.json | by 海若产品部业务方 | vehicle PR #170 → published`；F9 status→completed
- [x] **B**：PR #170 加 label `business-signoff: e3.F9`（promote_signoff 翻 topic-package-{discovery,curation}.feature → Verified）
- [x] **C**：CLAUDE.md 追加 `D42` 决策条
- [x] **D**：本文 frontmatter `status: approved` / `signed_off_at: 2026-05-30`

> A/C 由段 54 校验；本文证据真实性 + 结构由段 55 校验。
> 业务方 2026-05-30 本地部署逐条走查（①列表 3 标杆 ②订阅诚实回显 ③目录诚实展示 ④召回候选 422 修复）全部通过。合并到 main 仍待产品负责人指令。
