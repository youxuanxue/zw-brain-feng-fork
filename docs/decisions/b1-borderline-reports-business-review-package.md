---
doc_id: b1-borderline-reports-business-review-package
status: approved
gate: signed
scope: b1-borderline-reports
sign_off_required:
  - 海若产品部业务方
signed_off_by: 海若产品部业务方
signed_off_at: 2026-05-29
vehicle_pr: "#165"
driven_by:
  - docs/preflight-debt.md「2026-05-23 — 5 个 borderline B1 业务报表 capability 仍 live」
  - docs/reconstructs/p0-contract-classification.md §2.5 / §2.8
---

# B1 borderline 报表 capability 定性 业务方 review — 5 条留 live 还是转 external

> **本文是 D35 决策签字材料包**，对应 `preflight-debt.md`「2026-05-23」债，其触发条件 (a)
> 明文 = **"业务方下次 IA review 对 5 条逐一 sign-off"** —— 本次 IA review（D39）即该时机，一并签。
>
> **要业务方决定什么**：5 条 B1 capability 当前 `status: live`。它们是**业务运营报表**
> （基于 capability_call / 评价业务事实），还是**运维监控**（归集团运维监控平台、应转 external）？
> 逐条定性。

## 启动硬前置（sequencing）

- 无上游依赖。5 条已 live 运行，本签字是**定性确认**：留 live（业务报表）或翻 external
  （运维监控，由集团承担）。若翻 external，需重跑 `export_agent_contract.py` 让 5 消费面同步剔除。

## 概念边界澄清（业务报表 vs 运维监控）

| | 业务运营报表（留 live，B1.1） | 运维监控（转 external，集团承担） |
|---|---|---|
| 数据源 | capability_call / 评价等**业务事实** | 网关/主机/中间件**运行指标** |
| 谁负责 | zw-brain B1.1 合规与运营 | 集团统一运维监控平台（基线 §3.4） |
| 例 | 目录被申请多少次、服务调用业务统计 | CPU/内存/网关存活、熔断 |

## 1. 五条逐一定性（业务方圈选）

| capability | 含义 | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|---|
| `service.rating.submit` | 服务评价提交 | **留 live** — 评价是业务事实，非运维 | ☐ 留 live / ☐ 转 external |
| `ops.catalog.statistics.query` | 目录资源统计 | **留 live** — 基于目录/申请业务事实 | ☐ 留 live / ☐ 转 external |
| `ops.exchange.statistics.query` | 交换统计 | **留 live** — 基于交换业务事实 | ☐ 留 live / ☐ 转 external |
| `ops.service.invocation.query` | 服务调用统计 | **留 live** — 调用方/系统业务统计（与 A 类 D40 §3.5 一致） | ☐ 留 live / ☐ 转 external |
| `ops.service.report.query` | 服务运行态势 | **留 live** — 业务态势报表，非网关运维指标 | ☐ 留 live / ☐ 转 external |

> **建议整体留 live**：5 条都基于 zw-brain 自有业务事实（申请/调用/评价），不是网关/主机
> 运行指标；运维监控（CPU/存活/熔断）才归集团。与 D40 A 类「监控只读投影 + 对接集团运维」
> 的边界一致——业务报表内建、运维指标外接。

## 落盘（业务方 sign-off 后）

- [x] **A**：`.twin/e6-platform-m0/plan.yaml` F1 追加 `[SIGNOFF-CLOSED 2026-05-29] covers b1-borderline-reports`
- [x] **B**：PR #165 加 label `business-signoff: b1-borderline-reports`
- [x] **C**：CLAUDE.md D41；删除 `preflight-debt.md`「2026-05-23 — 5 个 borderline B1」债条
- [x] **D**：本文 `status: approved`

> A/C 由段 54 校验；本文结构由段 53 校验。
