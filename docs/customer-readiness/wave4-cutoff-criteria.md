---
doc_id: customer-readiness-wave4-cutoff
status: approved
gate: post-ship
revision_date: 2026-05-26
authors:
  - 薛娇（产品研发负责人）
  - Claude Code (claude-opus-4-7) — 设计协作
driven_by:
  - docs/approved/zw-brain-architecture.md §10.5 Wave 4
  - docs/approved/zw-brain-flywheel.md §九 反模式 #8
related_docs:
  - .testing/waves/wave-4-legacy-retirement/features/legacy-write-entry-deprecation.feature
---

# Wave 4 — legacy 退役判据（客户上线后的 SLI 看板）

> **本文回答**：客户上线后，多久 / 满足什么条件，legacy 平台可以正式退役关闭写入口。
>
> **本文不是 .feature**：90 天时间序列 SLI 判据无法用 GWT 表达；强行塞入 `.testing/` 会永远卡在 Status: Draft（飞轮反模式 #8）。
>
> **关联**：可机械测的"legacy 写入口流量 = 0"留在 `.testing/waves/wave-4-legacy-retirement/features/legacy-write-entry-deprecation.feature`；本文承接其余 4 类时间序列判据。

## 一、4 类退役判据（同时满足 = 可退役）

### 判据 A — J1 替代验证（90 天 SLI）

| 指标 | 阈值 | 监控源 | 触发动作 |
|---|---|---|---|
| 日均申请数（库表 + 文件 + 文件夹）| ≥ 10 笔 / 日 | 集团运维监控 / B1.1 panel | 连续 7 天 < 阈值 → 告警，调研客户是否仍在用 legacy |
| 申请审批通过率 | ≥ 70% | 同上 | 持续低于阈值 → J1 流程可用性回潮 |
| 凭据签发后调用成功率 | ≥ 95% | P4 调用监控 | 低于阈值 → 凭据生产化未达标 |
| P0/P1 阻断 bug | 0 | 客户工单 / issue | 任一阻断 = 替代验证不通过 |

### 判据 B — J2 替代验证（90 天 SLI）

| 指标 | 阈值 | 监控源 | 触发动作 |
|---|---|---|---|
| 周均新目录发布数 | ≥ 3 个 / 周 | B1.1 panel | 连续 4 周 < 阈值 → J2 流程废用 |
| 平均编制 → 发布耗时 | ≤ 5 工作日 | catalog 状态机时间序列 | 超阈值 → 流程瓶颈 |
| 部门审 round 平均次数 | ≤ 2 次 | data_audit | 超阈值 → 编制质量问题 |
| P0/P1 阻断 bug | 0 | 同上 | 同上 |

### 判据 C — B1 合规底线覆盖

| 指标 | 阈值 | 监控源 | 触发动作 |
|---|---|---|---|
| 审计事件覆盖率（write-critical / write-normal / read-sensitive 三级齐全）| 100% capability | preflight 段（审计同步）| 任一 capability 无审计 = 不通过 |
| 异议处理 5 维度都有真实案例 | 5/5 | data_objection 表 | 上线 90 天内若某维度 0 案例 = 该维度未真用，需业务方确认 |
| 安全审计回放可执行 | 任意 audit_event 可回放 | B1.1 调查助手 | 不可回放 = 审计总线生产化未达标 |
| 接入扩展中心至少 1 能力包注册 | ≥ 1 | registry | 若 0 → B1.2 形同虚设 |

### 判据 D — 长尾外部能力包覆盖

