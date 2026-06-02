---
doc_id: c1-demo-removal-credential-honesty-acceptance-package
status: approved
gate: signed
scope: c1-demo-removal-credential-honesty
evidence: .testing/acceptance/c1-demo-removal-credential-honesty/evidence.json
signed_off_by: 薛娇（产品研发负责人）
signed_off_at: 2026-06-02
sign_off_required:
  - 薛娇（产品研发负责人）
vehicle_pr: "#192"
driven_by:
  - PR #192「删演示单 + 凭据诚实化」（C-1 余下，承接 #191 读路径单一事实源 + 数据模型地基）
  - zw_brain/adapters/legacy/mappers/exchange.py（`_map_data_apply_authrization` granted 分支停 `derive_demo_credential`，改写 `credential=None` + `credential_status=not_issued`）
  - zw_brain/domain/seed_snapshot.json（清空捏造演示业务记录：requests/approvals/delivery_tasks/disputes/audit_events/alerts/tickets/knowledge_articles/discovery.resources + provider/capability_packages 演示项）
  - zw_brain/command/demo_state_sync.py（`sync_demo_state_views` 硬编码演示 cascade 退役为 no-op，保留通用助手）
  - scripts/check_credential_grant_invariant.py（段 66 重定向：granted 分支须显式处理凭据态 + 禁回潮捏造）
  - scripts/check_no_demo_id_literals.py（段 36 零 allow-list：全仓零 demo id 字面）
  - tests/test_credential_honesty_legacy_granted.py（守卫：legacy granted 导入 → credential=None + not_issued，无 AK-DEMO）
  - CLAUDE.md D47（C-1 删演示单 + 凭据诚实化 决策固化）
---

# c1-demo-removal-credential-honesty 效果验收材料包 — 删演示单 + 凭据诚实化

> **D37 效果验收**（"做完的东西真能跑，且真实数据如实呈现"）。PR #192 把捏造的演示单
> 整体删除、一切围绕真实导入，并停止 legacy granted 凭据捏造、改为诚实显「未签发」。
> 验收点挂 `.testing/acceptance/c1-demo-removal-credential-honesty/evidence.json`，由
> `capture_acceptance_evidence.py` 在 **customer_acceptance_up 重建的干净全量真实库** 上
> 现场跑出（契约 + 全套 pytest 退出码），段 55 守卫。浏览器层活跑作为「业务方眼见为实」人验补充。

## 验收范围

**覆盖**：
- **删演示单**：`seed_snapshot.json` 不再含任何捏造的演示业务记录；读路径单一事实源（#191）下，
  空库 → 诚实空、真库 → 真实全量。`demo_state_sync` 硬编码演示 cascade 退役为 no-op（通用
  待办/查找助手保留）；段 36 收紧为零 allow-list（全仓无 demo id 字面）。
- **凭据诚实化**：真实授权表 `data_apply_authrization` 无 per-grant 凭据列（真凭据在网关域
  `dsp_service.api_service_app.SECRET`、与 apply_id 无绑定供数）。legacy 导入 granted 分支
  停止 `derive_demo_credential` 捏造 AK-DEMO，改为显式标 `credential_status=not_issued`；
  `credential.query`/P4 诚实显「未签发」。段 66 重定向为「granted 分支须显式处理凭据态 +
  禁回潮捏造」。
- **新建在产单凭据保留**：平台自身在 approve 时自动签发的凭据不在本约束内（非捏造旧平台凭据），
  与 legacy 历史导入的未签发态并存 —— 两面均如实呈现。

**不在本次范围**：
- J1 凭据取网关 `api_service_app.SECRET` 的口径 + `apply_id↔service_id↔app` 绑定供数（上游缺供）
  ——属真凭据接入独立轨，**待业务方确认**，已登记 `docs/preflight-debt.md`（2026-06-02 C-1 条）。
- 历史导入申请的在线动作完整回填（混合裁决：能解析运行时实体才可动作，否则只读）——承接
  `j1-legacy-record-actionability` 债，独立工作面。
- WebUI Playwright e2e 机器证据本次不挂入本材料包（已在 PR #192 内随测量轴 `capture --with-e2e`
  全绿重采，见 `.testing/status/measurement/`）；本材料包机器证据以契约 + 全套 pytest 为准，
  浏览器活跑以人验记录。

## 验收点 + 证据（每条挂 evidence 标签）

| 验收点 | evidence（机读证据） | 结果 | 业务方判定 |
|---|---|---|---|
| 凭据诚实化守卫成立：legacy granted 停捏造、显式 not_issued、禁回潮 AK-DEMO（含 `test_credential_honesty_legacy_granted` 守卫）；删演示单后全套真数据回归不破 | `后端 / 契约测试套`（pytest exit 0） | pass | ☑ 通过 |
| 单一能力契约 → 五消费面投影一致，删演示单 / 凭据改造零漂移 | `5 消费面投影一致`（contract） | pass | ☑ 通过 |

## 业务方眼见为实（本地全栈 `:8800` 走查，2026-06-02 通过）

> 入口 `http://127.0.0.1:8800/zw-brain/`（dev bypass + mock 推理 + real-only 真实导入库）。

- **凭据诚实化两面**：真实历史 granted 授权（如 `46f0…` / `86013a7a…`，真实授权表无凭据）→ 凭据页
  诚实显「未签发」；走查时新建并审批的在产单 → 凭据页「已签发 + curl 三语样例」（平台自签）。
- **删演示单**：P2/P3/P4/P5/P7 全部展示真实导入数据（真实目录 / 专题包 / 交付 / 申请），无捏造演示单；
  空态为诚实空，非伪造。
- **J1 主链路**：资源发现 → 发起复用申请 → 部门审批（审批中 → 已授权）→ 凭据（已签发）逐动作通。
- **J2 主链路**：编目 → 提交部门审 → 部门审通过 → 平台审通过 → 发布，两步审核角色分级正确，
  生命周期 draft → pending_review → pending_platform_review → approved_pending_publish → active 逐态流转。
- **异议**：创建 → 提交至平台 → 我的异议列表回查在列。
- **权限可见性**：未授权角色入口不渲染（无权 = 不可见），无「可见 + 禁用 / 可见 + 403」反模式。
