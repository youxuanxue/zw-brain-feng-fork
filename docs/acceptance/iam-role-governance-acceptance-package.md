---
doc_id: iam-role-governance-acceptance-package
status: approved
gate: signed
scope: iam-role-governance
evidence: .testing/acceptance/iam-role-governance/evidence.json
signed_off_by: 薛娇（产品研发负责人）
signed_off_at: 2026-06-18
sign_off_required:
  - 产品研发负责人
vehicle_pr: "#303"
driven_by:
  - PR #303「D62 角色分派与角色治理 zw-brain 自建（IAM 只认证, binding=SoT）」（squash a272ec83）
  - docs/decisions/iam-role-governance-self-build-D62.md（D28 架构 + 角色/状态机门）
  - tests/test_iam_role_governance.py（仓储单边写 / A0 停用门 / A2 binding 权威 / 角色门 / 审计 / 回填 / token-ignored / disable-at-bearer / read-gate 负向）
  - tests/e2e/b12_iam_governance.spec.ts + tests/e2e/customer_acceptance_checklist.spec.ts（真 UI 走查）
---

# iam-role-governance 效果验收材料包 — D62 角色分派与角色治理（IAM 只认证, binding=SoT）

> **D37 效果验收**（"做完的东西真能跑"）。D62 把产品角色的事实源从通用共享 IAM token 收口到
> zw-brain 自有 `actor_org_role_binding`（IAM 只认证），并把"分派/撤销/停用/谁能访问什么"做进
> 身份治理产品页（媲美旧平台 BSP 运营能力面）。本验收每点挂
> `.testing/acceptance/iam-role-governance/evidence.json` 的机器证据，段 55 守卫。
> 承 docs/decisions/iam-role-governance-self-build-D62.md（D28 决策门，签字账本
> `.testing/signoff/iam-role-governance.signoff.yaml`）。

## 验收范围

本期验收覆盖 D62 全量交付，**不含**显式排除项（角色目录 CRUD/树/权重、APP 多产品域、菜单授权引擎全量复刻、区划直授——乔布斯 say-no，见 D62 §二）：

- **架构收口**：IAM 只认证；产品角色唯一可写事实源 = `actor_org_role_binding`，bearer/MCP/CLI 与浏览器两门都读它，token 角色永不进授权（段 73 守卫）。
- **运营能力面**：身份治理 3-tab（用户与角色 分派/撤销/停用 + 谁能访问什么只读矩阵 + 旧权限映射审核）+ 5 能力（全 ROLE_SYSTEM 门控 + 全程审计）。
- **安全边界**：A0 停用在认证边界 fail-closed（含浏览器 BFF 中途停用即时生效，xj-review R-001 修复）。
- **质量门**：对抗式代码审查 + CI 全绿。

## 验收点

| # | 验收点（客户/用户语言） | 结论 | evidence 标签 |
|---|---|---|---|
| 1 | 平台运维员一屏看清用户 + 角色 + 状态 + IAM 绑定（真库 713 actor 渲染，非样例） | 通过 | `Playwright 全旅程真 UI 走查（0 断点）` |
| 2 | 能给用户**分派角色**，写库 + 审计 + 立刻生效（角色 chip 出现） | 通过 | `身份治理 actor 管理面 e2e（b12_iam_governance + customer_acceptance + twin_browser）` |
| 3 | 能**撤销角色**（chip 清空，binding 置 disabled，带审计） | 通过 | `身份治理 actor 管理面 e2e（b12_iam_governance + customer_acceptance + twin_browser）` |
| 4 | 能**停用/启用用户**，停用在认证边界 fail-closed（停了就进不来，含浏览器中途停用） | 通过 | `后端/授权收口单测 + 回归簇` |
| 5 | 能看**谁能访问什么**（角色→能力只读矩阵） | 通过 | `Playwright 全旅程真 UI 走查（0 断点）` |
| 6 | **授权事实源收口**：产品角色来自 binding，IAM token 角色被忽略（负向 + 分叉测试钉死） | 通过 | `后端/授权收口单测 + 回归簇` |
| 7 | **角色即边界**：身份治理仅平台运维员可见，其它角色被路由挡回（无权=不可见） | 通过 | `Playwright 全旅程真 UI 走查（0 断点）` |
| 8 | 旧权限映射审核仍可人工审核（迁入第三 tab，无候选时诚实空态） | 通过 | `身份治理 actor 管理面 e2e（b12_iam_governance + customer_acceptance + twin_browser）` |
| 9 | 5 消费面（WebUI/REST/CLI/MCP/A2A）契约一致 | 通过 | `5 消费面契约一致` |
| 10 | 全旅程体验顺畅、无断点、无前端报错 | 通过 | `Playwright 全旅程真 UI 走查（0 断点）` |
| 11 | 代码经对抗式审查（10 条真问题修复闭环）+ CI 全绿方合并 | 通过 | `xj-review 对抗式代码审查（修复闭环）`；`CI 全绿（合并提交）` |

## 已知债（非本验收范围，已记录）

- **710 个 iam_account_missing 存量账号**：缺真实 IAM sub（根因在上游 IAM directory），按 A 线传送带（`export_iam_provisioning_request` → IAM 注入 → `ingest_iam_sub_backfill` → 重导入 / 或登录自愈 D51）治理；认领后角色由身份治理派或重导入 materialize。运维 runbook 待补。

## 签字

产品研发负责人 薛娇 2026-06-18 签字（D37 效果验收通过）；证据 `.testing/acceptance/iam-role-governance/evidence.json`（6 项 result=pass，git_sha=a272ec83 即 #303 合并提交）。决策门 D28 签字见 `.testing/signoff/iam-role-governance.signoff.yaml`。
