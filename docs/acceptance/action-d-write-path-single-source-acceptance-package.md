---
doc_id: action-d-write-path-single-source-acceptance-package
status: awaiting-signoff
gate: pending
scope: action-d-write-path-single-source
evidence: .testing/acceptance/action-d-write-path-single-source/evidence.json
sign_off_required:
  - 产品研发负责人（架构门，D28 承 D46/D48 先例）
vehicle_pr: TBD
driven_by:
  - docs/decisions/action-d-write-path-single-source-D56.md
  - .testing/waves/wave-0-golden-path/features/j1-application-draft.feature
  - .testing/waves/wave-0-golden-path/features/j1-approval-conditional.feature
  - .testing/waves/wave-0-golden-path/features/j1-approval-unconditional.feature
  - .testing/waves/wave-0-golden-path/features/j1-credential-issue.feature
---

# Action D 写路径单源化 效果验收材料包 — 申请/审批/交付三聚合 DB 单一事实源，演示时代双轨退役

> D37 骨架。决策面见 D56（docs/decisions/action-d-write-path-single-source-D56.md）；
> 本包验"改完的写路径真能跑"：契约、全量测试、真 UI 走查三轴机读证据。

## 验收范围（强制节，缺则段 55 FAIL）

- 运行时申请全链写路径：request.create（草稿）/ application.resource.submit（直提）
  / request.submit / request.field.update / 受理两级（platform_approve→dept_approve）
  / 单步受理（resource.review）/ 凭据签发与查询 / 授权暂停与收回 / 工作台待办投影。
- 申请编码新形态（uuid4().hex）下的 WebUI 导航闭环（起草→直达详情）、表单填报、
  D55 角色矩阵可见性（5 角色 × 10 壳 + 受理两级按钮归属）。
- **不在本次范围**：legacy 导入单在线动作门控（D47.b 既有债）、approval_case
  单步投影与条件引擎共写一表的进一步归一（D56 刻意不做节）、流程/状态机业务
  语义（零变更，不重验 D55/D49 签字面）。

## 验收点 + 证据（每条必须挂 evidence 标签）

| 验收点 | evidence（机读证据） | 结果 | 业务方判定 |
|---|---|---|---|
| 5 消费面投影一致（契约未漂移） | `5 消费面投影一致`（contract） | pass | ☐ 通过 / ☐ 打回 |
| 后端全量测试套真绿（含三聚合直写/会话/凭据重导出回归） | `后端 / 契约测试套`（pytest exit 0） | pass | ☐ 通过 / ☐ 打回 |
| 真 UI 走查：权限矩阵 + 受理两级全链自铸单 + 起草直达 + 表单填报 + 撤回暂停矩阵 | `WebUI 活跑验收（permission_matrix_walkthrough + draft_request_closure + form_autofill + j1_credential_revoke_monitoring（真 UI，:8800 干净真库栈））`（e2e） | pass | ☐ 通过 / ☐ 打回 |

## 业务方眼见为实（人验，机器测不了的）

- P2 找数据 → 已发布资源「申请」→ 直达草稿详情（新编码不再是 REQ-日期-序号，
  与历史导入单同形；导航/编辑/提交闭环不受影响）。
- 有条件资源直提 → 业务运营员受理队列可办 → 部门管理员二级审核 → 已授权 →
  凭据领取页 AK-SELF 凭据可见（重启服务后仍可见——凭据按签发事实读时重导出，
  secret 不再躺在任何持久化文件里）。
- 各角色工作台待办随状态实时投影（受理待办/审核待办/进度跟踪），刷新无丢失。

## 数字纪律（段 55 复用 D35 规则）

- 测试/用例计数一律以 evidence.json 与 `.testing/status/feature-status.md` 现算为准，prose 不裸写。

## 落盘（验收通过后 — D46.b/d，账本是唯一权威源）

- [x] **B**：CLAUDE.md 追加 `D56` 决策条。
- [ ] **A**：vehicle PR 加 label `signoff:action-d-write-path-single-source` + body 机读块（或 Method B 手工账本，已随 PR 附 `.testing/signoff/action-d-write-path-single-source.signoff.yaml`）。
- [ ] **C**：本文 frontmatter `status: approved`。
