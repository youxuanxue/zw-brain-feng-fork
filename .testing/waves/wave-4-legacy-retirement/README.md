---
wave: 4
title: legacy 退役判据
driven_by:
  - docs/approved/zw-brain-architecture.md §10.5
  - docs/approved/zw-brain-flywheel.md §九 反模式 #8
  - docs/customer-readiness/wave4-cutoff-criteria.md
---

# Wave 4 — legacy 退役判据

## 目标

证明 legacy 平台可以正式退役。判据**不**是"迁完多少菜单"，而是：

1. 核心旅程（J1 / J2）已被 zw-brain 稳定替代（90 天 SLI）
2. 后台支撑面（B1）合规底线已被覆盖
3. 长尾需求已被外部能力包覆盖 / 业务方接受不做
4. legacy 已无唯一写入口（**可机械测**）

## Scope（形态学拆分后）

**本目录只留 1 个可机械测的 .feature**：

| Feature | 类型 | 优先级 | 主要关注点 |
|---|---|---|---|
| legacy-write-entry-deprecation | 退役 | P0 | 关闭 legacy 写入口（写流量 = 0 / 写连接数 = 0）|

**其余 4 类时间序列 SLI 判据**：见 `docs/customer-readiness/wave4-cutoff-criteria.md`

| 判据 | 形态 | 位置 |
|---|---|---|
| A. J1 替代验证（90 天 SLI）| 监控 cron + 看板 | docs/customer-readiness/wave4-cutoff-criteria.md §一.A |
| B. J2 替代验证（90 天 SLI）| 监控 cron + 看板 | 同上 §一.B |
| C. B1 合规底线覆盖 | 集团审计回放 + manifest 校验 | 同上 §一.C |
| D. 长尾外部能力包覆盖 | 业务方签字 + 客户回访 | 同上 §一.D（与 `docs/legacy-not-reproduce-signoff.md` 联动）|
| E. Legacy 写入口已切断 | **本目录 .feature 承接** | 本目录 |

## 完成判据（同时满足 = 可退役）

详见 `docs/customer-readiness/wave4-cutoff-criteria.md` §一 五类判据。

简版：

- 判据 A：J1 客户上线 90 天每日 ≥10 次申请（SLI）
- 判据 B：J2 客户上线 90 天每周 ≥3 次新目录发布（SLI）
- 判据 C：B1.1 / B1.2 合规底线无 P0/P1 阻断 bug（SLI）
- 判据 D：长尾能力均有处置（业务方签字 / 客户回访接受）；当前分布由 `tests/fixtures/legacy_smoke.yaml` 实时维护（D31 后：✅73 / ❌16 / ⏸23 / ⚠4 / unmapped 15）
- 判据 E：legacy 写入口已切断（**本目录 .feature**）

## 形态学拆分历史（2026-05-26）

GATE-1.1 后审视发现：原 wave-4 5 个 feature 中 4 个是"客户上线 90 天 SLI"判据，无法用 GWT 表达（飞轮反模式 #8）。本次拆分：

- **删除**：`j1-replacement-validation.feature` / `j2-replacement-validation.feature` / `b1-compliance-coverage.feature` / `long-tail-external-coverage.feature`
- **新建**：`docs/customer-readiness/wave4-cutoff-criteria.md` 承接时间序列 SLI 判据
- **保留**：`legacy-write-entry-deprecation.feature`（可机械测）

参见飞轮文档 §九 反模式 #8。

## 不在 Wave 4 内

- legacy 数据迁移（一次性 migration，per memory `project_legacy_import_migration_only`）

## Trace 索引

- 基线 §10.5 Wave 4 必做清单
- 基线 §1.5 成功标准
- 基线 §10.6 明确不做的事
- 飞轮 §五.2 上线后回灌 ritual
- D11 旧平台真实数据回归
