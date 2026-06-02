---
doc_id: j1-approval-conditional-business-review-package
status: awaiting-signoff   # awaiting-signoff → approved（业务方 sign-off 后；PR 合并时 label signoff:<scope> 自动落账本 D46.d）
gate: pending              # pending → signed
sign_off_required:
  - 海若产品部业务方
vehicle_pr: <PR 号，待建>
scope: j1-approval-conditional
driven_by:
  - .testing/waves/wave-0-golden-path/features/j1-approval-conditional.feature（SPEC）
  - docs/approved/zw-brain-architecture.md §3.3 申请单状态机 / §10.1 有条件共享审批分支
  - 旧 xlsx 行 [86..90] 服务审核 + [91] 申请变更复用主审批流；业务反馈 #4
  - CLAUDE.md D28（角色/流程/状态机决策须业务方 sign-off 才进 D-编号）
---

# J1 有条件共享审批 业务方 review 材料包 — 部门审 + 平台复核两步状态机

> **本文是 D35 决策签字材料包**（D28 GATE 元规则：状态机决策须业务方 sign-off）。
> 通过 preflight 段 53/54 守卫。**本文不写 signed_by**——签字事实由 PR 合并时
> GitHub approvers 自动落 `.testing/signoff/j1-approval-conditional.signoff.yaml` 账本（D46.d）。

## 0. 背景速览（开会前先读）

- D28 触发链路：有条件共享 (shared_type=2) 资源的两步审批是**状态机决策**，须业务方
  sign-off 才进 D-编号。本期已落地运行时实装（handler + 服务 + 状态机 + guard）并由
  pytest 真写库覆盖，状态轴现为 **InTest（测量绿 / 待签）**——本次 sign-off 即把它推到 Done。
- 本次签字范围：业务可感知 2 项 —— ① 两步审批的状态迁移合法性表（谁能把单子从哪态推到哪态）；
  ② 两条方向/越权约束（提供方部门外的管理员不可审、申请人本人不可自审）。

## 启动硬前置（sequencing — 强制节）

- 无上游依赖。ExchangeMapper.data_apply_dept_approve 已把 sd-default 真实 department
  step 灌入数据底座（4 行 decision_mode='department'：2 approved + 1 rejected + 1 pending），
  运行时层在合成有条件共享单（临时 DB）上驱动 handler 真写库，二者互补，无待补种数据。

## 1. 决策点一：两步审批状态机迁移合法性（基线 §3.3）

> 真实性标签：状态机迁移闭包 `CONDITIONAL_TRANSITIONS`（`zw_brain/domain/services/conditional_approval.py`）；
> 数据底座 step 为 `seed 真实`（ExchangeMapper 灌入 sd-default）。

| from（态） | to（态） | actor / 动作 | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|---|---|
| 1 待审 submitted | 4 部门同意 dept_approved | 提供方部门管理员 dept.approve | **含** — 提供方部门保有数据使用决定权 | ☐ 含 / ☐ 改 |
| 1 待审 submitted | 3 驳回 rejected | 部门或平台 reject | **含** — 任一环节可驳回 | ☐ 含 / ☐ 改 |
| 1 待审 submitted | 6 已授权 granted | 平台 platform.approve（无条件直通） | **含** — 无条件资源单步直授 | ☐ 含 / ☐ 改 |
| 4 部门同意 dept_approved | 6 已授权 granted | 平台运营员 platform.approve | **含** — 主管部门保有合规复核权 | ☐ 含 / ☐ 改 |
| 4 部门同意 dept_approved | 3 驳回 rejected | 平台运营员 platform.reject（部门审记录保留） | **含** — 复核驳回不回退部门审记录（append-only） | ☐ 含 / ☐ 改 |
| 3 驳回 rejected | 1 待审 submitted | 申请人 resubmit（round+1，业务反馈 #4） | **含** — 补件重提，round 计数追踪重提次数 | ☐ 含 / ☐ 改 |
| 6 已授权 granted | （无后继） | — 终态，收回走独立 grant.revoke 能力 | **含** — granted 为终态，非法后继 raise InvalidStateError | ☐ 含 / ☐ 改 |

任何非法迁移由 `assert_legal_transition` raise `InvalidStateError`（entry 层映射 409）。

## 2. 决策点二：方向 / 越权约束（R11 + self-approval）

| 约束 | 实现 guard | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|---|
| 提供方部门外的 ROLE_ORGAN_MANAGER 不能审此申请（R11 方向由 owner_org_code 计算） | `policy.enforce_dept_approval_direction` → `ApprovalDirectionError` | **含** — 方向从 owner_org_code 算，跨部门管理员看不到也审不了 | ☐ 含 / ☐ 改 |
| 申请人本人不能审批自己的申请 | `policy.enforce_self_approval_guard` → `SelfApprovalNotAllowedError`（audit reason=self_approval_not_allowed） | **含** — 自审一律拒 + 落 audit reject，状态不变 | ☐ 含 / ☐ 改 |

## 测试证据（pytest 真写库，本期实跑通过）

> 标签：`seed 真实`（ExchangeMapper department step） + 运行时层临时 DB 驱动真实 handler。

- `tests/test_wave0_j1_approval_conditional_runtime.py` — **9 个 pytest 全通过**（2026-06-02 capture 实跑 `.........`）。
  覆盖：dept_approve 通过 / platform_approve 通过 / 部门驳回+重提 round+1 /
  平台驳回保留部门审 step / 跨部门 R11 拒 / self-approval 拒 /
  非法迁移（跳步、granted 终态再审）拒 / 状态机迁移表与 .feature 一致（纯函数断言）。
- `tests/test_wave0_j1_approval_conditional.py` — 数据底座层（断 ExchangeMapper 灌入的真实 department step），8 pass。
- `tests/test_wave0_j1_approval.py` — 无条件主审批流回归，11 pass。
- 运行时实装：`zw_brain/domain/services/conditional_approval.py`（ConditionalApprovalService）+
  `zw_brain/command/handlers/j1/approval.py`（handler_application_{dept,platform}_approve）+
  能力注册 `application.dept_approve` / `application.platform_approve`。

## 诚实留债

- **e2e 两步点击穿透未覆盖**：P3「我作为提供方」队列 → 部门审通过 → 平台复核队列 →
  平台通过的浏览器级穿透（.spec.ts）超本次成本，未实跑。运行时层 pytest 已断状态机 +
  step + decision + 审计反馈；UI 穿透留后续 e2e wave。
- 凭据签发：平台复核通过自动签发（平台自签，承接 C-1 凭据诚实化 D47），与历史未签发并存。

## 落盘（sign-off 后 — D46.b/d，账本是唯一权威源）

- [ ] **A**：vehicle PR 加 label `signoff:j1-approval-conditional` + PR body `<!-- signoff -->` 机读块
      （`scope: j1-approval-conditional` / `kind: 决策签字` / `covers: .testing/waves/wave-0-golden-path/features/j1-approval-conditional.feature`）。
- [ ] **B**：本文 frontmatter `status: approved`。
- [ ] **C**：CLAUDE.md 追加 D 决策条（记实质裁决）。

## sign-off PR body 机读块

```
<!-- signoff
scope: j1-approval-conditional
kind: 决策签字
decision_only: false
covers:
  - .testing/waves/wave-0-golden-path/features/j1-approval-conditional.feature
-->
```
