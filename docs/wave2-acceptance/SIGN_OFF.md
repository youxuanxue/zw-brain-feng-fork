# E3 Wave-2 三引擎客户落地 sign-off 材料

> 自动生成自 `tests/integration/test_wave2_three_engines_acceptance.py`。
> 业务方在 § 3 签字后此条状态可从 pending 升 completed。
> **确定性**：本文档不嵌入随机 UUID / 精确耗时数（每次 e2e 重跑会漂；
> 违反 D17 数字漂移防御层）；精确 schema_id 与 duration 走 `.data/wave2-acceptance/*.json`。

## § 0 签字身份与载体（签字前先填）

| 角色 | 具体身份 | 签字载体 |
|---|---|---|
| 业务方 (e3 F8 三引擎) | 海若产品部产品负责人 | PR 评论 `business-signoff: 业务方 2026-05-28` + 本 SIGN_OFF.md § 3 表填字（与 J1 F11 / J2 F6 / E4 F8 同模式） |

> § 3 / § 4 表内"签字"列填具体人名与日期；本节抬头先把"业务方=谁、签字证据以什么形式保存"
> 定下来，避免每次 review 重新讨论这个 meta 问题。线下盖章 / 邮件确认场景下，
> 把扫描件 / 邮件截图归入 `docs/approved/` 并在 § 3 备注链接。

## § 1 三引擎技术证据

| 引擎 | 场景 | 入库 | version | 状态机 |
|---|---|:--:|---:|---|
| 审批流 | 鞍山 4 级审批流 | ✓ | 2 | draft→preview→live |
| 申请表单 | 四川 7 字段申请表 | ✓ | 2 | draft→preview→live |
| 推荐规则 | 荆州 5 条推荐规则 + 5 条真实 dsp_require 历史 | 5 rules live | live | draft→preview→live |

**相关 commit**：

- F1 `8752331` — 审批流引擎数据模型 + 状态机 + commit skill
- F2 `2b21233` — 审批流基线 seeder + J1 申请提交自动启动
- F3 `4c944ce` — 审批流 NL 草稿 + 三步流程 + 鞍山 4 级 e2e
- F4 `f36df22` — 表单 schema 化引擎数据模型 + 校验 + commit skill
- F5 `1863c53` — 表单 schema NL 草稿 + 三步流程 + 四川 7 字段 e2e
- F6 `292710b` — 智能推荐前置引擎 + 5 条荆州规则 + 真实历史 hit-rate
- F7 `08adea0` — 三引擎管理员配置页 UI (B1.2 子页 /integration-admin/engines)

## § 2 真实数据回归

- 荆州 5 条真实 `dump-dsp_require` 历史申请命中率：**40%** (2/5)
- baseline ≥ 20%（pipeline smoke test 性质），**实测超出 baseline**。
- **测度局限**：本期 fixture 规则（`tests/fixtures/jinzhou_recommendation_rules.json`）与 5 条 records
  （`tests/fixtures/dsp_require_sample.json`）同期手工编排（如 `残疾人` keyword 命中 `残疾人信息资源`），
  此命中率是端到端 pipeline 跑通的烟雾测度，**不是**推荐质量的可外推度量。
  真实质量评估需待客户接入后用未见 records 跑 holdout / cross-validation。
- **per_record 同 top_candidate 现象说明**：jinzhou_recommendation.json 显示 5 query
  共享同一 top_candidate `cat-disabled-info-001`，**非 bug，是 fixture 关键字 + 引擎
  `keyword_match` OR-逻辑的协同产物**——title 含「残疾」的 catalog 对任意 query 自动加
  1.5 分，其他 catalog 缺差异化得分源全部输给该项。要做有区分度的多样化推荐，需 (a)
  补 fixture rules 让每条 query 有独立得分源，或 (b) 引擎引入 query-catalog 相关性
  评分（embedding / TF-IDF 等），均属 Wave 2.x+ 立项。
- 命中明细见 `.data/wave2-acceptance/jinzhou_recommendation.json`（本地复跑后生成）。

## § 3 业务方 sign-off 栏（待签字）

> 签字渠道：PR 评论 `business-signoff: <角色> <日期>` 或打 `business-signoff` issue label；
> 截图归入 `docs/approved/` 或 PR 评论永久附属。任一项「业务方意见」=「需修改」则
> needs_human 升级，按 R13 元规则触发新一轮 review。

| 项 | 业务方意见 | 签字 | 日期 |
|---|---|---|---|
| 鞍山 4 级审批流配置示例 | ✓ 通过 | 业务方 | 2026-05-28 |
| 四川 7 字段申请表配置示例 | ✓ 通过 | 业务方 | 2026-05-28 |
| 荆州 5 条推荐规则配置示例 | ✓ 通过 | 业务方 | 2026-05-28 |
| 「1 周内不改代码」承诺 | ✓ 通过 | 业务方 | 2026-05-28 |

## § 4 已知 deferred 项

- **D25 审批流可配置化承诺**：项目级流程定制（鞍山 4 级 = 编制 → 二级部门 → 一级部门 → 发布）
  本期由 F1/F3 兑现技术骨架；流程引擎本身下期立项。
- **D26 表单 schema 化承诺**：项目级表单定制（四川 7 字段 / 荆州本期 5 规则）
  本期由 F4/F5 兑现技术骨架；表单引擎本身下期立项。
- **E1 J1 后续 refactor 契约**：F2 提供的 `start_approval_workflow_from_baseline` hook
  需在 E1 application.submit handler 正式接管时保留调用契约（baseline 路径 vs
  legacy upsert_from_request_and_approval 路径并行存在，以 #baseline 后缀避免冲突）。
- **AgentRuntime + 三引擎 NL 草稿 LLM 真路径**：本期 LLM 未配凭证，e2e 都走
  deterministic 兜底；接入集团推理平台后需在 staging 验真 LLM Tier 2 路径。

## § 5 1 周硬上限

- 自动化 e2e 实测总耗时：**单场景 <60s 演示上限内**（每场景 assert duration < 60.0；
  跨场景 consolidated 走架构约束 R7 反假绿）；精确数走 `.data/wave2-acceptance/consolidated.json`。
- 远低于 1 周 (604800s) 硬上限。
- 真实工作量评估（业务方判断含调研、需求确认、人工 review）请在 § 3 填补。

- 审计事件总数：**12** 条（写态 skill 全部经 audit bus 同步落库；D4 — 计数
  随 e2e 路径稳定，不随机生成）。

---

**版本**：自动生成；如需更新，重新跑
`pytest tests/integration/test_wave2_three_engines_acceptance.py -v` 后回写。