| 类型 | 处置状态判据 | 数据源 |
|---|---|---|
| 旧 xlsx 原 50 条 ❌ 不复刻 | 业务方 PR #129 签字（已 approved 2026-05-27）：16 条接受 ❌ + 24 条转 ⏸ 按既存 reconstruction plan 落地（A 类 → dsp-dataservice / D 类 → sharezone-topic）| `docs/legacy-not-reproduce-signoff.md` + D31/D32 |
| 旧 xlsx 12 条 ⏸ 占位延后 | 客户接受延后 OR 由外部能力包承接 | 客户回访记录 |
| 旧 xlsx 6 条 ⚠ 外部依赖 | 集团运维 / 数据治理 / IAM 联通 | 集团服务联调记录 |
| 客户上线后新发现长尾需求 | 外部能力包承接 OR 业务方接受不做 | 客户上线 30 天 ritual |

### 判据 E — Legacy 写入口已切断（可机械测）

参见 `.testing/waves/wave-4-legacy-retirement/features/legacy-write-entry-deprecation.feature`。

| 指标 | 阈值 | 监控源 | 触发动作 |
|---|---|---|---|
| Legacy 写入口流量 | = 0 | API gateway | 任一写调用 = 未达退役标准 |
| Legacy 数据库写连接数 | = 0 | 数据库监控 | 同上 |

## 二、监控接入

### 2.1 监控源对接清单

| 数据源 | 接入方式 | 责任 worker | 状态 |
|---|---|---|---|
| 集团运维监控 | metrics 上报 | e6 (AC7) | pending |
| B1.1 panel | 实时查询 | e4 (AC2) | pending（Wave 2）|
| API gateway | 旁路日志 | 客户机房 + e6 | pending |
| 客户工单 | issue tracker | 产品 | pending |

### 2.2 监控 cron

```bash
# 每日跑（首客户上线后启用）
$ scripts/check_legacy_retirement_ready.py
# 输出：
#   判据 A: 8/10  ⏳  日均 8 笔 < 10（连续 3 天）
#   判据 B: 4/3   ✓  周均 4 个 ≥ 3
#   判据 C: 3/4   ⏳  异议 use 维度 0 案例（上线 60 天）
#   判据 D: 50/68 ⏳  18 条业务方未签字
#   判据 E: 0/0   ✓  写入口流量 0
#   退役准备度: 60% — 还需 30 天 + 业务方补签 18 条
```

### 2.3 判据闭合的退役 PR

当 5 类判据全绿 + 90 天 SLI 满足，提退役 PR：

- 删 `zw_brain/adapters/legacy/`（一次性迁移工具）
- 关闭 legacy 数据库连接
- 移除 `import_legacy_dumps` CLI
- 客户机房 legacy 实例关停文件签字

## 三、与飞轮的接口

| 飞轮节 | 本文承接 |
|---|---|
| `zw-brain-flywheel.md` §五.1 客户上线 5 步 | 第 5 步"90 天 SLI 监控"展开 |
| `zw-brain-flywheel.md` §九 反模式 #8 | Wave 4 时间序列判据从 GWT 中救出来 |
| `zw-brain-flywheel.md` §十 回灌 ritual | 退役期 SLI 异常 → 回灌 spec/test |

## 四、为什么不是 .feature

GWT 形态约束：

```
Scenario: 客户上线 90 天每日 ≥10 次申请
  Given 客户已上线
  When 90 天过去
  Then 日均申请 ≥ 10 笔
```

这种"等 90 天看时间序列"的判据，与 .feature 的"可立即重现 Given-When-Then"形态根本不匹配。强行塞入会：

- Status 永远 Draft（无法 InTest）
- 没有任何 commit 能让它绿
- 占用 R13 sign-off 槽位但永远不能签字
- 让"45 个 feature 全 Done"的成熟度指标永远到不了 100%

**形态学正确的做法**：时间序列 SLI 走监控 cron + 看板；GWT 形态留给"立即可验证"判据。

## 五、本文维护

- 客户上线后启用本文判据
- 每客户上线后回访 30 天内追加该客户的"判据 D 长尾发现清单"
- 判据 A/B/C 阈值需根据首客户实际跑出的数据调整（写入 §六 调整记录）

## 六、调整记录

（首客户上线后追加）
