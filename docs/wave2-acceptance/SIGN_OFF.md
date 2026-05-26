# E3 Wave-2 三引擎客户落地 sign-off 材料

> 自动生成自 `tests/integration/test_wave2_three_engines_acceptance.py`。
> 业务方在 § 3 签字后此条状态可从 pending 升 completed。

## § 1 三引擎技术证据

| 引擎 | 场景 | 入库 schema_id | version | 总耗时 (秒) | 状态机 |
|---|---|---|---:|---:|---|
| 审批流 | 鞍山 4 级审批流 | `8d220e9d-481b-4e03-80c6-eb2027a2644a` | 2 | 0.128 | draft→preview→live |
| 申请表单 | 四川 7 字段申请表 | `29257ea4-3e44-482e-9c39-55ef906057d8` | 2 | 0.131 | draft→preview→live |
| 推荐规则 | 荆州 5 条推荐规则 + 5 条真实 dsp_require 历史 | (5 rules) | live | 0.003 | draft→preview→live |

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
- 命中明细见 `.data/wave2-acceptance/jinzhou_recommendation.json`（本地复跑后生成）。

## § 3 业务方 sign-off 栏（待签字）

| 项 | 业务方意见 | 签字 | 日期 |
|---|---|---|---|
| 鞍山 4 级审批流配置示例 |  |  |  |
| 四川 7 字段申请表配置示例 |  |  |  |
| 荆州 5 条推荐规则配置示例 |  |  |  |
| 「1 周内不改代码」承诺 |  |  |  |

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

- 自动化 e2e 实测总耗时：**0.289s**（鞍山+四川+荆州 端到端）
- 远低于 1 周 (604800s) 硬上限。
- 真实工作量评估（业务方判断含调研、需求确认、人工 review）请在 § 3 填补。

- 审计事件总数：**24** 条（写态 skill 全部经 audit bus 同步落库；D4）。

---

**版本**：自动生成；如需更新，重新跑
`pytest tests/integration/test_wave2_three_engines_acceptance.py -v` 后回写。
