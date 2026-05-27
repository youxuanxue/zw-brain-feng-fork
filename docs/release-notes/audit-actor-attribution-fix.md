# 发布说明：审计操作人归属修正（Action F / PR #141）

> **受众**：客户审计 / 合规 / 纪检口；实施工程师。
> **影响面**：审计事件的「操作人（actor）」字段。**无 UI 变化、无权限变化、无数据迁移、无接口变化。**

## 一句话

本次升级后，若干「助手 / 解释」类只读操作的审计记录，操作人字段从固定值 `system` 修正为**真实发起人**（如 `user:gov:ROLE_ORGAN_OPERATER:…`）。这是一次归属**修正**，不是数据被篡改。

## 背景

升级前，下列只读 / 辅助类操作在写审计 feed 时，因一处历史遗留缺陷，操作人恒被记为 `system`：

- 资源搜索意图解析（`search.intent.parse`）
- 凭证样例渲染（`credential.sample.render`）
- 申请草稿建议（`application.draft.suggest`）
- 审批证据归纳（`approval.evidence.summarize`）
- 交付状态解释（`delivery.status.explain`）

这些操作均不改动业务数据，但其审计 feed 的「操作人」此前不准确。

## 升级后的变化

- 上述操作的审计 actor = 真实发起人的角色身份（`user:gov:<角色码>:<名称>`）。
- dev IAM bypass 模式下 actor 追加 `[bypass]` 后缀，便于审计员过滤合成身份。
- **改动业务数据的写操作（申请 / 审批 / 交付等）审计归属本就正确，本次不受影响。**

## 审计员须知（重要）

- **历史记录不回改**：升级前已落库的审计记录，操作人仍为 `system`；仅升级后新产生的记录才是真实操作人。审计时间线在升级时点会出现一次「`system` → 真实操作人」的不连续——**这是预期内的归属修正，不代表既有数据被改动**。
- 若按操作人做检索 / 统计，请以升级时点为界分别口径。

## 验证

- 上述每类操作的审计归属均有自动化回归测试锁定（断言 actor 为 `user:gov:ROLE_*` 且绝不为 `system`），见 `tests/test_wave1_*`。
- 代码门禁：preflight 段 46（`scripts/check_handler_no_ui_state.py`）禁止 handler 反向读进程级 `_ui_state`，防止该归属在后续迭代中静默回退。
