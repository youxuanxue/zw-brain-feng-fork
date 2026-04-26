# 场景 6：R7 审核外部能力包接入

**适用角色**：R7 目录管理员。

**目标**：验证外部能力包仍可接入，但只能作为辅助能力进入统一 Capability 契约，不能接管主状态机责任写动作。

## 进入路由

1. `#/p8-integration-admin`
2. `#/p8-integration-admin/package/PKG-2026-04-25-001`
3. `#/p8-integration-admin/package/PKG-2026-04-24-002`

## 关键动作

- 角色切到 **R7**。
- 在 `#/p8-integration-admin` 查看待审核能力包列表、审核状态、暴露面与内联 AI 审核意见。
- 打开 `#/p8-integration-admin/package/PKG-2026-04-25-001`。
- 分别点击 **批准**、**退回补充**、**驳回**，验证列表页与详情页状态同步变化。
- 打开另一个 package，确认不同终态下按钮与说明会跟随约束变化。

## 预期状态变化

- 批准后：
  - package 状态进入已批准/已上线语义。
  - AI 审核摘要与草拟意见同步更新为批准结论。
- 退回补充后：
  - package 状态进入待补充。
  - 结构化缺项和退回意见继续保留。
- 驳回后：
  - package 进入终态。
  - 不再允许重复批准或重复注册。
- 所有状态变化都应同时反映在列表与详情中。

## 审计 / 证据点

- manifest、schema、ACL、side effects、暴露面、版本与审核意见可回看。
- 对越界声明 `submit`、`review-and-decide`、`reconcile-receipt`、`register-version`、`apply-tenant-policy` 的阻塞理由可回看。
- AI 只负责草拟审核意见，不保留正式注册写权。

## 本场景验证哪条 v4 主张

- P8 是否只服务管理员，而不扩张成普通用户主叙事。
- 平台是否始终掌握能力注册、生效与暴露治理控制权。
- AI 是否帮助审核，但不接管最终判断与正式生效动作。
