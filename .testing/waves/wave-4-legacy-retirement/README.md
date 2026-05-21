---
wave: 4
title: legacy 退役判据
driven_by: docs/approved/zw-brain-architecture.md §10.5
---

# Wave 4 — legacy 退役判据

## 目标

证明 legacy 平台可以正式退役。判据**不**是"迁完多少菜单"，而是：

1. 核心旅程（J1 / J2）已被 zw-brain 稳定替代
2. 后台支撑面（B1）合规底线已被覆盖
3. 长尾需求已被外部能力包覆盖
4. legacy 已无唯一写入口

## Scope

| Feature | 类型 | 优先级 | 主要关注点 |
|---|---|---|---|
| j1-replacement-validation | 替代验证 | P0 | 客户上线 90 天 J1 真实使用 |
| j2-replacement-validation | 替代验证 | P0 | 客户上线 90 天 J2 真实使用 |
| b1-compliance-coverage | 替代验证 | P1 | 合规底线覆盖 |
| long-tail-external-coverage | 替代验证 | P1 | 长尾外部能力包覆盖 |
| legacy-write-entry-deprecation | 退役 | P0 | 关闭 legacy 写入口 |

## 完成判据（同时满足 = 可退役）

- J1 找数→用数：客户上线 90 天每日 ≥10 次申请（基线 §1.5 成功标准）
- J2 挂数→维数：客户上线 90 天每周 ≥3 次新目录发布
- B1.1 / B1.2 合规底线无 P0/P1 阻断 bug
- 长尾能力（旧 18 项一级目录中"不复造"+ "占位延后"项）均有处置：外部能力包 OR 业务方确认不需要
- legacy 写入口已切断（仅保留只读窗口或全部下线）

## 不在 Wave 4 内

- legacy 数据迁移（一次性 migration，per memory `project_legacy_import_migration_only`）

## Trace 索引

- 基线 §10.5 Wave 4 必做清单
- 基线 §1.5 成功标准
- 基线 §10.6 明确不做的事
- D11 旧平台真实数据回归
