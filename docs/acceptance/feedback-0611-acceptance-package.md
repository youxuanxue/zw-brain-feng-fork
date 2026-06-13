---
doc_id: feedback-0611-acceptance-package
status: approved
gate: signed
scope: feedback-0611-acceptance
evidence: .testing/acceptance/feedback-0611-acceptance/evidence.json
signed_off_by: 薛娇（产品研发负责人）
signed_off_at: 2026-06-13
sign_off_required:
  - 产品研发负责人
vehicle_pr: 259
driven_by:
  - docs/decisions/feedback-0611-gate-D57.md
  - .testing/signoff/feedback-0611-gate.signoff.yaml
---

# feedback-0611-acceptance 效果验收材料包 — D57 0611 批次实施（#258 权限/可达性 + #259 反向编目两级管线）

> D57 GATE（decision_only）已签于 2026-06-12；两个实施 PR 的 body 均承诺「D37 效果验收包随验收
> 回合另行成包」——本包即该验收回合产物。环境：2026-06-13 干净重建真实库
> （customer_acceptance_up 全过）本地部署 :8800，dev bypass + mock 推理。

## 验收范围（强制节）

- 裁决①：业务运营员「待受理异议」保留并接通受理面（objection.case.accept）；
- 裁决②：操作员工作台 = 「我的申请进度」语境，无协作待办、无虚构「办理建议」叙事；审计员工作台 = 监督概览；
- 裁决④：管理员申请人身份照 v5 保留，前端发起申请入口可用、办申请页「我的申请」与审核队列分栏不混；
- 裁决⑤：目录发布权收口仅业务运营员（含机械延伸：资源发布同口径），管理员发布卡整卡不渲染；
- 裁决⑥：管理员+安全审计员退全局服务调用监控，自家资源调用留凭据门内；
- 裁决⑧（状态机变更）：反向编目审核两级管线——管理员部门审 → 业务运营员平台审，同级展示升供数首屏主卡；
- 裁决⑨：挂接审核去盲批——被审登记详情行内可见、关联资源/目录名非「—」、驳回带理由且理由闭环到提交方读面；
- 裁决③⑦（维持现状类）：领数据口径维持 D55②、业务运营员查审计保留——确认未被误动；
- **不在本次验收范围**：挂接到存量导入目录的 org 归一（见下「诚实记载」，另记债）。

## 验收点 + 证据

| 验收点 | evidence（机读证据） | 结果 | 业务方判定 |
|---|---|---|---|
| 真 UI 走查：D57 批次九裁决可达性/语境/两级管线/去盲批全套 e2e | `WebUI 活跑验收（d57_permission_batch + p0_feedback_0611_chain + permission_matrix_walkthrough + wave15_two_stage_walkthrough（10 passed/2 skipped,A6 无 catalog_code 路径补采 1 passed））`（e2e passed） | pass | ☑ 通过 |
| 后端/契约/权限矩阵全量回归 | `后端 / 契约测试套`（pytest exit 0） | pass | ☑ 通过 |
| 5 消费面投影一致 | `5 消费面投影一致`（contract） | pass | ☑ 通过 |

## 诚实记载（skip 逐条判定，非假绿）

- `d57_permission_batch` A6 在真库 skip：根因 = 存量目录 `owner_org_id` 存机构名而资源侧用机构码，
  `resource_mount.py` org 一致性守卫裸比对误拒同机构 → 带 `catalog_code` 铸件失败。
  **该根因已在本 PR 内端到端修复**：守卫比对前两侧经参照主数据（org_projection）归一到码、
  未知/重名歧义仍 fail-closed 拒（`ReferenceService.resolve_org_code` +
  `test_resource_mount_org_normalization.py` 回归网）；修复后 A6 在真库带 `catalog_code`
  全套断言通过、不再 skip（采证回合当时的无 catalog_code 补采路径见 evidence e2e 名注记）。
  债 `legacy-catalog-owner-org-name-mismatch` 同 PR 关账（yaml 删除 + debt-status 现算重生成）；
- `wave15_two_stage_walkthrough` 两级链路用例 skip（需预铸单 env）：同一状态机路径由
  `permission_matrix_walkthrough` 业务流 1（自铸有条件直提单 → 受理 → 审核 → 已授权）等价覆盖通过。

## 数字纪律

- 用例通过/跳过计数由 evidence.json 承载，prose 不另写第二份。

## 落盘（D46.b — 账本是唯一权威源）

- [x] **B**：Method B 手写账本 `.testing/signoff/feedback-0611-acceptance.signoff.yaml`（负责人 2026-06-13 对话确认「全部签字」）。
- [x] 新债落账 `.testing/debt/legacy-catalog-owner-org-name-mismatch.debt.yaml` + debt-status 重生成。
- [x] 本文 frontmatter `status: approved`。
